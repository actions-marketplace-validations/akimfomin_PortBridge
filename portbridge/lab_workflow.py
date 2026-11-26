"""Opt-in Lab actions. Authentication is provided by the existing local Exchange."""

import json
import re
import time
from urllib.parse import urlsplit

from .catalog import public_url
from .exchange import Conflict, PermissionDenied
from .github import TOKEN_PATTERN
from .identity import stable_id
from .matching import canonical_url
from .radar_scan import HASH, candidate, draft_task, expire_claims, record_candidate
from .radar_store import (KEY, SCHEMA, TASK_TYPES, active_claim, encode, event, phase,
                          public_task_rows, recent, timestamp)

REVIEW_ACTIONS = {"queue", "review", "recheck", "deliver", "adopt", "decline", "withdraw_task"}
AUTHOR_ACTIONS = {"propose", "claim", "release", "submit", "correct", "withdraw_report", "profile"}
OUTCOMES = ("PASS", "FAIL", "SKIP", "ERROR")
EQUIPMENT = ("amd", "nvidia", "intel", "cpu")
REPORT_FIELDS = {"revisions", "environment", "equipment", "commands", "outcome", "expected", "observed",
                 "artifact_sha256", "source_url", "limitations", "ai_assistance", "share_public"}
REQUEST = re.compile(r"^[a-zA-Z0-9_-]{8,80}$")


def text(value, name, maximum, *, optional=False):
    if (not isinstance(value, str) or len(value) > maximum or (not optional and not value.strip())
            or TOKEN_PATTERN.search(value) or "\x00" in value):
        raise ValueError(f"Invalid {name}")
    return value.strip()


def source_url(value):
    if not public_url(value) or len(value) > 360:
        raise ValueError("Use a public GitHub permalink")
    return value


def actor_key(identity):
    # The Exchange ID is stable, while the display name can be consent-managed.
    return stable_id("local-volunteer", identity["id"], identity["name"].casefold())


def lookup_task(db, ident):
    if not isinstance(ident, str) or not KEY.fullmatch(ident):
        raise ValueError("Use a Lab task ID")
    row = db.execute("""SELECT t.*, c.payload AS candidate_payload, c.generation AS current_generation
                      FROM radar_tasks t JOIN radar_candidates c ON t.candidate=c.id WHERE t.id=?""",
                     (ident,)).fetchone()
    if row is None:
        raise LookupError("Unknown Lab task")
    return row


def pinned_task(task, now):
    card = json.loads(task["candidate_payload"])
    if task["generation"] != task["current_generation"] or not recent(card, now) or task["state"] in {"stale", "withdrawn"}:
        raise Conflict("Source revision or freshness changed. Recheck the task before claiming or reviewing.")
    return json.loads(task["payload"]), card


def release(db, task, claim, now, reason):
    db.execute("UPDATE radar_claims SET ended=?,reason=? WHERE id=? AND ended IS NULL",
               (now, reason, claim["id"]))


def source_team(value):
    return "/".join(urlsplit(value).path.lower().split("/")[1:3])


def form_report(payload, card):
    if not isinstance(payload, dict) or payload.keys() - REPORT_FIELDS:
        raise ValueError("Unknown report fields")
    result = {}
    for field, size in {"environment": 400, "equipment": 180, "commands": 1000, "expected": 500, "observed": 500,
                        "limitations": 500, "ai_assistance": 160}.items():
        result[field] = text(payload.get(field, ""), field, size, optional=True)
    outcome = payload.get("outcome")
    if outcome not in OUTCOMES:
        raise ValueError("Use PASS, FAIL, SKIP or ERROR")
    revisions = payload.get("revisions", [])
    if (not isinstance(revisions, list) or len(revisions) > 4 or any(not isinstance(x, str) or not HASH.fullmatch(x)
                                                                   for x in revisions)):
        raise ValueError("Report revisions must be full lowercase commit IDs")
    expected = {pin["sha"] for pin in card["revisions"]}
    if revisions and set(revisions) != expected:
        raise Conflict("Report pins do not match the task revision")
    artifact = payload.get("artifact_sha256", "")
    if not isinstance(artifact, str) or artifact and not re.fullmatch(r"[a-f0-9]{64}", artifact):
        raise ValueError("Invalid artifact SHA-256")
    link = payload.get("source_url", "")
    if link:
        source_url(link)
    visibility = payload.get("share_public", False)
    if type(visibility) is not bool:
        raise ValueError("share_public must be a boolean")
    complete = set(revisions) == expected and bool(link and artifact and all(
        result[field] for field in ("environment", "commands", "expected", "observed", "limitations", "ai_assistance")))
    result.update(revisions=revisions, outcome=outcome, artifact_sha256=artifact, source_url=link, share_public=visibility)
    return result, "valid_format" if complete else "incomplete"


def report_row(db, task, report_id):
    if not isinstance(report_id, str) or len(report_id) > 85:
        raise ValueError("Use a report ID")
    row = db.execute("SELECT * FROM radar_reports WHERE id=? AND task=?", (report_id, task["id"])).fetchone()
    if row is None:
        raise LookupError("Unknown Lab report")
    return row


def propose(db, args, now):
    from .catalog import OBSERVATION_KIND

    a, b = (source_url(args.get(field)) for field in ("target_url", "comparison_url"))
    if canonical_url(a) == canonical_url(b) or source_team(a) == source_team(b):
        raise ValueError("Use two different public project sources")
    pins = args.get("revisions")
    if (not isinstance(pins, list) or len(pins) != 2
            or any(not isinstance(pin, str) or not HASH.fullmatch(pin) for pin in pins)):
        raise ValueError("Provide two revisions")
    if args.get("kind") not in TASK_TYPES:
        raise ValueError("Use a supported Lab task type")
    expected = text(args.get("expected"), "expected", 500)
    title = text(args.get("title"), "title", 180)
    chosen = []
    for url, pin, role in zip((a, b), pins, ("target", "comparison")):
        observation = db.execute("""SELECT * FROM observations WHERE lower(url)=? ORDER BY fetched_at DESC LIMIT 1""",
                                 (url.lower(),)).fetchone()
        if not observation or observation["kind"] not in OBSERVATION_KIND:
            raise Conflict("Index the public sources before proposing a Lab task")
        item = dict(observation)
        item["metadata"] = json.loads(item["metadata"])
        from .radar_scan import evidence_source
        entry = evidence_source(item, role, {})
        if entry["revision"] != pin:
            raise Conflict("Proposal pins changed")
        chosen.append(entry)
    card = candidate(*chosen, "team_request", "review", [], title)
    existing = db.execute("SELECT generation FROM radar_candidates WHERE id=?", (card["id"],)).fetchone()
    if existing:
        raise Conflict("This pair is already tracked")
    record_candidate(db, card, now)
    task = draft_task(card)
    task.update(title=title, expected=expected, kind=args["kind"])
    equipment = args.get("equipment", ["cpu"])
    if not isinstance(equipment, list) or not equipment or any(x not in EQUIPMENT for x in equipment):
        raise ValueError("Provide public hardware categories")
    os_list = args.get("os", ["Any"])
    if not isinstance(os_list, list) or not os_list or any(x not in ("Any", "Windows", "Linux", "macOS") for x in os_list):
        raise ValueError("Provide supported operating systems")
    task.update(equipment=sorted(set(equipment)), os=sorted(set(os_list)))
    db.execute("INSERT INTO radar_tasks VALUES(?,?,?,'draft',1,?)",
               (task["id"], card["id"], card["generation"], encode(task)))
    return task["id"], card["id"]


def apply(catalog, exchange, token, action, args, *, now=None):
    if action not in REVIEW_ACTIONS | AUTHOR_ACTIONS or not isinstance(args, dict):
        raise ValueError("Unknown Lab action")
    identity = exchange.authenticate(token)
    if ("review" if action in REVIEW_ACTIONS else "contribute") not in identity["scopes"]:
        raise PermissionDenied("This Lab action requires the proper scope")
    actor = actor_key(identity)
    now = int(time.time() if now is None else now)
    request = args.get("request_id")
    if not isinstance(request, str) or not REQUEST.fullmatch(request):
        raise ValueError("Provide a stable request_id of 8 to 80 characters")
    ident = args.get("task")
    event_id = stable_id("radar-event", actor, action, ident, None, request)
    input_id = stable_id("lab-request", args)
    with catalog.connect() as db:
        db.executescript(SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT payload FROM radar_events WHERE id=?", (event_id,)).fetchone()
        if old is not None:
            value = json.loads(old["payload"])
            if value["input_id"] != input_id:
                raise Conflict("Repeated request has different contents")
            return value["result"]
        expire_claims(db, now)
        if action == "profile":
            result = preference(db, actor, args)
            candidate_id = None
        elif action == "propose":
            task_id, candidate_id = propose(db, args, now)
            result = {"task": task_id, "state": "draft"}
        else:
            task = lookup_task(db, ident)
            candidate_id = task["candidate"]
            result = act(db, task, actor, now, action, args)
        event(db, actor=actor, action=action, now=now, task=ident, candidate=None,
              request=request, details={"input_id": input_id, "result": result, "candidate_id": candidate_id})
        return result


def preference(db, actor, args):
    enabled = args.get("enabled")
    if type(enabled) is not bool:
        raise ValueError("Set enabled true or false")
    if not enabled:
        db.execute("DELETE FROM radar_preferences WHERE actor=?", (actor,))
        return {"enabled": False}
    equipment = args.get("equipment")
    if not isinstance(equipment, list) or not equipment or any(x not in EQUIPMENT for x in equipment):
        raise ValueError("Provide opt-in hardware categories")
    os = args.get("os", "Any")
    if os not in ("Any", "Windows", "Linux", "macOS"):
        raise ValueError("Provide a supported operating system")
    specialty = text(args.get("specialty", ""), "specialty", 60, optional=True)
    payload = {"enabled": True, "equipment": sorted(set(equipment)), "os": os, "specialty": specialty}
    db.execute("REPLACE INTO radar_preferences VALUES(?,?)", (actor, encode(payload)))
    return payload


def act(db, task, actor, now, action, args):
    state = task["state"]
    claim = active_claim(db, task, now)
    report_id = None
    details = {}
    if action == "queue":
        _, card = pinned_task(task, now)
        if state != "draft" or card["confidence"] == "research":
            raise Conflict("Only pinned drafts with an actionable link may be queued")
        details["note"] = text(args.get("note"), "review note", 300)
        state = "queued"
    elif action == "claim":
        pinned_task(task, now)
        if state not in ("queued", "claimed") or claim and claim["actor"] != actor:
            raise Conflict("This round is unavailable")
        if task["round"] > 1 and db.execute("SELECT 1 FROM radar_reports WHERE task=? AND actor=? AND round<?",
                                           (task["id"], actor, task["round"])).fetchone():
            raise Conflict("Independent verification needs a different volunteer")
        duration = args.get("ttl_seconds", 86400)
        if type(duration) is not int or not 60 <= duration <= 604800:
            raise ValueError("Claim duration must be between 60 and 604800 seconds")
        if claim is None:
            active = db.execute("SELECT count(*) FROM radar_claims WHERE actor=? AND ended IS NULL AND expires>?",
                                (actor, now)).fetchone()[0]
            if active >= 4:
                raise Conflict("Up to four active tasks per volunteer")
            db.execute("INSERT INTO radar_claims(task,generation,round,actor,opened,expires) VALUES(?,?,?,?,?,?)",
                       (task["id"], task["generation"], task["round"], actor, now, now + duration))
        state = "claimed"
        details["expires_at"] = timestamp(claim["expires"] if claim else now + duration)
    elif action == "release":
        if not claim or claim["actor"] != actor:
            raise PermissionDenied("Only the volunteer may release their claim")
        release(db, task, claim, now, "released")
        state = "queued"
    elif action in ("submit", "correct", "withdraw_report"):
        if action == "submit" and (state != "claimed" or not claim or claim["actor"] != actor):
            raise PermissionDenied("Claim this task before submitting a report")
        if action != "submit":
            previous = report_row(db, task, args.get("report_id"))
            if previous["actor"] != actor or previous["state"] in ("superseded", "withdrawn"):
                raise PermissionDenied("Only the author can change the current report")
            if action == "correct" and previous["generation"] != task["generation"]:
                raise Conflict("Correction requires the same revision")
            db.execute("UPDATE radar_reports SET state=? WHERE id=?",
                       ("superseded" if action == "correct" else "withdrawn", previous["id"]))
            details["supersedes"] = previous["id"]
        if action != "withdraw_report":
            card, _ = pinned_task(task, now)
            payload, report_state = form_report(args.get("report"), card)
            report_id = stable_id("lab-report", task["id"], task["generation"], actor, args["request_id"])
            db.execute("INSERT INTO radar_reports VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
                       (report_id, task["id"], task["generation"], task["round"], actor, "submitted", encode(payload), now))
            event(db, actor=actor, action="report_submitted", now=now, task=task["id"], candidate=task["candidate"],
                  details={"report_id": report_id, "generation": task["generation"], "round": task["round"]})
            db.execute("UPDATE radar_reports SET state=? WHERE id=?", (report_state, report_id))
            details["report_status"] = report_state
            if claim and claim["actor"] == actor:
                release(db, task, claim, now, "submitted")
            state = "investigated"
        elif previous["generation"] == task["generation"]:
            state = "investigated" if db.execute("""SELECT 1 FROM radar_reports WHERE task=? AND generation=?
                         AND state IN ('valid_format','reviewed','reproduced','incomplete') LIMIT 1""",
                      (task["id"], task["generation"])).fetchone() else "queued"
    elif action == "review":
        report = report_row(db, task, args.get("report_id"))
        if report["actor"] == actor:
            raise PermissionDenied("Report authors cannot review their own reports")
        if (state == "withdrawn" or report["generation"] != task["generation"]
                or report["state"] not in {"incomplete", "valid_format"}):
            raise Conflict("Review requires a current submitted report")
        note = text(args.get("note"), "review evidence", 500)
        decision = args.get("decision")
        if decision not in ("reviewed", "reproduced", "rejected"):
            raise ValueError("Unsupported review decision")
        outcome = json.loads(report["payload"])["outcome"]
        previous_reports = db.execute("""SELECT actor,payload FROM radar_reports WHERE task=? AND generation=? AND round<?
                         AND actor!=? AND state IN ('reviewed','reproduced')""",
                         (task["id"], task["generation"], report["round"], report["actor"])).fetchall()
        conflict = any({outcome, json.loads(item["payload"])["outcome"]} == {"PASS","FAIL"} for item in previous_reports)
        if decision != "rejected":
            pinned_task(task, now)
            if report["state"] != "valid_format" or args.get("checked_artifact") is not True:
                raise Conflict("An authorized reviewer must check an actual artifact before confirming evidence")
            if decision == "reproduced":
                if not previous_reports or conflict or not any(json.loads(item["payload"])["outcome"] == outcome
                                                            for item in previous_reports):
                    raise Conflict("Reproduction requires an independently observed matching outcome")
        db.execute("UPDATE radar_reports SET state=?,reviewer=?,reviewed=?,note=? WHERE id=?",
                   (decision, actor, now, note, report["id"]))
        state = ("investigated" if conflict and decision != "rejected" else
                 "tested" if decision != "rejected" and outcome in {"PASS", "FAIL"}
                 else "rejected" if decision == "rejected" else "queued")
        if args.get("hypothesis_rejected") is True:
            if decision != "reviewed" or outcome != "FAIL" or conflict:
                raise Conflict("Reject a hypothesis using an independently reviewed negative result")
            state = "rejected"
            details["hypothesis_rejected"] = True
        if conflict and decision != "rejected":
            details["conflicting_results"] = True
        report_id = report["id"]
        details["report_status"] = decision
    elif action == "recheck":
        pinned_task(task, now)
        if state not in {"tested", "rejected"}:
            raise Conflict("Finish the previous review round first")
        details["note"] = text(args.get("note"), "reason for the independent run", 300)
        db.execute("UPDATE radar_tasks SET round=round+1 WHERE id=?", (task["id"],))
        state = "queued"
    elif action in {"deliver", "adopt", "decline"}:
        card, _ = pinned_task(task, now)
        evidence = source_url(args.get("evidence_url"))
        required = "tested" if action == "deliver" else "delivered"
        if state != required:
            raise Conflict(f"This action requires {required}")
        destination = urlsplit(evidence)
        path = destination.path.rstrip("/")
        message = (re.fullmatch(r"/[^/]+/[^/]+/(?:issues|pull|discussions)/[0-9]+", path)
                   and re.fullmatch(r"(?:issuecomment-|discussioncomment-|discussion_r|pullrequestreview-)[0-9]+",
                                    destination.fragment))
        change = re.fullmatch(r"/[^/]+/[^/]+/(?:commit/[a-f0-9]{40}|pull/[0-9]+)", path)
        if (source_team(evidence) != source_team(card["receiving_url"]) or args.get("checked_artifact") is not True
                or not (message or action == "adopt" and change and canonical_url(evidence) != canonical_url(card["receiving_url"]))):
            raise ValueError("Record the exact message or acceptance in the receiving repository")
        details.update(evidence_url=evidence, note=text(args.get("note"), "receiving decision", 400))
        state = {"deliver": "delivered", "adopt": "adopted", "decline": "rejected"}[action]
    else:
        details["note"] = text(args.get("note"), "withdrawal reason", 300)
        if claim:
            release(db, task, claim, now, "withdrawn")
        state = "withdrawn"
    phase(db, task, state, now)
    return {"task": task["id"], "state": state, "report_id": report_id, **details}

def dashboard(catalog, exchange, token, *, task_id="", now=None):
    identity = exchange.authenticate(token)
    actor = actor_key(identity)
    now = int(time.time() if now is None else now)
    from .radar_store import present
    with catalog.connect() as db:
        if not present(db):
            return {"profile": {"enabled": False}, "digest": [], "reports": []}
        saved = db.execute("SELECT payload FROM radar_preferences WHERE actor=?", (actor,)).fetchone()
        profile = json.loads(saved[0]) if saved else {"enabled": False}
        cards = [
            card for card in public_task_rows(db, now)
            if card["workflow_state"] == "queued" and profile["enabled"]
            and set(card["equipment"]).intersection(profile["equipment"])
            and (profile["os"] in ("Any", *card["os"]) or "Any" in card["os"])
            and (not profile["specialty"] or card["specialty"] == profile["specialty"])
        ][:12]
        tasks = {"profile": profile, "digest": cards, "reports": []}
        if task_id:
            task = lookup_task(db, task_id)
            reviewer = "review" in identity["scopes"]
            reports = db.execute("""SELECT id,actor,reviewer,state,payload,note,round,submitted,reviewed FROM radar_reports
                   WHERE task=? AND (? OR actor=?) ORDER BY submitted DESC LIMIT 60""",
                   (task_id, reviewer, actor)).fetchall()
            tasks["reports"] = [{**dict(row), "payload": json.loads(row["payload"])} for row in reports]
            claim = active_claim(db, task, now)
            tasks["claim"] = {"mine": bool(claim and claim["actor"] == actor),
                              "expires_at": timestamp(claim["expires"]) if claim else None}
            approved = next((row for row in tasks["reports"] if row["state"] in {"reviewed", "reproduced"}
                             and row["payload"]["outcome"] in {"PASS", "FAIL"}), None)
            if approved:
                payload = approved["payload"]
                tasks["handoff_draft"] = (f"Lab {task_id} | {payload['outcome']} | {payload['source_url']}\n"
                                           + f"Revisions: {', '.join(payload['revisions'])}\n"
                                           + f"Observed: {payload['observed']}\nLimits: {payload['limitations']}\n"
                                           + f"Attribution: volunteer {approved['actor']}; reviewer {approved['reviewer']}.")
        return tasks


def main():
    import argparse
    import os
    from pathlib import Path
    from .__main__ import DEFAULT_DB, DEFAULT_SEED
    from .catalog import Catalog
    from .exchange import Exchange, AuthError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--exchange-db", type=Path, required=True)
    parser.add_argument("action", choices=sorted(REVIEW_ACTIONS | AUTHOR_ACTIONS | {"dashboard"}))
    parser.add_argument("--file", type=Path)
    parser.add_argument("--task", default="")
    args = parser.parse_args()
    if args.db.resolve() == args.exchange_db.resolve() or not args.exchange_db.is_file():
        parser.error("Use an existing, separate Exchange database")
    token = os.environ.get("PORTBRIDGE_EXCHANGE_TOKEN")
    try:
        catalog = Catalog(args.db, DEFAULT_SEED)
        exchange = Exchange(args.exchange_db)
        if args.action == "dashboard":
            result = dashboard(catalog, exchange, token, task_id=args.task)
        elif not args.file:
            parser.error("Provide an action JSON file")
        else:
            with args.file.open("rb") as stream:
                raw = stream.read(65537)
            if len(raw)>65536:
                raise ValueError("Action JSON exceeds 64 KiB")
            result = apply(catalog, exchange, token, args.action, json.loads(raw))
    except (OSError, ValueError, AuthError, Conflict, PermissionDenied, LookupError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
