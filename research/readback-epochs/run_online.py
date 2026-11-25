# SPDX-License-Identifier: MIT
"""Run and summarize paired online Vulkan readback trials."""

import argparse
import csv
import io
from itertools import permutations
import json
from pathlib import Path
from statistics import median
import subprocess

from run_matrix import telemetry


MODES = ("exact-online", "retain-online", "adaptive-online")
ORDERS = tuple(permutations(MODES))
REPEATS = 2


def stat(values):
    return {"median": round(median(values), 4), "min": round(min(values), 4), "max": round(max(values), 4)}


def summarize(manifest, rows):
    cases = {}
    for case in manifest:
        name = case["case"]
        summaries = {}
        durations = {}
        allocations = set()
        for mode in MODES:
            arms = sorted((row for row in rows if row["case"] == name and row["mode"] == mode),
                          key=lambda row: (int(row["block"]), int(row["repeat"])))
            expected_pairs = [(block, repeat) for block in range(len(ORDERS)) for repeat in range(REPEATS)]
            if [(int(row["block"]), int(row["repeat"])) for row in arms] != expected_pairs:
                raise ValueError(f"incomplete paired matrix for {name}/{mode}")
            if any(int(row["observed_pages"]) != case["observed_pages"] or
                   int(row["frame_count"]) != case["frames"] or float(row["wall_us"]) <= 0
                   for row in arms):
                raise ValueError(f"observations or timing disagree with the manifest for {name}/{mode}")

            constants = {}
            for key in ("copied_bytes", "staging_allocation_bytes", "mirror_bytes", "seed_frames", "reuse_frames",
                        "rebinds", "extra_drains"):
                values = {int(row[key]) for row in arms}
                if len(values) != 1:
                    raise ValueError(f"{name}/{mode} is nondeterministic for {key}")
                constants[key] = values.pop()
            if constants["copied_bytes"] > case["observed_pages"] * case["page_bytes"]:
                raise ValueError("online path transferred more than the exact requested bytes")
            if mode == "exact-online" and (
                constants["copied_bytes"] != case["observed_pages"] * case["page_bytes"] or
                any(constants[key] for key in ("mirror_bytes", "seed_frames", "reuse_frames", "rebinds", "extra_drains"))
            ):
                raise ValueError("the exact baseline did not follow its contract")
            allocations.add(constants["staging_allocation_bytes"])
            per_block = [median(float(row["wall_us"]) for row in arms if int(row["block"]) == i)
                         for i in range(len(ORDERS))]
            durations[mode] = per_block
            summaries[mode] = {"wall_us": stat(per_block), **constants}
        if len(allocations) != 1:
            raise ValueError(f"staging capacity differs across arms for {name}")
        exact = durations["exact-online"]
        for mode in MODES[1:]:
            relative = [100 * (candidate - base) / base
                        for candidate, base in zip(durations[mode], exact, strict=True)]
            summaries[mode]["paired_change_vs_exact_percent"] = stat(relative)
            summaries[mode]["faster_blocks"] = sum(value < 0 for value in relative)
        cases[name] = {"frames": case["frames"], "page_bytes": case["page_bytes"], "modes": summaries}
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runner", type=Path)
    parser.add_argument("shader", type=Path)
    parser.add_argument("traces", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--device", required=True)
    parser.add_argument("--nvidia-telemetry", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((args.traces / "online-workloads.json").read_text(encoding="utf-8"))
    runner, shader = args.runner.resolve(strict=True), args.shader.resolve(strict=True)
    rows = []
    diagnostics = set()
    gpu_samples = {}
    for block, order in enumerate(ORDERS):
        if args.nvidia_telemetry:
            gpu_samples[str(block)] = telemetry()
        for case in manifest:
            trace = (args.traces / case["filename"]).resolve(strict=True)
            for mode in order:
                result = subprocess.run([runner, shader, trace, mode, str(REPEATS), args.device,
                                         str(case["staging_pages"]), "sum"],
                                        capture_output=True, text=True, timeout=45)
                if result.returncode:
                    raise SystemExit(f"{trace.name}/{mode} failed: {result.stderr.strip()}")
                diagnostics.update(result.stderr.strip().splitlines())
                records = list(csv.DictReader(io.StringIO(result.stdout)))
                if len(records) != REPEATS or any(row.get("mode") != mode for row in records):
                    raise SystemExit(f"{trace.name}/{mode} returned invalid rows")
                rows.extend({"case": trace.stem, "block": block, **row} for row in records)
        print(f"Paired block {block + 1}/{len(ORDERS)} completed", flush=True)
    if args.nvidia_telemetry:
        gpu_samples["end"] = telemetry()
    summary = summarize(manifest, rows)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "hardware.csv").open("w", encoding="utf-8", newline="") as raw:
        writer = csv.DictWriter(raw, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for name, data in (
        ("summary", summary),
        ("environment", {"runner": sorted(diagnostics), "orders": ORDERS, "gpu_samples": gpu_samples}),
    ):
        (args.output / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
