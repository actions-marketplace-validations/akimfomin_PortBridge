# SPDX-License-Identifier: MIT
"""Measure how often a pinned open shader census reaches the factoring planner."""

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from statistics import median
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter
from xml.etree import ElementTree

from emit import emit
from factoring import factor
from spirv_census import census
from workloads import pcg32


REVISIONS = {
    "miniengine": "68a2b1e97f71642924e74c7757ca21756ad221b5",
    "naga": "c76dea031c688ecef0050dbf60506fff128fb23f",
    "fsr2": "1680d1edd5c034f88ebbbb793d8b88f8842cf804",
}
PROMOTION = ("--eliminate-local-single-block", "--eliminate-local-single-store",
             "--ssa-rewrite", "--eliminate-dead-code-aggressive")
FSR2_OPTIONS = ("REPROJECT_USE_LANCZOS_TYPE", "HDR_COLOR_INPUT",
                "LOW_RESOLUTION_MOTION_VECTORS", "JITTERED_MOTION_VECTORS",
                "INVERTED_DEPTH", "APPLY_SHARPENING")


@dataclass(frozen=True)
class Shader:
    group: str
    source: Path
    entry: str = "main"
    profile: str = "cs_6_2"
    flags: tuple[str, ...] = ()
    variant: str = ""


def invoke(command, *, cwd=None):
    start = perf_counter()
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    return result, round(1000 * (perf_counter() - start), 3)


def required(command, *, cwd=None):
    result, elapsed = invoke(command, cwd=cwd)
    result.check_returncode()
    return result.stdout, elapsed


def version(command):
    result, _ = invoke([command, "--version"])
    result.check_returncode()
    return (result.stdout + result.stderr).strip()


def verify_checkout(root, expected):
    sha, _ = required(["git", "rev-parse", "HEAD"], cwd=root)
    changed, _ = required(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root)
    if sha.strip() != expected or changed.strip():
        raise ValueError(f"{root.name} must be clean at {expected}")


def miniengine_jobs(root):
    project = root / "MiniEngine/Core/Core.vcxproj"
    namespaces = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
    stages = {"Compute": "cs", "Vertex": "vs", "Pixel": "ps"}
    for row in ElementTree.parse(project).findall(".//m:FxCompile[@Include]", namespaces):
        path = row.get("Include").replace("\\", "/")
        if path.endswith(".hlsl"):
            stage = row.findtext("m:ShaderType", "Compute", namespaces)
            yield Shader("miniengine", project.parent / path, profile=stages[stage] + "_6_2",
                         flags=("-HV", "2021", "-D_GAMING_DESKTOP=1"))


def fsr2_jobs(root):
    profile = ("-Wno-for-redefinition", "-Wno-ambig-lit-shift", "-DFFX_GPU=1",
               "-DFFX_HLSL=1", "-DFFX_HLSL_6_2=1", "-DFFX_HALF=0",
               "-DFFX_FSR2_OPTION_UPSAMPLE_SAMPLERS_USE_DATA_HALF=0",
               "-DFFX_FSR2_OPTION_ACCUMULATE_SAMPLERS_USE_DATA_HALF=0",
               "-DFFX_FSR2_OPTION_REPROJECT_SAMPLERS_USE_DATA_HALF=1",
               "-DFFX_FSR2_OPTION_POSTPROCESSLOCKSTATUS_SAMPLERS_USE_DATA_HALF=0",
               "-DFFX_FSR2_OPTION_UPSAMPLE_USE_LANCZOS_TYPE=2")
    for source in sorted((root / "src/ffx-fsr2-api/shaders").glob("*_pass.hlsl")):
        for variant, values in (("all-zero", (0, 0, 0, 0, 0, 0)),
                                ("all-one", (1, 1, 1, 1, 1, 1))):
            flags = tuple(f"-DFFX_FSR2_OPTION_{name}={value}"
                          for name, value in zip(FSR2_OPTIONS, values))
            yield Shader("fsr2", source, "CS", flags=profile + flags, variant=variant)


def naga_jobs(root):
    entries = re.compile(r'entry_point:\s*"([^"]+)",\s+target_profile:\s*"([^"]+)"')
    for ron in sorted((root / "naga/tests/out/hlsl").glob("*.ron")):
        for entry, profile in entries.findall(ron.read_text(encoding="utf-8")):
            stage, version, _ = profile.split("_")
            flags = ()
            if version == "5":
                profile = f"{stage}_6_0"
            if ron.stem == "wgsl-f16":
                flags = ("-enable-16bit-types",)
            yield Shader("naga-hlsl", ron.with_suffix(".hlsl"), entry, profile, flags)


def binary_stats(args, binary, target):
    required([args.spirv_val, "--target-env", target, binary])
    assembly, _ = required([args.spirv_dis, "--raw-id", binary])
    return {"bytes": binary.stat().st_size,
            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), **census(assembly)}


def optimized(args, binary, target, flags, destination):
    _, elapsed = required([args.spirv_opt, f"--target-env={target}", *flags,
                           binary, "-o", destination])
    return {"wall_ms": elapsed, **binary_stats(args, destination, target)}


def dxc_binary(args, shader, directory, mode):
    binary = directory / f"{mode}.spv"
    target = "vulkan1.2"
    command = [args.dxc, "-spirv", f"-fspv-target-env={target}", "-fvk-auto-shift-bindings",
               "-T", shader.profile, "-E", shader.entry, mode, *shader.flags,
               "-Fo", binary, shader.source.name]
    timings = []
    for _ in range(args.rounds):
        result, elapsed = invoke(command, cwd=shader.source.parent)
        if result.returncode:
            return {"error": result.stderr.strip().replace(str(shader.source.parent), ".")[:800]}
        timings.append(elapsed)
    try:
        return {"wall_ms": timings, **binary_stats(args, binary, target)}
    except subprocess.CalledProcessError as error:
        return {"error": str(error.stderr).strip().replace(str(directory), ".")[:800]}


def run_shader(args, shader, root, directory):
    row = {"group": shader.group, "file": shader.source.relative_to(root).as_posix(),
           "entry": shader.entry, "profile": shader.profile, "variant": shader.variant,
           "source_sha256": hashlib.sha256(shader.source.read_bytes()).hexdigest()}
    for mode in ("-Od", "-O3"):
        result = dxc_binary(args, shader, directory, mode)
        row[mode] = result
        if "error" not in result:
            flags = PROMOTION if mode == "-Od" else ("-O",)
            key = "promoted" if mode == "-Od" else "optimized"
            try:
                row[key] = optimized(args, directory / f"{mode}.spv", "vulkan1.2",
                                     flags, directory / f"{key}.spv")
            except subprocess.CalledProcessError as error:
                row[key] = {"error": str(error.stderr).strip().replace(str(directory), ".")[:800]}
    return row


def recover_naga_hlsl(args, shader, directory, primary):
    if not all("error" in primary[mode] for mode in ("-Od", "-O3")):
        return primary
    alternate = replace(shader, flags=(*shader.flags, "-HV", "2018"))
    row = run_shader(args, alternate, args.naga, directory)
    if all("error" in row[mode] for mode in ("-Od", "-O3")):
        return primary
    row["hlsl_version"] = "2018"
    row["default_language_errors"] = {mode: primary[mode]["error"] for mode in ("-Od", "-O3")}
    return row


def run_naga_spirv(args, directory):
    for source in sorted((args.naga / "naga/tests/out/spv").glob("*.spvasm")):
        version = re.search(r"; Version: (\d+\.\d+)", source.read_text(encoding="utf-8")).group(1)
        target = f"spv{version}"
        binary = directory / "naga.spv"
        row = {"group": "naga-native", "file": source.relative_to(args.naga).as_posix(),
               "target": target, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        try:
            required([args.spirv_as, "--target-env", target, source, "-o", binary])
            row["raw"] = binary_stats(args, binary, target)
            row["promoted"] = optimized(args, binary, target, PROMOTION, directory / "promoted.spv")
            row["optimized"] = optimized(args, binary, target, ("-O",), directory / "optimized.spv")
        except subprocess.CalledProcessError as error:
            row["error"] = str(error.stderr).strip().replace(str(directory), ".").replace(str(args.naga), ".")[:800]
        yield row


def summary(rows):
    groups = sorted({row["group"] for row in rows})
    result = {}
    for group in groups:
        cohort = [row for row in rows if row["group"] == group]
        stages = {}
        for key in ("raw", "-Od", "promoted", "-O3", "optimized"):
            observed = [row[key] for row in cohort if "plans" in row.get(key, {})]
            if observed:
                stages[key] = {
                    "checked": len(observed), "with_plan": sum(bool(stage["plans"]) for stage in observed),
                    "switches": sum(stage["switches"] for stage in observed),
                    "direct_switches": sum(stage["direct_switches"] for stage in observed),
                }
        paired = [row for row in cohort if "plans" in row.get("-O3", {})
                  and "plans" in row.get("promoted", {})]
        timing_ms = round(sum(median(row["-O3"]["wall_ms"]) for row in paired), 3)
        opportunity_ms = round(sum(median(row["-O3"]["wall_ms"]) for row in paired
                                   if row["promoted"]["plans"]), 3)
        result[group] = {"attempted": len(cohort), "stages": stages, "paired": len(paired),
                         "paired_dxc_o3_ms": timing_ms, "eligible_modules_dxc_o3_ms": opportunity_ms}
    return result


def write_report(output, report, rows):
    prefix = json.dumps(report, indent=2)[:-2]
    workload_rows = ",\n".join(f"    {json.dumps(row, separators=(',', ':'))}" for row in rows)
    output.write_text(f'{prefix},\n  "rows": [\n{workload_rows}\n  ]\n}}\n', encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (*REVISIONS, "output"):
        parser.add_argument(f"--{name}", required=True, type=lambda path: Path(path).resolve())
    for name in ("dxc", "spirv-as", "spirv-val", "spirv-dis", "spirv-opt"):
        parser.add_argument(f"--{name}", default=name)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 20:
        parser.error("--rounds must be between 1 and 20")
    for group, revision in REVISIONS.items():
        verify_checkout(getattr(args, group), revision)

    started = datetime.now(timezone.utc).isoformat()
    tools = {name: version(getattr(args, name))
             for name in ("dxc", "spirv_as", "spirv_dis", "spirv_opt", "spirv_val")}
    rows = []
    with TemporaryDirectory(prefix="portbridge-shader-corpus-") as temporary:
        directory = Path(temporary)
        region = pcg32(32)
        for variant, plan in (("baseline", None), ("factored", factor(region))):
            source = directory / f"{variant}.hlsl"
            source.write_text(emit(region, plan), encoding="utf-8")
            rows.append(run_shader(args, Shader("synthetic-control", source, variant=variant),
                                   directory, directory))
        for root, jobs in ((args.miniengine, miniengine_jobs), (args.fsr2, fsr2_jobs), (args.naga, naga_jobs)):
            for shader in jobs(root):
                row = run_shader(args, shader, root, directory)
                if shader.group == "naga-hlsl":
                    row = recover_naga_hlsl(args, shader, directory, row)
                rows.append(row)
        rows.extend(run_naga_spirv(args, directory))
    report = {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
              "tool_versions": tools, "revisions": REVISIONS, "rounds": args.rounds,
              "summary": summary(rows)}
    write_report(args.output, report, rows)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
