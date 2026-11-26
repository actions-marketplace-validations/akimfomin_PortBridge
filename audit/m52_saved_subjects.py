"""Count subject extraction in existing normalized PRs. All database access is read-only."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--db", type=Path, help="optional existing PortBridge database")
    args = parser.parse_args()
    sys.path.insert(0, str(args.code.resolve()))
    from portbridge.discovery_scan import subject

    if args.db:
        # A missing database must not be created. Never print its contents.
        db = sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            versions = Counter()
            total = signals = 0
            for title, meta in db.execute("SELECT title,metadata FROM observations WHERE kind='pr'"):
                metadata = json.loads(meta)
                versions[str(metadata.get("technical", {}).get("version"))] += 1
                total += 1
                signals += bool(subject({"title": title, "metadata": metadata}))
            print(json.dumps({"rows": total, "with_subject": signals, "signature_versions": versions}))
        finally:
            db.close()
    else:
        fixture = Path(__file__).resolve().parent / "evidence/m52/saved-observations.json"
        for row in json.loads(fixture.read_bytes())["examples"]:
            print(json.dumps({"url": row["url"], "subject": subject(row)}))


if __name__ == "__main__":
    main()
