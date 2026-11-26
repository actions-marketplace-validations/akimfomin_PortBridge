"""Paired DXC/SPIRV-Tools experiment for portable dispatch layouts."""

import argparse
import json
import random
import statistics
import struct
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter

from dispatch import Projection, adaptive, emit, partition, U32_MASK


ENVIRONMENT = "vulkan1.2"
CASES = {"small": 24, "dense": 512, "strided": 512, "sparse": 2048}


def workload(name: str) -> list[int]:
    count = CASES[name]
    if name == "small":
        return sorted((u * 7 + 31) & U32_MASK for u in range(count))
    if name == "dense":
        return sorted(u & U32_MASK for u in range(-count // 2, count // 2))
    if name == "strided":
        return [(u << 20) | 0x45678 for u in range(count)]
    generator = random.Random(202025)
    return sorted(generator.sample(range(1 << 32), count - 4) + [0, 0x80000000, 0xfffffffe, U32_MASK])


def compute(ordinal: int, sample: str = "a") -> str:
    salt = f"0x{(ordinal * 0x9e3779b9 + 0x1234567) & U32_MASK:08x}u"
    choices = [
        f"({sample} ^ {salt}) + seed",
        f"({sample} * 17u) ^ (seed + {salt})",
        f"(({sample} << 7u) | ({sample} >> 25u)) ^ seed ^ {salt}",
        f"(({sample} + {salt}) ^ seed) * 11u",
    ]
    return f"result = {choices[ordinal % len(choices)]};"


def switch_body(labels: list[int], plan) -> str:
    ordinals = {label: index for index, label in enumerate(labels)}

    def arm(label: int) -> str:
        ordinal = ordinals[label]
        return f"uint a = payload[{ordinal}u]; {compute(ordinal)}"

    return emit(plan, "tag", arm, "result = seed ^ 0x55aa55aau;")


def sorted_ranges_body(labels: list[int]) -> str:
    """Comparison tree over sorted bounds with exactly 32 literals per leaf."""
    groups = [labels[index:index + 32] for index in range(0, len(labels), 32)]
    ordinals = {label: index for index, label in enumerate(labels)}

    def arm(label):
        ordinal = ordinals[label]
        return f"uint a = payload[{ordinal}u]; {compute(ordinal)}"

    def branch(begin, end):
        if end - begin == 1:
            return emit(partition(groups[begin]), "tag", arm, "result = seed ^ 0x55aa55aau;")
        mid = (begin + end) // 2
        bound = groups[mid - 1][-1]
        return (
            f"if (tag <= 0x{bound:08x}u) {{\n"
            f"{branch(begin, mid)}\n}} else {{\n"
            f"{branch(mid, end)}\n}}"
        )

    return branch(0, len(groups)) if groups else "result = seed ^ 0x55aa55aau;"


def hlsl(body: str, data_index: bool = False) -> str:
    declarations = "[[vk::binding(0, 0)]] StructuredBuffer<uint> payload : register(t0);\n"
    if data_index:
        declarations += "[[vk::binding(1, 0)]] StructuredBuffer<uint> sorted_labels : register(t1);\n"
    return declarations + """[[vk::binding(2, 0)]] RWStructuredBuffer<uint> outputs : register(u0);
[numthreads(64, 1, 1)]
void main(uint3 id : SV_DispatchThreadID) {
    uint tag = payload[id.x + 2048u];
    uint seed = payload[id.x + 4096u];
    uint result;
""" + body + "\n    outputs[id.x] = result;\n}\n"


def table_body(count: int) -> str:
    return f"""    uint lo = 0u, hi = {count}u;
    [loop] while (lo < hi) {{
        uint mid = lo + ((hi - lo) >> 1u);
        if (sorted_labels[mid] < tag) lo = mid + 1u;
        else hi = mid;
    }}
    result = seed ^ 0x55aa55aau;
    if (lo < {count}u) {{
        if (sorted_labels[lo] == tag) {{
            uint a = payload[lo];
            uint salt = lo * 0x9e3779b9u + 0x01234567u;
            switch (lo & 3u) {{
              case 0u: result = (a ^ salt) + seed; break;
              case 1u: result = (a * 17u) ^ (seed + salt); break;
              case 2u: result = ((a << 7u) | (a >> 25u)) ^ seed ^ salt; break;
              default: result = ((a + salt) ^ seed) * 11u; break;
            }}
        }}
    }}"""


def run(exe: Path, *args: str | Path) -> str:
    result = subprocess.run([exe, *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError(f"{exe.name}: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout or result.stderr


def cfg(blob: bytes) -> dict:
    """Count structural properties via SPIR-V instruction opcodes."""
    words = struct.unpack(f"<{len(blob) // 4}I", blob)
    if words[0] != 0x07230203:
        raise ValueError("expected little-endian SPIR-V")
    offset = 5
    switch_sizes = []
    label_count = 0
    phi_inputs = []
    while offset < len(words):
        length, opcode = words[offset] >> 16, words[offset] & 0xffff
        if not length or offset + length > len(words):
            raise ValueError("malformed SPIR-V instruction")
        if opcode == 251:  # OpSwitch, a 32-bit selector throughout this experiment.
            switch_sizes.append(1 + (length - 3) // 2)
        elif opcode == 248:  # OpLabel
            label_count += 1
        elif opcode == 245:  # OpPhi
            phi_inputs.append((length - 3) // 2)
        offset += length
    return {
        "bytes": len(blob),
        "switches": len(switch_sizes),
        "max_switch_edges": max(switch_sizes, default=0),
        "switch_square_sum": sum(n * n for n in switch_sizes),
        "basic_blocks": label_count,
        "max_phi_inputs": max(phi_inputs, default=0),
    }


def benchmark(args: argparse.Namespace) -> dict:
    generator = random.Random(250115)
    results = {
        "dxc": run(args.dxc, "--version").strip(),
        "spirv_opt": run(args.spirv_opt, "--version").splitlines()[0],
        "target": ENVIRONMENT,
        "rounds": args.rounds,
        "workloads": {},
    }
    with tempfile.TemporaryDirectory(prefix="portbridge-dispatch-") as tmp:
        work = Path(tmp)
        for name in args.workload:
            labels = workload(name)
            layouts = {
                "flat": lambda: partition(labels),
                "fixed_low_6_10": lambda: partition(labels, Projection(6, 10)),
                "fixed_high_24_8": lambda: partition(labels, Projection(24, 8)),
                "adaptive": lambda: adaptive(labels),
                "radix_without_size_gate": lambda: adaptive(labels, minimum_cases=1),
            }
            paths: dict[str, tuple[Path, Path, Path]] = {}
            rows: dict[str, dict] = {}
            for variant in (*layouts, "sorted_ranges_32", "table"):
                source = work / f"{variant}.hlsl"
                raw = source.with_suffix(".spv")
                optimized = source.with_suffix(".opt.spv")
                paths[variant] = source, raw, optimized
                rows[variant] = {"generate_ms": [], "dxc_ms": [], "spirv_opt_ms": []}
            for round_id in range(args.rounds):
                order = list(rows)
                generator.shuffle(order)
                for variant in order:
                    source, raw, optimized = paths[variant]
                    start = perf_counter()
                    if variant in layouts:
                        plan = layouts[variant]()
                        body = switch_body(labels, plan)
                    elif variant == "sorted_ranges_32":
                        plan = None
                        body = sorted_ranges_body(labels)
                    else:
                        plan = None
                        body = table_body(len(labels))
                    source.write_text(hlsl(body, variant == "table"), encoding="ascii")
                    dxc_start = perf_counter()
                    run(args.dxc, "-spirv", f"-fspv-target-env={ENVIRONMENT}",
                        "-T", "cs_6_0", "-E", "main", "-O3", source, "-Fo", raw)
                    opt_start = perf_counter()
                    run(args.spirv_opt, "-O", f"--target-env={ENVIRONMENT}", raw, "-o", optimized)
                    end = perf_counter()
                    row = rows[variant]
                    row["generate_ms"].append(round((dxc_start - start) * 1000, 3))
                    row["dxc_ms"].append(round((opt_start - dxc_start) * 1000, 3))
                    row["spirv_opt_ms"].append(round((end - opt_start) * 1000, 3))
                    if round_id != 0:
                        continue
                    run(args.spirv_val, "--target-env", ENVIRONMENT, raw)
                    run(args.spirv_val, "--target-env", ENVIRONMENT, optimized)
                    row["layout"] = ([plan.projection.offset, plan.projection.width]
                                     if plan and plan.projection else None)
                    row["arm_count"] = len(labels)
                    row["source_bytes"] = source.stat().st_size
                    row["dxc_cfg"] = cfg(raw.read_bytes())
                    row["optimized_cfg"] = cfg(optimized.read_bytes())
            for row in rows.values():
                row["median_dxc_ms"] = round(statistics.median(row["dxc_ms"]), 3)
                row["median_end_to_end_ms"] = round(statistics.median(
                    sum(phase) for phase in zip(row["generate_ms"], row["dxc_ms"], row["spirv_opt_ms"])), 3)
            results["workloads"][name] = rows
            print(name, {variant: row["median_end_to_end_ms"] for variant, row in rows.items()}, flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dxc", required=True, type=Path)
    parser.add_argument("--spirv-opt", required=True, type=Path)
    parser.add_argument("--spirv-val", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rounds", default=5, type=int)
    parser.add_argument("--workload", choices=CASES, nargs="+", default=list(CASES))
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("rounds must be positive")
    args.output.write_text(json.dumps(benchmark(args), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
