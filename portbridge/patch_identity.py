"""Compare two local diff files without applying either one."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess


MAX_PATCH = 256 * 1024
REVISION = re.compile(r"[a-fA-F0-9]{40,64}")


def patch_id(path, git):
    with Path(path).open("rb") as stream:
        return patch_bytes(stream.read(MAX_PATCH + 1), git)


def patch_bytes(data, git):
    if len(data) > MAX_PATCH:
        raise ValueError("Patch exceeds the 256 KiB comparison limit")
    completed = subprocess.run([git, "patch-id", "--stable"], input=data, capture_output=True, timeout=5)
    if completed.returncode:
        raise ValueError("Git could not read the patch")
    values = completed.stdout.decode("ascii", errors="replace").splitlines()
    if len(values) != 1:
        raise ValueError("Provide one non-empty unified diff per file")
    result = values[0].split()[0]
    if not REVISION.fullmatch(result):
        raise ValueError("Git returned an invalid patch ID")
    return result


def related_revisions(repository, left, right, git):
    if not REVISION.fullmatch(left or "") or not REVISION.fullmatch(right or ""):
        raise ValueError("Ancestry requires two full local revision IDs")
    root = Path(repository).resolve(strict=True)
    completed = subprocess.run([git, "-C", str(root), "merge-base", left, right],
                               capture_output=True, timeout=5)
    base = completed.stdout.decode("ascii", errors="replace").strip()
    if completed.returncode > 1:
        raise ValueError("Local Git could not read the revisions")
    return base if completed.returncode == 0 and REVISION.fullmatch(base) else None


def compare(left, right, *, repository=None, left_revision=None, right_revision=None):
    git = shutil.which("git")
    if git is None:
        raise ValueError("Git is required for stable patch identity")
    first, second = patch_id(left, git), patch_id(right, git)
    base = related_revisions(repository, left_revision, right_revision, git) if repository else None
    return {"left_patch_id": first, "right_patch_id": second, "same_patch": first == second,
            "common_ancestor": base,
            "relationship": "same_patch" if first == second else "different_patch",
            "limits": "Stable patch IDs ignore whitespace and hunk offsets. Ancestry and patch equality alone do not establish applicability."}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("left", type=Path)
    cli.add_argument("right", type=Path)
    cli.add_argument("--repository", type=Path)
    cli.add_argument("--left-revision")
    cli.add_argument("--right-revision")
    try:
        result = compare(**vars(cli.parse_args()))
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        cli.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
