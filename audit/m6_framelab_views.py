"""Read the two public FrameLab reports and verify their public export in an isolated directory."""
import argparse
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portbridge.__main__ import DEFAULT_SEED
from portbridge.catalog import Catalog
from portbridge.export import export
from portbridge.identity import lab_report_id
from portbridge.lab import FRAMELAB_HANDOFF, FRAMELAB_RESULTS, TASKS
from portbridge.lab_reports import FRAMELAB_TASK, TABLE, read_report_states, refresh_reports, review_scope, save_scan, scope
from portbridge.mcp import PortBridgeMCP
from portbridge.release_gate import audit


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.urls.add(dict(attrs).get("href"))


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def verify_browser(binary, site, routes, profile_dir):
    passed = []
    with ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(site))) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for name, (route, expected) in routes.items():
                args = [binary, "--headless", "--disable-gpu", "--disable-background-networking", "--no-first-run",
                        "--user-data-dir=" + str(profile_dir), "--virtual-time-budget=7000", "--dump-dom",
                        f"http://127.0.0.1:{server.server_port}/?lang=en#/" + route]
                proc = subprocess.run(args, capture_output=True, check=True, timeout=45)
                links = Links()
                links.feed(proc.stdout.decode("utf-8"))
                if missing := expected - links.urls:
                    raise ValueError(f"Missing rendered evidence links in {name}: {sorted(missing)}")
                passed.append(name)
        finally:
            server.shutdown()
            worker.join()
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", help="Path to a Chromium executable for checking actual rendered links")
    parser.add_argument("--live", action="store_true", help="Refresh both public GitHub threads instead of replaying the captured receipts")
    args = parser.parse_args()
    task = next(t for t in TASKS if t["id"] == FRAMELAB_TASK)
    expected = {FRAMELAB_RESULTS + "#issuecomment-" + ref: FRAMELAB_RESULTS + "#issuecomment-" + approval
                for ref, approval in (("7147944059", "7160150401"), ("7153817545", "7160151831"))}
    ids = {lab_report_id(url) for url in expected}
    urls = set(expected) | set(expected.values())
    with TemporaryDirectory(prefix="portbridge-m6-framelab-") as tmp:
        root = Path(tmp)
        catalog = Catalog(root / "public.sqlite3", DEFAULT_SEED)
        for _ in range(2):
            if args.live:
                state = refresh_reports(catalog, [task])[FRAMELAB_TASK]
            else:
                captured = json.loads(Path(__file__).with_name("fixtures").joinpath("m6-framelab-receipts.json").read_bytes())
                with catalog.connect() as db:
                    db.execute(TABLE)
                    for url, receipt in captured.items():
                        key = scope(task, url)
                        for kind, record_scope in (("reviews", review_scope(key)), ("reports", key)):
                            if kind in receipt:
                                at = receipt["checked_at"]
                                save_scan(db, task, record_scope, at, state="fresh", checked=at,
                                          reports=receipt[kind], replace=True)
                state = read_report_states(catalog, [task])[FRAMELAB_TASK]
            if state["state"] != "fresh":
                raise ValueError("Both configured public threads must be readable")
            active = {r["url"]: r for r in state["reports"] if r.get("review", {}).get("decision") == "approve"}
            for url, approval in expected.items():
                if url not in active or active[url]["review"]["url"] != approval or active[url]["outcome"] != "pass":
                    raise ValueError("The public decision changed. Inspect the source before recording a result.")
            if len({r["url"] for r in state["reports"]}) != len(state["reports"]):
                raise ValueError("Duplicate report after import")
        site = export(catalog, root / "export")
        if failures := audit(site):
            raise ValueError(f"Release gate failed: {failures}")
        def read(name):
            return json.loads((site / "data" / (name + ".json")).read_bytes())
        search = PortBridgeMCP(catalog).run_tool({"name": "portbridge_preflight", "arguments": {"url": FRAMELAB_HANDOFF}})
        for view, rows in (("search", search["structuredContent"].get("radar_findings", [])),
                           ("radar", read("activity")["radar"]["findings"]), ("impact", read("impact")["stories"])):
            if sorted(r["id"] for r in rows if r["id"] in ids) != sorted(ids):
                raise ValueError(f"Missing or duplicated public review in {view}")
        task = next(t for t in read("lab")["tasks"] if t["id"] == FRAMELAB_TASK)
        tester = "github-user:71070620"
        owner = "github-user:71517730"
        profiles = {p["id"]: {e["source"] for e in p["evidence"]} for p in read("people")["profiles"]}
        if not (set(expected) <= profiles.get(tester, set()) and set(expected.values()) <= profiles.get(owner, set())
                and task["status"] == "completed"):
            raise ValueError("Missing attribution or incomplete Lab coverage")
        output = {"run": "live public import" if args.live else "captured public receipts in isolated export",
                  "imports": 2, "report_reviews": expected,
                  "reporter": tester, "reviewer": owner, "lab": task["status"], "report_ids": sorted(ids),
                  "views_verified": ["Search (MCP preflight)", "Radar", "Lab", "People", "Impact"],
                  "browser_routes_verified": []}
        routes = {"Search": ("problems?" + urlencode({"q": FRAMELAB_HANDOFF}), urls), "Radar": ("activity", urls),
                  "Lab": ("lab?task=" + FRAMELAB_TASK, urls), "People (tester)": ("people?profile=" + tester, set(expected)),
                  "People (owner)": ("people?profile=" + owner, set(expected.values())),
                  "Impact": ("impact?" + urlencode({"target": FRAMELAB_HANDOFF}), urls)}
        if args.browser:
            output["browser_routes_verified"] = verify_browser(args.browser, site, routes, root / "browser-profile")
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
