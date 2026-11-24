"""Local authenticated exchange for work notices and reviewable evidence."""

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from .catalog import EVIDENCE_KIND, EVIDENCE_OUTCOME, PROBLEM_ID


SCOPES = frozenset({"read", "contribute", "review"})
TOKEN = re.compile(r"pbx_[A-Za-z0-9_-]{43}")
REVISION = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
NUMBER = r"[1-9][0-9]{0,18}"
OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]{1,100}")
ISSUE_OR_PR = re.compile(rf"(?:issues|pull)/{NUMBER}")
ACTIONS = re.compile(rf"actions/runs/{NUMBER}(?:/(?:job|attempts)/{NUMBER})?")
COMMENT = re.compile(rf"(?:issuecomment-|discussion_r|pullrequestreview-){NUMBER}")
EXTERNAL_LINK = re.compile(r"(?i)(?:[a-z][a-z0-9+.-]*://|\bwww\.)")
PROPOSAL_KEYS = {"problem_id", "source_url", "revision", "platform", "evidence_kind", "outcome", "summary"}
MAX_SQL_INTEGER = (1 << 63) - 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS principals (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    scopes TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS revoked_principals (
    principal_id INTEGER PRIMARY KEY REFERENCES principals(id),
    revoked_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS work (
    id INTEGER PRIMARY KEY,
    actor_id INTEGER NOT NULL REFERENCES principals(id),
    problem_id TEXT NOT NULL,
    registered_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    UNIQUE(actor_id, problem_id)
);
CREATE INDEX IF NOT EXISTS work_by_expiry ON work(expires_at);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES principals(id),
    problem_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    revision TEXT NOT NULL,
    platform TEXT NOT NULL,
    evidence_kind TEXT NOT NULL,
    outcome TEXT NOT NULL,
    summary TEXT NOT NULL,
    submitted_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS results_by_problem ON results(problem_id);
CREATE INDEX IF NOT EXISTS results_by_author_problem ON results(author_id, problem_id);
CREATE TABLE IF NOT EXISTS decisions (
    result_id INTEGER PRIMARY KEY REFERENCES results(id),
    reviewer_id INTEGER NOT NULL REFERENCES principals(id),
    decision TEXT NOT NULL CHECK(decision IN ('accepted', 'rejected')),
    reason TEXT NOT NULL,
    reviewed_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS approved_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER NOT NULL UNIQUE REFERENCES results(id)
);
"""

RESULTS = """
SELECT r.id, r.problem_id, r.source_url, r.revision, r.platform, r.evidence_kind, r.outcome,
       r.summary, coalesce(d.decision, 'pending') AS status, a.name AS author, r.submitted_at,
       m.name AS reviewer, d.reviewed_at, d.reason, e.id AS event_id
FROM results r JOIN principals a ON r.author_id = a.id
LEFT JOIN decisions d ON d.result_id = r.id
LEFT JOIN principals m ON d.reviewer_id = m.id
LEFT JOIN approved_events e ON e.result_id = r.id
"""


class AuthError(Exception):
    """A bearer token is absent or invalid."""


class PermissionDenied(AuthError):
    """An authenticated principal lacks permission for the operation."""


class Conflict(Exception):
    """The requested change conflicts with an existing record."""


def _timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds") if value is not None else None


def _text(value, label, limit, *, optional=False):
    if (not isinstance(value, str) or len(value) > limit or (value and not value.isprintable()) or
            EXTERNAL_LINK.search(value)):
        raise ValueError(f"{label} must be single-line text of at most {limit} characters without links")
    if TOKEN.search(value):
        raise ValueError(f"{label} must not include an exchange bearer token")
    normalized = value.strip()
    if not normalized and not optional:
        raise ValueError(f"{label} is required")
    return normalized


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer between {low} and {high}")
    return value


def _source(value):
    if (not isinstance(value, str) or len(value) > 300 or not value.isascii() or
            any(not 33 <= ord(character) <= 126 for character in value)):
        raise ValueError("source_url must be a public GitHub issue, pull request, commit, or Actions permalink")
    parsed = urlsplit(value)
    parts = parsed.path.split("/", 3)
    if len(parts) != 4 or parts[0]:
        raise ValueError("source_url must be a public GitHub issue, pull request, commit, or Actions permalink")
    _, owner, repo, route = parts
    issue = ISSUE_OR_PR.fullmatch(route)
    commit = route.startswith("commit/") and REVISION.fullmatch(route[7:])
    if (parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or "?" in value or
            OWNER.fullmatch(owner) is None or REPOSITORY.fullmatch(repo) is None or repo in {".", ".."} or
            not (issue or commit or ACTIONS.fullmatch(route)) or
            ("#" in value and not (issue and COMMENT.fullmatch(parsed.fragment)))):
        raise ValueError("source_url must be a public GitHub issue, pull request, commit, or Actions permalink")
    return f"https://github.com/{owner}/{repo}/{route}" + (f"#{parsed.fragment}" if parsed.fragment else "")


def _result(row):
    result = dict(row)
    for field in ("submitted_at", "reviewed_at"):
        result[field] = _timestamp(result[field])
    return result


class Exchange:
    def __init__(self, path, *, problem_exists=None):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.problem_exists = problem_exists
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _problem(self, ident):
        if not isinstance(ident, str) or len(ident) > 64 or not PROBLEM_ID.fullmatch(ident):
            raise ValueError("problem_id must be a PortBridge PB identifier")
        if self.problem_exists is not None and not self.problem_exists(ident):
            raise ValueError("problem_id is absent from the catalog")
        return ident

    def create_principal(self, name, scopes):
        """Provision a local identity and return its bearer secret once."""
        name = _text(name, "name", 64)
        if (not isinstance(scopes, (list, tuple, set, frozenset)) or not scopes or
                any(not isinstance(scope, str) or scope not in SCOPES for scope in scopes)):
            raise ValueError("scopes must contain read, contribute, or review")
        scopes = sorted(set(scopes))
        token = f"pbx_{secrets.token_urlsafe(32)}"
        digest = sha256(token.encode("ascii")).hexdigest()
        try:
            with self._connect() as db:
                ident = db.execute("INSERT INTO principals(name, name_key, scopes, token_hash) VALUES (?, ?, ?, ?)",
                                   (name, name.casefold(), json.dumps(scopes), digest)).lastrowid
        except sqlite3.IntegrityError as error:
            raise Conflict("principal already exists") from error
        return {"id": ident, "name": name, "scopes": scopes, "token": token}

    def revoke_principal(self, name):
        """Disable a local identity's token while preserving its attribution."""
        name = _text(name, "name", 64)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            identity = db.execute("SELECT id, name FROM principals WHERE name_key=?", (name.casefold(),)).fetchone()
            if identity is None:
                raise LookupError("principal not found")
            db.execute("INSERT INTO revoked_principals VALUES (?, ?) ON CONFLICT(principal_id) DO NOTHING",
                       (identity["id"], int(time.time())))
            revoked = db.execute("SELECT revoked_at FROM revoked_principals WHERE principal_id=?",
                                 (identity["id"],)).fetchone()[0]
        return {**dict(identity), "revoked_at": _timestamp(revoked)}

    def _principal(self, db, token, required=None):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise AuthError("invalid bearer token")
        digest = sha256(token.encode("ascii")).hexdigest()
        row = db.execute("""SELECT p.id, p.name, p.scopes FROM principals p
            LEFT JOIN revoked_principals r ON r.principal_id=p.id
            WHERE p.token_hash=? AND r.principal_id IS NULL""", (digest,)).fetchone()
        if row is None:
            raise AuthError("invalid bearer token")
        identity = {"id": row["id"], "name": row["name"], "scopes": json.loads(row["scopes"])}
        if required is not None and required not in identity["scopes"]:
            raise PermissionDenied(f"{required} scope required")
        return identity

    def authenticate(self, token):
        with self._connect() as db:
            return self._principal(db, token)

    def register_work(self, token, problem_id, *, ttl_seconds=3600):
        """Register or renew a non-exclusive work notice."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = self._principal(db, token, "contribute")
            problem = self._problem(problem_id)
            ttl = _integer(ttl_seconds, "ttl_seconds", 60, 86400)
            now = int(time.time())
            db.execute("""INSERT INTO work(actor_id, problem_id, registered_at, expires_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(actor_id, problem_id) DO UPDATE SET
                    registered_at=excluded.registered_at, expires_at=excluded.expires_at""",
                       (actor["id"], problem, now, now + ttl))
            ident = db.execute("SELECT id FROM work WHERE actor_id=? AND problem_id=?",
                               (actor["id"], problem)).fetchone()[0]
        return {"id": ident, "problem_id": problem, "actor": actor["name"],
                "registered_at": _timestamp(now), "expires_at": _timestamp(now + ttl)}

    def active_work(self, token, *, problem_id=None):
        with self._connect() as db:
            self._principal(db, token, "read")
            now = int(time.time())
            query = """SELECT w.id, w.problem_id, p.name AS actor, w.registered_at, w.expires_at
                       FROM work w JOIN principals p ON w.actor_id=p.id
                       LEFT JOIN revoked_principals r ON r.principal_id=p.id
                       WHERE w.expires_at > ? AND r.principal_id IS NULL"""
            args = (now,)
            if problem_id is not None:
                query += " AND w.problem_id=?"
                args += (self._problem(problem_id),)
            rows = db.execute(query + " ORDER BY w.id", args).fetchall()
        return [{**dict(row), "registered_at": _timestamp(row["registered_at"]),
                 "expires_at": _timestamp(row["expires_at"])} for row in rows]

    def submit_result(self, token, payload):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            author = self._principal(db, token, "contribute")
            if not isinstance(payload, dict) or payload.keys() != PROPOSAL_KEYS:
                raise ValueError("result requires problem_id, source_url, revision, platform, evidence_kind, outcome and summary")
            problem = self._problem(payload["problem_id"])
            source = _source(payload["source_url"])
            revision = payload["revision"]
            if not isinstance(revision, str) or not REVISION.fullmatch(revision):
                raise ValueError("revision must be a full hexadecimal Git commit SHA")
            platform = _text(payload["platform"], "platform", 120)
            summary = _text(payload["summary"], "summary", 600)
            evidence, outcome = payload["evidence_kind"], payload["outcome"]
            if not isinstance(evidence, str) or evidence not in EVIDENCE_KIND | {"simulation"}:
                raise ValueError("invalid evidence_kind")
            if not isinstance(outcome, str) or outcome not in EVIDENCE_OUTCOME:
                raise ValueError("invalid outcome")
            fields = (author["id"], problem, source, revision.lower(), platform, evidence, outcome, summary)
            existing = db.execute(RESULTS + """ WHERE r.author_id=? AND r.problem_id=? AND lower(r.source_url)=lower(?)
                AND r.revision=? AND r.platform=? AND r.evidence_kind=? AND r.outcome=? AND r.summary=?
                ORDER BY r.id LIMIT 1""", fields).fetchone()
            if existing is not None:
                return _result(existing)
            ident = db.execute("""INSERT INTO results(author_id, problem_id, source_url, revision, platform,
                evidence_kind, outcome, summary, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (*fields, int(time.time()))).lastrowid
            return _result(db.execute(RESULTS + " WHERE r.id=?", (ident,)).fetchone())

    def pending_results(self, token, *, limit=50):
        with self._connect() as db:
            self._principal(db, token, "review")
            limit = _integer(limit, "limit", 1, 100)
            return [_result(row) for row in db.execute(RESULTS + " WHERE d.result_id IS NULL ORDER BY r.id LIMIT ?",
                                                        (limit,))]

    def review_result(self, token, result_id, *, decision, reason=""):
        """Record one review decision and append a local event atomically."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            reviewer = self._principal(db, token, "review")
            ident = _integer(result_id, "result_id", 1, MAX_SQL_INTEGER)
            if decision not in ("accepted", "rejected"):
                raise ValueError("decision must be accepted or rejected")
            reason = _text(reason, "reason", 400, optional=True)
            current = db.execute("""SELECT r.author_id, d.result_id FROM results r
                LEFT JOIN decisions d ON d.result_id=r.id WHERE r.id=?""", (ident,)).fetchone()
            if current is None:
                raise LookupError("result not found")
            if current["author_id"] == reviewer["id"]:
                raise PermissionDenied("authors cannot review their own results")
            if current["result_id"] is not None:
                raise Conflict("result already reviewed")
            db.execute("INSERT INTO decisions VALUES (?, ?, ?, ?, ?)",
                       (ident, reviewer["id"], decision, reason, int(time.time())))
            if decision == "accepted":
                db.execute("INSERT INTO approved_events(result_id) VALUES (?)", (ident,))
            return _result(db.execute(RESULTS + " WHERE r.id=?", (ident,)).fetchone())

    def evidence(self, token, problem_id, *, limit=50):
        with self._connect() as db:
            self._principal(db, token, "read")
            problem = self._problem(problem_id)
            limit = _integer(limit, "limit", 1, 100)
            return [_result(row) for row in db.execute(RESULTS + """ WHERE e.id IS NOT NULL AND r.problem_id=?
                        ORDER BY e.id DESC LIMIT ?""", (problem, limit))]

    def poll_events(self, token, *, after=0, limit=50):
        with self._connect() as db:
            self._principal(db, token, "read")
            after = _integer(after, "after", 0, MAX_SQL_INTEGER)
            limit = _integer(limit, "limit", 1, 100)
            rows = db.execute(RESULTS + " WHERE e.id > ? ORDER BY e.id LIMIT ?", (after, limit))
            events = [{"id": row["event_id"], "kind": "result_accepted", "result": _result(row)} for row in rows]
        return {"events": events, "next_cursor": events[-1]["id"] if events else after}
