"""Evidence-backed People profiles, technical graph and Impact projections."""
from collections import Counter, defaultdict
import json
import re
import time

from .catalog import public_url, source_sync_failed
from .community_sources import DATA, LOGIN, TECH, captured, evidence_key, fact, repository, topics
from .consoles import console_families
from .discovery_scan import cached_index
from .identity import contributor_id, stable_id
from .matching import source_revision
from .radar_store import epoch, public_outcome_receipts, radar_view, reviewed_snapshot, timestamp

KINDS = {
    "repository_owner": "official", "maintainer": "official", "lead": "official",
    "developer": "observed", "reviewer": "observed", "researcher": "observed",
    "technical_discussion": "observed", "hardware_tester": "observed", "tester": "observed",
    "coordinator": "observed", "infrastructure_author": "observed", "bridge": "observed",
}
DISPLAY_EVIDENCE = 6
DEFAULT_LIMIT = 24
REPORT_WINDOW = 30 * 86400
ROLE_WINDOW = 90 * 86400
HEX = re.compile(r"[a-f0-9]{40,64}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def read_data(name):
    return json.loads((DATA / name).read_bytes())


def participant(login, user_id=None):
    if not isinstance(login, str) or not LOGIN.fullmatch(login):
        return None
    return {"login": login, "user_id": user_id if type(user_id) is int and user_id > 0 else None}


def record_facts(observations, tracked):
    for row in observations:
        meta = row["metadata"]
        url = row["url"]
        repo = repository(url)
        if not repo or meta.get("author_type") in {"Bot", "Organization", "Mannequin"}:
            continue
        subject = EMAIL.sub("[contact omitted]", row["title"])
        technical = topics(subject, " ".join((meta.get("technical") or {}).get("signals", [])))
        kind = row["kind"]
        if kind in {"pr", "commit"}:
            # An unlinked Git commit author string is free text.
            if kind == "commit" and not meta.get("github_user_id"):
                continue
            role = "infrastructure_author" if technical == ["infrastructure"] else "developer"
        elif kind == "issue" and technical and meta.get("github_user_id"):
            role = "researcher"
        else:
            continue
        person = participant(meta.get("author"), meta.get("github_user_id"))
        at = meta.get("created_at") or row["updated_at"]
        basis = {"pr": "Authored public pull request", "commit": "Attributed public commit", "issue": "Opened technical issue"}[kind]
        if item := fact(url, url, person, at, role, basis, technical, title=subject[:180], kind=kind,
                        revision=source_revision(row), status=row["status"],
                        checked_at=row["fetched_at"], source_state="stale" if source_sync_failed(tracked.get(repo, {}), url)
                        else "available"):
            yield item
        if (kind == "pr" and row["status"] == "merged" and (merged := meta.get("merged_by"))
                and (who := participant(merged.get("login"), merged.get("user_id")))):
            if related := fact(url, url, who, meta.get("merged_at"), "repository_action", "GitHub lists this account as merger",
                               technical, revision=source_revision(row)):
                related["role"] = "repository_action"
                yield related


def historical_facts(index):
    for row in index.get("entries", []):
        source = row.get("source")
        if not public_url(source):
            continue
        for author in row.get("authors", []):
            # Free-form credited names stay in Discovery. Only explicitly
            # checked GitHub identities from published receipts become People.
            if isinstance(author, dict) and author.get("github_url") == f"https://github.com/{author.get('login')}":
                if item := fact(source, source, participant(author["login"], author.get("user_id")), row.get("reviewed_on"),
                                "researcher", "Linked external Discovery authorship", topics(row.get("title")),
                                kind="discovery", revision=row.get("revision")):
                    yield {**item, "id": stable_id("community-fact", evidence_key(source), item["role"], author["login"].casefold())}
    for origin, scan in index.get("automatic", {}).items():
        for row in scan.get("matches", []):
            if not (who := row.get("author")):
                continue
            if item := fact(row["source"], row["source"], participant(who.get("login"), who.get("user_id")),
                            row.get("observed_at"), "researcher", "Author of external Discovery search result",
                            topics(row.get("title")), kind="discovery",
                            discovery_for=evidence_key(origin if origin.startswith("https://") else "https://" + origin),
                            source_state=scan.get("status", "unknown"), checked_at=row.get("retrieved_on")):
                yield item


def report_facts(lab):
    for task in lab["tasks"]:
        for row in task.get("report_sync", {}).get("reports", []):
            if row.get("state") in {"withdrawn", "retracted", "rejected", "invalid"}:
                continue
            source = row.get("url")
            if not public_url(source):
                continue
            setup = row.get("adapter") or row.get("configuration") or row.get("gpu") or ""
            hardware = setup if isinstance(setup, str) and setup and len(setup) < 90 and re.fullmatch(
                r"[\w .()/-]+", setup) else ""
            if item := fact(source.split("#")[0], source, participant(row.get("author"), row.get("author_id")),
                            row.get("reported_at"), "hardware_tester" if hardware else "tester",
                            "Public structured Lab report", topics(task.get("title")) + ["testing"],
                            kind="lab", task=task["id"], hardware=hardware, revision=row.get("revision"),
                            outcome=row.get("outcome"), checked_at=row.get("updated_at")):
                yield item


def curated_facts(records):
    for row in records:
        ident = row.get("actor") or {}
        if (who := participant(ident.get("login"), ident.get("user_id"))) and row.get("role") in KINDS:
            item = fact(row["subject"], row["source"], who, row["at"], row["role"], row["basis"],
                        row.get("specialties", []), **{key: row[key] for key in (
                            "hardware", "kind", "source_state", "checked_at", "revision", "title", "task",
                            "role_state", "discovery_for") if key in row})
            if item:
                yield item


class Identity:
    def __init__(self, events, policy):
        self.policy = policy
        self.ids = defaultdict(set)
        self.logins = {}
        for item in events:
            who = item["actor"]
            if who["user_id"]:
                ident = contributor_id(who["login"], who["user_id"])
                self.ids[who["login"].casefold()].add(ident)
                if (item["at"], who["login"]) > self.logins.get(ident, ("", "")):
                    self.logins[ident] = (item["at"], who["login"])
        self.hidden_ids = set(policy.get("hidden_ids", ()))
        self.hidden_logins = {value.casefold() for value in policy.get("hidden_logins", ())}
        for login in self.hidden_logins:
            self.hidden_ids.update(self.ids.get(login, ()))

    def identify(self, who):
        login = who["login"].casefold()
        if who["user_id"]:
            return contributor_id(login, who["user_id"])
        matches = self.ids.get(login, ())
        if len(matches) > 1:
            return None
        return next(iter(matches), contributor_id(login))

    def visible(self, who):
        ident = self.identify(who)
        return ident if ident and ident not in self.hidden_ids and who["login"].casefold() not in self.hidden_logins else None

    def display(self, ident, fallback):
        return self.logins.get(ident, (None, fallback))[1]


def apply_policy(events, policy):
    corrections = policy.get("corrections", {})
    source_checks = policy.get("source_checks", {})
    withdrawn = set(policy.get("withdrawn", ()))
    edited = {}
    for item in events:
        key = evidence_key(item["source"])
        if key in withdrawn or item["id"] in withdrawn:
            continue
        change = corrections.get(key)
        if change and ("roles" not in change or item["role"] in change["roles"]):
            author = change["actor"]
            updated = participant(author.get("login"), author.get("user_id"))
            if updated:
                item = {**item, "actor": updated, "correction": change["proof"]}
                if "specialties" in change:
                    item["specialties"] = change["specialties"]
        checked = source_checks.get(key)
        if checked and epoch(checked["at"]) > epoch(item.get("checked_at")):
            item = {**item, "source_state": checked["state"], "checked_at": checked["at"]}
        previous = edited.get(item["id"])
        if previous is None or (epoch(item.get("checked_at")), bool(item["actor"]["user_id"])) >= (
                epoch(previous.get("checked_at")), bool(previous["actor"]["user_id"])):
            edited[item["id"]] = item
    return list(edited.values())


def edge(kind, left, right, row, **extra):
    url = row["source"]
    return {"id": stable_id("people-edge", kind, left, right, evidence_key(url)), "kind": kind,
            "from": left, "to": right, "source": url, "at": row["at"], "basis": row["basis"], **extra}


def people_profiles(events, identity, platforms, now):
    authored = {}
    for item in events:
        if item.get("kind") == "pr" and (person := identity.visible(item["actor"])):
            authored[evidence_key(item["subject"])] = person
    profiles = {}
    for item in sorted(events, key=lambda x: (epoch(x["at"]), x["id"]), reverse=True):
        if not (ident := identity.visible(item["actor"])):
            continue
        login = identity.display(ident, item["actor"]["login"])
        profile = profiles.setdefault(ident, {"id": ident, "login": login, "url": f"https://github.com/{login}",
                                            "latest": None, "events": 0, "roles": {}, "projects": {},
                                            "specialties": {}, "evidence": [], "interactions": [], "hardware": []})
        if not profile["latest"] and item["role"] not in {"repository_owner", "maintainer", "lead"}:
            profile["latest"] = item["at"]
        profile["events"] += 1
        repo = item["repo"]
        event_freshness = "historical" if now - epoch(item["at"]) > ROLE_WINDOW else (
            "stale" if item.get("source_state", "available") not in {"available", "complete", "partial"} else "recent")
        proof = {key: item[key] for key in ("source", "at", "basis", "role", "repo")}
        proof.update({"age": item.get("role_state", event_freshness), "checked_at": item.get("checked_at"),
                      "source_state": item.get("source_state", "available")})
        for key in ("subject", "title", "revision", "correction", "task", "discovery_for"):
            if item.get(key):
                proof[key] = item[key]
        version = proof.get("revision")
        if version and (not isinstance(version, str) or not HEX.fullmatch(version)):
            proof.pop("revision")
        if len(profile["evidence"]) < DISPLAY_EVIDENCE:
            profile["evidence"].append(proof)
        project = profile["projects"].setdefault(repo, {"repo": repo, "count": 0, "consoles": platforms.get(repo, console_families(repo)),
                                                        "edge": edge("contributed_to", ident, repo, item), "current": False})
        project["current"] |= proof["age"] == "recent"
        project["count"] += 1
        if item["role"] in KINDS:
            k = (item["role"], repo)
            profile["roles"].setdefault(k, {**proof, "confidence": KINDS[item["role"]]})
        for specialty in item["specialties"]:
            if specialty not in TECH:
                continue
            segment = profile["specialties"].setdefault(specialty, {"name": specialty, "count": 0, "confidence": "inferred",
                                                                  "edge": edge("worked_on", ident, specialty, item)})
            segment["count"] += 1
        if item["role"] == "reviewer" and (other := authored.get(evidence_key(item["subject"]))) and other != ident:
            if len(profile["interactions"]) < DISPLAY_EVIDENCE:
                profile["interactions"].append(edge("reviewed_work_of", ident, other, item, subject=item["subject"]))
        if item.get("hardware") and item["hardware"] not in {entry["name"] for entry in profile["hardware"]}:
            if len(profile["hardware"]) < DISPLAY_EVIDENCE:
                profile["hardware"].append({"name": item["hardware"], "edge": edge("reported_hardware", ident, item["hardware"], item)})
    for profile in profiles.values():
        profile["projects"] = list(profile["projects"].values())
        profile["roles"] = list(profile["roles"].values())
        profile["specialties"] = sorted(profile["specialties"].values(), key=lambda x: (-x["count"], x["name"]))
        profile["consoles"] = sorted({c for project in profile["projects"] for c in project["consoles"]})
        profile["cross_platform"] = {"xbox-series", "ps5"} <= set(profile["consoles"])
        active = {c for project in profile["projects"] if project["current"] for c in project["consoles"]}
        profile["cross_platform_state"] = ("current" if {"xbox-series", "ps5"} <= active else "historical"
                                           if profile["cross_platform"] else None)
        profile["multi_project"] = len(profile["projects"]) > 1
        if profile["multi_project"]:
            support = profile["projects"][:2]
            profile["roles"].append({"role": "bridge", "confidence": "observed",
                "repo": support[0]["repo"], "at": support[0]["edge"]["at"],
                "source": support[0]["edge"]["source"], "other_source": support[1]["edge"]["source"],
                "basis": "Attributed technical work across public repositories",
                "age": "recent" if all(project["current"] for project in support) else "historical"})
        profile["activity"] = "recent" if now - epoch(profile["latest"]) <= ROLE_WINDOW else "historical"
    return sorted(profiles.values(), key=lambda row: (-epoch(row["latest"]), row["login"].casefold(), row["id"]))


def people(catalog, *, lab=None, radar=None, observations=None, projects=None, now=None, policy=None):
    now = int(time.time() if now is None else now)
    if observations is None:
        observations = catalog.observations(limit=None)
    if projects is None:
        projects = catalog.projects()
    if lab is None:
        from .lab import build_lab
        lab = build_lab(catalog)
    if radar is None:
        radar = radar_view(catalog, now, include_catalog=True)
    tracked = {repository("https://github.com/" + p["repo"]): p for p in projects}
    platforms = {key: p.get("consoles", []) for key, p in tracked.items()}
    extra, states = captured(catalog)
    config = read_data("impact_evidence.json")
    policy = read_data("people_policy.json") if policy is None else policy
    current_ids = {row["id"] for row in extra}
    historical = []
    for row in curated_facts(config["people"]):
        scope = states.get(f"review:{evidence_key(row['subject'])}") if row["role"] == "reviewer" else None
        if scope and scope["status"] == "complete" and row["id"] not in current_ids:
            continue
        if scope:
            row["source_state"] = scope["status"]
        historical.append(row)
    events = apply_policy([*record_facts(observations, tracked), *historical_facts(cached_index(catalog)),
                           *extra, *report_facts(lab), *historical], policy)
    identity = Identity(events, policy)
    profiles = people_profiles(events, identity, platforms, now)
    links = technical_links(radar, config, policy)
    for profile in profiles:
        profile["availability"] = next(({"source": entry["proof"], "until": entry["until"], "scope": entry["scope"]}
            for entry in policy.get("availability", []) if identity.visible(entry["actor"]) == profile["id"]
            and epoch(entry["until"]) > now), None)
    focus = {evidence_key(url) for row in links for url in (row["source"], row["comparison"])}
    target_index = defaultdict(dict)
    for item in events:
        subject = evidence_key(item["subject"])
        if subject in focus and (ident := identity.visible(item["actor"])):
            proof = {"source": item["source"], "at": item["at"], "basis": item["basis"], "role": item["role"]}
            if ident not in target_index[subject] or target_index[subject][ident]["at"] < proof["at"]:
                target_index[subject][ident] = proof
    scope = {"tracked_projects": len(tracked), "projects_with_actor_evidence": len({e["repo"] for e in events} & tracked.keys()),
             "observed_events": sum(profile["events"] for profile in profiles), "people": len(profiles),
             "multi_project": sum(p["multi_project"] for p in profiles),
             "cross_platform_people": sum(p["cross_platform"] for p in profiles),
             "source_scopes": len(states), "source_states": dict(Counter(row["status"] for row in states.values())),
             "links": len(links), "project_edges": sum(len(p["projects"]) for p in profiles),
             "technical_interactions": sum(len(p["interactions"]) for p in profiles)}
    secured = {evidence_key(item["source"]): identity.visible(item["actor"]) for item in events}
    result = {"as_of": timestamp(now), "profiles": profiles, "connections": links, "scope": scope,
              "target_index": target_index,
              "filters": {"projects": sorted({row["repo"] for profile in profiles for row in profile["projects"]}),
                          "specialties": list(TECH)},
              "sensitivities": "Public professional activity. Availability requires a separate opt-in."}
    return result, build_impact(catalog, config, policy, identity, radar, secured, now)


def technical_links(radar, config, policy):
    withdrawn = set(policy.get("withdrawn", []))
    links = {}
    for card in radar.get("catalog", radar["candidates"]):
        if card["state"] == "withdrawn":
            continue
        a, b = card["sources"]
        ra, rb = repository(a["url"]), repository(b["url"])
        if not ra or not rb or ra == rb or withdrawn.intersection(map(evidence_key, (a["url"], b["url"]))):
            continue
        links[card["id"]] = {"id": card["id"], "from": ra, "to": rb, "kind": card["kind"],
            "source": a["url"], "comparison": b["url"], "at": card["updated_at"], "basis": card["reason"],
            "state": "historical" if card["state"] == "stale" else "potential" if card["confidence"] != "research" else "research",
            "task": card["task_id"],
            "consoles": card["consoles"], "specialty": card["specialty"]}
    for case in config["stories"]:
        if len(case.get("related", [])) >= 2 and case["state"] not in {"withdrawn", "pending"} and not withdrawn.intersection(
                (case["id"], *(evidence_key(link["url"]) for link in case["sources"]))):
            row = case["related"]
            if repository(row[0]) == repository(row[1]):
                continue
            links[case["id"]] = {"id": case["id"], "from": repository(row[0]), "to": repository(row[1]),
                "kind": case["type"], "source": row[0], "comparison": row[1], "at": case["at"], "basis": case["summary"],
                "state": case["state"], "consoles": case["consoles"], "specialty": case["specialty"]}
    for row in config.get("research_links", []):
        if row["id"] not in withdrawn and not withdrawn.intersection(map(evidence_key, (row["source"], row["comparison"]))):
            links[row["id"]] = row
    distinct = {}
    order = {"accepted": 0, "reviewed": 1, "research": 2, "potential": 2, "historical": 3}
    for row in sorted(links.values(), key=lambda row: (order.get(row["state"], 2), row["id"])):
        pair = tuple(sorted(map(evidence_key, (row["source"], row["comparison"]))))
        distinct.setdefault(pair, row)
    return sorted(distinct.values(), key=lambda row: (row["state"] == "historical", -epoch(row["at"]), row["id"]))


def build_impact(catalog, config, policy, identity, radar, secured, now):
    withdrawn = set(policy.get("withdrawn", []))
    stories, credits, metrics = [], {}, defaultdict(set)
    for case in config["stories"]:
        if case["id"] in withdrawn or case["state"] in {"withdrawn", "pending"}:
            continue
        sources = [row for row in case["sources"] if public_url(row["url"]) and evidence_key(row["url"]) not in withdrawn]
        if len(sources) != len(case["sources"]):
            continue
        group = []
        for row in case["credits"]:
            key = evidence_key(row["source"])
            if key in withdrawn or not public_url(row["source"]):
                continue
            who = participant(row.get("login"), row.get("user_id"))
            correction = policy.get("corrections", {}).get(key)
            if correction and ("roles" not in correction or row["kind"] in correction.get("credit_kinds", [])):
                who = participant(**correction["actor"])
            person = identity.visible(who) if who else secured.get(key)
            login = identity.display(person, who["login"] if who else None) if person else None
            credit_id = stable_id("impact-credit", key, row["kind"])
            credit = {"id": credit_id, "kind": row["kind"], "source": row["source"], "person": person,
                      "login": login, "team": row.get("team"), "basis": row["basis"]}
            credits[credit_id] = credit
            if credit_id not in {entry["id"] for entry in group}:
                group.append(credit)
        hidden_names = identity.hidden_logins | {identity.display(person, "") for person in identity.hidden_ids}
        hidden_names = {name for name in hidden_names if name}
        body = {key: case[key] for key in ("title", "summary", "scope", "title_ru", "summary_ru", "scope_ru") if key in case}
        for name in hidden_names:
            pattern = rf"(?<![\w-])@?{re.escape(name)}(?![\w-])"
            body = {key: re.sub(pattern, "the contributor", value, flags=re.I) for key, value in body.items()}
        story = {**case, **body, "sources": sources, "credits": group}
        stories.append(story)
        for name, source in case.get("measures", []):
            if public_url(source) and evidence_key(source) not in withdrawn:
                metrics[name].add(evidence_key(source))
    for item in reviewed_snapshot(catalog):
        source = item["source_url"]
        if item["id"] in withdrawn or evidence_key(source) in withdrawn or item.get("contested"):
            continue
        key = item["id"]
        metrics["reviewed_lab_results"].add(key)
        if item["status"] == "reproduced":
            metrics["independent_reproductions"].add(key)
        if item["outcome"] == "FAIL":
            metrics["negative_results"].add(key)
        stories.append({"id": key, "title": item["title"], "state": "reviewed", "type": "lab_review",
                        "at": item.get("reviewed_at") or "",
                        "summary": item["observed"], "scope": item["limitations"], "consoles": item["consoles"],
                        "sources": [{"label": "Pinned report source", "url": source}], "credits": [
                           {"kind": "negative_result" if item["outcome"] == "FAIL" else "independent_test",
                            "person": None, "basis": "Separate local volunteer account", "source": source},
                           {"kind": "review", "person": None, "basis": "Different authorized reviewer", "source": source}],
                        "related": [item["target_url"], item["peer_url"]]})
    receiving = {}
    for row in public_outcome_receipts(catalog):
        source = row["proof"]
        story_id = stable_id("impact", row["task"], "receiving")
        if not public_url(source) or evidence_key(source) in withdrawn or story_id in withdrawn:
            continue
        measure = "accepted_changes" if row["step"] == "adopt" else "delivered_results"
        metrics[measure].add(evidence_key(source))
        card = row["candidate"]
        story = receiving.setdefault(row["task"], {
            "id": story_id, "title": card["sources"][0]["title"],
            "type": "receiving_outcome", "consoles": card["consoles"],
            "related": [source["url"] for source in card["sources"]], "sources": [], "credits": [],
            "scope": "Receiving evidence is reviewed for this task and revision. Ongoing use is measured separately.",
        })
        adopted = row["step"] == "adopt"
        basis = "Acceptance recorded by the receiving team" if adopted else "Linked evidence delivered to the receiving project"
        story.update({"state": "accepted" if adopted else "reviewed", "at": row["at"], "summary": basis})
        story["sources"].append({"url": source, "label": basis})
        if adopted:
            story["credits"].append({"kind": "receiving_team", "team": repository(source), "basis": basis,
                                     "person": None, "source": source})
    stories.extend(receiving.values())
    candidates = radar.get("catalog", radar["candidates"])
    definitions = {
        "candidates": "Distinct Radar pair IDs currently visible in the catalog",
        "recorded_stories": "Distinct evidence-backed stories in this snapshot",
        "credited_acts": "Distinct evidence permalink + contribution type",
        "reviewed_lab_results": "Distinct opted-in and uncontested reports reviewed by another authorized account",
        "independent_reproductions": "Unique evidence receipts where an independent result is verified",
        "negative_results": "Unique reviewed negative result IDs or primary links",
        "rejected_hypotheses": "Distinct Radar pair IDs marked rejected",
        "delivered_results": "Unique receiving-project delivery evidence links",
        "accepted_changes": "Unique receiving default-branch merge or attributed adoption receipts",
        "cross_project_transfers": "Unique confirmed receiving receipts for a change originating elsewhere",
        "evidence_reuse": "Distinct receipts confirming reuse of a result rather than merely linking it",
        "integration_use": "Unique external evidence of documented infrastructure use",
        "duplicate_work_avoided": "Case count with a first-party statement that duplicate work was avoided",
        "repeat_contributors": "Identified participants credited at more than one permalink",
        "active_teams": "Unique external teams with current evidence of actual PortBridge use",
        "mcp_users": "Unavailable. PortBridge does not count individual MCP users",
        "installations": "Unavailable without independently reported installation evidence",
    }
    metrics["candidates"] = {c["id"] for c in candidates}
    metrics["recorded_stories"] = {s["id"] for s in stories}
    metrics["credited_acts"] = set(credits)
    metrics["rejected_hypotheses"] = {c["id"] for c in candidates if c["state"] == "rejected"}
    per_person = defaultdict(set)
    for credit in credits.values():
        if credit["person"]:
            per_person[credit["person"]].add(evidence_key(credit["source"]))
    metrics["repeat_contributors"] = {person for person, refs in per_person.items() if len(refs) > 1}
    origins = {"candidates": "Radar candidate queue", "recorded_stories": "Impact records",
               "credited_acts": "Scoped attribution receipts", "reviewed_lab_results": "Opted-in Lab review events",
               "rejected_hypotheses": "Radar decision history", "repeat_contributors": "Scoped attribution receipts"}
    measurements = {name: {"value": None if name in {"mcp_users", "installations", "active_teams"} and not metrics[name]
                      else len(metrics[name]), "definition": desc, "period": "evidence retained through this snapshot",
                      "as_of": timestamp(now), "evidence": origins.get(name, "Public primary source receipts"),
                      "sources": sorted(x for x in metrics[name] if public_url(x))[:8]} for name, desc in definitions.items()}
    return {"as_of": timestamp(now), "stories": sorted(stories, key=lambda story: (story.get("at", ""), story["id"]), reverse=True),
            "metrics": measurements,
            "visibility": config.get("visibility", {})}


def filter_people(payload, *, q="", profile="", project="", specialty="", console="", period="", target="", after=0, limit=DEFAULT_LIMIT):
    if (not all(isinstance(v, str) and len(v) <= 300 for v in (q, profile, project, specialty, console, period, target))
            or type(limit) is not int or not 1 <= limit <= 100 or type(after) is not int or after < 0
            or specialty and specialty not in TECH or console not in {"", "xbox-series", "ps5"}
            or period not in {"", "recent", "historical"} or target and not public_url(target)):
        raise ValueError("Invalid People filters")
    query = q.casefold().lstrip("@")
    focus = repository(target)
    matches = []
    for item in payload["profiles"]:
        if profile and profile not in (item["id"], item["login"].casefold()):
            continue
        repos = {r["repo"] for r in item["projects"]}
        tags = {tag["name"] for tag in item["specialties"]}
        if (project and project.casefold() not in repos or specialty and specialty not in tags
                or console and console not in item["consoles"] or period and item["activity"] != period
                or query and query not in item["login"].casefold() and not any(query in x for x in repos | tags)):
            continue
        matches.append(item)
    if target:
        links = [row for row in payload["connections"] if any(evidence_key(target) == evidence_key(link)
                 for link in (row["source"], row["comparison"]))]
        related = {repo for row in links for repo in (row["from"], row["to"])} | {focus}
        subjects = {evidence_key(target)} | {evidence_key(link) for row in links for link in (row["source"], row["comparison"])}
        targets = payload.get("target_index", {})
        direct = {ident: proof for subject in sorted(subjects - {evidence_key(target)})
                  for ident, proof in targets.get(subject, {}).items()}
        direct.update(targets.get(evidence_key(target), {}))
        def rank(item):
            declared = item["id"] in direct or any(evidence_key(row.get("subject", row["source"])) in subjects
                                                    for row in item["evidence"])
            return (not declared, -len({r["repo"] for r in item["projects"]} & related), -epoch(item["latest"]))
        matches = [row for row in matches if ({project["repo"] for project in row["projects"]} & related
                   or any(item.get("discovery_for") == evidence_key(target) for item in row["evidence"]))]
        matches.sort(key=rank)
        matches = [{**row, "target_evidence": direct.get(row["id"])} for row in matches]
    else:
        links = [row for row in payload["connections"] if (not project or project.casefold() in (row["from"], row["to"]))
                 and (not console or console in row["consoles"]) and (not specialty or row["specialty"] == specialty)]
    public = {key: value for key, value in payload.items() if key != "target_index"}
    return {**public, "profiles": matches[after:after+limit], "total": len(matches), "connections": links[:limit],
            "next": after + limit if after + limit < len(matches) else None}


def filter_impact(payload, *, console="", kind="", target=""):
    if console not in {"", "ps5", "xbox-series"} or not isinstance(kind, str) or len(kind) > 80 or (
            target and not public_url(target)):
        raise ValueError("Invalid Impact filters")
    return {**payload, "stories": [row for row in payload["stories"]
            if (not console or console in row["consoles"]) and (not kind or kind == row["type"])
            and (not target or any(evidence_key(target) == evidence_key(url) for url in
                 [*row.get("related", []), *(source["url"] for source in row["sources"])]))]}
