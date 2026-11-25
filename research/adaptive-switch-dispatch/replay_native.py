"""Compile the exact emitted dispatch bodies as C++ and replay u32 results."""

import argparse
import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from benchmark import CASES, sorted_ranges_body, switch_body, table_body, workload
from dispatch import Projection, U32_MASK, adaptive, partition


def expected(ordinal: int | None, payload: list[int], seed: int) -> int:
    if ordinal is None:
        return seed ^ 0x55aa55aa
    value = payload[ordinal]
    salt = (ordinal * 0x9e3779b9 + 0x01234567) % (1 << 32)
    mode = ordinal % 4
    if mode == 0:
        return ((value ^ salt) + seed) & U32_MASK
    if mode == 1:
        return ((value * 17) ^ ((seed + salt) & U32_MASK)) & U32_MASK
    if mode == 2:
        return (((value << 7) | (value >> 25)) ^ seed ^ salt) & U32_MASK
    return (((value + salt) ^ seed) * 11) & U32_MASK


def make_replay(labels: list[int]) -> tuple[str, int, int]:
    rng = random.Random(240115)
    payload = [rng.getrandbits(32) for _ in labels]
    ordinals = {value: ordinal for ordinal, value in enumerate(labels)}
    probes = sorted(set(labels + [(value + delta) & U32_MASK for value in labels for delta in (-1, 1)]
                        + [0, U32_MASK, 1 << 31, (1 << 31) - 1]
                        + [rng.getrandbits(32) for _ in range(1024)]))
    funcs = {
        "flat": switch_body(labels, partition(labels)),
        "adaptive": switch_body(labels, adaptive(labels)),
        "without_size_gate": switch_body(labels, adaptive(labels, minimum_cases=1)),
        "fixed_low": switch_body(labels, partition(labels, Projection(6, 10))),
        "fixed_high": switch_body(labels, partition(labels, Projection(24, 8))),
        "sorted_ranges": sorted_ranges_body(labels),
        "table": table_body(len(labels)).replace("[loop] ", ""),
    }
    lines = ["#include <cstdint>", "#include <cstdio>", "using uint = std::uint32_t;"]
    for name, values in (("payload", payload), ("sorted_labels", labels)):
        literals = ", ".join(f"0x{value:x}u" for value in values)
        lines.append(f"static const uint {name}[] = {{{literals}}};")
    for name, body in funcs.items():
        lines.extend((f"uint {name}(uint tag, uint seed) {{ uint result;", body, "return result; }"))
    lines.extend(("struct Probe { uint tag, seed, value; };", "static const Probe probes[] = {"))
    for value in probes:
        seed = rng.getrandbits(32)
        want = expected(ordinals.get(value), payload, seed)
        lines.append(f"{{0x{value:x}u, 0x{seed:x}u, 0x{want:x}u}},")
    lines.append("};")
    lines.append("int main() { for (auto p : probes) {")
    for name in funcs:
        lines.append(f'if ({name}(p.tag, p.seed) != p.value) {{ std::printf("{name}: %u\\n", p.tag); return 1; }}')
    lines.append("} return 0; }")
    return "\n".join(lines), len(probes), len(funcs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    located = shutil.which(str(args.clang))
    if not located:
        parser.error("could not resolve the Clang++ executable")
    compiler = Path(located).resolve()
    version = subprocess.run([compiler, "--version"], check=True, text=True,
                             capture_output=True, timeout=15).stdout.splitlines()[0]
    results = {"compiler": version, "cases": {}}
    with tempfile.TemporaryDirectory(prefix="portbridge-dispatch-native-") as tmp:
        folder = Path(tmp)
        for name in CASES:
            source, probes, variants = make_replay(workload(name))
            cpp = folder / "replay.cpp"
            exe = folder / "replay.exe"
            cpp.write_text(source, encoding="ascii")
            subprocess.run([compiler, "-std=c++17", "-O1", cpp, "-o", exe], check=True, timeout=90)
            subprocess.run([exe], check=True, timeout=15)
            results["cases"][name] = {"probes": probes, "variants": variants, "matched": probes * variants}
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
