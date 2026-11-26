"""Review-only planning for technical collaboration and evidence of repeated use."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from .catalog import ReadOnlyCatalog, public_url
from .community_partners import opportunities
from .community_sources import DATA, evidence_key, repository
from .radar_store import epoch

CHANNELS = DATA / "network_channels.json"
EVIDENCE_KINDS = {"technical_trial", "technical_reuse"}


def repeat_use(events):
    """Count a team once only after different tasks on different UTC days."""
    observed = defaultdict(set)
    for event in events:
        stamp = event.get("at")
        proof = event.get("proof")
        target = event.get("task")
        if (event.get("kind") not in EVIDENCE_KINDS or event.get("reviewed") is not True
                or not epoch(stamp) or not public_url(proof) or not public_url(target)):
            continue
        team = repository(proof)
        if (not team or team == "akimfomin/portbridge" or repository(target) != team
                or event.get("actor") in {None, "", "akimfomin", "portbridge"}):
            continue
        observed[team].add((evidence_key(target).split("#")[0], stamp[:10], evidence_key(proof)))
    repeated = sorted(team for team, records in observed.items() if any(
        a[0] != b[0] and a[1] != b[1] and a[2] != b[2] for a in records for b in records))
    return {"target": 3, "verified_repeat_teams": repeated,
            "single_or_repeat_teams": sorted(observed), "reached": len(repeated) >= 3}


def plan(catalog, local, *, console=""):
    public = json.loads(CHANNELS.read_bytes())
    prior = {*public["hold_repositories"]}
    hidden = set()
    occupied = set()
    for row in local.get("history", []):
        if row.get("state") in {"refused", "opt_out"}:
            if row.get("scope") == "repository":
                prior.add(row.get("repository", "").lower())
            else:
                hidden.add(str(row.get("profile", "")))
        if public_url(row.get("task")):
            occupied.add((str(row.get("profile", "")), evidence_key(row["task"])))
    raw = opportunities(catalog, console=console)
    categories = {
        "xbox_owners": [], "ps5_owners": [], "cross_project": [], "technical": [],
        "hardware": [], "trackers": [], "infrastructure": [],
    }
    for row in raw["opportunities"]:
        repo = row["project"]
        if (repo in prior or row["profile"] in hidden
                or (row["profile"], evidence_key(row["need_source"])) in occupied):
            continue
        role = row["role"]
        if role in {"repository_owner", "maintainer", "lead"}:
            category = "ps5_owners" if "ps5" in row["consoles"] else "xbox_owners"
        elif role == "hardware_tester":
            category = "hardware"
        elif role == "infrastructure_author":
            category = "infrastructure"
        elif row["multi_project"]:
            category = "cross_project"
        else:
            category = "technical"
        categories[category].append(row)
    categories["trackers"] = [channel for channel in public["channels"]
                               if channel["status"] in {"listed", "candidate", "used_in_task"}]
    return {"as_of": raw["as_of"], "categories": categories, "prior_channel_summary": public["channels"],
            "outcome": repeat_use(public["usage"] + local.get("usage", [])),
            "delivery": "Local review only. Every contact requires a separate owner decision."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--ledger", type=Path, help="private decisions and earlier technical evidence")
    parser.add_argument("--console", default="")
    args = parser.parse_args(argv)
    local = json.loads(args.ledger.read_bytes()) if args.ledger else {}
    with ReadOnlyCatalog(args.db).read_view() as catalog:
        print(json.dumps(plan(catalog, local, console=args.console), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
