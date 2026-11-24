"""Export the same catalog to a portable directory of public static files."""

from html import escape
import json
from pathlib import Path

from .catalog import REPO_NAME, timestamp
from .feed import build_feed


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
ASSETS = {"index.html": "index.html", "static/styles.css": "styles.css", "static/app.js": "app.js"}
SNAPSHOTS = {"site", "projects", "problems", "matches", "health", "observations", "coordination", "outreach"}
EXPORT_FILES = {*ASSETS, "api.html", "feed.xml", ".nojekyll", *(f"data/{name}.json" for name in SNAPSHOTS)}


def docs_page():
    docs = escape((ROOT / "API.md").read_text(encoding="utf-8"))
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PortBridge API</title><link rel="stylesheet" href="./static/styles.css"></head>
<body><main class="api-documentation"><p><a href="./">← Вернуться в PortBridge</a></p><pre>{docs}</pre></main></body></html>
'''


def output_path(directory):
    directory = Path(directory).expanduser().resolve()
    if directory == ROOT or directory in ROOT.parents or directory == PACKAGE or PACKAGE in directory.parents:
        raise ValueError("export must use a separate output directory")
    if directory.is_dir():
        allowed_dirs = {"data", "static"}
        for child in directory.iterdir():
            if child.is_symlink() or (hasattr(child, "is_junction") and child.is_junction()):
                raise ValueError("export directory contains a link")
            if child.is_dir() and child.name in allowed_dirs:
                for entry in child.iterdir():
                    if entry.is_symlink() or not entry.is_file() or f"{child.name}/{entry.name}" not in EXPORT_FILES:
                        raise ValueError("export directory contains files outside PortBridge's public snapshot")
            elif not child.is_file() or child.name not in EXPORT_FILES:
                raise ValueError("export directory contains files outside PortBridge's public snapshot")
    return directory


def export(catalog, directory, repository=""):
    if repository and not REPO_NAME.fullmatch(repository):
        raise ValueError("--repository expects a GitHub owner/repo")
    directory = output_path(directory)
    data = {
        "site": {"name": "PortBridge", "api_version": 1, "mode": "snapshot", "generated_at": timestamp(),
                 "repository": repository or None, "issue_template": "evidence.yml"},
        "projects": {"projects": catalog.projects()},
        "problems": {"problems": catalog.problems()},
        "matches": {"matches": catalog.matches(limit=200)},
        "health": catalog.health(),
        "observations": {"observations": catalog.observations(limit=None)},
        "coordination": {"coordination": catalog.coordination()},
        "outreach": {"drafts": catalog.outreach()},
    }
    contents = {f"data/{name}.json": json.dumps(value, ensure_ascii=False).encode("utf-8")
                for name, value in data.items()}
    contents.update({path: (PACKAGE / "static" / source).read_bytes() for path, source in ASSETS.items()})
    contents["api.html"] = docs_page().encode("utf-8")
    contents["feed.xml"] = build_feed(catalog)
    contents[".nojekyll"] = b""
    for path, value in contents.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    return directory
