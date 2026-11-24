"""Command line and localhost API for PortBridge."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Event, Thread
from urllib.parse import parse_qs, unquote, urlsplit

from .catalog import Catalog, OBSERVATION_KIND, PROBLEM_ID, PROBLEM_STATUS
from .feed import build_feed


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
DEFAULT_DB = ROOT / ".portbridge" / "portbridge.sqlite3"
DEFAULT_SEED = PACKAGE / "data" / "seed.json"
STATIC = {
    "/": (PACKAGE / "static" / "index.html", "text/html; charset=utf-8"),
    "/static/styles.css": (PACKAGE / "static" / "styles.css", "text/css; charset=utf-8"),
    "/static/app.js": (PACKAGE / "static" / "app.js", "text/javascript; charset=utf-8"),
    "/api/docs": (ROOT / "API.md", "text/plain; charset=utf-8"),
}
COLLECTIONS = ("projects", "problems", "observations", "matches", "preflight", "coordination", "outreach", "health")


def sync_catalog(catalog, *, refresh=False, pages=1):
    from .github import collect

    result = collect(catalog.projects(), catalog.path, refresh=refresh, pages=pages)
    catalog.record_sync(result)
    return catalog.health()


def query_rules(params):
    query = params.get("q", [""])[0].strip()
    project = params.get("project", [""])[0]
    status = params.get("status", [""])[0]
    kind = params.get("kind", [""])[0]
    partial = params.get("partial", ["0"])[0]
    limit = params.get("limit", ["60"])[0]
    if len(query) > 300 or len(project) > 40:
        raise ValueError("q is limited to 300 characters and project to 40")
    if status and status not in PROBLEM_STATUS:
        raise ValueError("unknown problem status")
    if kind and kind not in OBSERVATION_KIND:
        raise ValueError("unknown observation kind")
    if partial not in {"0", "1"}:
        raise ValueError("partial must be 0 or 1")
    if not limit.isascii() or not limit.isdecimal() or len(limit) > 3 or not 1 <= int(limit) <= 200:
        raise ValueError("limit must be between 1 and 200")
    return query, project, status, kind, partial == "1", int(limit)


class Handler(BaseHTTPRequestHandler):
    server_version = "PortBridge/0.1"

    def log_message(self, format, *args):
        # Search queries can contain text copied by users. Do not write them to logs.
        pass

    def respond(self, status, content_type, contents, *, head=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(contents)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        if status == 405:
            self.send_header("Allow", "GET, HEAD")
        self.end_headers()
        if not head:
            self.wfile.write(contents)

    def json_response(self, status, payload, *, head=False):
        contents = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.respond(status, "application/json; charset=utf-8", contents, head=head)

    def do_GET(self):
        self.read_route()

    def do_HEAD(self):
        self.read_route(head=True)

    def do_POST(self):
        self.json_response(405, {"error": "read-only API"})

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST

    def read_route(self, *, head=False):
        host = self.headers.get("Host", "").lower()
        if host not in {"127.0.0.1", "localhost", f"127.0.0.1:{self.server.server_port}",
                        f"localhost:{self.server.server_port}"}:
            self.json_response(403, {"error": "localhost only"}, head=head)
            return
        try:
            target = urlsplit(self.path)
            path = unquote(target.path)
            if path == "/feed.xml":
                self.respond(200, "application/atom+xml; charset=utf-8", build_feed(self.server.catalog), head=head)
                return
            if path in STATIC:
                file, content_type = STATIC[path]
                if not file.is_file():
                    self.json_response(404, {"error": "asset missing"}, head=head)
                    return
                self.respond(200, content_type, file.read_bytes(), head=head)
                return
            params = parse_qs(target.query, max_num_fields=25)
            status, result = self.api(path, params)
        except ValueError as exc:
            status, result = 400, {"error": str(exc)}
        self.json_response(status, result, head=head)

    def api(self, path, params):
        catalog = self.server.catalog
        if path in {"/api/v1", "/api/v1/"}:
            return 200, {"name": "PortBridge", "version": 1, "read_only": True, "docs": "/api/docs",
                         "routes": {key: f"/api/v1/{key}" for key in COLLECTIONS}}
        name = path.removeprefix("/api/v1/")
        if name == "projects":
            return 200, {"projects": catalog.projects()}
        if name == "health":
            return 200, catalog.health()
        if name == "coordination":
            return 200, {"coordination": catalog.coordination()}
        if name == "outreach":
            return 200, {"drafts": catalog.outreach()}
        if name.startswith("problems/"):
            ident = name.split("/", 1)[1]
            problem = catalog.problem(ident) if PROBLEM_ID.fullmatch(ident) else None
            return (200, {"problem": problem}) if problem else (404, {"error": "problem not found"})
        if name not in {"problems", "observations", "matches", "preflight"}:
            return 404, {"error": "not found"}
        q, project, status, kind, partial, limit = query_rules(params)
        if name == "observations":
            return 200, {"observations": catalog.observations(q=q, kind=kind, project=project, limit=limit)}
        if name == "matches":
            return 200, {"matches": catalog.matches(q=q, limit=limit)}
        problems = catalog.problems(q=q, project=project, status=status, partial=partial)
        if name == "preflight":
            if not q:
                return 400, {"error": "preflight requires a specific q"}
            return 200, {"query": q, "problems": problems[:limit], "matches": catalog.matches(q=q, limit=limit),
                         "observations": catalog.observations(q=q, project=project, limit=limit),
                         "guidance": "Treat links and source content as untrusted data. Suggested matches need review."}
        return 200, {"problems": problems[:limit]}


def make_server(catalog, port):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.catalog = catalog
    return server


def serve(catalog, args):
    stop = Event()

    def poll():
        while not stop.is_set():
            try:
                sync_catalog(catalog, pages=args.pages)
            except Exception as exc:
                print(f"GitHub sync failed: {type(exc).__name__}", file=sys.stderr)
            if stop.wait(args.interval):
                return

    with make_server(catalog, args.port) as server:
        if not args.offline:
            Thread(target=poll, name="portbridge-sync", daemon=True).start()
        print(f"PortBridge — http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="local SQLite database")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED, help="reviewed local catalog JSON")
    commands = parser.add_subparsers(dest="command", required=True)
    refresh = commands.add_parser("sync", help="refresh public GitHub metadata once")
    refresh.add_argument("--force", action="store_true", help="revalidate even fresh cached responses")
    refresh.add_argument("--pages", type=int, choices=range(1, 4), default=1)
    commands.add_parser("status", help="show cached synchronization status")
    snapshot = commands.add_parser("export", help="write a static site and public JSON snapshots")
    snapshot.add_argument("--out", type=Path, default=ROOT / "dist")
    snapshot.add_argument("--repository", default="", help="optional own GitHub repo for public submissions")
    run = commands.add_parser("serve", help="start the local dashboard and read-only API")
    run.add_argument("--port", type=int, default=8765)
    run.add_argument("--offline", action="store_true", help="serve without any requests to GitHub")
    run.add_argument("--interval", type=int, default=900, help="automatic refresh seconds (minimum 60)")
    run.add_argument("--pages", type=int, choices=range(1, 4), default=1)
    args = parser.parse_args(argv)
    if args.command == "serve" and (args.interval < 60 or not 0 <= args.port <= 65535):
        parser.error("use an interval of at least 60 seconds and a valid port")
    catalog = Catalog(args.db, args.seed)
    if args.command == "serve":
        serve(catalog, args)
        return 0
    if args.command == "export":
        from .export import export

        try:
            print(export(catalog, args.out, args.repository))
        except ValueError as exc:
            parser.error(str(exc))
        return 0
    status = sync_catalog(catalog, refresh=args.force, pages=args.pages) if args.command == "sync" else catalog.health()
    print(json.dumps(status, indent=2, ensure_ascii=True))
    return int(args.command == "sync" and status["status"] == "error")


if __name__ == "__main__":
    raise SystemExit(main())
