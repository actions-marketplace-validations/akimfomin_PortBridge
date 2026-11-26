"""Stable additive keys and provenance for the reviewed catalog and public observations."""

from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from .matching import canonical_url, repository_identity, source_revision


SCHEMA_VERSION = 1
REVISION = re.compile(r"[a-fA-F0-9]{40,64}")
RELATION_TYPES = {"same_problem", "related_implementation", "same_patch", "source_port",
                  "shared_symptom", "contradiction", "test_reuse"}


def stable_id(kind, *parts):
    key = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return f"{kind}:{sha256(key.encode()).hexdigest()[:32]}"


def repository_id(repo):
    return f"repository:{repository_identity(repo).casefold()}"


def source_id(url):
    parsed = urlsplit(url)
    base = canonical_url(url)
    fragment = parsed.fragment
    if re.fullmatch(r"(?:issuecomment|discussion_r|pullrequestreview)-?[0-9]+", fragment):
        base += f"#{fragment}"
    return stable_id("source", base)


def revision_id(sha):
    return f"revision:{sha.lower()}" if isinstance(sha, str) and REVISION.fullmatch(sha) else None


def contributor_id(login, github_id=None):
    if type(github_id) is int and github_id > 0:
        return f"github-user:{github_id}"
    return f"github-login:{login.casefold()}" if isinstance(login, str) and login else None


def provenance(url, *, kind, revision=None, event_at=None, fetched_at=None, limits=()):
    return {"url": url, "source_id": source_id(url), "revision": revision or None,
            "revision_id": revision_id(revision), "event_at": event_at or None, "collected_at": fetched_at or None,
            "evidence_kind": kind, "limits": list(limits)}


def observation_provenance(item):
    metadata = item["metadata"]
    return provenance(item["url"], kind=metadata.get("evidence_kind", "source_observation"),
                      revision=source_revision(item) or metadata.get("sha"), event_at=item.get("updated_at"),
                      fetched_at=item.get("fetched_at"), limits=["public GitHub metadata"])


def evidence_fields(row, observed=None):
    observed = observed or {}
    kind = row.get("kind", "source_reference")
    origin = provenance(row["url"], kind=kind, revision=row.get("revision") or observed.get("revision"),
                        event_at=row.get("reported_at") or observed.get("updated_at"),
                        fetched_at=observed.get("fetched_at"),
                        limits=row.get("limits", ("scope limited to the linked record",)))
    # Keep the ID across edits to findings and decisions about the same artifact.
    scope = row.get("id") or (row.get("title"), sorted(row.get("platforms", ())), sorted(row.get("check_for", ())))
    identity = stable_id("evidence", origin["source_id"], kind, row.get("revision") or "", scope)
    return {"evidence_id": identity, "provenance": origin}


def relation_fields(left, right, *, kind, state, reason, confidence=None, directed=False):
    if kind not in RELATION_TYPES:
        raise ValueError("unknown relationship type")
    endpoints = [source_id(left["url"]), source_id(right["url"])]
    identity = stable_id("relation", kind, *(endpoints if directed else sorted(endpoints)))
    return {"id": identity, "type": kind, "direction": "left_to_right" if directed else "undirected",
            "state": state, "confidence": confidence, "reason": reason, "sources": endpoints}


def lab_report_id(url):
    return stable_id("report", source_id(url))


def attribution_fields(report, task):
    """Keep report, evidence, adoption and credit identities independently countable."""
    origin = report.get("url")
    if not origin:
        return report
    person = contributor_id(report.get("author"), report.get("author_id"))
    ident = lab_report_id(origin)
    revision = report.get("revision")
    return {**report, "report_id": ident, "evidence_id": stable_id("evidence", ident, task, revision),
            "contributor_id": person, "credit_id": stable_id("credit", person, ident, "report"),
            "provenance": provenance(origin, kind="public_test_report", revision=revision,
                                     event_at=report.get("reported_at"), limits=("review scope is task-specific",))}
