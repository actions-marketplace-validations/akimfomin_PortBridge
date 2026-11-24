"""Evaluate cross-project retrieval against a frozen, source-linked sample."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode

from .github import API, Unavailable, _Sync
from .matching import RelatedIndex, canonical_url, terms

from contextlib import closing
import sqlite3


def source_url(value):
    return canonical_url(value["url"] if isinstance(value, dict) else value)


def github_results(client, query, repositories, origin, limit):
    repos = [repo for repo in repositories if origin is None or f"https://github.com/{repo.casefold()}/"
             not in origin]
    if not repos:
        return []
    # GitHub App installation tokens require each result type to be queried explicitly.
    lanes = ("is:issue", "is:pull-request") if client.token else ("",)
    ranks = {}
    for lane in lanes:
        scope = " ".join(f"repo:{repo}" for repo in repos)
        params = {"q": " ".join(filter(None, (scope, query, lane))), "per_page": limit}
        response, _ = client._request(f"{API}/search/issues?{urlencode(params)}", "search", None)
        if response.get("incomplete_results"):
            raise Unavailable("GitHub search returned incomplete results")
        for rank, entry in enumerate(response["items"], 1):
            ranks.setdefault(source_url(entry["html_url"]), rank)
    return sorted(ranks, key=lambda url: (ranks[url], url))[:limit]


def measure(ranked, positives, negatives):
    return {"hits": sum(url in positives for url in ranked), "judged_negatives": sum(url in negatives for url in ranked),
            "unjudged": sum(url not in positives | negatives for url in ranked), "results": ranked}


def run(fixture, *, limit=5, github=None):
    index = RelatedIndex(fixture["observations"])
    title_only = RelatedIndex([{**row, "metadata": {}} for row in fixture["observations"]])
    rows = []
    repositories = fixture["repositories"]
    if isinstance(repositories, dict):
        repositories = list(repositories.values())
    for query in fixture["queries"]:
        starting_url = query.get("origin_url")
        origin = source_url(starting_url) if starting_url else None
        positives = {source_url(value) for value in query["positives"]} - {origin}
        negatives = {source_url(value) for value in query["hard_negatives"]} - {origin}
        if not positives:
            continue
        present = len(positives & index.rows.keys())
        if origin and origin in index.rows:
            def ranked(model, links):
                return [source_url(row["right"]) for row in
                        model.matches({}, origin=origin, use_references=links, limit=limit)]
        else:
            seeds = terms(query["query"])

            def ranked(model, links):
                candidates = [(len(seeds & description), url) for url, description in model.subjects.items()]
                return [url for score, url in sorted(candidates, key=lambda item: (-item[0], item[1]))[:limit] if score]

        row = {"id": query["id"], "positive_count": len(positives), "present_in_corpus": present,
               "origin_indexed": origin in index.rows if origin else None,
               "title_only": measure(ranked(title_only, False), positives, negatives),
               "technical_only": measure(ranked(index, False), positives, negatives),
               "portbridge": measure(ranked(index, True), positives, negatives)}
        if github:
            try:
                row["github"] = measure(github_results(github, query["query"], repositories, origin, limit),
                                        positives, negatives)
            except Unavailable as error:
                row["github_error"] = str(error)
        rows.append(row)
    return {"corpus_size": len(index.rows), "top_k": limit, "queries": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--github", action="store_true", help="also run the scoped native GitHub search")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    with closing(sqlite3.connect(":memory:")) as db:
        github = _Sync(db, False) if args.github else None
        print(json.dumps(run(fixture, github=github), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
