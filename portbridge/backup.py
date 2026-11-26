"""Create a consistent, separate SQLite backup without overwriting files."""

from contextlib import closing
from pathlib import Path
import sqlite3


PUBLIC_TABLES = {"projects", "problems", "withdrawn_problems", "observations", "source_changes", "sync_projects",
                 "history_sync", "source_context", "settings", "ecosystem_sources", "github_cache", "github_rate_limit",
                 "github_history", "github_history_anchor", "lab_report_checks", "core_events", "sqlite_sequence"}


def checkpoint_count(source):
    """Read and validate the public catalog checkpoint before it becomes a live cache."""
    path = Path(source).resolve(strict=True)
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=8)) as connection:
        connection.execute("PRAGMA trusted_schema=OFF")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("catalog checkpoint integrity check failed")
        schema = dict(connection.execute("SELECT name, type FROM sqlite_master"))
        if not all(schema.get(name) == "table" for name in ("projects", "problems", "observations", "settings")):
            raise ValueError("file is not a public catalog checkpoint")
        if any(kind != "index" and (kind != "table" or name not in PUBLIC_TABLES)
               for name, kind in schema.items()):
            raise ValueError("unexpected table, view or trigger in public catalog checkpoint")
        return connection.execute("SELECT count(*) FROM observations").fetchone()[0]


def backup_database(source, destination):
    source = Path(source).expanduser().resolve(strict=True)
    destination = Path(destination).expanduser().resolve()
    if source == destination:
        raise ValueError("backup must use a separate file")
    with closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True, timeout=8)) as original:
        with destination.open("xb"):
            pass
        try:
            with closing(sqlite3.connect(destination, timeout=8)) as copy:
                original.backup(copy, pages=128)
                if copy.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("backup integrity check failed")
        except (sqlite3.Error, OSError, ValueError):
            destination.unlink()
            raise
    return destination
