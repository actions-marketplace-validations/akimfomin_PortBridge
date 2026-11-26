"""Prepare a local, reviewable technical partner shortlist without contacting anyone."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from .catalog import ReadOnlyCatalog
from .community import people
from .community_sources import evidence_key, repository, topics
from .radar_store import epoch


def opportunities(catalog, *, console=""):
    if console not in {"", "xbox-series", "ps5"}:
        raise ValueError("Use an Xbox Series or PS5 platform")
    sources = catalog.observations(kind="pr", limit=None)
    profiles, _ = people(catalog)
    recent = epoch(profiles["as_of"]) - 14 * 86400
    projects = {repository("https://github.com/" + row["repo"]): row for row in catalog.projects()}
    by_subject, by_repo = defaultdict(list), defaultdict(list)
    for profile in profiles["profiles"]:
        if profile["activity"] != "recent":
            continue
        for proof in profile["evidence"]:
            if proof["age"] == "recent":
                by_subject[evidence_key(proof.get("subject") or proof["source"])].append((profile, proof))
        for role in profile["roles"]:
            if role["age"] == "recent" and role["role"] in {
                "repository_owner", "maintainer", "reviewer", "hardware_tester", "infrastructure_author"
            }:
                by_repo[role["repo"]].append((profile, role))
    pairs = {}
    for need in sources:
        url = need["url"]
        repo = repository(url)
        project = projects.get(repo, {})
        tags = set(topics(need["title"]))
        if (need["status"] != "open" or need["metadata"].get("draft") or not tags
                or epoch(need["updated_at"]) < recent or console and console not in project.get("consoles", [])):
            continue
        actors = by_subject.get(evidence_key(url), []) + by_repo[repo]
        for profile, proof in actors:
            person = profile["id"]
            shared = tags.intersection(tag["name"] for tag in profile["specialties"])
            if not shared or (person, repo) in pairs:
                continue
            pairs[person, repo] = {
                "profile": person, "login": profile["login"], "role": proof["role"],
                "multi_project": profile["multi_project"],
                "project": repo, "consoles": project.get("consoles", []),
                "need": need["title"], "need_source": url, "role_source": proof["source"], "role_observed_at": proof["at"],
                "specialties": sorted(shared),
                "benefit": "Compare prior work on " + ", ".join(sorted(shared))
                + " against the behavior in this PR, with one pinned Lab check.",
                "next_step": "Ask the project if a single source-only comparison would help its current work.",
                "public_channel": url, "status": "internal_review", "contact_permission": "not_granted",
            }
    return {"as_of": profiles["as_of"], "opportunities": list(pairs.values())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--console", default="")
    args = parser.parse_args(argv)
    with ReadOnlyCatalog(args.db).read_view() as catalog:
        print(json.dumps(opportunities(catalog, console=args.console), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
