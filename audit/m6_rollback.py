"""Check the previous renderer on a separate restored catalog before a release."""
import argparse
import json
from pathlib import Path


def snapshot(directory, name):
    return json.loads((directory / "data" / (name + ".json")).read_bytes())


def check(current, previous):
    count = snapshot(current, "health")["observation_count"]
    if not count or snapshot(previous, "health")["observation_count"] != count:
        raise ValueError("The rollback export lost catalog observations")
    def cards(directory):
        return {row["id"] for row in snapshot(directory, "problems")["problems"]}

    if cards(previous) - cards(current):
        raise ValueError("The rollback export would bring back an unlisted card")
    for directory in (current, previous):
        if not (directory / "index.html").is_file() or not snapshot(directory, "lab")["tasks"]:
            raise ValueError("The site or Test Lab did not rebuild")
    print(f"Previous renderer rebuilt {count} observations, preserved card exclusions and produced the site and Lab.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", type=Path)
    parser.add_argument("previous", type=Path)
    args = parser.parse_args()
    check(args.current, args.previous)
