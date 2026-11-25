# SPDX-License-Identifier: MIT
"""Run balanced paired Vulkan readback trials on one physical device."""

import argparse
import csv
import io
import json
from pathlib import Path
import subprocess


ORDERS = (
    ("full", "ranges", "guarded", "epochs"),
    ("ranges", "epochs", "full", "guarded"),
    ("epochs", "guarded", "ranges", "full"),
    ("guarded", "full", "epochs", "ranges"),
)
FIELDS = ("case", "block", "device", "mode", "repeat", "wall_us", "copied_bytes", "observed_pages",
          "frame_count", "staging_allocation_bytes", "mirror_bytes", "effective_mode")


def telemetry():
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=timestamp,name,driver_version,utilization.gpu,memory.used",
         "--format=csv,noheader"],
        check=True, capture_output=True, text=True, timeout=10,
    )
    return result.stdout.strip().splitlines()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runner", type=Path)
    parser.add_argument("shader", type=Path)
    parser.add_argument("traces", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--device", required=True)
    parser.add_argument("--nvidia-telemetry", action="store_true")
    args = parser.parse_args()
    cases = json.loads((args.traces / "workloads.json").read_text(encoding="utf-8"))
    runner = args.runner.resolve(strict=True)
    shader = args.shader.resolve(strict=True)
    rows = []
    diagnostics = set()
    gpu_samples = {}

    for block, order in enumerate(ORDERS):
        if args.nvidia_telemetry:
            gpu_samples[str(block)] = telemetry()
        for case in cases:
            trace = (args.traces / case["path"]).resolve(strict=True)
            for mode in order:
                result = subprocess.run([runner, shader, trace, mode, "1", args.device],
                                        capture_output=True, text=True, timeout=45)
                if result.returncode:
                    raise SystemExit(f"{trace.name}/{mode} failed: {result.stderr.strip()}")
                diagnostics.update(result.stderr.strip().splitlines())
                records = list(csv.DictReader(io.StringIO(result.stdout)))
                if len(records) != 1 or records[0].get("mode") != mode:
                    raise SystemExit(f"{trace.name}/{mode} returned an invalid row")
                rows.append({"case": trace.stem, "block": block, **records[0]})
        print(f"Paired block {block + 1}/{len(ORDERS)} completed", flush=True)

    if args.nvidia_telemetry:
        gpu_samples["end"] = telemetry()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "hardware.csv").open("w", encoding="utf-8", newline="") as raw:
        writer = csv.DictWriter(raw, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "environment.json").write_text(
        json.dumps({"runner": sorted(diagnostics), "orders": ORDERS, "gpu_samples": gpu_samples}, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
