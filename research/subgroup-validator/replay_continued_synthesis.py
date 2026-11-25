# SPDX-License-Identifier: MIT
"""Measure and validate the selected lowering on Continued's public synthetic compute fixtures."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

from check_continued import run as capture
from lane_contract import Domain, Lowering, Participation
from spirv_synthesis import UNSAFE_CONTROL, optimize, prove_plan


CONTINUED = "1bedab24c39d0b3ae325f6f0f6c43e47bbb6430e"
VARIANTS = {
    "default": {},
    "defined-exec": {"defined_exec": True},
    "select-masks-poison": {"defined_exec": True, "allow_masked_poison": True},
}


def run(*args) -> str:
    return subprocess.check_output(args, text=True, encoding="utf-8", timeout=30)


def executable(root: Path, filename: str) -> Path:
    return root / (filename + (".exe" if os.name == "nt" else ""))


def stats(path: Path) -> dict:
    binary = path.read_bytes()
    words = struct.unpack(f"<{len(binary) // 4}I", binary)
    if words[0] != 0x07230203:
        raise ValueError("expected a SPIR-V module")
    index = 5
    count = 0
    while index < len(words):
        length = words[index] >> 16
        if length == 0 or index + length > len(words):
            raise ValueError("invalid SPIR-V instruction length")
        index += length
        count += 1
    return {"bytes": len(binary), "instructions": count, "sha256": hashlib.sha256(binary).hexdigest()}


def measure(tools: Path, source: Path) -> dict:
    binary = source.with_suffix(".spv")
    validate = executable(tools, "spirv-val")
    run(executable(tools, "spirv-as"), "--target-env", "vulkan1.3", source, "-o", binary)
    run(validate, "--target-env", "vulkan1.3", binary)
    results = {"raw": stats(binary)}
    for mode in ("-O", "-Os"):
        out = binary.with_name(binary.stem + mode + ".spv")
        run(executable(tools, "spirv-opt"), "--target-env=vulkan1.3", mode, binary, "-o", out)
        run(validate, "--target-env", "vulkan1.3", out)
        results[mode] = stats(out)
    return results


def interpret(name: str, assembly: str) -> dict:
    # These modules are already loaded by capture from the clean, pinned checkout.
    import spirv_mini_interp
    import test_wave64_cross_half as cross
    import test_wave64_subgroup_ops as partial

    results = {}
    for width in (32, 64):
        if name == "bpermute":
            values = cross.run(assembly, width)
        else:
            memory = spirv_mini_interp.run_workgroup(
                assembly, 40, width,
                inputs_for=lambda i: {"%wg_id": (0, 0, 0), "%local_id": (i, 0, 0), "%sg_lane": i % width},
                push_constants=partial.VSHARP + [0] * 28, memory=partial.Heap())
            values = partial.words(memory, len(partial.GPU_DUMPS["cs_w64x_partial"]))
        results[str(width)] = values
    return results


def observed_subgroup_width(log: str) -> int | None:
    match = re.search(
        r"(?m)^compute subgroup size: (\d+)(?: \(observed: all \d+ invocations of a "
        r"\d+x\d+x\d+ group(?:, full subgroups)?\))?[ \t]*\r?$",
        log,
    )
    return int(match[1]) if match else None


def dispatch(runner, device, width, binary, expected) -> dict:
    output = binary.with_suffix(".bin")
    env = {name: value for name, value in os.environ.items() if not name.startswith("VKC_")}
    env.update(LEONIDA_VK_DEVICE=device, VKC_SUBGROUP_SIZE=str(width), VKC_OUT_WORDS="256", VKC_DUMP=str(output))
    output_log = subprocess.check_output(
        (runner, binary, "1", "dump"), text=True, encoding="utf-8", env=env, timeout=30, stderr=subprocess.STDOUT)
    actual_device = re.search(r"(?m)^device: (.+?) \(subgroup ", output_log)
    subgroup = observed_subgroup_width(output_log)
    if not actual_device or device.casefold() not in actual_device[1].casefold() or subgroup != width:
        raise ValueError("runner did not observe the requested device and subgroup width")
    words = output.read_bytes()
    if len(words) != 256 * 4:
        raise ValueError(f"runner did not return the full 256-word buffer for {binary.name}")
    values = struct.unpack_from(f"<{len(expected)}I", words)
    if tuple(expected) != values:
        raise ValueError(f"unexpected readback prefix for {binary.name}: {values}")
    return {"adapter": actual_device[1], "subgroup_width": subgroup, "bytes": len(words),
            "readback_sha256": hashlib.sha256(words).hexdigest()}


def replay(args) -> dict:
    head = run("git", "-C", args.checkout, "rev-parse", "HEAD").strip()
    dirty = run("git", "-C", args.checkout, "status", "--porcelain", "--untracked-files=no").strip()
    if head != CONTINUED or dirty:
        raise ValueError("expected the clean, pinned Continued checkout")
    originals = args.output / "original"
    original = capture(args.checkout, originals, args.spirv_tools)
    report = {"continued_commit": head, "spirv_tools": original["spirv_tools"], "fixtures": {}}
    for name, count in (("bpermute", 3), ("partial", 2)):
        assembly = (originals / f"{name}.spvasm").read_text(encoding="utf-8")
        outputs = interpret(name, assembly)
        fixture = {"interpreter": outputs, "variants": {}}
        report["fixtures"][name] = fixture
        for label, options in (("baseline", None), *VARIANTS.items()):
            result = {}
            fixture["variants"][label] = result
            revised = assembly
            if options is not None:
                revised, decision = optimize(assembly, participation=Participation.SUPERSET, **options)
                selected = [row for row in decision["reads"] if row["plan"]]
                if len(selected) != count or outputs != interpret(name, revised):
                    raise ValueError(f"rewrite/interpreter mismatch for {name} {label}")
                result["plans"] = [row["plan"] for row in selected]
                result["removed_operations"] = sum(row["removed_operations"] for row in selected)
            source = args.output / f"{name}-{label}.spvasm"
            source.write_text(revised, encoding="utf-8", newline="\n")
            result["modules"] = measure(args.spirv_tools, source)
            if options is not None:
                before = fixture["variants"]["baseline"]["modules"]["raw"]["instructions"]
                if before - result["modules"]["raw"]["instructions"] != result["removed_operations"]:
                    raise ValueError("emitted instruction count differs from the proved plan")
            if args.vulkan_runner:
                for mode in (("", "-O") if label in {"baseline", "default"} else ("",)):
                    binary = source.with_name(source.stem + mode + ".spv")
                    readback = dispatch(args.vulkan_runner, args.device, args.subgroup_width, binary,
                                        outputs[str(args.subgroup_width)])
                    expected = fixture["variants"]["baseline"].get("vulkan", {}).get("raw", readback)
                    if expected != readback:
                        raise ValueError(f"full Vulkan readback differs for {binary.name}")
                    result.setdefault("vulkan", {})[mode or "raw"] = readback

    report["unsafe_control"] = prove_plan(
        UNSAFE_CONTROL, Lowering(32), Domain(64, 32, Participation.SUPERSET)).record()
    if not report["unsafe_control"]["failures"]:
        raise ValueError("poison control unexpectedly passed")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--spirv-tools", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vulkan-runner", type=Path)
    parser.add_argument("--device")
    parser.add_argument("--subgroup-width", type=int, choices=(32, 64))
    args = parser.parse_args()
    hardware = (args.vulkan_runner, args.device, args.subgroup_width)
    if any(hardware) and not all(hardware):
        parser.error("pass --vulkan-runner, --device and --subgroup-width together")
    args.output.mkdir(parents=True, exist_ok=True)
    report = replay(args)
    (args.output / "synthesis-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8",
                                                      newline="\n")
    for name, fixture in report["fixtures"].items():
        original = fixture["variants"]["baseline"]["modules"]
        revised = fixture["variants"]["default"]["modules"]
        print(f"{name}: {original['raw']['instructions'] - revised['raw']['instructions']} instructions removed, "
              f"spirv-opt -O {original['-O']['bytes']} -> {revised['-O']['bytes']} bytes")


if __name__ == "__main__":
    main()
