"""Measure checkpoint recovery and a release rollback on a saved public observations.json."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portbridge import community_sources, discovery_scan, radar_scan
from portbridge.__main__ import DEFAULT_SEED
from portbridge.backup import backup_database, checkpoint_count
from portbridge.catalog import Catalog


def command(root, *args):
    return subprocess.check_output([sys.executable, "-B", "-m", *map(str, args)], cwd=root, timeout=600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--rollback-code", required=True, type=Path)
    args = parser.parse_args()
    previous = args.rollback_code.resolve()
    previous_sha = subprocess.check_output(["git", "-C", str(previous), "rev-parse", "HEAD"], text=True).strip()
    previous_changes = subprocess.check_output(["git", "-C", str(previous), "status", "--porcelain", "--", "portbridge"])
    if previous_changes or previous_sha != "56e2262d62c492f4a866c350f3f708c3f694f77f":
        parser.error("rollback checkout must use the clean, previous public release 56e2262")
    raw = args.observations.read_bytes()
    rows = json.loads(raw)["observations"]
    metrics = {"observations_sha256": sha256(raw).hexdigest(), "input_rows": len(rows),
               "rollback_code": previous_sha}
    with TemporaryDirectory(prefix="portbridge-m6-recovery-") as temp:
        data = Path(temp)
        live = Catalog(data / "primary.sqlite3", DEFAULT_SEED)
        live.record_sync({"items": rows, "projects": []})
        with live.connect() as db:
            db.executescript(community_sources.SCHEMA + discovery_scan.SCHEMA)
        radar_scan.refresh(live)
        started = monotonic()
        archive = backup_database(live.path, data / "checkpoint.sqlite3", public_checkpoint=True)
        metrics["archive_seconds"] = round(monotonic() - started, 3)
        metrics["archive_bytes"] = archive.stat().st_size
        if checkpoint_count(archive) != len(rows):
            raise ValueError("The checkpoint does not contain all input observations")
        for label, code in (("recovered", ROOT), ("rollback", previous)):
            started = monotonic()
            # Each isolated reader starts from the same verified checkpoint, with no live cache.
            db = backup_database(archive, data / (label + ".sqlite3"))
            site = data / (label + "-site")
            command(code, "portbridge", "--db", db, "export", "--out", site)
            if code == ROOT:
                command(code, "portbridge.release_gate", site)
            health = json.loads((site / "data/health.json").read_bytes())
            restored = json.loads((site / "data/observations.json").read_bytes())["observations"]
            def identity(row):
                return (row["project"], row["kind"], row["source_id"], row["url"])
            if (health["observation_count"] != len(rows) or len(restored) != len(rows)
                    or {identity(row) for row in rows} != {identity(row) for row in restored}):
                raise ValueError("Recovery or rollback changed the public source identities")
            metrics[label] = {"exported_rows": len(restored), "source_identity_equal": True,
                              "files": sum(p.is_file() for p in site.rglob("*")),
                              "seconds": round(monotonic() - started, 3)}
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
