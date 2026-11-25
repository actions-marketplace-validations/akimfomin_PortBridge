# SPDX-License-Identifier: MIT
"""Create current-event replay inputs and independent whole-observation checksums."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np

from make_traces import PAGE_BYTES, merge_ranges, ring_range


CHUNK_WORDS = 1 << 20


def source_cases():
    path = Path(__file__).with_name("source-traces") / "workload-shapes.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as source:
        cases = json.load(source)["cases"]
    for case in cases:
        # The scripted grounding consumer is capped at 128 scalar requests per
        # frame. Full-field source controls declare their complete field size.
        case["staging_pages"] = 128 if "grounding" in case["name"] else case["total_pages"]
    return cases


def changed_phases():
    total = 4096
    observed_pages = 1024
    frames = []
    for epoch in range(56):
        start_read = 256 if epoch < 40 else 2560
        reads = [(start_read, observed_pages)]
        if epoch == 0 or 12 <= epoch < 24:
            writes = [(0, total)]
        else:
            writes = merge_ranges(ring_range(start_read + (epoch * 29) % observed_pages, 64, total) +
                                  ring_range((total // 2 + epoch * 53) % total, 192, total))
        frames.append({"epoch": epoch, "writes": writes, "reads": reads,
                       "exact_request_bytes": observed_pages * PAGE_BYTES})
    return {"name": "switch-16", "page_bytes": PAGE_BYTES, "total_pages": total,
            "staging_pages": observed_pages, "scope": "Synthetic phase and observation change control",
            "frames": frames}


def typed_water_control():
    # Three u32 values per texel model height and two displacement components.
    # The write and observation patterns are controls, not measurements from the fork.
    side = 256
    total = side * side * 3
    reads = [(row * side * 3 + 64 * 3, 64 * 3) for row in range(64, 128)]
    count = sum(length for _, length in reads)
    frames = [{"epoch": epoch, "writes": [(0, total)], "reads": reads,
               "exact_request_bytes": count * 4} for epoch in range(48)]
    return {"name": "water-shape-control", "page_bytes": 4, "total_pages": total,
            "staging_pages": count, "scope": "Synthetic full-write crop control with VIctory #999-format sizes",
            "frames": frames}


def generate_contents(memory, first, count, epoch):
    version = np.uint32(((epoch + 1) * 747796405) & 0xffffffff)
    for start in range(first, first + count, CHUNK_WORDS):
        end = min(start + CHUNK_WORDS, first + count)
        indices = np.arange(start, end, dtype=np.uint32)
        memory[start:end] = ((indices * np.uint32(1664525) + np.uint32(1013904223)) ^ version) + (
            (indices >> np.uint32(10)) ^ np.uint32(0x9e3779b9)
        )


def observed_checksum(memory, reads, page_words):
    checksum = 0
    position = 1
    for first, count in reads:
        first *= page_words
        count *= page_words
        for start in range(first, first + count, CHUNK_WORDS):
            end = min(start + CHUNK_WORDS, first + count)
            width = end - start
            weights = np.arange(position, position + width, dtype=np.uint64)
            checksum += int(np.sum(memory[start:end] * weights, dtype=np.uint64))
            position += width
    return checksum & ((1 << 64) - 1)


def emit(case, destination):
    page_words = case["page_bytes"] // 4
    total = case["total_pages"]
    capacity = case["staging_pages"]
    frames = case["frames"]
    memory = np.zeros(total * page_words, dtype=np.uint32)
    observed_pages = 0
    path = destination / (case["name"] + ".tsv")
    with path.open("w", encoding="ascii", newline="\n") as stream:
        print(case["page_bytes"], total, len(frames), file=stream)
        for frame in frames:
            writes, reads, epoch = frame["writes"], frame["reads"], frame["epoch"]
            pages = sum(count for _, count in reads)
            if pages > capacity:
                raise ValueError(f"{case['name']} exceeds its declared staging limit")
            for first, count in writes:
                generate_contents(memory, first * page_words, count * page_words, epoch)
            checksum = observed_checksum(memory, reads, page_words)
            print(epoch, len(writes), len(reads), 0, checksum, file=stream)
            for first, count in (*writes, *reads):
                print(first, count, file=stream)
            observed_pages += pages
    return {"case": case["name"], "filename": path.name, "scope": case["scope"],
            "page_bytes": case["page_bytes"], "state_bytes": total * case["page_bytes"],
            "staging_pages": capacity, "frames": len(frames), "observed_pages": observed_pages,
            "source": case.get("source")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    cases = [*source_cases(), typed_water_control(), changed_phases()]
    manifest = [emit(case, args.destination) for case in cases]
    (args.destination / "online-workloads.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    for case in manifest:
        print(case["case"], case["frames"], case["observed_pages"] * case["page_bytes"])


if __name__ == "__main__":
    main()
