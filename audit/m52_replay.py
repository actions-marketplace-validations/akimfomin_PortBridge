"""Compare one implementation on predeclared PRs. The default mode is fully offline."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent / "evidence" / "m52"
ROOT = HERE.parents[2]
BASE = "0738093add1ed01dad89c4bdcb6df74eb8891701"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def api_url(pr):
    return f"https://api.github.com/repos/{pr['repo']}/pulls/{pr['number']}"


def public_input(pr):
    # GitHub PR prose is mutable even when a commit remains available.
    req = Request(api_url(pr), headers={"User-Agent": "PortBridge public evidence verification"})
    try:
        with urlopen(req, timeout=12) as response:
            raw = json.load(response)
    except HTTPError as exc:
        raise SystemExit(f"Public metadata returned HTTP {exc.code} at {pr['url']}. "
                         "Use offline replay or retry after GitHub permits reads.") from None
    if (raw["title"] != pr["title"] or raw["head"]["sha"] != pr["head"]["sha"] or
            sha256(raw["body"].encode()).hexdigest() != pr["body_sha256"]):
        raise ValueError(f"Public title, head or body changed at {pr['url']}. Use offline replay.")
    # Reconstruct the original status, labels and timestamp from the public manifest.
    return {**pr, "body": raw["body"]}


def check_origin(raw, pr):
    expected = (pr["number"], pr["title"], pr["head"]["sha"], pr["state"], pr.get("merged_at"),
                [label["name"] for label in pr["labels"]], pr["body_sha256"], pr["updated_at"])
    actual = (raw["number"], raw["title"], raw["head"]["sha"], raw["state"], raw.get("merged_at"),
              [label["name"] for label in raw["labels"]], sha256(raw["body"].encode()).hexdigest(), raw["updated_at"])
    if actual != expected:
        raise ValueError(f"Origin changed for {pr['url']}. Use the frozen normalized replay.")


def search_page(data):
    # Both releases consume these public metadata fields. Bodies and accounts stay outside the fixture.
    keys = ("html_url", "title", "state", "updated_at")
    return {"incomplete_results": data["incomplete_results"],
            "items": [{key: item[key] for key in keys} for item in data["items"]]}


def transport(store, raw, origin_url, record, events, original, unavailable):
    def request(client, url, resource, etag):
        if client.token:
            raise ValueError("Audit requires anonymous reads")
        if resource == "core" and url == origin_url and raw is not None:
            events.append({"route": "origin", "mode": "frozen PR", "network_attempts": 0})
            return raw, {}
        if resource != "search" or urlsplit(url).netloc != "api.github.com" or urlsplit(url).path != "/search/issues":
            raise ValueError(f"Unexpected transport request {resource}: {url}")
        if url not in store:
            if not record:
                raise ValueError("No frozen reply for this exact query. Replay made no network request.")
            with patch.object(client.opener, "open", wraps=client.opener.open) as opened:
                try:
                    data, _ = original(client, url, resource, etag)
                except unavailable as exc:
                    entry = {"error": exc.reason, "http_status": exc.http_status}
                else:
                    entry = {"page": search_page(data)}
                entry["captured_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                entry["network_attempts"] = opened.call_count
            store[url] = entry
            events.append({"route": "search", "mode": "live", "network_attempts": entry["network_attempts"]})
        else:
            events.append({"route": "search", "mode": "frozen search", "network_attempts": 0})
        entry = store[url]
        if "error" in entry:
            raise unavailable("Captured public search error", reason=entry["error"], http_status=entry["http_status"])
        return entry["page"], {}
    return request


def normalized(raw, pr, catalog, github):
    projects = {project["repo"].lower(): project for project in catalog.projects()}
    row = github._item(raw, "pr", projects[pr["repo"].lower()],
                       {name: project["repo"] for name, project in projects.items()})
    # The scan does not use actor identities. Retain the input shape and fields needed by the product.
    metadata = row["metadata"]
    row["metadata"] = {key: metadata[key] for key in ("number", "head_sha", "technical", "labels", "merged_at")}
    return row


def baseline(catalog, obs, scan, discover):
    report = scan.scan(catalog, [obs], online=True, max_lookups=1)
    result = discover(origin_url=obs["url"], index=scan.cached_index(catalog), limit=5)
    return {"subject": scan.subject(obs), "lookups": report["lookups"], "cache_hits": report["cache_hits"],
            "eligible": report["eligible"], "batch_status": report["status"], "status": result["scan_status"],
            "top5": [{"url": row["url"], "title": row["title"], "route": "automatic",
                      "evidence_status": row["evidence_status"]} for row in result["automatic_matches"]],
            "reviewed_top5": [{"url": row["source"], "title": row["title"],
                               "evidence_status": row["evidence_status"]} for row in result["matches"]]}


def summarize_new(result):
    return {key: result[key] for key in ("subject", "lookups", "cache_hits", "status", "explanation", "top5")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, default=ROOT, help="checkout containing the release to execute")
    parser.add_argument("--arm", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--record", action="store_true", help="capture missing search replies and save release output")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--public-inputs", action="store_true", help="verify and replay original prose via GitHub")
    source.add_argument("--raw", type=Path, help="private JSON array of original PR input fields, verified against pins")
    args = parser.parse_args()
    if args.record and not (args.raw or args.public_inputs):
        parser.error("--record requires original PR bytes via --raw or --public-inputs")
    sys.path.insert(0, str(args.code.resolve()))
    from portbridge import github, discovery_scan as scan
    from portbridge.__main__ import DEFAULT_SEED
    from portbridge.catalog import Catalog
    from portbridge.discovery_search import discover

    def tree(rev):
        return subprocess.check_output(["git", "-C", str(args.code), "rev-parse", rev + ":portbridge"], text=True).strip()

    if args.arm == "baseline" and tree("HEAD") != tree(BASE):
        raise ValueError("Select the M5.1 checkout for the baseline")
    names = subprocess.check_output(["git", "-C", str(args.code), "ls-files", "-z", "--cached", "--others",
                                     "--exclude-standard", "--", "portbridge"]).decode().split("\0")
    fingerprint = sha256()
    for name in sorted(filter(None, names)):
        content = (args.code / name).read_bytes().replace(b"\r\n", b"\n")
        fingerprint.update(name.encode() + b"\0" + sha256(content).digest())
    version = fingerprint.hexdigest()
    prs = read(HERE / "inputs.json") + [read(HERE / "known-regression.json")]
    response_file = HERE / "search-responses.json"
    store = read(response_file) if response_file.is_file() else {}
    results_file = HERE / f"{args.arm}.json"
    frozen = {} if args.record else read(results_file)
    if frozen and frozen["product_sha256"] != version:
        raise ValueError("The selected checkout does not match the recorded product tree")
    sources = {item["url"]: item for item in read(args.raw)} if args.raw else {}
    results = []
    evidence = []
    for position, pr in enumerate(prs):
        raw = public_input(pr) if args.public_inputs else sources.get(pr["url"])
        if args.raw and raw is None:
            raise ValueError(f"Missing original PR bytes for {pr['url']}")
        if raw is not None:
            check_origin(raw, pr)
        events = []
        with TemporaryDirectory() as temporary:
            catalog = Catalog(Path(temporary) / "discovery.sqlite", DEFAULT_SEED)
            obs = normalized(raw, pr, catalog, github) if raw is not None else frozen["cases"][position]["observation"]
            wrapped = transport(store, raw, api_url(pr), args.record, events, github._Sync._request, github.Unavailable)
            with patch.object(github._Sync, "_request", wrapped):
                if args.arm == "baseline":
                    result = baseline(catalog, obs, scan, discover)
                elif raw is not None:
                    result = summarize_new(scan.search_link(catalog, pr["url"]))
                else:
                    result = summarize_new(scan.link_result(catalog, obs))
        results.append({"url": pr["url"], "observation": obs, "result": result})
        evidence.append({"url": pr["url"], "transport": events})
    actual = {"product_sha256": version, "cases": results}
    if args.record:
        write(response_file, store)
        write(results_file, actual)
        write(HERE / f"{args.arm}-transport.json", evidence)
    elif actual != frozen:
        print(json.dumps(actual, indent=2))
        raise SystemExit("Replay differs from the published results")
    core = len(prs) if args.public_inputs else 0
    print(f"{args.arm}: {core} live origin reads; {len(results)} PRs; {sum(len(r['result']['top5']) for r in results)} rank entries; "
          f"{sum(e['network_attempts'] for row in evidence for e in row['transport'])} search HTTP attempts")


if __name__ == "__main__":
    main()
