# SPDX-License-Identifier: MIT
"""Measure source generation and fresh optimized compiler invocations."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import statistics
import struct
import subprocess
import time

from emit import emit
from factoring import UINT32, evaluate, factor
from workloads import matrix


if os.name == "nt":
    from ctypes import wintypes

    class MemoryCounters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (field, ctypes.c_size_t) for field in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
            )
        ]

    kernel32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL


def run(arguments, *, timeout=90):
    start = time.perf_counter_ns()
    with subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          encoding="utf-8", errors="replace") as process:
        handle = kernel32.OpenProcess(0x0410, False, process.pid) if os.name == "nt" else None
        counters = MemoryCounters() if handle else None
        try:
            if counters:
                counters.cb = ctypes.sizeof(counters)
            output, _ = process.communicate(timeout=timeout)
            elapsed = time.perf_counter_ns() - start
            if counters and not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                counters = None
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise
        finally:
            if handle:
                kernel32.CloseHandle(handle)
        if process.returncode:
            raise RuntimeError(f"compiler exit {process.returncode}: {output[:1000]}")
        return {"wall_ms": elapsed / 1_000_000,
                "peak_ws": counters.PeakWorkingSetSize if counters else None}, output


def tool_version(tool):
    return run([tool, "--version"])[1].strip().splitlines()[0]


def compile_one(args, directory, stem, tuples=None):
    hlsl = directory / f"{stem}.hlsl"
    dxil = directory / f"{stem}.dxil"
    dxil_dump = dxil.with_suffix(".ll")
    spirv = directory / f"{stem}.spv"
    optimized = directory / f"{stem}.opt.spv"
    common = [args.dxc, "-T", "cs_6_0", "-E", "main", "-O3", hlsl]

    listing_flags = ["-Fc", dxil_dump] if args.emit_listings else []
    dx, _ = run([*common, "-Fo", dxil, *listing_flags])
    spv, _ = run([*common, "-spirv", "-fspv-target-env=vulkan1.1", "-fvk-u-shift", "1", "0", "-Fo", spirv])
    opt, _ = run([args.spirv_opt, "--target-env=vulkan1.1", "-O", spirv, "-o", optimized])
    for binary in (spirv, optimized):
        run([args.spirv_val, "--target-env", "vulkan1.1", binary])
    fields = {"dxil_bytes": dxil.stat().st_size, "dxc_spirv_bytes": spirv.stat().st_size,
              "spirv_opt_bytes": optimized.stat().st_size}
    if args.emit_listings:
        fields["dxil_phi_instructions"] = dxil_dump.read_text(encoding="utf-8").count(" = phi ")
    record = {"dxc_dxil_o3": dx, "dxc_spirv_o3": spv, "spirv_opt_o": opt, "sizes": fields}
    if tuples:
        source, expected, stride_words = tuples
        replay = directory / f"{stem}.readback"
        runtime, measured = run([args.replay, dxil, source, replay, str(stride_words), args.adapter])
        if replay.read_bytes() != expected:
            raise RuntimeError(f"D3D12 output differs from the CPU reference for {stem}")
        result = json.loads(measured)
        if result.pop("software") != (args.adapter == "warp"):
            raise RuntimeError("D3D12 ran on an unexpected adapter")
        record["d3d12"] = {**runtime, **result}
    return record


def inputs_for(region, count):
    rng = random.Random(27286)
    edge = [0, 1, 31, 32, UINT32]
    for index in range(count):
        if index < len(region.arms):
            inputs = [edge[(index + offset) % len(edge)] for offset in range(region.input_count)]
            yield (index, *inputs)
        else:
            yield tuple(rng.getrandbits(32) for _ in range(region.input_count + 1))


def compare_compiled_cpu(args, directory, region, paths):
    baseline, rewritten = (path.with_name(path.name + ".dll") for path in paths)
    for artifact in (baseline, rewritten):
        source = artifact.with_name(artifact.name.removesuffix(".dll") + ".c")
        run([args.clang, "-std=c17", "-O3", "-shared", source, "-o", artifact])
    values = []
    libraries = [ctypes.CDLL(str(artifact.resolve())) for artifact in (baseline, rewritten)]
    for library in libraries:
        method = library.run_region
        method.argtypes = [ctypes.c_uint32] * (region.input_count + 1)
        method.restype = ctypes.c_uint32
        values.append(method)
    for index, (selector, *inputs) in enumerate(inputs_for(region, args.checks)):
        expected = evaluate(region, selector, inputs)
        if any(function(selector, *inputs) != expected for function in values):
            raise RuntimeError(f"optimized CPU oracles differ on tuple {index}")
    return args.checks


def summary(rows):
    medians = {}
    for phase in ("dxc_dxil_o3", "dxc_spirv_o3", "spirv_opt_o", "d3d12"):
        if phase in rows[0]:
            medians[phase] = {}
            for key in rows[0][phase]:
                values = [row[phase][key] for row in rows if row[phase][key] is not None]
                medians[phase][key] = statistics.median(values) if values else None
    return medians


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("dxc", "spirv-opt", "spirv-val", "clang", "directory", "output"):
        parser.add_argument(f"--{label}", required=True, type=Path)
    parser.add_argument("--cases", nargs="*", default=None)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--checks", type=int, default=1024)
    parser.add_argument("--replay", type=Path, help="optional D3D12 replay executable")
    parser.add_argument("--adapter", choices=("warp", "rtx4070ti-super"), default="warp")
    parser.add_argument("--emit-listings", action="store_true",
                        help="record textual DXIL and include its generation in the measured compile")
    args = parser.parse_args()
    if args.rounds < 1 or args.checks < 64 or (args.replay and args.checks % 64):
        parser.error("expected a positive number of rounds and at least 64 checks, grouped in 64 for D3D12")
    args.directory.mkdir(parents=True, exist_ok=True)
    variants = matrix()
    report = {"toolchain": {key: tool_version(getattr(args, key)) for key in ("dxc", "spirv_opt", "spirv_val", "clang")},
              "platform": platform.system() + " " + platform.machine(), "rounds": args.rounds,
              "d3d12_adapter": args.adapter if args.replay else None,
              "dxil_listings": args.emit_listings, "cases": {}}
    for case in args.cases or variants:
        region = variants[case]
        started = time.perf_counter_ns()
        plan = factor(region)
        planning_ms = (time.perf_counter_ns() - started) / 1_000_000
        arms = {"baseline": None, "factored": plan} if plan else {"baseline": None}
        row = {"arms": len(region.arms), "unfactored_operations": sum(map(len, region.arms)),
               "planning_ms": planning_ms, "matched_tail": len(plan.body) if plan else 0,
               "edge_parameters": plan.parameter_count if plan else 0, "arms_measured": {}}
        tuples = None
        if args.replay:
            prepared = tuple(inputs_for(region, args.checks))
            words = tuple(word for item in prepared for word in item)
            results = tuple(evaluate(region, item[0], item[1:]) for item in prepared)
            input_file = args.directory / f"{case}.tuples"
            input_file.write_bytes(struct.pack(f"<{len(words)}I", *words))
            tuples = input_file, struct.pack(f"<{len(results)}I", *results), region.input_count + 1
        for mode, replacement in arms.items():
            stem = f"{case}-{mode}"
            started = time.perf_counter_ns()
            hlsl = emit(region, replacement)
            generation_ms = (time.perf_counter_ns() - started) / 1_000_000
            args.directory.joinpath(stem + ".hlsl").write_bytes(hlsl.encode("utf-8"))
            args.directory.joinpath(stem + ".c").write_bytes(emit(region, replacement, "c").encode("utf-8"))
            row["arms_measured"][mode] = {"generate_ms": generation_ms, "hlsl_bytes": len(hlsl),
                                         "hlsl_sha256": hashlib.sha256(hlsl.encode()).hexdigest(), "samples": []}
        if plan:
            row["clang_o3_exact_tuple_checks"] = compare_compiled_cpu(
                args, args.directory, region, [args.directory / f"{case}-{mode}" for mode in arms],
            )
        for trial in range(args.rounds):
            for mode in (arms if trial % 2 == 0 else reversed(arms)):
                sample = compile_one(args, args.directory, f"{case}-{mode}", tuples)
                row["arms_measured"][mode]["samples"].append(sample)
        for data in row["arms_measured"].values():
            data["medians"] = summary(data["samples"])
        report["cases"][case] = row
        print(f"{case}: {row['matched_tail']} shared operations, {row['edge_parameters']} parameters", flush=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
