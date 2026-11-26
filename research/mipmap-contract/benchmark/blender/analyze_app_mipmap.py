# SPDX-License-Identifier: MIT
"""Analyze Vulkan CPU profiling events from the stock Blender replay."""
import argparse
import json
from pathlib import Path
from statistics import median


def distribution(values):
    ordered = sorted(values)
    return {
        "median": round(median(ordered), 3),
        "p90_nearest_rank": round(ordered[(9 * len(ordered) + 9) // 10 - 1], 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
    }


def analyze(samples_path, profile_path):
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    events = json.loads(profile_path.read_text(encoding="utf-8"))
    rows = samples["samples"]
    mipmaps = [event for event in events
               if event["name"] == "Update Mipmaps" and event["ph"] == "X"]
    if any(event["pid"] != 2 for event in mipmaps):
        raise ValueError("Expected Vulkan Update Mipmaps events only on the CPU track")
    mipmaps = sorted(mipmaps, key=lambda event: event["ts"])
    cold = [row for row in rows if row["cache"] == "cold"]
    if len(mipmaps) != len(cold):
        raise ValueError(f"Expected one profile marker per cold read, got "
                         f"{len(mipmaps)} markers for {len(cold)} cold reads")
    for row, event in zip(cold, mipmaps):
        row["native_mipmap_cpu_us"] = event["dur"]
        row["native_mipmap_event_us"] = event["ts"]
        if not 0 < event["dur"] <= row["acquire_cpu_us"]:
            raise ValueError("Mipmap CPU scope does not fit the application acquire wall time")
    results = {}
    for case in sorted(samples["probe_values"]):
        case_rows = [row for row in rows if row["case"] == case]
        signatures = {row["probe_sha256"] for row in case_rows}
        levels = {row["checked_levels"] for row in case_rows}
        if len(signatures) != 1 or len(levels) != 1:
            raise ValueError(f"Texture sentinel changed for {case}")
        cold_rows = {row["pair"]: row for row in case_rows
                     if row["cache"] == "cold" and not row["warmup"]}
        hot_rows = {row["pair"]: row for row in case_rows
                    if row["cache"] == "hot" and not row["warmup"]}
        if cold_rows.keys() != hot_rows.keys() or len(cold_rows) != samples["pairs"]:
            raise ValueError(f"Expected a balanced cache control for {case}")
        result = {
            "pairs": len(cold_rows),
            "checked_levels": levels.pop(),
            "probe_sha256": signatures.pop(),
        }
        for key in ("acquire_cpu_us", "synchronized_with_probe_us"):
            result[key] = {
                "cold": distribution([row[key] for row in cold_rows.values()]),
                "hot": distribution([row[key] for row in hot_rows.values()]),
                "paired_cold_minus_hot": distribution([cold_rows[p][key] - hot_rows[p][key]
                                                       for p in cold_rows]),
            }
        result["native_mipmap_cpu_us"] = distribution([row["native_mipmap_cpu_us"]
                                                        for row in cold_rows.values()])
        result["native_mipmap_cpu_percent_of_cold_acquire"] = distribution([
            100 * row["native_mipmap_cpu_us"] / row["acquire_cpu_us"] for row in cold_rows.values()
        ])
        results[case] = result
    return {
        "blender_build": samples["blender_build"],
        "device": samples["device"],
        "source_png_sha256": samples["source_png_sha256"],
        "cpu_mipmap_markers_including_warmup": len(mipmaps),
        "gpu_mipmap_markers": 0,
        "cases": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = analyze(args.samples, args.profile)
    output = json.dumps(result, indent=2) + "\n"
    args.output.write_text(output, encoding="utf-8")
    print(output)
