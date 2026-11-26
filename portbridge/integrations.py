"""Public partner feed and optional client-side pull subscription."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlencode

from .catalog import public_url
from .consoles import CONSOLES
from .identity import stable_id
from .radar_store import epoch, timestamp

SCHEMA = 1
SNAPSHOT_TTL = 48 * 3600
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,60}")
KEY = re.compile(r"[A-Za-z0-9-]{1,80}")
EVENTS = {"task", "result"}


def projection(projects, lab, impact, *, as_of):
    aliases = {project["slug"]: project["repo"].lower() for project in projects}
    by_repo = {repo: slug for slug, repo in aliases.items()}
    items = {}
    for task in lab["tasks"]:
        state = task.get("workflow_state")
        if state and (state != "queued" or task.get("age_state") != "fresh"):
            continue
        if not state and task.get("status") != "needs_run":
            continue
        ident, source = task.get("id"), task.get("source_url")
        if not KEY.fullmatch(ident or "") or not public_url(source) or not task.get("revisions"):
            continue
        labels = [row for row in task.get("projects", []) if row in aliases]
        tags = sorted(set(task.get("consoles") or (console for project in projects if project["slug"] in labels
                        for console in project.get("consoles", []))))
        items["task:" + ident] = {
            "id": "task:" + ident, "kind": "task", "title": task["title"],
            "state": "available" if state else "check_source",
            "projects": labels, "repositories": [aliases[key] for key in labels],
            "consoles": tags, "equipment": task.get("equipment", []), "source": source,
            "revisions": [pin["sha"] for pin in task["revisions"]], "generation": task.get("generation"),
            "link": "#/lab?" + urlencode({"task": ident}),
        }
    for item in impact["stories"]:
        if item["state"] not in {"reviewed", "accepted"}:
            continue
        proofs = list(dict.fromkeys(entry["url"] for entry in item["sources"] if public_url(entry["url"])))
        if not proofs:
            continue
        repos = sorted({"/".join(link.casefold().split("/")[3:5]) for link in [*proofs, *item.get("related", [])]
                        if public_url(link)})
        ident = stable_id("result", item["id"])
        items[ident] = {"id": ident, "kind": "result", "state": item["state"], "title": item["title"],
                        "projects": [by_repo[repo] for repo in repos if repo in by_repo], "repositories": repos,
                        "consoles": item.get("consoles", []), "source": proofs[0], "proofs": proofs[:6],
                        "at": item.get("at") or None,
                        "link": "#/impact?" + urlencode({"target": item.get("related", proofs)[0] if item.get("related") else proofs[0]})}
    rows = sorted(items.values(), key=lambda row: (row["kind"] != "task", row["id"]))
    return {"schema_version": SCHEMA, "generated_at": as_of, "attribution": "PortBridge · public primary sources",
            "counts": dict(Counter(row["kind"] for row in rows)), "items": rows}


def select(feed, *, project="", console="", kind="", limit=None):
    if (project and not SLUG.fullmatch(project) or console and console not in CONSOLES
            or kind and kind not in EVENTS or limit is not None and (type(limit) is not int or not 1 <= limit <= 100)):
        raise ValueError("Invalid partner feed filters")
    rows = [row for row in feed["items"] if (not project or project in row["projects"])
            and (not console or console in row["consoles"]) and (not kind or kind == row["kind"])]
    return {**feed, "items": rows[:limit], "total": len(rows)}


def public_feed(catalog, *, now=None):
    from .community import people
    from .lab import build_lab

    now = int(time.time() if now is None else now)
    lab = build_lab(catalog, now=now)
    _, impact = people(catalog, now=now, lab=lab)
    return projection(catalog.projects(), lab, impact, as_of=timestamp(now))


def digest(feed, previous, *, project="", console="", kind="", now=None):
    now = int(time.time() if now is None else now)
    as_of = epoch(feed.get("generated_at"))
    if (feed.get("schema_version") != SCHEMA or not as_of or as_of > now + 120
            or now - as_of > SNAPSHOT_TTL or as_of < epoch(previous.get("generated_at"))):
        return {"state": "stale_or_invalid", "added_or_changed": [], "no_longer_listed": []}, None
    scope = {"project": project, "console": console, "kind": kind}
    if previous and previous.get("scope") != scope:
        raise ValueError("Use a separate subscription cursor for each set of filters")
    rows = select(feed, **scope)["items"]
    signatures = {row["id"]: sha256(json.dumps(row, sort_keys=True).encode()).hexdigest() for row in rows}
    old = previous.get("items", {})
    return {"state": "available", "added_or_changed": [row for row in rows if old.get(row["id"]) != signatures[row["id"]]],
            "no_longer_listed": sorted(old.keys() - signatures.keys())}, {
            "generated_at": feed["generated_at"], "scope": scope, "items": signatures}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--snapshot", type=Path, help="read a locally exported partner.json")
    source.add_argument("--db", type=Path, help="read the existing local catalog")
    parser.add_argument("--cursor", type=Path, help="write a local cursor only after a usable pull")
    parser.add_argument("--project", default="")
    parser.add_argument("--console", default="")
    parser.add_argument("--kind", default="")
    args = parser.parse_args(argv)
    try:
        if args.cursor and args.snapshot and args.cursor.resolve() == args.snapshot.resolve():
            raise ValueError("Use a different path for the cursor")
        if args.snapshot:
            feed = json.loads(args.snapshot.read_bytes())
        elif args.db:
            from .catalog import ReadOnlyCatalog
            with ReadOnlyCatalog(args.db).read_view() as view:
                feed = public_feed(view)
        else:
            from .preflight import snapshot
            feed = snapshot("partner")
        filters = {"project": args.project, "console": args.console, "kind": args.kind}
        if args.cursor:
            previous = json.loads(args.cursor.read_bytes()) if args.cursor.is_file() else {}
            payload, update = digest(feed, previous, **filters)
            if update is not None:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.cursor.parent, delete=False) as stream:
                    output = Path(stream.name)
                    json.dump(update, stream, ensure_ascii=True)
                output.replace(args.cursor)
        else:
            payload = select(feed, **filters)
    except OSError:
        payload = {"state": "unavailable", "added_or_changed": [], "no_longer_listed": []}
    except (KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
