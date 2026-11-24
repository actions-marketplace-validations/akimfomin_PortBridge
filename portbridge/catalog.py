"""Persistent curated problems and public GitHub observations."""

from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit


PROBLEM_STATUS = {"investigating", "partial", "verified", "resolved"}
SOLUTION_STATUS = {"reported", "open", "partial", "verified", "merged", "unknown"}
EVIDENCE_KIND = {"maintainer_claim", "automated_test", "independent", "source_observation"}
OBSERVATION_KIND = {"issue", "pr", "commit", "test"}
SYNC_STATUS = {"ok", "partial", "stale", "error", "seed-only"}
PROBLEM_ID = re.compile(r"PB-[0-9]{4,}")
REPO_NAME = re.compile(r"[\w.-]+/[\w.-]+", re.ASCII)
WORDS = re.compile(r"[^\W_]+")
STOP_WORDS = set("a an the on in to of for by and or from that it its is at with into after before as this then "
                 "test tests tested fix fixes add adds support update merge pull request windows linux xbox "
                 "game would about when build issue code commit main using use like fails error crash "
                 "this github before after make target runtime".split())


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def public_url(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return (parsed.scheme == "https" and parsed.netloc == "github.com" and
            bool(parsed.path.strip("/")) and not any(ch.isspace() for ch in url))


def canonical_url(url):
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/").lower()
    return f"https://github.com{path}"


def expect(condition, message):
    if not condition:
        raise ValueError(message)


def validate_seed(seed):
    projects = seed["projects"]
    slugs = {project["slug"] for project in projects}
    expect(len(slugs) == len(projects), "Duplicate project slug")
    for project in projects:
        expect(re.fullmatch(r"[a-z0-9-]+", project["slug"]), "Invalid project slug")
        expect(REPO_NAME.fullmatch(project["repo"]), "Invalid GitHub repository")
        expect(public_url(project["url"]), "Invalid project URL")

    problems = seed["problems"]
    ids = {problem["id"] for problem in problems}
    expect(len(ids) == len(problems), "Duplicate problem ID")
    for problem in problems:
        ident = problem["id"]
        expect(PROBLEM_ID.fullmatch(ident), f"Invalid problem ID: {ident}")
        expect(problem["status"] in PROBLEM_STATUS, f"Invalid problem status: {ident}")
        dependencies = set(problem["dependency_ids"])
        expect(dependencies <= ids and ident not in dependencies, f"Invalid dependencies: {ident}")
        solution_projects = set()
        for solution in problem["solutions"]:
            project = solution["project"]
            expect(project in slugs and project not in solution_projects, f"Invalid solution project: {ident}")
            solution_projects.add(project)
            expect(solution["status"] in SOLUTION_STATUS, f"Invalid solution status: {ident}")
            expect(bool(solution["source_refs"]), f"Missing solution sources: {ident}")
            for source in solution["source_refs"] + solution["evidence"]:
                expect(public_url(source["url"]), f"Invalid source URL: {ident}")
            for evidence in solution["evidence"]:
                expect(evidence["kind"] in EVIDENCE_KIND, f"Invalid evidence kind: {ident}")
                expect(bool(evidence["observed"]), f"Missing evidence summary: {ident}")
    reference = seed.get("coordination", {}).get("reference")
    if reference:
        expect(reference["project"] in slugs and public_url(reference["url"]), "Invalid reference build")


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    slug TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    project TEXT NOT NULL REFERENCES projects(slug),
    kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT,
    fetched_at TEXT NOT NULL,
    metadata TEXT NOT NULL,
    PRIMARY KEY (project, kind, source_id)
);
CREATE INDEX IF NOT EXISTS observation_recent ON observations(updated_at DESC);
CREATE TABLE IF NOT EXISTS sync_projects (
    slug TEXT PRIMARY KEY REFERENCES projects(slug), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
"""


def encode(value):
    return json.dumps(value, ensure_ascii=False)


class Catalog:
    def __init__(self, path, seed_path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        seed = json.loads(Path(seed_path).read_text(encoding="utf-8"))
        validate_seed(seed)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            db.executemany("INSERT INTO projects VALUES(?, ?) ON CONFLICT(slug) DO UPDATE SET payload=excluded.payload",
                           ((p["slug"], encode(p)) for p in seed["projects"]))
            db.executemany("INSERT INTO problems VALUES(?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                           ((p["id"], encode(p)) for p in seed["problems"]))
            db.execute("INSERT INTO settings VALUES('coordination', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (encode(seed.get("coordination", {})),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def projects(self):
        with self.connect() as db:
            rows = db.execute("""SELECT projects.payload, sync.payload AS sync
                FROM projects LEFT JOIN sync_projects sync USING(slug) ORDER BY projects.rowid""").fetchall()
        projects = []
        for row in rows:
            sync = json.loads(row["sync"]) if row["sync"] else {}
            projects.append({**json.loads(row["payload"]), "sync_status": sync.get("sync_status", "seed-only"),
                             "last_success": sync.get("last_success"), "sources": sync.get("sources", {})})
        return projects

    def coordination(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='coordination'").fetchone()
        return json.loads(row[0]) if row else {}

    def record_sync(self, result):
        observed_at = timestamp()
        with self.connect() as db:
            projects = {row[0] for row in db.execute("SELECT slug FROM projects")}
            for item in result["items"]:
                if (item["project"] not in projects or item["kind"] not in OBSERVATION_KIND or
                        not public_url(item["url"])):
                    continue
                db.execute("""INSERT INTO observations VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project, kind, source_id) DO UPDATE SET
                    title=excluded.title, url=excluded.url, status=excluded.status,
                    updated_at=excluded.updated_at, fetched_at=excluded.fetched_at, metadata=excluded.metadata""",
                    (item["project"], item["kind"], str(item["source_id"]), item["title"][:300],
                     item["url"], item["status"], item["updated_at"], item.get("fetched_at") or observed_at,
                     encode(item["metadata"])))
            for status in result.get("projects", []):
                slug = status.get("slug")
                if slug in projects:
                    previous = db.execute("SELECT payload FROM sync_projects WHERE slug=?", (slug,)).fetchone()
                    record = {**(json.loads(previous[0]) if previous else {}), **status}
                    if not status.get("last_success") and previous:
                        record["last_success"] = json.loads(previous[0]).get("last_success")
                    db.execute("INSERT INTO sync_projects VALUES(?, ?) ON CONFLICT(slug) DO UPDATE SET payload=excluded.payload",
                               (slug, encode(record)))
            health = {"refresh_at": observed_at, "warnings": result.get("warnings", [])}
            db.execute("INSERT INTO settings VALUES('sync', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (encode(health),))

    def health(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='sync'").fetchone()
            count = db.execute("SELECT count(*) FROM observations").fetchone()[0]
        projects = self.projects()
        states = {project["sync_status"] for project in projects}
        if row is None:
            status = "seed-only"
        elif states == {"ok"}:
            status = "ok"
        elif states == {"stale"}:
            status = "stale"
        elif not count:
            status = "error"
        else:
            status = "partial"
        details = json.loads(row[0]) if row else {"refresh_at": None, "warnings": []}
        return {"status": status, "observation_count": count, **details}

    def problems(self, *, q="", project="", status="", partial=False):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM problems ORDER BY id").fetchall()
        found = []
        for row in rows:
            problem = summarize(json.loads(row[0]))
            if status and status != problem["status"]:
                continue
            if project and project not in {solution["project"] for solution in problem["solutions"]}:
                continue
            if partial and not problem["partial_opportunity"]:
                continue
            if contains(problem, q):
                found.append(problem)
        return found

    def problem(self, ident):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM problems WHERE id=?", (ident,)).fetchone()
        return summarize(json.loads(row[0])) if row else None

    def observations(self, *, q="", kind="", project="", limit=100):
        clauses, arguments = [], []
        for column, value in (("kind", kind), ("project", project)):
            if value:
                clauses.append(f"{column}=?")
                arguments.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as db:
            result = []
            for row in db.execute("SELECT * FROM observations" + where + " ORDER BY updated_at DESC", arguments):
                item = dict(row)
                item["metadata"] = json.loads(item["metadata"])
                if contains(item, q):
                    result.append(item)
                    if len(result) >= limit:
                        break
        return result

    def matches(self, *, q="", limit=60):
        problems = self.problems()
        approved, known_links = [], defaultdict(set)
        for problem in problems:
            references = []
            for solution in problem["solutions"]:
                refs = [{**ref, "project": solution["project"]} for ref in solution["source_refs"]]
                for ref in refs:
                    known_links[canonical_url(ref["url"])].add(problem["id"])
                references.append(refs[0])
            if contains(problem, q):
                state = "reviewed_symptom" if problem.get("relationship") == "shared_symptom" else "reviewed_same"
                reason = ("Совпадает симптом. Общая причина не установлена." if state == "reviewed_symptom"
                          else "Связь указана в проверенной карточке каталога.")
                for left, right in combinations(references, 2):
                    approved.append(match(left, right, None, reason, state, problem["id"]))
        records = self.observations(limit=600)
        stacks = {project["slug"]: project["stack"] for project in self.projects()}
        suggested = similar(records, known_links, stacks, q)
        return (approved + suggested)[:limit]

    def outreach(self):
        projects = {project["slug"]: project for project in self.projects()}
        with self.connect() as db:
            states = {canonical_url(row["url"]): row["status"] for row in
                      db.execute("SELECT url, status FROM observations WHERE kind IN ('issue', 'pr')")}
        drafts = []
        for problem in self.problems(partial=True):
            sources = [solution for solution in problem["solutions"]
                       if solution["status"] in {"verified", "merged"} and solution.get("outreach_summary")]
            if not sources or problem.get("relationship") == "shared_symptom":
                continue
            for target in problem["solutions"]:
                if target["status"] in {"verified", "merged"}:
                    continue
                receiver = projects[target["project"]]
                target_path = f"https://github.com/{receiver['repo'].lower()}"
                target_url = next((ref["url"] for ref in target["source_refs"]
                                   if re.fullmatch(re.escape(target_path) + r"/(?:issues|pull)/[0-9]+",
                                                   canonical_url(ref["url"]))
                                   and states.get(canonical_url(ref["url"])) not in {"closed", "merged"}), None)
                if not target_url:
                    continue
                source = min(sources, key=lambda solution: projects[solution["project"]]["stack"] != receiver["stack"])
                sender = projects[source["project"]]
                source_url = source["source_refs"][0]["url"]
                mode = "reference" if sender["stack"] == receiver["stack"] else "comparison"
                caveat = ("Please confirm on this branch before treating the issue as fixed."
                          if mode == "reference" else
                          "The graphics backends differ. The test case may help; the implementation needs separate validation.")
                ident = problem["id"]
                drafts.append({
                    "id": f"{ident}:{target['project']}",
                    "problem_id": ident,
                    "target_project": target["project"],
                    "target_url": target_url,
                    "target_status": states.get(canonical_url(target_url), "unobserved"),
                    "source_project": source["project"],
                    "source_url": source_url,
                    "mode": mode,
                    "message": f"Cross-project note prepared with PortBridge ({ident}).\n\n"
                               f"{source['outreach_summary']}\n\n{caveat}",
                })
        return drafts


def summarize(problem):
    solutions = problem["solutions"]
    confirmed = {solution["project"] for solution in solutions if
                 any(e["kind"] in {"independent", "automated_test"} for e in solution["evidence"])}
    progress = {"partial", "verified", "merged"}
    partial = (len(solutions) > 1 and any(s["status"] in progress for s in solutions) and
               any(s["status"] not in {"verified", "merged"} for s in solutions) and
               problem["status"] != "resolved")
    return {**problem, "project_count": len(solutions), "verified_count": len(confirmed),
            "partial_opportunity": partial}


def contains(payload, query):
    terms = query.casefold().split()
    if not terms:
        return True
    text = encode(payload).casefold()
    for term in terms:
        if re.fullmatch(r"#[0-9]+", term):
            number = term[1:]
            if not re.search(rf"(?:#|/issues/|/pull/){number}(?![0-9])", text):
                return False
        elif term not in text:
            return False
    return True


def keywords(title):
    return {word for word in WORDS.findall(title.casefold())
            if len(word) >= 3 and word not in STOP_WORDS and not word.isdecimal()}


def match(left, right, score, reason, state, problem_id=None):
    return {"left": {k: left[k] for k in ("project", "title", "url")},
            "right": {k: right[k] for k in ("project", "title", "url")},
            "score": score, "reason": reason, "state": state, "problem_id": problem_id}


def similar(records, known_links, stacks, query):
    items = [item for item in records if item["kind"] in {"issue", "pr", "commit"}]
    terms = [keywords(item["title"]) for item in items]
    frequency = Counter(word for words in terms for word in words)
    common = {word for word, count in frequency.items() if count > max(20, len(items) // 6)}
    inverted = defaultdict(list)
    found = []
    for i, left in enumerate(items):
        words = terms[i] - common
        seen = Counter(j for word in words for j in inverted[word])
        for j, shared_count in seen.items():
            right = items[j]
            if shared_count < 3 or left["project"] == right["project"]:
                continue
            if query and not contains([left, right], query):
                continue
            if known_links.get(canonical_url(left["url"]), set()) & known_links.get(canonical_url(right["url"]), set()):
                continue
            right_words = terms[j] - common
            score = shared_count / len(words | right_words)
            if score < 0.25:
                continue
            common_text = ", ".join(sorted(words & right_words)[:6])
            reason = f"Общие термины в заголовках — {common_text}."
            if stacks.get(left["project"]) != stacks.get(right["project"]):
                reason += " Разные стеки могут требовать разных исправлений."
            found.append(match(left, right, round(score, 3), reason, "suggested"))
        for word in words:
            inverted[word].append(i)
    return sorted(found, key=lambda row: (-row["score"], row["left"]["url"], row["right"]["url"]))
