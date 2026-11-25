# SPDX-License-Identifier: MIT
"""Check physically replayed arms and summarize paired full-chain timings."""

import argparse
import csv
import json
from pathlib import Path
from statistics import median


MODES = {"full": "full_bytes", "ranges": "requested_bytes", "epochs": "epoch_bytes"}


def paired_statistics(values):
    return {"median": round(median(values), 4), "min": round(min(values), 4),
            "max": round(max(values), 4), "samples": [round(value, 4) for value in values]}


def summarize(workloads, measurements):
    rows = {}
    for data in measurements:
        key = (data["case"], int(data["block"]), data["mode"])
        if key in rows:
            raise ValueError(f"duplicate arm {key}")
        rows[key] = data

    cases = {}
    for case in workloads:
        name = case["path"].removesuffix(".tsv")
        blocks = sorted({block for key, block, _ in rows if key == name})
        if len(blocks) < 3:
            raise ValueError(f"insufficient paired blocks for {name}")
        by_mode = {}
        allocations = {}
        guarded = ("epochs" if case["epoch_bytes"] * 2 <= case["requested_bytes"] and
                   case["requested_bytes"] - case["epoch_bytes"] >= 1024 * 1024 else "ranges")
        for mode in (*MODES, "guarded"):
            effective = guarded if mode == "guarded" else mode
            byte_field = MODES[effective]
            mirror = case["mirror_payload_bytes"] if effective == "epochs" else 0
            peak = case["staging_peak_payload_bytes"][effective]
            arms = [rows.pop((name, block, mode)) for block in blocks]
            if any(int(row["copied_bytes"]) != case[byte_field] or
                   int(row["frame_count"]) != case["frames"] or
                   int(row["observed_pages"]) * 4096 != case["requested_bytes"] or
                   row["effective_mode"] != effective or
                   int(row["mirror_bytes"]) != mirror or int(row["staging_allocation_bytes"]) < peak
                   for row in arms):
                raise ValueError(f"measurements differ from trace for {name}/{mode}")
            allocation_sizes = {int(row["staging_allocation_bytes"]) for row in arms}
            if len(allocation_sizes) != 1:
                raise ValueError(f"unstable staging allocation size for {name}/{mode}")
            allocations[mode] = {
                "staging_allocation_bytes": allocation_sizes.pop(),
                "mirror_bytes": mirror,
            }
            by_mode[mode] = [float(row["wall_us"]) for row in arms]
            if any(value <= 0 for value in by_mode[mode]):
                raise ValueError(f"nonpositive timing for {name}/{mode}")
        epochs = by_mode["epochs"]
        ranges = by_mode["ranges"]
        full = by_mode["full"]
        cases[name] = {
            **case,
            "wall_us": {mode: paired_statistics(values) for mode, values in by_mode.items()},
            "allocation": allocations,
            "guarded_effective_mode": guarded,
            "paired_guarded_vs_ranges_percent": paired_statistics(
                [100 * (candidate - baseline) / baseline for candidate, baseline in zip(by_mode["guarded"], ranges)]
            ),
            "paired_epoch_vs_ranges_percent": paired_statistics(
                [100 * (candidate - baseline) / baseline for candidate, baseline in zip(epochs, ranges)]
            ),
            "paired_epoch_with_measured_python_plan_vs_ranges_percent": paired_statistics(
                [100 * (candidate + case["planner_total_cpu_us"] - baseline) / baseline
                 for candidate, baseline in zip(epochs, ranges)]
            ),
            "paired_epoch_vs_full_percent": paired_statistics(
                [100 * (candidate - baseline) / baseline for candidate, baseline in zip(epochs, full)]
            ),
            "bytes_avoided_vs_ranges_percent": round(100 * (1 - case["epoch_bytes"] / case["requested_bytes"]), 4),
        }
    if rows:
        raise ValueError("unrecognized measurement cases")
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workloads", type=Path)
    parser.add_argument("measurements", type=Path)
    args = parser.parse_args()
    workloads = json.loads(args.workloads.read_text(encoding="utf-8"))
    with args.measurements.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    print(json.dumps(summarize(workloads, rows), indent=2))


if __name__ == "__main__":
    main()
