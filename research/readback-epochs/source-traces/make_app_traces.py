# SPDX-License-Identifier: MIT
"""Normalize captures and emit PortBridge legacy Vulkan replay traces."""

from pathlib import Path
import json
import sys


PAGES = 4096
U32 = (1 << 32) - 1
U64 = (1 << 64) - 1


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def union(items):
    out = []
    for first, length in sorted(items):
        if out and first <= out[-1][0] + out[-1][1]:
            start, previous = out[-1]
            out[-1] = [start, max(first + length, start + previous) - start]
        else:
            out.append([first, length])
    return out


def contents(position, epoch):
    affine = (position * 1664525 + 1013904223) & U32
    version = ((epoch + 1) * 747796405) & U32
    return ((affine ^ version) + ((position >> 10) ^ 0x9e3779b9)) & U32


def frame(epoch, writes, reads, exact):
    return {"epoch": epoch, "writes": writes, "reads": reads, "exact_request_bytes": exact}


def case(name, provenance, size, frames, scope, granularity=PAGES):
    if size <= 0 or size % granularity:
        raise ValueError(f"unaligned modeled allocation: {name}")
    return {
        "name": name, "source": provenance["source"], "source_license": provenance["license"],
        "scope": scope, "page_bytes": granularity, "total_pages": size // granularity, "frames": frames,
    }


def write_trace(scenario, folder):
    name = scenario["name"]
    pages = scenario["total_pages"]
    stride = scenario["page_bytes"]
    n_words = stride // 4
    versions = [-1] * pages
    mirrored = [-2] * pages
    frames = scenario["frames"]
    counts = {"exact_request_bytes": 0, "aligned_request_bytes": 0, "reusable_bytes": 0}
    with (folder / f"{name}.tsv").open("w", encoding="ascii") as trace:
        print(stride, pages, len(frames), file=trace)
        for f in frames:
            epoch, writes, reads = (f[key] for key in ("epoch", "writes", "reads"))
            for first, length in writes:
                versions[first:first + length] = [epoch] * length
            digest = 1469598103934665603
            stale = []
            for first, length in reads:
                for page in range(first, first + length):
                    rev = versions[page]
                    if rev == -1:
                        raise ValueError(f"uninitialized requested page in {name}")
                    if mirrored[page] != rev:
                        stale.append((page, 1))
                        mirrored[page] = rev
                    for offset in (0, n_words // 2, n_words - 1):
                        digest = ((digest ^ contents(page * n_words + offset, rev)) * 1099511628211) & U64
            deltas = union(stale)
            print(epoch, len(writes), len(reads), len(deltas), digest, file=trace)
            for first, length in writes + reads + deltas:
                print(first, length, file=trace)
            counts["exact_request_bytes"] += f["exact_request_bytes"]
            counts["aligned_request_bytes"] += stride * sum(length for _, length in reads)
            counts["reusable_bytes"] += stride * (sum(length for _, length in reads) -
                                                  sum(length for _, length in deltas))
    return counts


def main(out):
    root = Path(__file__).resolve().parent
    heat = load(root / "heat-capture.json")
    snow = load(root / "snowflow-capture.json")
    scenarios = []
    for name, capture in heat["captures"].items():
        size = 4 * capture["size"] ** 2
        ranges = [[0, size // PAGES]]
        frames = [
            frame(f["epoch"], ranges, ranges if f["readbacks"] else [], size if f["readbacks"] else 0)
            for f in capture["frames"]
        ]
        scenarios.append(case(name, heat, size, frames,
                              f"Stock dense command schedule captured on mocked WebGPU, "
                              f"{capture['assumedMapDelayFrames']} injected map-delay frames"))
    for name, route in snow["routes"].items():
        size = snow["cpuMirrorBytes"]
        for granularity in (PAGES, 4):
            frames = [
                frame(f["epoch"], [[0, size // granularity]] if f["epoch"] == 0 else [],
                      union((word * 4 // granularity, 1) for word in f["words"]),
                      len(f["words"]) * 4)
                for f in route
            ]
            scenarios.append(case(name if granularity == PAGES else name + "-exact-word",
                                  snow, size, frames,
                                  "Stock CPU grounding addresses on scripted input with generated "
                                  "heights. Counterfactual deferred access after stock startup reduction",
                                  granularity))
    size = snow["readbackCalls"][0]["bytes"]
    n = size // PAGES
    stock = [frame(0, [[0, n]], [[0, n]], size)]
    scenarios.append(case("snowflow-stock-bake", snow, size, stock,
                          "Stock one-shot RG32F command captured against mocked readPixels; "
                          "an isolated readback event, not a gameplay frame"))
    out.mkdir(exist_ok=True)
    manifest = {item["name"]: write_trace(item, out) for item in scenarios}
    (out / "workload-shapes.json").write_text(json.dumps({
        "schema": 1, "cases": scenarios, "census": manifest,
    }, separators=(",", ":")) + "\n", encoding="utf-8")
    (out / "census.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for name, counts in manifest.items():
        print(name, counts)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
