"""Replay the reviewed Discovery rank list; --online also repeats the public PR scan."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from portbridge.__main__ import DEFAULT_SEED
from portbridge.catalog import Catalog
from portbridge.discovery_scan import cached_index, scan, subject
from portbridge.discovery_search import DATA, discover
from portbridge.github import _item

ORIGIN = "https://github.com/LooperSalty/AnyXboxX/pull/429"
API = "https://api.github.com/repos/LooperSalty/AnyXboxX/pulls/429"
QUERY = "D3D12_TILE_RANGE_FLAG_NULL UpdateTileMappings reclaim unmapped mip tiles before heap reuse fence completion"


def ranked(result):
    return [{"rank": i, "id": row["id"], "title": row["title"], "url": row["source"],
             "revision": row["revision"], "score": row["score"]}
            for i, row in enumerate(result["matches"], 1)]


def online_scan():
    with urlopen(Request(API, headers={"User-Agent": "PortBridge public M5.1 audit"}), timeout=20) as response:
        pr = json.load(response)
    with TemporaryDirectory() as directory:
        catalog = Catalog(Path(directory) / "holdout.sqlite3", DEFAULT_SEED)
        projects = catalog.projects()
        project = next(item for item in projects if item["repo"].lower() == "loopersalty/anyxboxx")
        repositories = {item["repo"].lower(): item["repo"] for item in projects}
        observation = _item(pr, "pr", project, repositories)
        report = scan(catalog, [observation], online=True, max_lookups=1)
        readback = discover(QUERY, origin_url=ORIGIN, index=cached_index(catalog), limit=5)
        return {
            "head": pr["head"]["sha"], "title": pr["title"], "source_state": pr["state"],
            "subject_extracted": subject(observation), "eligible": report["eligible"],
            "lookups": report["lookups"], "batch_status": report["status"],
            "scan_status": readback["scan_status"],
            "automatic_top5": [{"rank": i, "title": row["title"], "url": row["url"]}
                               for i, row in enumerate(readback["automatic_matches"], 1)]
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()
    result = discover(QUERY, origin_url=ORIGIN, limit=5)
    report = {"origin": ORIGIN, "query": QUERY, "limit": 5,
              "index_sha256": sha256(DATA.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
              "case_present": result["case"] is not None, "ranked_top5": ranked(result)}
    if args.online:
        report["automatic"] = online_scan()
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
