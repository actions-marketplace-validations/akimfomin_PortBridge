"""Offline readback and browser presentation of a saved Discovery search."""

import json
import os
from pathlib import Path
import shutil
import subprocess
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from portbridge.__main__ import make_server
from portbridge.discovery_search import discover, discovery_index, key
from portbridge.mcp import PortBridgeMCP
from portbridge.preflight import public_preflight
from test_portbridge import CatalogFixture


PR = "https://github.com/xcl-dev/xcl/pull/99999"
ROOT = Path(__file__).resolve().parents[1]


def browser_binary():
    windows = Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe"
    return next((path for name in ("google-chrome", "chromium", "chromium-browser") if (path := shutil.which(name))),
                str(windows) if windows.is_file() else None)


class DiscoveryPresentationTest(CatalogFixture):
    def test_empty_url_states_distinguish_search_coverage(self):
        for status, reason, expected, message in (
            ("available", None, "no_match", "no matching source"),
            ("partial", None, "partial", "incomplete"),
            ("offline", None, "offline", "No external sources were checked"),
            ("stale", None, "stale", "out of date"),
            ("unavailable", "rate_limit", "unavailable", "rate-limited"),
            ("unavailable", None, "unavailable", "could not be completed"),
            ("no_subject", None, "no_subject", "No external search ran"),
            ("not_scanned", None, "not_scanned", "--online --url"),
        ):
            with self.subTest(status=status, reason=reason):
                scan = {"subject": "", "status": status, "reason": reason, "matches": []}
                index = {**discovery_index(), "automatic": {key(PR): scan}}
                result = discover(origin_url=PR, index=index)
                self.assertEqual((result["status"], result["scan_status"], result["scan_reason"]), (expected, status, reason))
                self.assertIn(message, result["empty_reason"])
        for url in (PR.replace("pull", "issues"), PR.replace("pull/99999", "commit/" + "a" * 40)):
            report = discover(origin_url=url)
            self.assertNotIn("--url", report["empty_reason"])

    def test_mcp_and_snapshot_outage_retell_the_available_evidence(self):
        mcp = PortBridgeMCP(self.catalog)
        result = mcp.run_tool({"name": "portbridge_preflight", "arguments": {"url": PR}})
        self.assertEqual(result["structuredContent"]["discovery"]["status"], "not_scanned")
        with patch("portbridge.preflight.read_public_file", side_effect=OSError("offline")):
            fallback = public_preflight(url=PR)["discovery"]
            self.assertEqual(fallback["status"], "unavailable")
            self.assertEqual(fallback["scan_reason"], "snapshot_unavailable")
            self.assertIn("bundled", fallback["empty_reason"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to run the static ranker")
    def test_exported_ranker_uses_the_same_subject_for_an_unmapped_pr(self):
        index = {**discovery_index(), "automatic": {
            key(PR): {"subject": "vkimagememorybarrier2", "status": "partial", "matches": []}
        }}
        ranked = discover(origin_url=PR, index=index)
        self.assertTrue(ranked["matches"])
        script = (ROOT / "portbridge/static/discovery.js").read_text(encoding="utf-8")
        script += "\nconst [index, url] = JSON.parse(require('fs').readFileSync(0, 'utf8'));" \
                  "\nconst {matches, scan_status} = PortBridgeDiscovery.search(index, url);" \
                  "\nconsole.log(JSON.stringify([matches.map(row => row.id), scan_status]));"
        result = subprocess.run(["node", "-e", script], input=json.dumps([index, PR]), text=True,
                                capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), [[row["id"] for row in ranked["matches"]], "partial"])

    @unittest.skipUnless(browser_binary(), "Chromium is needed to render the search route")
    def test_empty_search_route_explains_an_unscanned_pr(self):
        with make_server(self.catalog, 0) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                route = f"http://127.0.0.1:{server.server_port}/?lang=ru#/problems?" + urlencode({"q": PR})
                rendered = subprocess.run([
                    browser_binary(), "--headless", "--disable-gpu", "--disable-background-networking", "--no-sandbox",
                    "--no-first-run", f"--user-data-dir={self.workspace / 'browser'}", "--virtual-time-budget=3000",
                    "--dump-dom", route,
                ], capture_output=True, timeout=25, check=True)
                self.assertIn("Для этого PR пока нет сохранённого внешнего поиска.", rendered.stdout.decode("utf-8"))
            finally:
                server.shutdown()
                thread.join()
