"""Repeat the frozen M5.3 URL-only comparison. No product code is modified."""
import argparse
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import m52_replay
from m52_replay import api_url, check_origin, normalized, public_input, read, transport, write


HERE = Path(__file__).resolve().parent / "evidence" / "m53"
PRIVATE = HERE.parents[2] / ".portbridge" / "m53"


def git(code, *args):
    return subprocess.check_output(["git", "-C", str(code), *args], text=True).strip()


def search_page(data):
    # Keep the public timeline used to distinguish already merged PRs.
    fields = ("html_url", "title", "state", "created_at", "updated_at")
    items = []
    for raw in data["items"]:
        item = {field: raw[field] for field in fields if field in raw}
        if isinstance(raw.get("pull_request"), dict):
            item["pull_request"] = {"merged_at": raw["pull_request"].get("merged_at")}
        items.append(item)
    return {"incomplete_results": data["incomplete_results"], "items": items}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--arm", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--record", action="store_true", help="capture previously unseen exact queries")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--raw", type=Path, help="original PRs captured privately at freeze")
    modes.add_argument("--public-inputs", action="store_true", help="re-fetch the pinned body through GitHub")
    args = parser.parse_args()
    if args.record and not (args.raw or args.public_inputs):
        parser.error("recording needs the original PR inputs")
    code = args.code.resolve()
    if git(code, "status", "--porcelain", "--untracked-files=all", "--", "portbridge"):
        parser.error("the product must be clean")
    product = git(code, "rev-parse", "HEAD:portbridge")
    if args.arm == "baseline" and product != git(code, "rev-parse", "df8cfd879c17df04644127c35330ef07407e9392:portbridge"):
        parser.error("baseline must use the frozen M5.2 product")
    sys.path.insert(0, str(code))
    from portbridge import github
    from portbridge.__main__ import DEFAULT_SEED
    from portbridge.catalog import Catalog
    from portbridge.discovery_scan import link_result, search_link

    path = HERE / f"{args.arm}.json"
    expected = read(path) if path.exists() else None
    if args.record and expected:
        parser.error("a recording already exists for this arm")
    if not args.record and (not expected or expected["product_tree"] != product):
        parser.error("this product tree has no matching recording")
    responses = HERE / "search-responses.json"
    pages = read(responses) if responses.exists() else {}
    inputs = read(HERE / "inputs.json")
    timestamps = {r["url"]: r["created_at"] for r in read(HERE / "origin-verification.json")["origins"]}
    originals = {pr["url"]: pr for pr in read(args.raw)} if args.raw else {}
    events = []
    cases = []
    network = github._Sync._request

    def original(client, url, resource, etag):
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        if parsed.path != "/search/issues" or query.get("per_page") != ["5"] or query.get("page", ["1"]) != ["1"]:
            raise ValueError("Unexpected Discovery search route or budget")
        data, headers = network(client, url, resource, etag)
        # Keep intact public replies private, independently of the published field subset.
        PRIVATE.mkdir(parents=True, exist_ok=True)
        write(PRIVATE / ("page-" + sha256(url.encode()).hexdigest() + ".json"), data)
        return data, headers

    for index, pr in enumerate(inputs):
        raw = public_input(pr) if args.public_inputs else originals.get(pr["url"])
        if args.public_inputs:
            raw["created_at"] = timestamps[pr["url"]]
        if args.raw and raw is None:
            raise ValueError(f"Missing original input for {pr['url']}")
        if raw is not None:
            check_origin(raw, pr)
            if raw.get("created_at") != timestamps[pr["url"]]:
                raise ValueError("PR creation time differs from the independently verified pin")
        log = []
        request = transport(pages, raw, api_url(pr), args.record, log, original, github.Unavailable)

        def traced(client, url, resource, etag):
            try:
                return request(client, url, resource, etag)
            finally:
                if log and resource == "search":
                    log[-1]["url"] = url
        with TemporaryDirectory() as temp:
            catalog = Catalog(Path(temp) / "discovery.sqlite", DEFAULT_SEED)
            with patch.object(github._Sync, "_request", traced), patch.object(m52_replay, "search_page", search_page):
                if raw is not None:
                    observation = normalized(raw, pr, catalog, github)
                    observation["metadata"]["created_at"] = raw["created_at"]
                    result = search_link(catalog, pr["url"])
                else:
                    observation = expected["cases"][index]["observation"]
                    result = link_result(catalog, observation)
        cases.append({"url": pr["url"], "observation": observation, "result": result})
        events.append({"url": pr["url"], "transport": log})
    report = {"product_tree": product, "cases": cases}
    if args.record:
        write(responses, pages)
        write(path, report)
        write(HERE / f"{args.arm}-transport.json", events)
    elif report != expected:
        raise SystemExit("Recorded and replayed results differ")
    attempts = sum(event["network_attempts"] for row in events for event in row["transport"])
    print(f"{args.arm}: {len(cases)} cases, {sum(len(c['result']['top5']) for c in cases)} ranks, {attempts} new search HTTP requests")


if __name__ == "__main__":
    main()
