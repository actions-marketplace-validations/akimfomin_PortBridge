"""Recheck the six public source files used in the historical M5 Lab replay."""
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

RECEIPTS = Path(__file__).parent / "fixtures" / "pilot" / "source-receipts.json"


def verify(record):
    source = urlsplit(record["source"])
    match = re.fullmatch(r"/([\w.-]+/[\w.-]+)/blob/([\da-f]{40})/(.+)", source.path)
    if source.scheme != "https" or source.netloc != "github.com" or not match:
        raise ValueError("Expected a public GitHub blob at an exact revision")
    repo, revision, path = match.groups()
    if revision != record["revision"] or ".." in path.split("/"):
        raise ValueError("Invalid pinned source")
    raw = f"https://raw.githubusercontent.com/{repo}/{revision}/{path}"
    with urlopen(Request(raw, headers={"User-Agent": "PortBridge source audit"}), timeout=20) as response:
        data = response.read(4_800_001)
    if len(data) != record["size"] or sha256(data).hexdigest() != record["sha256"]:
        raise ValueError(f"Source size or SHA-256 mismatch: {record['source']}")
    lines = data.decode().splitlines()
    for token, positions in record["anchors"].items():
        if not positions or any(n < 1 or n > len(lines) or token not in lines[n - 1] for n in positions):
            raise ValueError(f"Source anchor mismatch: {record['source']} {token}")


if __name__ == "__main__":
    for case, records in json.loads(RECEIPTS.read_bytes())["checks"].items():
        for entry in records:
            verify(entry)
        print(f"{case}: {len(records)} pinned source files verified")
