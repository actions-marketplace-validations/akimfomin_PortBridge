"""Create a consistent, separate SQLite backup without overwriting files."""

from contextlib import closing
from pathlib import Path
import sqlite3


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
