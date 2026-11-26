"""Bounded public discussion, review and patch metadata for reviewed source links."""

from contextlib import closing
from hashlib import sha256
import json
import re
import sqlite3
import time
from urllib.parse import urlencode, urlsplit

from .github import API, WORK_URL, Unavailable, _Sync, _login, _number, _object, _text, _utc
from .matching import current_repository
from .source_health import source_time


MAX_SOURCES = 3
PAGE_SIZE = 12
CONTEXT_TTL = 3600


def entries(raw, kind, source):
    if not isinstance(raw, list) or len(raw) > PAGE_SIZE or any(not isinstance(row, dict) for row in raw):
        raise Unavailable("Invalid GitHub context page", reason="invalid_payload")
    if kind == "files":
        items = []
        for row in raw:
            name = _text(row.get("filename"), 250)
            patch = row.get("patch")
            if name and not re.search(r"(?i)(?:github_pat_|gh[pousr]_)", name):
                items.append({"path": name, "status": _text(row.get("status"), 30),
                              "additions": _number(row.get("additions")) or 0,
                              "deletions": _number(row.get("deletions")) or 0,
                              "patch_prefix_sha256": (sha256(patch[:4096].encode()).hexdigest()
                                                      if isinstance(patch, str) else None)})
        return items
    items = {}
    for row in raw:
        ident = _number(row.get("id"))
        at = row.get("submitted_at" if kind == "reviews" else "updated_at")
        if not ident or not source_time(at):
            continue
        actor = _object(row.get("user"))
        fragment = "pullrequestreview" if kind == "reviews" else "issuecomment"
        items[ident] = {"id": f"github:{kind}:{ident}", "url": f"{source}#{fragment}-{ident}",
                        "author": _login(actor), "github_user_id": _number(actor.get("id")), "event_at": at,
                        "evidence_kind": "public_review" if kind == "reviews" else "public_discussion",
                        "state": _text(row.get("state"), 30) or None}
    return list(items.values())


def refresh_context(catalog, projects, references):
    known = {current_repository(p["repo"]).casefold()
             for p in projects if p.get("sync_status") != "unavailable"}
    targets = {}
    for source in references:
        if not isinstance(source, str) or not WORK_URL.fullmatch(source):
            continue
        owner, repo, route, number = urlsplit(source).path.strip("/").split("/")
        name = current_repository(f"{owner}/{repo}")
        if name.casefold() in known:
            targets[f"https://github.com/{name}/{route}/{number}"] = (name, route, number)
    if not targets:
        return
    with closing(sqlite3.connect(catalog.path, timeout=8)) as db:
        saved = {url: (at, json.loads(payload)) for url, at, payload in db.execute(
            "SELECT url, attempted_at, payload FROM source_context")}
        now = time.time()
        pending = [url for url in targets if url not in saved or now - saved[url][0] >= CONTEXT_TTL]
        if not pending:
            return
        sync = _Sync(db, False, time_budget=24)
        for source in sorted(pending, key=lambda url: (saved.get(url, (0,))[0], url))[:MAX_SOURCES]:
            name, route, number = targets[source]
            endpoints = {"comments": f"issues/{number}/comments"}
            if route == "pull":
                endpoints.update(reviews=f"pulls/{number}/reviews", files=f"pulls/{number}/files")
            previous = saved.get(source, (0, {}))[1]
            channels = {}
            actual_attempt = False
            for kind, endpoint in endpoints.items():
                old = previous.get(kind, {})
                params = {"per_page": PAGE_SIZE}
                if kind == "comments":
                    params.update(sort="updated", direction="desc")
                try:
                    sync._require_public(name)
                    sync.require_reference_feed(name, "pr" if route == "pull" else "issue")
                    raw, headers = sync._request(f"{API}/repos/{name}/{endpoint}?{urlencode(params)}", "core", None)
                    observed = entries(raw, kind, source)
                    history = {item["id"]: item for item in old.get("entries", []) if "id" in item}
                    if kind != "files":
                        history.update((item["id"], item) for item in observed)
                        observed = sorted(history.values(), key=lambda item: (item["event_at"], item["id"]),
                                          reverse=True)[:3 * PAGE_SIZE]
                    channels[kind] = {"entries": observed, "last_success": _utc(now), "last_attempt": _utc(now),
                                      "status": "ok", "more_available": 'rel="next"' in headers.get("Link", "")}
                    actual_attempt = True
                except Unavailable as error:
                    channels[kind] = {**old, "status": "stale" if old.get("last_success") else "unavailable",
                                      "last_attempt": _utc(now) if error.attempted else old.get("last_attempt"),
                                      "error": error.reason}
                    actual_attempt |= error.attempted
            last_attempt = now if actual_attempt else saved.get(source, (0,))[0]
            with db:
                db.execute("""INSERT INTO source_context VALUES (?, ?, ?)
                           ON CONFLICT(url) DO UPDATE SET attempted_at=excluded.attempted_at, payload=excluded.payload
                           WHERE excluded.attempted_at >= source_context.attempted_at""",
                           (source, last_attempt, json.dumps(channels, ensure_ascii=True)))
