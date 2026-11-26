"""Read all five frozen PRs back through one complete static export. No network."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from m52_replay import HERE, ROOT, read, transport

sys.path.insert(0, str(ROOT))
from portbridge.__main__ import DEFAULT_SEED
from portbridge.catalog import Catalog
from portbridge.discovery_scan import link_result
from portbridge.discovery_search import discover
from portbridge.export import RELEASE_FILES, export
from portbridge.github import Unavailable, _Sync
from portbridge.release_gate import audit


def main():
    cases = read(HERE / "candidate.json")["cases"]
    pages = read(HERE / "search-responses.json")
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        catalog = Catalog(root / "catalog.sqlite3", DEFAULT_SEED)
        for case in cases:
            row = case["observation"]
            catalog.record_sync({"items": [row]}, update_health=False)
            replay = transport(pages, None, "", False, [], _Sync._request, Unavailable)
            with patch.object(_Sync, "_request", replay):
                result = link_result(catalog, row)
            if result["top5"] != case["result"]["top5"]:
                raise ValueError(f"Lookup differs from archived ranking for {case['url']}")
        site = root / "site"
        export(catalog, site, repository="akimfomin/PortBridge")
        errors = audit(site)
        if errors:
            raise ValueError(errors)
        manifest = read(site / "data/site.json")
        index = read(site / "data" / manifest["snapshots"]["discovery"])
        checked = []
        for case in cases:
            actual = discover(origin_url=case["url"], index=index)
            expected = case["result"]
            links = [r["url"] for r in expected["top5"] if r["route"] == "github"]
            if (actual["subject"] != expected["subject"] or actual["scan_status"] != expected["status"]
                    or [r["source"] for r in actual["automatic_matches"]] != links):
                raise ValueError(f"Exported search differs for {case['url']}")
            checked.append({"url": case["url"], "subject": actual["subject"], "state": actual["scan_status"],
                            "external_results": len(links)})
        print(json.dumps({"release_gate": "pass", "cases": checked,
                          "inventory_files": len(read(site / RELEASE_FILES)["files"])}, indent=2))


if __name__ == "__main__":
    main()
