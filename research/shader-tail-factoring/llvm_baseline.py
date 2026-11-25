# SPDX-License-Identifier: MIT
"""Compare the native C analogue under current LLVM -O3."""

import argparse
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    version = subprocess.check_output([args.clang, "--version"], text=True).splitlines()[0]
    result = {"compiler": version, "optimization": "-O3", "cases": {}}
    for source in sorted(args.generated.glob("*.c")):
        ir = subprocess.check_output(
            [args.clang, "-std=c17", "-O3", "-S", "-emit-llvm", source, "-o", "-"],
            text=True, encoding="utf-8", timeout=90,
        )
        try:
            function = ir.split("define ", 1)[1].split("\n}", 1)[0]
        except IndexError as error:
            raise ValueError(f"no function emitted for {source.name}") from error
        result["cases"][source.stem] = {
            "ssa_definitions": len(re.findall(r"^  %[-.\w]+ = ", function, flags=re.MULTILINE)),
            "phi_instructions": function.count(" = phi "),
            "switches": len(re.findall(r"^  switch ", function, flags=re.MULTILINE)),
        }
    if not result["cases"]:
        raise ValueError("no generated C counterparts")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
