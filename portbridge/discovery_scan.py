"""Run a bounded public Discovery search for recent catalog observations."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from .catalog import Catalog, public_url
from .community_sources import DATA, SCHEMA as PEOPLE_SCHEMA, actor, remember_discovery
from .consoles import console_families
from .discovery_search import SOURCE_FOUND, discovery_index, key
from .github import API, API_SYMBOL, _Sync, _text, Unavailable
from .global_search import result_entry, RESULT_PATH
from .matching import ISA_OPCODE, source_revision

MAX_ORIGINS = 64
MAX_LOOKUPS = 5
PAGE_SIZE = 5
TTL = 24 * 3600
FAILURE_TTL = 15 * 60
BATCH_SECONDS = 14
QUERY_VERSION = "m21-v1"
# Subjects and repository scope are independent. No subject names an expected result.
SYMBOLS = re.compile(
    r"\b(?:DXGI|D3D12|VK|SPV|GL)_[A-Z0-9_]{3,60}\b|"
    r"\b(?:GetCopyableFootprints|CopyTextureRegion|EnumAdapterByGpuPreference|"
    r"requiredSubgroupSize|R\d+G\d+B\d+E\d+|ds_bpermute(?:_b32)?)\b"
)
MECHANISMS = re.compile(
    r"\b(?:subgroup[-_ ]size|shared exponent|memory budget|device loss|typed buffer|"
    r"raw buffer view|pipeline state|frame pacing|texture upload|texture uploads|robust buffer access)\b", re.I
)
EXTERNAL = (
    "doitsujin/dxvk", "HansKristian-Work/vkd3d-proton", "KhronosGroup/Vulkan-ValidationLayers",
    "KhronosGroup/Vulkan-Docs", "KhronosGroup/SPIRV-Tools", "shadps4-emu/shadPS4",
    "xenia-project/xenia", "RPCS3/rpcs3", "microsoft/DirectXShaderCompiler",
    "GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator", "GPUOpen-LibrariesAndSDKs/D3D12MemoryAllocator",
    "llvm/llvm-project", "wine-mirror/wine", "gfx-rs/wgpu", "KhronosGroup/MoltenVK",
)
PS5_PEERS = ("boykopovar/AnyPS5", "KytyPS5/KytyPS5")
XBOX_PEERS = ("xcl-dev/xcl", "ubiquitarianism/leonida")
EXTERNAL_NAMES = {repo.lower() for repo in (*EXTERNAL, *PS5_PEERS, *XBOX_PEERS)}
SCHEMA = """
CREATE TABLE IF NOT EXISTS discovery_observation (
    url TEXT PRIMARY KEY, revision TEXT, query TEXT NOT NULL, seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_query (
    query TEXT PRIMARY KEY, retrieved REAL NOT NULL, retry_at REAL NOT NULL, status TEXT NOT NULL, items TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_lease (
    id INTEGER PRIMARY KEY, lease TEXT, expires REAL NOT NULL
);
"""


def symbol_terms(text):
    return [match.group() for pattern in (SYMBOLS, API_SYMBOL, ISA_OPCODE) for match in pattern.finditer(text)]


def subject(observation):
    title = _text(observation["title"])
    symbols = symbol_terms(title)
    phrases = [" ".join(word.group().casefold().replace("_", " ").replace("-", " ").split())
               for word in MECHANISMS.finditer(title)]
    metadata = observation.get("metadata", {}).get("technical", {})
    signals = [term for term in metadata.get("signals", [])[:8] if isinstance(term, str)
               and (API_SYMBOL.fullmatch(term) or ISA_OPCODE.fullmatch(term))]
    options = symbols + phrases + signals
    if options:
        return options[0].casefold()
    # Short fixed conjunctions match signs of the mechanism even when the title's
    # prose differs from documentation or an older tracker.
    tokens = set(re.findall(r"[a-z0-9]+", title.casefold()))
    for words in (("dxgi", "budget"), ("adapter", "performance"), ("compute", "subobject")):
        if set(words) <= tokens:
            return " ".join(words)
    if "budget" in tokens and ({"eviction", "evict", "clamping", "vram"} & tokens):
        return "memory budget"
    if {"sparse", "tiles"} <= tokens:
        return "sparse binding"
    return ""


def source_repo(url):
    return "/".join(urlsplit(url).path.lower().split("/")[1:3])


def source_results(rows):
    seen = set()
    for raw in rows[:PAGE_SIZE]:
        row = result_entry(raw)
        if not row or (repo := source_repo(row["url"])) not in EXTERNAL_NAMES:
            continue
        url = key(row["url"])
        if url in seen:
            continue
        seen.add(url)
        yield {**row, "title": _text(row["title"]), "project": repo.split("/")[1],
               "id": url, "source": row["url"], "repository": repo, "evidence_status": SOURCE_FOUND,
               "match_level": "research", "consoles": console_families(row["url"],
                   default=("xbox-series",) if repo in XBOX_PEERS else ()),
               "author": actor(raw.get("user"))}


def cached_index(catalog):
    index = discovery_index()
    with catalog.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='discovery_observation'").fetchone():
            return index
        rows = db.execute("""
            SELECT observation.url, query.retrieved, query.status, query.items
            FROM discovery_observation AS observation JOIN discovery_query AS query USING (query)
            ORDER BY observation.seen DESC, observation.url LIMIT ?
        """, (MAX_ORIGINS,)).fetchall()
    now = time.time()
    automatic = {}
    for url, retrieved, status, items in rows:
        if retrieved + TTL <= now and status in {"available", "partial"}:
            status = "stale"
        checked_on = datetime.fromtimestamp(retrieved, timezone.utc).date().isoformat()
        automatic[key(url)] = {"status": status, "matches": [
            {**item, "retrieved_on": checked_on, "retrieval_status": status} for item in json.loads(items)
        ]}
    return {**index, "automatic": automatic} if automatic else index


def acquire(db, lease):
    with db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT expires FROM discovery_lease WHERE id=1").fetchone()
        if existing and existing[0] > time.time():
            return False
        db.execute("REPLACE INTO discovery_lease VALUES (1,?,?)", (lease, time.time() + BATCH_SECONDS + 15))
    return True


def fetch(client, term, *, family="xbox-series"):
    targets = XBOX_PEERS if family=="ps5" else PS5_PEERS
    qualifier = " ".join(f"repo:{repo}" for repo in (*EXTERNAL,*targets))
    literal = f'"{term}"' if term not in {"dxgi budget", "adapter performance", "compute subobject"} else term
    query = f"{literal} is:public {qualifier}"
    data, _ = client._request(f"{API}/search/issues?{urlencode({'q': query, 'per_page': PAGE_SIZE})}", "search", None)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise Unavailable("Invalid Discovery search response", reason="invalid_payload")
    return ("partial" if data.get("incomplete_results") else "available"), list(source_results(data["items"]))


def lookup_plan(observations, known):
    plan = {}
    for observation in observations:
        url = observation["url"]
        if (observation["status"] != "open" or not public_url(url) or not RESULT_PATH.fullmatch(urlsplit(url).path)
                or source_repo(url) not in known or not (term := subject(observation))):
            continue
        plan.setdefault(url.lower(), (source_revision(observation) or observation.get("updated_at"), term))
    return plan


def scan(catalog, observations, *, online=False, max_lookups=MAX_LOOKUPS):
    if type(max_lookups) is not int or not 1 <= max_lookups <= MAX_LOOKUPS:
        raise ValueError(f"Use 1 to {MAX_LOOKUPS} Discovery lookups per batch")
    known = {row["repo"].lower() for row in catalog.projects()}
    plan = lookup_plan(observations[:MAX_ORIGINS], known)
    report = {"status": "offline" if not online else "complete", "eligible": len(plan),
              "lookups": 0, "cache_hits": 0, "origins": []}
    if not online:
        return report
    with catalog.connect() as db:
        db.execute("PRAGMA busy_timeout=650")
        db.executescript(SCHEMA + PEOPLE_SCHEMA)
        lease = uuid4().hex
        if not acquire(db, lease):
            return {**report, "status": "busy"}
        try:
            client = _Sync(db, False, anonymous=True, time_budget=BATCH_SECONDS)
            policy = json.loads((DATA / "people_policy.json").read_bytes())
            for url, (revision, term) in plan.items():
                family = "ps5" if "ps5" in console_families(url) else "xbox-series"
                query = f"{QUERY_VERSION}:{family}:{term}"
                prior = db.execute("SELECT retrieved,retry_at,status,items FROM discovery_query WHERE query=?",
                                   (query,)).fetchone()
                now = time.time()
                if prior and prior["retry_at"] > now:
                    status, items = prior["status"], json.loads(prior["items"])
                    report["cache_hits"] += 1
                elif report["lookups"] >= max_lookups or time.monotonic() >= client.deadline:
                    report["status"] = "budget"
                    break
                else:
                    report["lookups"] += 1
                    try:
                        status, items = fetch(client, term, family=family)
                    except Unavailable as error:
                        items = json.loads(prior["items"]) if prior else []
                        status = "stale" if items else "unavailable"
                        report["status"] = error.reason
                    finished = time.time()
                    retrieved = prior["retrieved"] if status == "stale" else finished
                    with db:
                        db.execute("REPLACE INTO discovery_query VALUES (?,?,?,?,?)",
                                   (query, retrieved, finished + (TTL if status == "available" else FAILURE_TTL),
                                    status, json.dumps(items)))
                with db:
                    db.execute("""
                        INSERT INTO discovery_observation VALUES (?,?,?,?)
                        ON CONFLICT(url) DO UPDATE SET revision=excluded.revision, query=excluded.query, seen=excluded.seen
                        WHERE revision IS NOT excluded.revision OR query != excluded.query
                    """, (url, revision, query, now))
                    if status in {"available", "partial"}:
                        remember_discovery(db, url, items, now, policy)
                report["origins"].append({"url": url, "revision": revision, "query": term, "status": status,
                                          "matches": [item["url"] for item in items]})
                if report["status"] not in {"complete", "budget"}:
                    break
        finally:
            with db:
                db.execute("DELETE FROM discovery_lease WHERE id=1 AND lease=?", (lease,))
                db.execute("DELETE FROM discovery_observation WHERE url NOT IN (SELECT url FROM discovery_observation "
                           "ORDER BY seen DESC, url LIMIT ?)", (MAX_ORIGINS,))
                db.execute("DELETE FROM discovery_query WHERE query NOT IN (SELECT query FROM discovery_observation)")
    return report


def main():
    from .__main__ import DEFAULT_DB, DEFAULT_SEED

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--online", action="store_true", help="allow bounded anonymous GitHub reads")
    parser.add_argument("--limit", type=int, default=MAX_LOOKUPS)
    args = parser.parse_args()
    catalog = Catalog(args.db, DEFAULT_SEED)
    print(json.dumps(scan(catalog, catalog.observations(limit=MAX_ORIGINS), online=args.online, max_lookups=args.limit),
                     indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
