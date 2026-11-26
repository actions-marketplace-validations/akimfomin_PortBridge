"""Local review of People corrections, display choices and expiring availability."""
import argparse
import json
from pathlib import Path
import re
import tempfile

from .catalog import public_url
from .community import participant
from .community_sources import DATA, evidence_key
from .identity import contributor_id, stable_id
from .radar_store import epoch

CONFIG = DATA / "people_policy.json"
DURATION = 90 * 86400


def permission_actor(value):
    if not isinstance(value, dict) or set(value) - {"login", "user_id"}:
        raise ValueError("Use a public GitHub login and its verified numeric ID")
    who = participant(value.get("login"), value.get("user_id"))
    if not who or not who["user_id"]:
        raise ValueError("Use a public GitHub login and its verified numeric ID")
    return who


def decide(policy, decision):
    if not isinstance(decision, dict) or not public_url(decision.get("proof")) or not epoch(decision.get("at")):
        raise ValueError("A verified public proof and dated maintainer decision are required")
    action = decision.get("action")
    proof = decision["proof"]
    target = decision.get("source")
    ident = stable_id("people-policy", action, evidence_key(proof), target, decision.get("actor"))
    if ident in policy["decisions"]:
        return policy
    if action in {"hide", "restore", "opt-in", "opt-out", "withdraw-availability", "correct"}:
        who = permission_actor(decision.get("actor"))
        user_id = contributor_id(who["login"], who["user_id"])
        login = who["login"].casefold()
    else:
        who = None
    if action in {"hide", "opt-out"}:
        policy["hidden_ids"] = sorted(set(policy["hidden_ids"]) | {user_id})
        policy["hidden_logins"] = sorted(set(policy["hidden_logins"]) | {login})
        policy["availability"] = [row for row in policy["availability"] if row["actor"]["user_id"] != who["user_id"]]
    elif action == "restore":
        policy["hidden_ids"] = [item for item in policy["hidden_ids"] if item != user_id]
        policy["hidden_logins"] = [item for item in policy["hidden_logins"] if item != login]
    elif action in {"opt-in", "withdraw-availability"}:
        if action == "opt-in" and (not 0 < epoch(decision.get("until")) - epoch(decision["at"]) <= DURATION
                                   or user_id in policy["hidden_ids"]
                                   or decision.get("scope") not in {"source-review", "lab-test", "both"}):
            raise ValueError("Explicit consent must expire within 90 days and the profile must be visible")
        policy["availability"] = [row for row in policy["availability"] if row["actor"]["user_id"] != who["user_id"]]
        if action == "opt-in":
            policy["availability"].append({"actor": who, "until": decision["until"], "proof": proof,
                                            "scope": decision["scope"]})
    elif action == "correct" and public_url(target):
        policy["corrections"][evidence_key(target)] = {"actor": who, "proof": proof}
    elif action == "withdraw" and (public_url(target) or isinstance(target, str) and re.fullmatch(
            r"(?:impact|lab-report|community-fact):[a-z0-9-]{6,80}", target)):
        key = evidence_key(target) if public_url(target) else target
        policy["withdrawn"] = sorted(set(policy["withdrawn"]) | {key})
    else:
        raise ValueError("Unsupported People decision or invalid source")
    policy["decisions"].append(ident)
    return policy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=CONFIG)
    parser.add_argument("--decision", type=Path, required=True)
    args = parser.parse_args(argv)
    updated = decide(json.loads(args.policy.read_bytes()), json.loads(args.decision.read_bytes()))
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf8", dir=args.policy.parent, delete=False) as output:
        path = Path(output.name)
        json.dump(updated, output, indent=2)
        output.write("\n")
    path.replace(args.policy)
    print("Local People policy updated")


if __name__ == "__main__":
    main()
