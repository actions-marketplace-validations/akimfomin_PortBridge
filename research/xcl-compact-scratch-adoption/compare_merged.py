# SPDX-License-Identifier: MIT
"""Summarize aggregate-only A/B measurements on the merged XCL #2126 base."""

import argparse
import itertools
import json
import math
from pathlib import Path
import re
from statistics import median


BASE = "afc5ee86ae3a9521c9f15d96505cd73fe72f2191"
PATCH_SHA256 = "18e20d785ad6788f0fb30e823de0e14c3b49b3fae40f3d4a42b043f2a108d99f"
CASES = (
    ("ef008c0f", "early-exit"),
    ("ef008c0f", "late-shading"),
    ("c3ae6819", "representative"),
    ("fb1c6d2d", "representative"),
)
BUILDS = ("baseline", "candidate")
FIELDS = {
    "case", "input", "build", "grid", "pieces", "scratch_dwords_per_group",
    "words_checked", "different_words", "gpu_us_rounds",
}


def positive_int(value):
    return type(value) is int and value > 0


def load_measurements(path):
    measurements = {}
    with path.open(encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            try:
                row = json.loads(line)
            except ValueError as error:
                raise ValueError(f"row {line_no} does not contain JSON") from error
            if type(row) is not dict or set(row) != FIELDS:
                raise ValueError(f"row {line_no} uses fields outside the aggregate schema")
            if any(type(row[name]) is not str for name in ("case", "input", "build")):
                raise ValueError(f"row {line_no} has invalid labels")
            case = row["case"], row["input"]
            if case not in CASES or row["build"] not in BUILDS:
                raise ValueError(f"row {line_no} has an unexpected case or build")
            key = (*case, row["build"])
            if key in measurements:
                raise ValueError(f"row {line_no} duplicates an earlier measurement")
            grid = row["grid"]
            if type(grid) is not list or len(grid) != 3 or not all(map(positive_int, grid)):
                raise ValueError(f"row {line_no} needs three positive dispatch dimensions")
            if not positive_int(row["pieces"]) or row["pieces"] < 2:
                raise ValueError(f"row {line_no} needs a split chain of at least two pieces")
            if not positive_int(row["scratch_dwords_per_group"]):
                raise ValueError(f"row {line_no} has invalid scratch")
            checked, different = row["words_checked"], row["different_words"]
            if not positive_int(checked) or type(different) is not int or not 0 <= different <= checked:
                raise ValueError(f"row {line_no} has invalid output comparison counts")
            rounds = row["gpu_us_rounds"]
            if type(rounds) is not list or len(rounds) != 4:
                raise ValueError(f"row {line_no} needs four timing rounds")
            for block in rounds:
                if type(block) is not list or len(block) != 20:
                    raise ValueError(f"row {line_no} needs 20 GPU times per round")
                if not all(type(t) in (int, float) and 1e-6 <= t <= 1e9 and math.isfinite(t) for t in block):
                    raise ValueError(f"row {line_no} has invalid GPU times")
            measurements[key] = row
    expected_keys = {(*case, build) for case in CASES for build in BUILDS}
    if not expected_keys.issubset(measurements):
        missing = ", ".join("/".join(key) for key in sorted(expected_keys - measurements.keys()))
        raise ValueError(f"incomplete comparison, missing {missing}")
    return measurements


def summarize(measurements):
    rows = []
    for case, kind in CASES:
        before, after = (measurements[case, kind, build] for build in BUILDS)
        if before["grid"] != after["grid"] or before["words_checked"] != after["words_checked"]:
            raise ValueError(f"{case}/{kind} must use the same grid and output reference coverage")
        if before["pieces"] != after["pieces"]:
            raise ValueError(f"{case}/{kind} changed split plans. Verify the build configuration")
        before_words = before["scratch_dwords_per_group"]
        after_words = after["scratch_dwords_per_group"]
        before_rounds, after_rounds = (row["gpu_us_rounds"] for row in (before, after))
        before_us, after_us = (median(itertools.chain.from_iterable(rounds)) for rounds in (before_rounds, after_rounds))
        round_deltas = [
            100 * (median(candidate) / median(baseline) - 1)
            for baseline, candidate in zip(before_rounds, after_rounds, strict=True)
        ]
        rows.append({
            "case": case,
            "input": kind,
            "grid": before["grid"],
            "pieces": before["pieces"],
            "baseline_scratch_dwords_per_group": before_words,
            "candidate_scratch_dwords_per_group": after_words,
            "scratch_reduction_percent": round(100 * (1 - after_words / before_words), 3),
            "baseline_gpu_us_median": round(before_us, 6),
            "candidate_gpu_us_median": round(after_us, 6),
            "candidate_time_delta_percent": round(100 * (after_us / before_us - 1), 3),
            "round_time_delta_percent_min_max": [round(delta, 3) for delta in (min(round_deltas), max(round_deltas))],
            "words_checked_per_build": before["words_checked"],
            "baseline_different_words": before["different_words"],
            "candidate_different_words": after["different_words"],
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurements", type=Path, help="local JSON Lines with numerical A/B measurements")
    parser.add_argument("--candidate-revision", required=True, help="full Git commit of the measured candidate")
    arguments = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", arguments.candidate_revision) or arguments.candidate_revision == BASE:
        parser.error("--candidate-revision must be a full Git SHA-1 distinct from the baseline")
    try:
        measurements = load_measurements(arguments.measurements)
        rows = summarize(measurements)
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    output_ok = all(row["baseline_different_words"] == row["candidate_different_words"] == 0 for row in rows)
    scratch_ok = all(row["candidate_scratch_dwords_per_group"] <= row["baseline_scratch_dwords_per_group"] for row in rows)
    print(json.dumps({
        "baseline_xcl_revision": BASE,
        "candidate_xcl_revision": arguments.candidate_revision,
        "candidate_patch_sha256": PATCH_SHA256,
        "rounds": 4,
        "samples_per_build_per_round": 20,
        "output_check": "pass" if output_ok else "fail",
        "scratch_nonincrease_check": "pass" if scratch_ok else "fail",
        "results": rows,
    }, allow_nan=False, indent=2))
    return 0 if output_ok and scratch_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
