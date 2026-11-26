"""Check a static publication candidate before packaging or deployment."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from .catalog import public_url
from .integrations import SCHEMA
from .pages_health import verify_linked_snapshots


def audit(path):
    data = path / "data"
    read = lambda name: json.loads((data / (name + ".json")).read_bytes())
    manifest = read("site")
    site_digest = sha256((data / "site.json").read_bytes()).hexdigest()
    failed = list(verify_linked_snapshots(site_digest, request=lambda name: (data / (name + ".json")).open("rb")))
    for item in path.rglob("*"):
        if item.is_file() and (item.name.startswith(".env")
                or item.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".pem", ".key"}):
            failed.append(item.relative_to(path).as_posix())
    partner = read(manifest["snapshots"]["partner"].removesuffix(".json"))
    if partner != read("partner") or partner.get("schema_version") != SCHEMA:
        failed.append("partner contract")
    rows = partner["items"]
    if len({row["id"] for row in rows}) != len(rows):
        failed.append("duplicate partner rows")
    for row in rows:
        if not public_url(row.get("source")) or row.get("kind") not in {"task", "result"}:
            failed.append("partner item " + row["id"])
    for name in ("lab", "radar", "impact", "partner"):
        snapshot = data / manifest["snapshots"][name]
        scope = snapshot.read_bytes().lower()
        if any(value in scope for value in (b"m5-fixture", b"test-only-local-principal", b"synthetic-staging-only")):
            failed.append("staging marker in " + name)
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    failed = audit(args.directory)
    if failed:
        raise SystemExit("Publication gate failed: " + ", ".join(failed))
    print("Publication gate passed: snapshot checksums, partner contract and staging exclusions")


if __name__ == "__main__":
    main()
