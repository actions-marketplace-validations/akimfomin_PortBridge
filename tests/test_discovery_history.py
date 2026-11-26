"""Bounded PR-link search using revision-time evidence from the receiver."""
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from portbridge.discovery_history import history_identifier
from portbridge.discovery_scan import cached_index, search_link
from portbridge.discovery_search import key
from test_portbridge import CatalogFixture


PREFIX = "https://github.com/sample/engine/pull/"
CREATED = "2026-11-20T11:22:33Z"


def pull(number):
    return {"number": number, "title": "Fix a runtime cache mismatch",
            "body": "The test exercises `load_variant`. The runtime calls load_variant twice.",
            "created_at": CREATED, "state": "open", "head": {"sha": "a" * 40}}


def previous(repo="sample/engine", number=1, merged="2026-11-20T11:22:32Z"):
    return {"title": "Earlier runtime change", "html_url": f"https://github.com/{repo}/pull/{number}",
            "state": "closed", "pull_request": {"merged_at": merged}, "user": {"login": "ExampleContributor"}}


class HistorySearchTests(CatalogFixture):
    def test_requires_a_repeated_inline_identifier_and_preserves_shared_api_priority(self):
        self.assertEqual(history_identifier("cache `load_variant` then load_variant"), "load_variant")
        self.assertEqual(history_identifier("test `MAX_LANGUAGE` or MAX_LANGUAGE"), "MAX_LANGUAGE")
        for message in ("cache load_variant load_variant", "cache `load_variant` only once",
                        "cache `load_variant` load_variant vkQueueSubmit",
                        "cache `load_variant` load_variant UpdateTileMappings",
                        "test `/private/load_variant` load_variant", "cache `VK_SHADER_STAGE_ALL` VK_SHADER_STAGE_ALL",
                        "test `user_token` user_token", "contact `first_last` at first_last@example.invalid",
                        "test `first_last`\n> ping @first_last",
                        "build\n~~~\n```\n`load_variant` load_variant\n~~~",
                        "test <!-- `load_variant` load_variant -->", "test `ghp_privatefixture` ghp_privatefixture"):
            with self.subTest(message=message):
                self.assertEqual(history_identifier(message), "")

    def test_one_url_lookup_excludes_unmerged_later_other_repo_and_self(self):
        rows = [previous(), previous(number=2, merged=None), previous(number=3, merged=CREATED),
                previous(repo="sample/other"), previous(number=99)]
        def request(url, resource, _etag):
            if resource == "core":
                return pull(99), {}
            q = parse_qs(urlsplit(url).query)
            self.assertEqual(q["per_page"], ["5"])
            self.assertEqual(q["q"], [f'"load_variant" is:public is:pr is:merged repo:sample/engine merged:<{CREATED}'])
            return {"items": rows}, {}
        with patch("portbridge.github._Sync._request", side_effect=request) as transport, \
                patch("portbridge.discovery_scan.remember_discovery") as people:
            result = search_link(self.catalog, PREFIX + "99")
            cached = search_link(self.catalog, PREFIX + "99")
        self.assertEqual(transport.call_count, 2)
        people.assert_not_called()
        self.assertEqual(result["search_scope"], "receiver_merged_before_pr")
        self.assertEqual([(r["url"], r["route"], r["evidence_status"]) for r in result["top5"]],
                         [(PREFIX + "1", "repository_history", "source_found")])
        self.assertEqual((cached["lookups"], cached["cache_hits"]), (0, 1))
        saved = cached_index(self.catalog)["automatic"][key(PREFIX + "99")]
        self.assertEqual(saved["scope"], "receiver_merged_before_pr")
        self.assertNotIn("author", saved["matches"][0])

    def test_cache_is_partitioned_by_repository_and_creation_cutoff(self):
        def request(url, resource, _etag):
            if resource == "search":
                return {"items": []}, {}
            num = int(url.rsplit("/", 1)[-1])
            return {**pull(num), "created_at": CREATED if num == 98 else "2026-11-21T11:22:33Z"}, {}
        with patch("portbridge.github._Sync._request", side_effect=request):
            for source in (PREFIX + "98", PREFIX + "99", PREFIX.replace("/engine/", "/other/") + "99"):
                result = search_link(self.catalog, source)
                self.assertEqual((result["lookups"], result["cache_hits"], result["top5"]), (1, 0, []))
                self.assertIn("No earlier merged PR", result["explanation"])

    def test_no_date_means_no_history_claim_and_no_extra_lookup(self):
        raw = {**pull(99), "created_at": "", "title": "Fix memory budget"}
        with patch("portbridge.github._Sync._request", side_effect=[(raw, {}), ({"items": []}, {})]) as transport:
            result = search_link(self.catalog, PREFIX + "99")
        self.assertEqual(result["search_scope"], "external")
        self.assertNotIn("is:merged", parse_qs(urlsplit(transport.call_args.args[0]).query)["q"][0])
