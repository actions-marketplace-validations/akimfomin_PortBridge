"""Score frozen Discovery judgments and pinned issue-search receipts."""

import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from .__main__ import DEFAULT_SEED
from .catalog import Catalog
from .discovery_search import DATA, discover, discovery_index, features, key
from .preflight import preflight


DEFAULT_FIXTURE = Path("tests/fixtures/discovery-holdout-v1.json")


def score(samples, predictions, timings):
    ranked = []
    for sample in samples:
        actual = predictions.get(sample["id"])
        if actual is None:
            continue
        positive = set(sample["expected"])
        negative = set(sample["hard_negatives"])
        positions = [number for number, value in enumerate(actual[:5], 1) if value in positive]
        ranked.append({"id": sample["id"], "returned": actual[:5], "expected": len(positive),
                       "hits": len(positions), "first": positions[0] if positions else None,
                       "hard_negatives": sum(value in negative for value in actual[:5]),
                       "unjudged": sum(value not in positive | negative for value in actual[:5])})
    positive_rows = [row for row in ranked if row["expected"]]
    controls = [row for row in ranked if not row["expected"]]
    if not ranked:
        return {"eligible_queries": 0}
    timings = sorted(timings)
    def average(values):
        return round(mean(values), 4) if positive_rows else None

    return {"eligible_queries": len(ranked), "positive_queries": len(positive_rows), "control_queries": len(controls),
            "precision_at_5_lower_bound": average(row["hits"] / 5 for row in positive_rows),
            "recall_at_5": average(row["hits"] / row["expected"] for row in positive_rows),
            "mrr": average(1 / row["first"] if row["first"] else 0 for row in positive_rows),
            "hard_negatives": sum(row["hard_negatives"] for row in ranked),
            "unjudged": sum(row["unjudged"] for row in ranked),
            "no_answer_controls_with_results": sum(bool(row["returned"]) for row in controls),
            "p95_local_ms": round(timings[int(0.95 * (len(timings) - 1))] / 1_000_000, 3) if timings else None,
            "results": ranked}


def fts_index(connection, entries):
    connection.execute("CREATE VIRTUAL TABLE docs USING fts5(id UNINDEXED, title, symbols, context)")
    connection.executemany("INSERT INTO docs VALUES(?, ?, ?, ?)",
                           [(row["id"], " ".join(row["features"]["title"]),
                             " ".join(row["features"]["symbols"]), " ".join(row["features"]["context"]))
                            for row in entries])


def fts_results(connection, query):
    terms = features(query)
    if not terms:
        return []
    quoted = " OR ".join(f'"{term}"' for term in terms)
    cursor = connection.execute("SELECT id FROM docs WHERE docs MATCH ? ORDER BY bm25(docs, 0, 3, 5, 1), id LIMIT 5",
                                (quoted,))
    return [row[0] for row in cursor]


def run(fixture, native=None):
    started = perf_counter_ns()
    runtime = discovery_index()
    index = {**runtime, "entries": [entry for entry in runtime["entries"] if not entry.get("supplemental")]}
    index_ms = (perf_counter_ns() - started) / 1_000_000
    samples = fixture["queries"]
    models = {name: {} for name in ("lexical", "hybrid", "fts5")}
    times = {name: [] for name in models}
    units = native.get("queries", []) if native else []
    by_url = {key(item["source"]): item["id"] for item in index["entries"]}
    github = {row["id"]: [by_url.get(key(value["url"]), value["url"]) for value in row["results"] if value.get("url")]
              for row in units if row["ok"]}
    with closing(sqlite3.connect(":memory:")) as connection:
        started = perf_counter_ns()
        fts_index(connection, index["entries"])
        fts_ms = (perf_counter_ns() - started) / 1_000_000
        fts_bytes = connection.execute("PRAGMA page_count").fetchone()[0] * connection.execute(
            "PRAGMA page_size").fetchone()[0]
        for sample in samples:
            for model in models:
                for _ in range(3):
                    started = perf_counter_ns()
                    if model == "fts5":
                        results = fts_results(connection, sample["q"])
                    else:
                        results = [entry["id"] for entry in discover(sample["q"], index=index, profile=model)["matches"]]
                    times[model].append(perf_counter_ns() - started)
                models[model][sample["id"]] = results
    with TemporaryDirectory(prefix="portbridge-discovery-bench-") as directory:
        catalog = Catalog(Path(directory) / "baseline.sqlite3", DEFAULT_SEED)
        exact = []
        for ident in fixture["exact_pb_ids"]:
            cards = preflight(catalog, q=ident)["problems"]
            exact.append({"expected": ident, "first": cards[0]["id"] if cards else None})
        reports = []
        for sample in fixture["baseline_report_links"]:
            cards = preflight(catalog, url=sample["url"])["problems"]
            reports.append({"expected": sample["expected"], "first": cards[0]["id"] if cards else None})
    overlap = [sample for sample in samples if sample["id"] in github]
    return {"judgment_count": len(samples) + len(exact) + len(reports), "discovery_queries": len(samples),
            "corpus_records": len(index["entries"]), "runtime_records": len(runtime["entries"]),
            "source_data_bytes": DATA.stat().st_size + DATA.with_suffix(".ru.json").stat().st_size,
            "fixture_sha256": None,
            "feature_build_ms": round(index_ms, 3), "fts5_build_ms": round(fts_ms, 3), "fts5_bytes": fts_bytes,
            "index_json_bytes": len(json.dumps(runtime, ensure_ascii=False).encode("utf-8")),
            "exact_pb": exact, "exact_reports": reports,
            "models": {name: score(samples, predictions, times[name]) for name, predictions in models.items()},
            "github_issues": score(overlap, github, []),
            "hybrid_same_github_queries": score(overlap, models["hybrid"], []),
            "github_limits": "GitHub Issues/PR Search cannot return source-file permalinks. Unknown results remain unjudged."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--github-capture", type=Path)
    args = parser.parse_args()
    raw = args.fixture.read_bytes()
    native = json.loads(args.github_capture.read_bytes()) if args.github_capture else None
    result = run(json.loads(raw), native)
    result["fixture_sha256"] = sha256(raw).hexdigest()
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
