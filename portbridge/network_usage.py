"""Count reviewed external use against the historical and relaunch evidence separately."""
from collections import defaultdict
import re
import time
from urllib.parse import urlsplit

from .catalog import public_url
from .community_sources import LOGIN, repository
from .github import REPO
from .matching import repository_identity
from .radar_store import epoch

KINDS = ("technical_trial", "technical_reuse")
TASK = re.compile(r"/([^/]+/[^/]+)/(issues|pull|discussions)/([1-9][0-9]*)/?", re.I)
COMMENT = re.compile(r"(?:issuecomment-|pullrequestreview-|discussion_r|discussioncomment-)[1-9][0-9]*", re.I)
COMMIT = re.compile(r"/[^/]+/[^/]+/commit/([a-f0-9]{40})/?", re.I)


def task_key(url):
    if not public_url(url):
        return None
    match = TASK.fullmatch(urlsplit(url).path)
    if not match or not REPO.fullmatch(match[1]):
        return None
    # A PR is also an issue. The same repository and number count as one task.
    # https://docs.github.com/en/rest/issues/issues
    return repository(url), match[3]


def receipt(event, as_of):
    if not isinstance(event, dict) or event.get("reviewed") is not True or event.get("kind") not in KINDS:
        return None
    at = epoch(event.get("at"))
    actor = event.get("actor")
    if not 0 < at <= as_of or not isinstance(actor, str) or not LOGIN.fullmatch(actor):
        return None
    if actor.casefold() in {"akimfomin", "portbridge"}:
        return None
    task = task_key(event.get("task"))
    proof = event.get("proof")
    if not task or not public_url(proof) or repository(proof) != task[0] or task[0].startswith("akimfomin/"):
        return None
    link = urlsplit(proof)
    commit = COMMIT.fullmatch(link.path)
    if commit:
        key = (task[0], "commit", commit[1].lower())
    elif task_key(proof) == task and COMMENT.fullmatch(link.fragment):
        key = (task[0], "comment", link.fragment.lower())
    elif task_key(proof) == task and not link.fragment:
        key = task
    else:
        return None
    return key, (task, at, actor.casefold())


def summary(receipts, teams=None):
    observed = defaultdict(set)
    for task, at, _ in receipts:
        repo = task[0]
        team = repo if teams is None else teams.get(repo)
        if team:
            observed[team].add((task, at // 86400))
    repeated = sorted(team for team, records in observed.items()
                      if len({task for task, _ in records}) >= 2 and len({day for _, day in records}) >= 2)
    return {"target": 3, "verified_repeat_team_count": len(repeated), "verified_repeat_teams": repeated,
            "single_or_repeat_team_count": len(observed), "single_or_repeat_teams": sorted(observed),
            "reached": len(repeated) >= 3}


def collect(events, as_of):
    # A repeated import is one receipt. Conflicting attribution cannot verify a use.
    collected = defaultdict(set)
    for event in events:
        entry = receipt(event, as_of)
        if entry:
            key, record = entry
            collected[key].add(record)
    return collected


def unambiguous(collected):
    return (next(iter(records)) for records in collected.values() if len(records) == 1)


def repeat_use(events):
    """Historical repository-level aggregation retained for callers with an existing ledger."""
    return summary(unambiguous(collect(events, float("inf"))))


def reviewed_teams(public, local):
    # One reviewed team may use several receiving repositories, even across owners.
    assignments = defaultdict(set)
    for ledger in (public, local):
        for repo, team in ledger.get("relaunch_teams", {}).items():
            if REPO.fullmatch(repo) and isinstance(team, str) and REPO.fullmatch(team):
                team = repository_identity(team).casefold()
                if not team.startswith("akimfomin/"):
                    assignments[repository_identity(repo).casefold()].add(team)
    unique = {repo: next(iter(teams)) for repo, teams in assignments.items() if len(teams) == 1}
    return {repo: team for repo, team in unique.items() if team not in assignments or unique.get(team) == team}


def version_confirmed(event, versions):
    if not isinstance(event, dict):
        return False
    revision = event.get("portbridge_revision")
    excerpt = event.get("version_evidence")
    if not isinstance(revision, str) or revision not in versions or not isinstance(excerpt, str):
        return False
    version = versions[revision]
    name = re.escape(version["name"])
    # Do not mistake 'PortBridge M5.1' for an explicit mention of 'PortBridge M5'.
    identifies_version = re.search(rf"(?<!\w)(?:{revision}|{name})(?![\w-]|\.\d)", excerpt, re.I)
    return bool(identifies_version) and epoch(event.get("at")) >= epoch(version["committed_at"]) > 0


def outcomes(public, local, *, as_of=None):
    now = time.time() if as_of is None else as_of
    historical = collect([*public["usage"], *local.get("usage", [])], now)
    new_events = [*public["relaunch_usage"], *local.get("relaunch_usage", [])]
    current = collect((event for event in new_events if version_confirmed(event, public["relaunch_versions"])), now)
    for proof in historical:
        current.pop(proof, None)
    return {"historical": summary(unambiguous(historical)),
            "relaunch": summary(unambiguous(current), reviewed_teams(public, local))}
