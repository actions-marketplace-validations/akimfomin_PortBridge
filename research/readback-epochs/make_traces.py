# SPDX-License-Identifier: MIT
"""Generate legal height-field observation traces and an independent sample oracle."""

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from epoch_plan import EpochPlan, View


PAGE_BYTES = 4096
FRAMES = 48
U32 = (1 << 32) - 1
U64 = (1 << 64) - 1


def merge_ranges(ranges):
    merged = []
    for first, count in sorted(ranges):
        end = first + count
        if merged and first <= merged[-1][0] + merged[-1][1]:
            previous, size = merged[-1]
            merged[-1] = previous, max(previous + size, end) - previous
        else:
            merged.append((first, count))
    return merged


def ring_range(first, count, total):
    start = first % total
    if start + count <= total:
        return [(start, count)]
    return [(0, start + count - total), (start, total - start)]


def workload(name, total, epoch):
    if name in {"global-writes", "height256", "opaque"}:
        writes = [(0, total)]
    elif name == "mostly-dirty":
        writes = [(total // 8 + epoch % 11, total * 7 // 32),
                  (3 * total // 4, total // 16)]
    else:
        # The producer keeps the rest of the field live and updates tiles in place.
        width = total // (24 if name == "small" else 12)
        writes = merge_ranges(ring_range(epoch * 97, width, total) +
                              ring_range(total // 2 + epoch * 31, width, total))
    if epoch == 0:
        writes = [(0, total)]

    if name == "opaque":
        observations = [(0, total)]
    elif name == "medium":
        observations = [(total // 10 + epoch * 3, total // 16),
                        (total // 2 + epoch, total // 16)]
    elif name == "rolling":
        # Independent observation regions move by one page every four frames.
        region = total // 64
        shift = epoch // 4
        observations = merge_ranges(
            interval for tile in range(64)
            for interval in ring_range(tile * region + shift, region // 8, total)
        )
    else:
        observations = [(total // 8, total // 4)]
    return writes, observations


def word_at(position, epoch):
    affine = (position * 1664525 + 1013904223) & U32
    version = ((epoch + 1) * 747796405) & U32
    return ((affine ^ version) + ((position >> 10) ^ 0x9e3779b9)) & U32


def sample_hash(observations, versions):
    checksum = 1469598103934665603
    page_words = PAGE_BYTES // 4
    for first, count in observations:
        for page in range(first, first + count):
            for offset in (0, page_words // 2, page_words - 1):
                value = word_at(page * page_words + offset, versions[page])
                checksum = ((checksum ^ value) * 1099511628211) & U64
    return checksum


def observe_alias(plan, intervals, midpoint, *, opaque):
    if opaque:
        return plan.observe_opaque(["terrain"])
    reads = []
    for first, count in intervals:
        limit = first + count
        if first < midpoint:
            reads.append(("west", first * PAGE_BYTES, (min(midpoint, limit) - first) * PAGE_BYTES))
        if limit > midpoint:
            first_east = max(first, midpoint)
            reads.append(("east", (first_east - midpoint // 2) * PAGE_BYTES,
                          (limit - first_east) * PAGE_BYTES))
    return plan.observe_many(reads)


def generate(destination, name, size_mib):
    state_bytes = int(size_mib * 1024 * 1024)
    total = state_bytes // PAGE_BYTES
    midpoint = total // 2
    plan = EpochPlan({"terrain": total * PAGE_BYTES}, {
        "writer": View("terrain", 0, total * PAGE_BYTES),
        "west": View("terrain", 0, 3 * midpoint // 2 * PAGE_BYTES),
        "east": View("terrain", midpoint // 2 * PAGE_BYTES, 3 * midpoint // 2 * PAGE_BYTES),
    })
    versions = [-1] * total
    observed_pages = copied_pages = writes_pages = empty_frames = 0
    observed_union = set()
    staging_slot_peaks = {mode: [PAGE_BYTES] * 3 for mode in ("full", "ranges", "epochs")}
    planner_us = []
    trace_path = destination / f"{name}-{size_mib}.tsv"
    with trace_path.open("w", encoding="ascii") as trace:
        print(PAGE_BYTES, total, FRAMES, file=trace)
        for epoch in range(FRAMES):
            writes, observations = workload(name, total, epoch)
            started = perf_counter_ns()
            for first, count in writes:
                plan.gpu_write("writer", first * PAGE_BYTES, count * PAGE_BYTES)
            copies = observe_alias(plan, observations, midpoint, opaque=name == "opaque")
            delta = merge_ranges((copy.offset // PAGE_BYTES, copy.size // PAGE_BYTES) for copy in copies)
            planner_us.append((perf_counter_ns() - started) / 1000)
            for first, count in writes:
                versions[first:first + count] = [epoch] * count
            expected = sample_hash(observations, versions)
            print(epoch, len(writes), len(observations), len(delta), expected, file=trace)
            for first, count in writes + observations + delta:
                print(first, count, file=trace)
            observed_count = sum(count for _, count in observations)
            delta_count = sum(count for _, count in delta)
            observed_pages += observed_count
            copied_pages += delta_count
            for first, count in observations:
                observed_union.update(range(first, first + count))
            for mode, count in (("full", total), ("ranges", observed_count), ("epochs", delta_count)):
                slot = epoch % 3
                peaks = staging_slot_peaks[mode]
                peaks[slot] = max(peaks[slot], count * PAGE_BYTES)
            writes_pages += sum(count for _, count in writes)
            empty_frames += not delta
    return {
        "path": trace_path.name,
        "frames": FRAMES,
        "state_bytes": state_bytes,
        "written_bytes": writes_pages * PAGE_BYTES,
        "full_bytes": total * FRAMES * PAGE_BYTES,
        "requested_bytes": observed_pages * PAGE_BYTES,
        "epoch_bytes": copied_pages * PAGE_BYTES,
        "epoch_no_copy_frames": empty_frames,
        "mirror_payload_bytes": len(observed_union) * PAGE_BYTES,
        "staging_peak_payload_bytes": {mode: sum(peaks) for mode, peaks in staging_slot_peaks.items()},
        "planner_median_cpu_us": round(median(planner_us), 3),
        "planner_total_cpu_us": round(sum(planner_us), 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    results = [
        generate(args.destination, name, size)
        for name, size in [
            ("height256", 0.25), ("small", 8), ("stable", 32), ("rolling", 32),
            ("global-writes", 32), ("opaque", 32), ("medium", 16), ("mostly-dirty", 16),
        ]
    ]
    (args.destination / "workloads.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for case in results:
        print(case["path"], case["requested_bytes"], case["epoch_bytes"], case["epoch_no_copy_frames"])


if __name__ == "__main__":
    main()
