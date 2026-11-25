# SPDX-License-Identifier: MIT
"""Pair device timestamp samples on the pinned Continued replay shaders."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import re
from statistics import median
import subprocess
from tempfile import TemporaryDirectory


CASES = ("bpermute", "partial")
VARIANTS = ("baseline", "default", "full-subgroup")
HEADER = re.compile(r"(?m)^gpu timestamp ns: batch=(\d+) validBits=(\d+) period=([0-9.]+)$")
SAMPLE = re.compile(r"(?m)^gpu sample ns: ([0-9.]+) wall ns: ([0-9.]+)$")
PHYSICAL_WIDTH = re.compile(r"(?m)^compute subgroup size: (\d+)(?: \(observed: [^\n]*\))?$")
DEVICE = re.compile(r"(?m)^device: (.+?) \(subgroup ")


def inspect_gpu():
    """Record outside load without changing GPU clocks or system settings."""
    try:
        return subprocess.check_output(
            ("nvidia-smi", "--query-gpu=name,driver_version,utilization.gpu,clocks.current.sm",
             "--format=csv,noheader,nounits"), encoding="utf-8", timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def replay(runner, shader, args, batch, output):
    output.unlink(missing_ok=True)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("VKC_", "LEONIDA_VK_", "LEONIDA_PC_TAIL"))}
    env.update(LEONIDA_VK_DEVICE=args.device, VKC_SUBGROUP_SIZE=str(args.width),
               VKC_OUT_WORDS="256", VKC_GPU_BENCH=str(args.samples), VKC_GPU_BATCH=str(batch),
               VKC_DUMP=str(output))
    log = subprocess.check_output((runner, shader, "1", "dump"), env=env,
                                  encoding="utf-8", stderr=subprocess.STDOUT, timeout=25)
    metadata = HEADER.search(log)
    device = DEVICE.search(log)
    width = PHYSICAL_WIDTH.search(log)
    if (not metadata or int(metadata[1]) != batch or int(metadata[2]) not in range(1, 65)
            or float(metadata[3]) <= 0 or not device or args.device.casefold() not in device[1].casefold()
            or not width or int(width[1]) != args.width):
        raise ValueError(f"unexpected device, width or query parameters for {shader.name}")
    samples = [(float(device_ns), float(wall_ns)) for device_ns, wall_ns in SAMPLE.findall(log)]
    if len(samples) != args.samples or any(device_ns <= 0 or device_ns > wall_ns
                                          for device_ns, wall_ns in samples):
        raise ValueError(f"invalid timing samples for {shader.name}")
    readback = output.read_bytes()
    if len(readback) != 1024:
        raise ValueError(f"expected all 256 output words for {shader.name}")
    return {"adapter": device[1], "subgroup_width": int(width[1]), "timestamp_bits": int(metadata[2]),
            "timestamp_period_ns": float(metadata[3]), "sha256": sha256(readback).hexdigest(),
            "samples": samples}


def summary(rounds, batch):
    tables = {}
    for counter, column, scale in (("device_ns_per_dispatch", 0, batch), ("submit_wait_ns_per_batch", 1, 1)):
        per_variant = {label: [median(pair[column] for pair in arm[label]["samples"]) / scale
                               for arm in rounds] for label in VARIANTS}
        entries = {}
        for label in VARIANTS:
            effects = [result - baseline for result, baseline in zip(per_variant[label], per_variant["baseline"])]
            entries[label] = {"median": median(per_variant[label]), "paired_delta": median(effects),
                              "faster_rounds": sum(delta < 0 for delta in effects), "paired_deltas": effects}
        tables[counter] = entries
    return tables


def compare(args):
    # Latin rotation in each three-round block balances position; each block has a fixed-seed order.
    rng = random.Random(2322)
    report = {"seed": 2322, "rounds_per_case": args.rounds, "samples_per_arm": args.samples,
              "external_load_before": inspect_gpu(), "cases": {}}
    with TemporaryDirectory() as temp:
        for case in CASES:
            files = {variant: args.shaders / f"{case}-{variant}-O.spv" for variant in VARIANTS}
            bytes_by_variant = {label: sha256(shader.read_bytes()).hexdigest() for label, shader in files.items()}
            if case == "partial" and bytes_by_variant["default"] != bytes_by_variant["full-subgroup"]:
                raise ValueError("partial fallback must be a byte-identical timing control")
            checked = (args.shaders / f"{case}-baseline-O.bin").read_bytes()
            if len(checked) != 1024:
                raise ValueError(f"missing trusted full readback for {case}")
            expected = sha256(checked).hexdigest()
            case_data = {"shaders": bytes_by_variant, "expected_full_readback_sha256": expected, "batches": {}}
            report["cases"][case] = case_data
            for batch in (1, 32):
                rounds = []
                for index in range(args.rounds):
                    if index % 3 == 0:
                        order = rng.sample(VARIANTS, len(VARIANTS))
                    rotation = index % 3
                    arms = {}
                    for label in order[rotation:] + order[:rotation]:
                        arm = replay(args.runner, files[label], args, batch, Path(temp) / "result.bin")
                        if arm["sha256"] != expected:
                            raise ValueError(f"timed output differs for {case}/{label}")
                        arms[label] = arm
                    rounds.append(arms)
                case_data["batches"][batch] = {"rounds": rounds, "summary": summary(rounds, batch),
                                                "external_load": inspect_gpu()}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--shaders", type=Path, required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--width", required=True, type=int, choices=(32, 64))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rounds", default=9, type=int)
    parser.add_argument("--samples", default=24, type=int)
    args = parser.parse_args()
    if not 3 <= args.rounds <= 30 or args.rounds % 3 or not 5 <= args.samples <= 1000:
        parser.error("rounds must be a multiple of three from 3 to 30; samples must be from 5 to 1,000")
    report = compare(args)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    for case, findings in report["cases"].items():
        for batch, evidence in findings["batches"].items():
            table = evidence["summary"]["device_ns_per_dispatch"]
            print(case, batch, {label: (data["median"], data["paired_delta"], data["faster_rounds"])
                                for label, data in table.items()})


if __name__ == "__main__":
    main()
