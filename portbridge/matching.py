"""Rank cross-project leads from references and technical evidence."""

from collections import Counter, defaultdict
from math import log, sqrt
import re
from urllib.parse import urlsplit


WORDS = re.compile(r"[^\W_]+")
STOP_WORDS = set("a an the on in to of for by and or from that it its is at with into after before as this then "
                 "test tests tested fix fixes add adds support update merge pull request windows linux xbox "
                 "game would about when build issue code commit main using use like fails error crash "
                 "github make target runtime logs output example version project passed result".split())
ALIASES = {
    "direct3d12": "d3d12", "rectlist": "rectangle",
    "rectlists": "rectangle", "rectangles": "rectangle", "vertices": "vertex",
    "shaders": "shader", "atomics": "atomic", "queues": "queue", "quads": "quad",
}


def canonical_url(url):
    path = urlsplit(url).path.rstrip("/").lower()
    return f"https://github.com{path}"


def terms(text):
    words = WORDS.findall(text.casefold().replace("spir-v", "spirv"))
    return {ALIASES.get(word, word) for word in words
            if len(word) >= 3 and word not in STOP_WORDS and not word.isdecimal()}


def source_revision(row):
    metadata = row["metadata"]
    value = metadata.get("sha") or metadata.get("head_sha")
    return value.lower() if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{40,64}", value) else None


class RelatedIndex:
    def __init__(self, records):
        self.rows = {canonical_url(row["url"]): row for row in records if row["kind"] in {"issue", "pr", "commit"}}
        self.titles, self.subjects, self.signals = {}, {}, {}
        self.references = defaultdict(set)
        self.postings = defaultdict(set)
        self.symbols = defaultdict(set)
        self.revisions = defaultdict(set)
        for url, row in self.rows.items():
            technical = row["metadata"].get("technical") or {}
            self.titles[url] = terms(row["title"])
            self.subjects[url] = self.titles[url] | terms(" ".join(technical.get("terms", [])))
            self.signals[url] = {value.casefold() for value in technical.get("signals", [])}
            for word in self.subjects[url]:
                self.postings[word].add(url)
            for signal in self.signals[url]:
                self.symbols[signal].add(url)
            revision = source_revision(row)
            if revision:
                self.revisions[revision].add(url)
            for target in technical.get("references", []):
                other = canonical_url(target)
                if other in self.rows and self.rows[other]["project"] != row["project"]:
                    self.references[url].add(other)
                    self.references[other].add(url)
        count = len(self.rows)
        cap = min(160, max(18, count // 8))
        self.weight = {word: 1 + log((count + 1) / (len(urls) + 1))
                       for word, urls in self.postings.items() if len(urls) <= cap}
        self.lengths = {url: sum(self.weight[word] for word in words & self.weight.keys())
                        for url, words in self.subjects.items()}
        self.symbol_cap = cap

    def candidates(self, url, *, use_references=True):
        reference_urls = self.references.get(url, set()) if use_references else set()
        target_hits = Counter(other for term in self.subjects[url] & self.weight.keys()
                              for other in self.postings[term])
        signal_urls = {other for signal in self.signals[url] if len(self.symbols[signal]) <= self.symbol_cap
                       for other in self.symbols[signal]}
        shared_revision = self.revisions.get(source_revision(self.rows[url]), set())
        for other in sorted(set(target_hits) | reference_urls | signal_urls | shared_revision):
            if self.rows[url]["project"] == self.rows[other]["project"]:
                continue
            if other in shared_revision:
                yield other, 1.0, "shared_revision", []
                continue
            if other in reference_urls:
                yield other, 1.0, "reference", []
                continue
            shared = self.subjects[url] & self.subjects[other] & self.weight.keys()
            symbols = {signal for signal in self.signals[url] & self.signals[other]
                       if len(self.symbols[signal]) <= self.symbol_cap}
            if other in signal_urls and shared and symbols:
                yield other, 0.78 + 0.04 * min(len(symbols), 3), "technical_signal", sorted(symbols)[:6]
                continue
            if target_hits[other] < 3:
                continue
            title_shared = self.titles[url] & self.titles[other]
            if not title_shared and len(shared) < 5:
                continue
            weight = sum(self.weight[word] for word in shared)
            score = weight / sqrt(self.lengths[url] * self.lengths[other])
            if score >= 0.26:
                words = sorted(shared, key=lambda word: (-self.weight[word], word))
                yield other, min(score, 0.77), "technical_terms", words[:6]

    def matches(self, stacks, *, origin=None, exclude=None, keep=None, use_references=True, limit=60):
        pairs = set()
        found = []
        origins = self.rows if origin is None else [origin] if origin in self.rows else []
        for url in origins:
            first = self.rows[url]
            for other, score, basis, signals in self.candidates(url, use_references=use_references):
                if exclude and exclude(url, other):
                    continue
                second = self.rows[other]
                if keep and not keep([first, second]):
                    continue
                pair = tuple(sorted((url, other)))
                if pair in pairs:
                    continue
                pairs.add(pair)
                reason = {
                    "reference": "В одном из источников есть прямая ссылка на другой проект.",
                    "shared_revision": "Совпадает полный идентификатор коммита.",
                    "technical_signal": "Совпадают технические идентификаторы.",
                    "technical_terms": "Совпадают редкие технические термины в описании или заголовке.",
                }[basis]
                if signals:
                    reason += " " + ", ".join(signals) + "."
                different = stacks.get(first["project"]) != stacks.get(second["project"])
                if different:
                    reason += " Проверьте различия между архитектурами."
                found.append({
                    "left": {key: first[key] for key in ("project", "title", "url")},
                    "right": {key: second[key] for key in ("project", "title", "url")},
                    "score": round(score, 3), "reason": reason, "basis": basis, "state": "suggested",
                    "problem_id": None, "different_stacks": different,
                })
        return sorted(found, key=lambda row: (-row["score"], row["left"]["url"], row["right"]["url"]))[:limit]
