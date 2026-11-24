from contextlib import closing
from email.message import Message
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from portbridge import github


class GitHubSyncTest(unittest.TestCase):
    project = {"slug": "example", "repo": "example/port"}
    sha = "a" * 40

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "catalog.sqlite"
        env = patch.dict(os.environ, {"PORTBRIDGE_GITHUB_TOKEN": "", "GITHUB_TOKEN": ""})
        env.start()
        self.addCleanup(env.stop)

    def fake_request(self, url, resource, etag):
        headers = {"ETag": '"metadata"'}
        if "/search/issues?" in url:
            data = {"items": [
                {"number": 1, "state": "open", "title": "Texture stalls", "body": "ignored body",
                 "user": {"login": "author"}},
                {"number": 2, "pull_request": {}, "title": "An overlapping pull request"},
            ]}
        elif "/pulls?" in url:
            data = [{"number": 2, "state": "closed", "merged_at": "2026-01-01T00:00:00Z",
                     "title": "Handle texture stub", "head": {"sha": self.sha}, "body": "ignored body"}]
        elif "/commits?" in url:
            data = [{"sha": self.sha, "commit": {"message": "Fix texture stub\nignore commit body"}}]
        elif "/actions/runs?" in url:
            data = {"workflow_runs": [{"id": 3, "name": "Windows CI", "status": "completed",
                                      "conclusion": "success", "head_sha": self.sha,
                                      "pull_requests": [{"number": 2}]}]}
        else:
            self.fail(f"unexpected endpoint {url}")
        return data, headers

    def test_collect_normalized_metadata_and_reuse_fresh_cache(self):
        with patch.object(github._Sync, "_request", side_effect=self.fake_request) as network:
            first = github.collect([self.project], self.db_path)
            fresh = github.collect([self.project], self.db_path)
        self.assertEqual(network.call_count, 4)
        self.assertEqual(first["items"], fresh["items"])
        self.assertEqual(first["projects"][0]["sync_status"], "ok")
        self.assertIsNotNone(first["projects"][0]["last_success"])
        self.assertFalse(first["warnings"])
        self.assertEqual([x["kind"] for x in first["items"]], ["issue", "pr", "commit", "test"])
        _, pr, commit, test = first["items"]
        self.assertEqual(pr["status"], "merged")
        self.assertEqual(commit["title"], "Fix texture stub")
        self.assertEqual(test["metadata"]["pull_requests"], [2])
        self.assertEqual(test["metadata"]["evidence_kind"], "automated")
        self.assertEqual(test["metadata"]["scope"], "workflow_run")
        with closing(sqlite3.connect(self.db_path)) as db:
            rows = db.execute("SELECT items FROM github_cache").fetchall()
        self.assertNotIn("ignored body", repr(rows))
        self.assertNotIn("ignore commit body", repr(rows))

    def test_conditional_refresh_retains_stale_page_when_other_pages_are_revalidated(self):
        with patch.object(github._Sync, "_request", side_effect=self.fake_request), \
                patch.object(github.time, "time", return_value=1700000000):
            first = github.collect([self.project], self.db_path)

        def revalidate(url, resource, etag):
            self.assertEqual(etag, '"metadata"')
            if "/pulls?" in url:
                raise github.Unavailable("GitHub HTTP 503")
            return github.NOT_MODIFIED, {}

        with patch.object(github._Sync, "_request", side_effect=revalidate) as network, \
                patch.object(github.time, "time", return_value=1700000060):
            again = github.collect([self.project], self.db_path, refresh=True)
        self.assertEqual(network.call_count, 4)
        self.assertEqual(first["items"], again["items"])
        self.assertEqual(again["projects"][0]["sync_status"], "partial")
        self.assertEqual(again["projects"][0]["sources"]["pr"]["sync_status"], "stale")
        self.assertEqual(again["projects"][0]["sources"]["pr"]["last_success"], "2023-11-14T22:13:20+00:00")
        self.assertEqual(again["projects"][0]["sources"]["issue"]["last_success"], "2023-11-14T22:14:20+00:00")
        self.assertIn("using stale cache", again["warnings"][0])

    def test_private_repositories_cannot_be_listed_with_token(self):
        def check(url, resource, etag):
            self.assertEqual(url, "https://api.github.com/repos/example/port")
            return {"private": True, "visibility": "private"}, {}

        with patch.dict(os.environ, {"PORTBRIDGE_GITHUB_TOKEN": "test-token"}), \
                patch.object(github._Sync, "_request", side_effect=check) as network:
            result = github.collect([self.project], self.db_path)
        self.assertEqual(network.call_count, 1)
        self.assertFalse(result["items"])
        self.assertEqual(result["projects"][0]["sync_status"], "error")
        self.assertTrue(all("repository is not public" in msg for msg in result["warnings"]))

    def test_rate_limit_suppresses_more_requests_for_the_same_resource(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            sync = github._Sync(db, True)
            headers = Message()
            headers["Retry-After"] = "60"
            error = HTTPError("https://api.github.com/repos/example/port/pulls", 429, "limit", headers, None)
            with patch.object(sync.opener, "open", side_effect=error) as network:
                with self.assertRaisesRegex(github.Unavailable, "429"):
                    sync._request("https://api.github.com/repos/example/port/pulls", "core", None)
                with self.assertRaisesRegex(github.Unavailable, "retry after"):
                    sync._request("https://api.github.com/repos/example/port/commits", "core", None)
                self.assertEqual(network.call_count, 1)
                self.assertEqual(network.call_args.args[0].get_method(), "GET")
                self.assertIsNone(network.call_args.args[0].data)
                with self.assertRaisesRegex(ValueError, "only https"):
                    sync._request("https://example.com/redirect", "search", None)

    def test_pagination_uses_own_numbered_url_instead_of_link_destination(self):
        seen = []

        def get_page(url, resource, etag):
            seen.append(url)
            if "/search/issues?" not in url:
                return self.fake_request(url, resource, etag)
            if "&page=1&" in url:
                return {"items": [{"number": 1, "title": "First"}]}, {
                    "Link": '<https://example.com/unsafe>; rel="next"',
                }
            return {"items": [{"number": 2, "title": "Second"}]}, {}

        with patch.object(github._Sync, "_request", side_effect=get_page):
            result = github.collect([self.project], self.db_path, pages=2)
        self.assertEqual(len(seen), 5)
        self.assertTrue(all(url.startswith("https://api.github.com/") for url in seen))
        self.assertEqual(result["projects"][0]["sources"]["issue"]["pages_checked"], 2)
        self.assertEqual([x["source_id"] for x in result["items"] if x["kind"] == "issue"], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
