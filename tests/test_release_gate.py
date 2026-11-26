"""The release candidate must include the exact bytes the client will request."""
import json
from unittest.mock import patch

from portbridge.export import RELEASE_FILES, export
from portbridge.release_gate import audit
from test_portbridge import CatalogFixture


class ReleaseFilesTest(CatalogFixture):
    def test_missing_page_and_valid_json_corruption_identify_each_file(self):
        # Force a second page without needing a large network fixture.
        with patch("portbridge.public_browse.PAGE_SIZE", 2):
            site = export(self.catalog, self.workspace / "site")
        data = site / "data"
        browse = json.loads((data / "browse-index.json").read_bytes())
        first = data / f"browse-{browse['generation']}-matches-page-0.json"
        second = data / f"browse-{browse['generation']}-matches-page-1.json"
        terms = next(data.glob(f"browse-{browse['generation']}-matches-terms-*.json"))
        app = next((site / "static").glob("app-*.js"))
        self.assertEqual(audit(site), [])
        self.assertEqual(len(json.loads(second.read_bytes())["items"]), 2)
        first.unlink()
        second.write_bytes(b'{"items":[]}')
        terms.write_bytes(b'{"format":"PortBridge search shard v1","entries":{}}')
        app.write_bytes(app.read_bytes() + b" ")
        self.assertEqual(set(audit(site)), {f.relative_to(site).as_posix() for f in (first, second, terms, app)})

    def test_a_partial_or_missing_checksum_inventory_cannot_pass(self):
        site = export(self.catalog, self.workspace / "site")
        receipt = site / RELEASE_FILES
        inventory = json.loads(receipt.read_bytes())
        del inventory["files"][next(name for name in inventory["files"] if "-matches-page-" in name)]
        receipt.write_text(json.dumps(inventory), encoding="utf-8")
        self.assertEqual(audit(site), [RELEASE_FILES])
        receipt.unlink()
        self.assertEqual(audit(site), [RELEASE_FILES])
