"""Bounded, public actor evidence beyond the standard issue and PR index."""
from collections import defaultdict
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlsplit

from .catalog import public_url
from .github import API, NOT_MODIFIED, REPO, Unavailable, _Sync, _login, _number
from .identity import contributor_id, stable_id
from .matching import canonical_url, repository_identity
from .radar_store import epoch, timestamp

DATA = Path(__file__).parent / "data"
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
SUBJECT = re.compile(r"/[^/]+/[^/]+/(?:issues|pull|discussions)/[1-9][0-9]*")
TECH = {
    "shaders": r"\b(?:shader|spir-?v|dxil|rdna[23]?|v_[a-z0-9_]+|subgroup|wave(?:32|64))",
    "graphics": r"\b(?:vulkan|render|raster|agc|d3d12|texture|graphics|descriptor)",
    "memory": r"\b(?:memory|vram|heap|allocat|cache|paging|decommit|buffer)",
    "performance": r"\b(?:perf(?:ormance)?|latency|throughput|optimi[sz]|microbench|profil)",
    "cpu": r"\b(?:cpu|x86|arm64|jit|interpreter|thread|scheduler)",
    "api": r"\b(?:api|abi|vulkan|d3d12|dxgi|win32|posix|syscall|agc)",
    "testing": r"\b(?:test|fixture|regression|reproduc|oracle|validation|benchmark)",
    "infrastructure": r"\b(?:workflow|github actions|build system|ci|indexer|tracker|test lab)",
}
TECH = {name: re.compile(pattern, re.I) for name, pattern in TECH.items()}
SCHEMA = """
CREATE TABLE IF NOT EXISTS community_facts (
    id TEXT PRIMARY KEY, scope TEXT NOT NULL, repo TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS community_fact_scope ON community_facts(scope);
CREATE TABLE IF NOT EXISTS community_scopes (
    name TEXT PRIMARY KEY, repo TEXT NOT NULL, attempted INTEGER NOT NULL,
    status TEXT NOT NULL, success INTEGER, etag TEXT
);
"""
MAX_SCOPES = 8
PAGE = 20
BODY_LIMIT = 10000

def repository(url):
    if not public_url(url):
        return ""
    return repository_identity("/".join(urlsplit(url).path.strip("/").split("/")[:2])).casefold()


def evidence_key(url):
    parsed = urlsplit(url)
    return canonical_url(url) + ("#" + parsed.fragment.casefold() if parsed.fragment else "")


def topics(*texts):
    text = " ".join(s for s in texts if isinstance(s, str))[:BODY_LIMIT]
    return [name for name, pattern in TECH.items() if pattern.search(text)]


def actor(user):
    user = user if isinstance(user, dict) else {}
    login = _login(user)
    if user.get("type") in {"Bot", "Organization", "Mannequin"} or not LOGIN.fullmatch(login or ""):
        return None
    return {"login": login, "user_id": _number(user.get("id")) or None}


def fact(subject, source, participant, at, role, basis, specialties=(), **extra):
    if not participant or not epoch(at) or not repository(subject) or repository(subject) != repository(source):
        return None
    return {"id": stable_id("community-fact", evidence_key(source), role),
            "source": source, "subject": subject, "repo": repository(subject),
            "actor": participant, "at": at, "role": role, "basis": basis,
            "specialties": sorted(set(specialties)), **extra}


def thread_entry(entry, scope, parent=None):
    if not isinstance(entry, dict) or entry.get("minimized") is True:
        return None
    source = entry.get("html_url")
    if not public_url(source) or not SUBJECT.fullmatch(urlsplit(source).path):
        return None
    subject = source.split("#")[0]
    if repository(subject) != scope or parent and evidence_key(parent) != evidence_key(subject):
        return None
    body = entry.get("body")
    body = body[:BODY_LIMIT] if isinstance(body, str) else ""
    domain = topics(body)
    participant = actor(entry.get("user"))
    date = entry.get("submitted_at") or entry.get("created_at")
    fragment = urlsplit(source).fragment
    ident = _number(entry.get("id"))
    if not ident:
        return None
    if entry.get("state") in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}:
        if fragment != f"pullrequestreview-{ident}" or entry["state"] == "COMMENTED" and not domain:
            return None
        return fact(subject, source, participant, date, "reviewer", "Submitted GitHub review", domain,
                    review_state=entry["state"].lower(), revision=entry.get("commit_id"))
    if fragment != f"issuecomment-{ident}" or len(body.strip()) < 45 or not domain:
        return None
    # A report text may describe a different person's equipment. Structured
    # Lab reports and individually reviewed public receipts provide that fact.
    return fact(subject, source, participant, date, "technical_discussion", "Technical GitHub thread comment", domain)


def captured(catalog):
    with catalog.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='community_facts'").fetchone():
            return [], {}
        states = {row["name"]: dict(row) for row in db.execute("SELECT * FROM community_scopes")}
        facts = []
        for row in db.execute("SELECT scope,payload FROM community_facts"):
            value = json.loads(row["payload"])
            if row["scope"] == "discovery":
                facts.append(value)
                continue
            check = states.get(row["scope"], {})
            facts.append(value | {"source_state": check.get("status", "unknown"),
                                  "checked_at": timestamp(check["success"]) if check.get("success") else None})
        return facts, states


def remember_discovery(db, origin, items, checked, policy):
    for item in items:
        who = item.get("author")
        if (not who or who["login"].casefold() in policy["hidden_logins"]
                or contributor_id(who["login"], who["user_id"]) in policy["hidden_ids"]):
            continue
        source = item["source"]
        row = fact(source, source, who, item.get("observed_at"), "researcher",
                   "Author of an external Discovery source", topics(item.get("title")),
                   kind="discovery", discovery_for=evidence_key(origin), checked_at=timestamp(checked),
                   title=item.get("title", ""))
        if row:
            db.execute("REPLACE INTO community_facts VALUES(?, 'discovery', ?, ?)",
                       (row["id"], row["repo"], json.dumps(row)))


def refresh(catalog, *, limit=MAX_SCOPES, now=None):
    if type(limit) is not int or not 1 <= limit <= MAX_SCOPES:
        raise ValueError(f"Use 1 to {MAX_SCOPES} People source checks")
    now = int(time.time() if now is None else now)
    with catalog.read_view() as view:
        projects = view.projects()
        changes = defaultdict(list)
        for row in view.observations(kind="pr", limit=None):
            if row["status"] in {"open", "merged", "closed"} and epoch(row["updated_at"]) >= now - 14 * 86400:
                changes[row["project"]].append(row)
    scopes = []
    for project in projects:
        repo = project["repo"]
        if not REPO.fullmatch(repo):
            continue
        scopes.append((f"comments:{repository_identity(repo).casefold()}", repo, None))
        scopes.append((f"repository:{repository_identity(repo).casefold()}", repo, None))
        for row in changes[project["slug"]][:2]:
            url = row["url"]
            if SUBJECT.fullmatch(urlsplit(url).path) and "/pull/" in url and not urlsplit(url).fragment:
                scopes.append((f"review:{evidence_key(url)}", repo, url))
    with catalog.connect() as db:
        db.executescript(SCHEMA)
        policy = json.loads((DATA / "people_policy.json").read_bytes())
        hidden_ids, hidden_logins = set(policy["hidden_ids"]), set(policy["hidden_logins"])

        def visible(row):
            who = row["actor"]
            return (who["login"].casefold() not in hidden_logins
                    and contributor_id(who["login"], who["user_id"]) not in hidden_ids)

        if hidden_ids or hidden_logins:
            private_rows = [(row["id"],) for row in db.execute("SELECT id,payload FROM community_facts")
                            if not visible(json.loads(row["payload"]))]
            with db:
                db.executemany("DELETE FROM community_facts WHERE id=?", private_rows)
        saved = {row["name"]: dict(row) for row in db.execute("SELECT * FROM community_scopes")}
        # Public-only anonymous transport before reading contributor evidence.
        client = _Sync(db, False, projects, anonymous=True, time_budget=18)
        report = {"eligible_scopes": len(scopes), "checked": 0, "facts": 0, "errors": []}
        for name, repo, parent in sorted(scopes, key=lambda row: (saved.get(row[0], {}).get("attempted", 0),
                                                                 row[2] is not None, row[0]))[:limit]:
            previous = saved.get(name, {})
            if previous.get("attempted", 0) >= now - 900 or time.monotonic() >= client.deadline:
                break
            fetched = previous.get("success")
            etag = previous.get("etag")
            identity = repository_identity(repo).casefold()
            replace = False
            try:
                url = f"{API}/repos/{repo}"
                is_repository = name.startswith("repository:")
                if not is_repository:
                    endpoint = f"pulls/{urlsplit(parent).path.rsplit('/',1)[1]}/reviews" if parent else "issues/comments"
                    query = {"per_page": PAGE}
                    if not parent:
                        query.update(sort="updated", direction="desc")
                    url += f"/{endpoint}?{urlencode(query)}"
                result, headers = client._request(url, "core", etag)
                pending = []
                if result is not NOT_MODIFIED:
                    if is_repository and isinstance(result, dict) and result.get("private") is False:
                        source = result.get("html_url")
                        if repository(source) == identity:
                            pending = [row for row in (fact(source, source, actor(result.get("owner")), timestamp(now),
                                                            "repository_owner", "Public GitHub repository owner"),) if row]
                        replace = True
                    elif not is_repository and isinstance(result, list):
                        pending = [row for entry in result[:PAGE]
                                   if (row := thread_entry(entry, identity, parent))]
                        replace = bool(parent) and not headers.get("Link") and len(result) < PAGE
                    else:
                        raise Unavailable("Unexpected contributor evidence response", reason="invalid_payload")
                state = ("complete" if parent and replace or result is NOT_MODIFIED and previous.get("status") == "complete"
                         else "available")
                fetched = now
                etag = headers.get("ETag") or etag
            except Unavailable as error:
                state = error.reason
                pending = []
                report["errors"].append({"repo": repo, "scope": name, "reason": state})
            with db:
                if replace:
                    db.execute("DELETE FROM community_facts WHERE scope=?", (name,))
                db.execute("REPLACE INTO community_scopes VALUES(?,?,?,?,?,?)",
                           (name, identity, now, state, fetched, etag))
                db.executemany("REPLACE INTO community_facts VALUES(?,?,?,?)",
                               [(row["id"], name, row["repo"], json.dumps(row)) for row in pending if visible(row)])
            report["checked"] += 1
            report["facts"] += len(pending)
            if state in {"rate_limit", "secondary_limit", "budget"}:
                break
        return report
