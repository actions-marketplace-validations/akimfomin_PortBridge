"""Replay the three development cases from public, normalized observations and search pages."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import ANY, patch


RECEIPT = Path(__file__).resolve().parent / "evidence" / "m53" / "development-search.json"
ORIGINS = {
    "https://github.com/xcl-dev/xcl/pull/2852",
    "https://github.com/ubiquitarianism/leonida/pull/2392",
    "https://github.com/KytyPS5/KytyPS5/pull/2565",
}


def product_fingerprint(code):
    paths = subprocess.check_output([
        "git", "-C", str(code), "ls-files", "-z", "--cached", "--others",
        "--exclude-standard", "--", "portbridge",
    ]).decode("utf-8").split("\0")
    digest = sha256()
    for name in sorted(filter(None, paths)):
        content = (code / name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode("utf-8") + b"\0" + sha256(content).digest())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, required=True, help="checkout of the recorded M5.3 candidate")
    code = parser.parse_args().code.resolve()
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if product_fingerprint(code) != receipt["product_sha256"]:
        raise SystemExit("The product files differ from the candidate recorded in the development receipt.")
    cases = receipt["cases"]
    if len(cases) != len(ORIGINS) or {case["url"] for case in cases} != ORIGINS:
        raise SystemExit("The development receipt must include each of the three recorded origins once.")

    sys.path.insert(0, str(code))
    from portbridge import discovery_scan, github
    from portbridge.__main__ import DEFAULT_SEED
    from portbridge.catalog import Catalog

    for case in cases:
        page = case["search"]
        with TemporaryDirectory() as directory, patch.object(github._Sync, "_request", autospec=True) as request:
            catalog = Catalog(Path(directory) / "replay.sqlite", DEFAULT_SEED)
            request.return_value = (page["response"], {})
            result = discovery_scan.link_result(catalog, case["normalized"])
            request.assert_called_once_with(ANY, page["url"], "search", None)
        if result != case["result"] or result["url"] != case["url"]:
            raise SystemExit(f"Replay differs for {case['url']}.")
        print(f"{case['url']}  {result['subject']}  {len(result['top5'])} results")
    print("3/3 results matched, 0 HTTP requests.")


if __name__ == "__main__":
    main()
