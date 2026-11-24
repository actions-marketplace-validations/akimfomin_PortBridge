"""Read-only GitHub metadata sync with a conditional-request SQLite cache."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


API = "https://api.github.com"
REPO = re.compile(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+")
SHA = re.compile(r"[0-9a-fA-F]{40,64}")
PAGE_SIZE = 20
CACHE_TTL = 900
MAX_RESPONSE = 4 * 1024 * 1024
NOT_MODIFIED = object()


class NoRedirect(HTTPRedirectHandler):
    """A repository move must not send a token to a redirect destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Unavailable(Exception):
    """The page is temporarily unavailable or cannot be read."""


def _text(value, limit=300):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _object(value):
    return value if isinstance(value, dict) else {}


def _array(value):
    return value if isinstance(value, list) else []


def _login(value):
    return _text(_object(value).get("login"), 100)


def _sha(value):
    return value.lower() if isinstance(value, str) and SHA.fullmatch(value) else ""


def _etag(value):
    if isinstance(value, str) and len(value) <= 240 and all(32 <= ord(char) <= 126 for char in value):
        return value or None
    return None


def _utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds") if value else None


def _number(value):
    return value if type(value) is int and value > 0 else None


def _project(entry):
    repo = entry.get("repo") or entry.get("repository") or entry.get("repo_full_name")
    if not isinstance(repo, str) or not REPO.fullmatch(repo) or repo.rsplit("/", 1)[1] in (".", ".."):
        raise ValueError("a GitHub project must specify a repository as owner/name")
    slug = entry.get("slug") or entry.get("id") or repo.lower()
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError("a GitHub project must specify a non-empty string slug")
    return {**entry, "slug": slug, "repo": repo}


def _item(entry, kind, project):
    repo = project["repo"]
    metadata = {"evidence_kind": "reported", "github_endpoint": kind}
    author = _login(entry.get("user"))
    status = _text(entry.get("state"), 40) or "unknown"
    title = _text(entry.get("title"))
    updated = _text(entry.get("updated_at"), 40)
    if kind == "commit":
        ident = _sha(entry.get("sha"))
        commit = _object(entry.get("commit"))
        git_author = _object(commit.get("author"))
        git_committer = _object(commit.get("committer"))
        author = _login(entry.get("author")) or _text(git_author.get("name"), 100)
        message = commit.get("message")
        if isinstance(message, str):
            title = _text(message.partition("\n")[0])
        updated = _text(git_committer.get("date") or git_author.get("date"), 40)
        status = "recorded"
        endpoint = "commit"
        metadata["sha"] = ident
    elif kind == "test":
        ident = _number(entry.get("id"))
        endpoint = "actions/runs"
        conclusion = _text(entry.get("conclusion"), 40)
        status = conclusion or _text(entry.get("status"), 40) or "unknown"
        author = _login(entry.get("actor"))
        title = _text(entry.get("name")) or _text(entry.get("display_title"))
        metadata.update({
            "evidence_kind": "automated",
            "scope": "workflow_run",
            "workflow": _text(entry.get("name"), 120),
            "run_status": _text(entry.get("status"), 40),
            "conclusion": conclusion or None,
            "head_sha": _sha(entry.get("head_sha")),
            "head_branch": _text(entry.get("head_branch"), 120),
            "event": _text(entry.get("event"), 40),
            "pull_requests": [
                pr["number"] for pr in _array(entry.get("pull_requests"))[:20]
                if isinstance(pr, dict) and _number(pr.get("number"))
            ],
        })
    else:
        ident = _number(entry.get("number"))
        endpoint = "issues" if kind == "issue" else "pull"
        labels = [
            _text(_object(label).get("name"), 80)
            for label in _array(entry.get("labels"))[:30]
        ]
        metadata.update({"number": ident, "labels": [label for label in labels if label]})
        if kind == "pr":
            merged_at = _text(entry.get("merged_at"), 40)
            if merged_at:
                status = "merged"
            metadata.update({
                "merged_at": merged_at or None,
                "draft": entry.get("draft") is True,
                "head_sha": _sha(_object(entry.get("head")).get("sha")),
                "base_branch": _text(_object(entry.get("base")).get("ref"), 120),
            })
        else:
            metadata["state_reason"] = _text(entry.get("state_reason"), 40) or None
    if not ident:
        return None
    metadata["author"] = author
    return {
        "project": project["slug"], "kind": kind, "source_id": str(ident),
        "title": title or f"{kind} {ident}", "url": f"https://github.com/{repo}/{endpoint}/{ident}",
        "status": status, "updated_at": updated, "metadata": metadata,
    }


def _query(project, kind, page):
    params = {"per_page": PAGE_SIZE, "page": page}
    repo = project["repo"]
    if kind == "issue":
        params.update(q=f"repo:{repo} is:issue", sort="updated", order="desc")
        return f"{API}/search/issues?{urlencode(params)}", "search"
    endpoint = {"pr": "pulls", "commit": "commits", "test": "actions/runs"}[kind]
    if kind == "pr":
        params.update(state="all", sort="updated", direction="desc")
    return f"{API}/repos/{repo}/{endpoint}?{urlencode(params)}", "core"


class _Sync:
    def __init__(self, db, refresh):
        self.db = db
        self.refresh = refresh
        self.token = os.environ.get("PORTBRIDGE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
        self.context = "authenticated" if self.token else "anonymous"
        self.opener = build_opener(NoRedirect())
        self.deadline = time.monotonic() + 45
        self.public_checks = {}
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS github_cache (
                url TEXT PRIMARY KEY,
                etag TEXT,
                fetched_at REAL NOT NULL,
                items TEXT NOT NULL,
                has_next INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS github_rate_limit (
                context TEXT NOT NULL,
                resource TEXT NOT NULL,
                resume_at REAL NOT NULL,
                PRIMARY KEY (context, resource)
            );
        """)

    def _pause(self, resource, resume_at):
        with self.db:
            self.db.execute("""
                INSERT INTO github_rate_limit VALUES (?, ?, ?)
                ON CONFLICT(context, resource) DO UPDATE SET resume_at = max(resume_at, excluded.resume_at)
            """, (self.context, resource, resume_at))

    def _rate_headers(self, resource, headers, status):
        now = time.time()
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset", "")
        if remaining == "0":
            self._pause(resource, float(reset) if reset.isdigit() else now + 60)
        retry = headers.get("Retry-After")
        if status in (403, 429, 503) and retry:
            try:
                resume_at = now + int(retry) if retry.isdigit() else parsedate_to_datetime(retry).timestamp()
            except (ValueError, TypeError, OverflowError):
                resume_at = now + 60
            self._pause(resource, max(resume_at, now + 1))
        elif status == 429:
            self._pause(resource, now + 60)

    def _request(self, url, resource, etag):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise ValueError("GitHub sync permits only https://api.github.com")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PortBridge/0.1 (read-only repository metadata)",
        }
        if validator := _etag(etag):
            headers["If-None-Match"] = validator
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for attempt in range(2):
            limit = self.db.execute("SELECT resume_at FROM github_rate_limit WHERE context=? AND resource=?",
                                    (self.context, resource)).fetchone()
            if limit and limit[0] > time.time():
                raise Unavailable(f"GitHub rate limit, retry after {_utc(limit[0])}")
            left = self.deadline - time.monotonic()
            if left <= 0:
                raise Unavailable("GitHub request time budget exhausted")
            try:
                request = Request(url, headers=headers, method="GET")
                with self.opener.open(request, timeout=min(8.0, left)) as response:
                    self._rate_headers(resource, response.headers, response.status)
                    data = response.read(MAX_RESPONSE + 1)
                    if len(data) > MAX_RESPONSE:
                        raise Unavailable("GitHub metadata exceeds page size budget")
                    return json.loads(data), response.headers
            except HTTPError as e:
                with e:
                    self._rate_headers(resource, e.headers, e.code)
                    if e.code == 304:
                        return NOT_MODIFIED, e.headers
                    failure = f"GitHub HTTP {e.code}"
                    retryable = e.code in (500, 502, 503, 504) and not e.headers.get("Retry-After")
                    detail = b""
                    if e.code == 403:
                        try:
                            detail = e.read(4096).lower()
                        except (OSError, HTTPException):
                            pass
                    if b"rate limit" in detail:
                        reset = self.db.execute(
                            "SELECT resume_at FROM github_rate_limit WHERE context=? AND resource=?",
                            (self.context, resource),
                        ).fetchone()
                        if not reset or reset[0] <= time.time():
                            self._pause(resource, time.time() + 60)
                        failure += " (rate limited)"
            except (TimeoutError, URLError, OSError, HTTPException):
                failure, retryable = "GitHub connection failed or timed out", True
            except (ValueError, UnicodeError) as e:
                raise Unavailable("GitHub returned invalid JSON metadata") from e
            if attempt or not retryable:
                raise Unavailable(failure)
            time.sleep(0.25)
        raise Unavailable("GitHub request failed")

    def _require_public(self, repo):
        # Anonymous requests already cannot read private repositories. For a token
        # that can see private repositories, check visibility before listing metadata.
        if not self.token:
            return
        if repo not in self.public_checks:
            try:
                data, _ = self._request(f"{API}/repos/{repo}", "core", None)
                if _object(data).get("private") is not False or _object(data).get("visibility", "public") != "public":
                    raise Unavailable("repository is not public")
            except Unavailable as e:
                self.public_checks[repo] = str(e)
            else:
                self.public_checks[repo] = None
        if self.public_checks[repo]:
            raise Unavailable(self.public_checks[repo])

    def page(self, project, kind, number):
        url, resource = _query(project, kind, number)
        row = self.db.execute("SELECT etag, fetched_at, items, has_next FROM github_cache WHERE url=?",
                              (url,)).fetchone()
        cached = None
        if row:
            etag, fetched_at, encoded, has_next = row
            try:
                cached = json.loads(encoded)
                if not isinstance(cached, list):
                    cached = None
            except (TypeError, ValueError):
                pass
            if fetched_at + CACHE_TTL > time.time() and cached is not None and not self.refresh:
                return cached, has_next, "cached", fetched_at, None
        try:
            self._require_public(project["repo"])
            raw, headers = self._request(url, resource, row[0] if cached is not None else None)
            if raw is NOT_MODIFIED:
                if cached is None:
                    raise Unavailable("GitHub returned 304 without a cached page")
                items = cached
                has_next = row[3]
                etag = _etag(headers.get("ETag")) or row[0]
            else:
                if kind == "test":
                    records = _object(raw).get("workflow_runs")
                elif kind == "issue":
                    if _object(raw).get("incomplete_results") is True:
                        raise Unavailable("GitHub issue search returned incomplete results")
                    records = _object(raw).get("items")
                else:
                    records = raw
                if not isinstance(records, list):
                    raise Unavailable("GitHub returned unexpected metadata")
                items = [
                    normalized for record in records[:PAGE_SIZE]
                    if isinstance(record, dict) and (kind != "issue" or "pull_request" not in record)
                    and (normalized := _item(record, kind, project)) is not None
                ]
                # Follow pagination numerically and ignore the untrusted URLs inside Link.
                has_next = 'rel="next"' in headers.get("Link", "")
                etag = _etag(headers.get("ETag"))
            fetched_at = time.time()
            if raw is not NOT_MODIFIED:
                for item in items:
                    item["fetched_at"] = _utc(fetched_at)
            with self.db:
                self.db.execute("""
                    INSERT INTO github_cache VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET etag=excluded.etag, fetched_at=excluded.fetched_at,
                        items=excluded.items, has_next=excluded.has_next
                """, (url, etag, fetched_at, json.dumps(items, ensure_ascii=False), has_next))
            return items, has_next, "live", fetched_at, None
        except Unavailable as e:
            if cached is not None:
                return cached, row[3], "stale", row[1], str(e)
            return [], False, "error", None, str(e)


def _status(states):
    states = set(states)
    if states <= {"live", "cached"}:
        return "ok"
    if states == {"stale"}:
        return "stale"
    if states == {"error"}:
        return "error"
    return "partial"


def collect(projects: list[dict], db_path: Path, *, refresh=False, pages=1) -> dict:
    """Collect recent issue, PR, commit and workflow-run metadata.

    Input projects use slug (or id) and repo (or repository/repo_full_name) as owner/name.
    The response contains normalized items, human-readable warnings, and augmented projects
    with sync_status, last_success (latest known successful page time in UTC), and per-kind sources.
    Existing cached pages remain available if an endpoint fails. An item's fetched_at is the
    UTC time when its response body arrived, retained across stale reads and HTTP 304 responses.
    The caller owns catalog storage.
    """
    if type(pages) is not int or not 1 <= pages <= 5:
        raise ValueError("pages must be an integer from 1 to 5")
    checked = [_project(entry) for entry in projects]
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path, timeout=8)
    result = {"items": [], "warnings": [], "projects": []}
    try:
        sync = _Sync(db, refresh)
        for project in checked:
            source_data = {}
            results = []
            seen = set()
            for kind in ("issue", "pr", "commit", "test"):
                states, times = [], []
                count = 0
                for index in range(1, pages + 1):
                    items, has_next, state, stamp, warning = sync.page(project, kind, index)
                    states.append(state)
                    if stamp is not None:
                        times.append(stamp)
                    for item in items:
                        key = (kind, item["source_id"])
                        if key not in seen:
                            seen.add(key)
                            # Multiple project slugs may refer to the same API repository.
                            results.append({
                                **item, "project": project["slug"],
                                "fetched_at": item.get("fetched_at") or _utc(stamp),
                            })
                            count += 1
                    if warning:
                        fallback = " (using stale cache)" if state == "stale" else ""
                        result["warnings"].append(f"{project['repo']} {kind} page {index}: {warning}{fallback}")
                    if not has_next:
                        break
                source_data[kind] = {
                    "sync_status": _status(states),
                    "last_success": _utc(max(times, default=None)),
                    "item_count": count,
                    "pages_checked": len(states),
                    "more_available": bool(has_next),
                }
            flags = {source["sync_status"] for source in source_data.values()}
            result["projects"].append({
                **project,
                "sync_status": next(iter(flags)) if len(flags) == 1 else "partial",
                "last_success": max((x["last_success"] for x in source_data.values() if x["last_success"]),
                                    default=None),
                "sources": source_data,
            })
            result["items"].extend(results)
    finally:
        db.close()
    return result
