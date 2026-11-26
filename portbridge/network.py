"""Review-only planning for technical collaboration and evidence of repeated use."""
import argparse
import json
from pathlib import Path

from .catalog import ReadOnlyCatalog, public_url
from .community_partners import opportunities
from .community_sources import DATA, evidence_key
from .network_usage import outcomes, repeat_use

CHANNELS = DATA / "network_channels.json"


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
            "outcome": outcomes(public, local),
            "delivery": "Local review only. Every contact requires a separate owner decision."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="catalog for the full local plan")
    parser.add_argument("--outcomes-only", action="store_true", help="show historical and relaunch metrics only")
    parser.add_argument("--ledger", type=Path, help="local decisions and reviewed technical evidence")
    parser.add_argument("--console", default="")
    args = parser.parse_args(argv)
    if not args.db and not args.outcomes_only:
        parser.error("--db is required for the full plan")
    local = json.loads(args.ledger.read_bytes()) if args.ledger else {}
    if args.outcomes_only:
        result = {"outcome": outcomes(json.loads(CHANNELS.read_bytes()), local)}
    else:
        with ReadOnlyCatalog(args.db).read_view() as catalog:
            result = plan(catalog, local, console=args.console)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
