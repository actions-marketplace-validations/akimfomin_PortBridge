from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from portbridge.exchange import AuthError, Conflict, Exchange, PermissionDenied


class ExchangeTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "exchange.sqlite3"
        self.exchange = Exchange(self.path, problem_exists={"PB-0001", "PB-0002"}.__contains__)
        self.author = self.exchange.create_principal("Author", ["read", "contribute", "review"])["token"]
        self.reviewer = self.exchange.create_principal("Reviewer", ["read", "review"])["token"]
        self.reader = self.exchange.create_principal("Reader", ["read"])["token"]

    def proposal(self, **changes):
        return {
            "problem_id": "PB-0001", "source_url": "https://github.com/example/source/pull/12#issuecomment-456",
            "revision": "a" * 40, "platform": "Windows 11 / Vulkan", "evidence_kind": "independent",
            "outcome": "failed", "summary": "The synthetic rectangle remained black.", **changes,
        }

    def test_principal_persists_scope_and_only_a_token_hash(self):
        identity = Exchange(self.path).authenticate(self.author)
        self.assertEqual(identity, {"id": 1, "name": "Author", "scopes": ["contribute", "read", "review"]})
        with closing(sqlite3.connect(self.path)) as db:
            hashes = {row[0] for row in db.execute("SELECT token_hash FROM principals")}
        digest = sha256(self.author.encode("ascii")).hexdigest()
        self.assertIn(digest, hashes)
        self.assertNotIn(self.author.encode("ascii"), self.path.read_bytes())
        with self.assertRaises(Conflict):
            self.exchange.create_principal("author", ["review"])
        for token in (None, digest, "pbx_" + "a" * 43):
            with self.subTest(token_type=type(token)), self.assertRaises(AuthError):
                self.exchange.authenticate(token)
        with self.assertRaises(PermissionDenied):
            self.exchange.submit_result(self.reader, self.proposal())
        with self.assertRaises(PermissionDenied):
            self.exchange.pending_results(self.reader)

    def test_work_is_nonexclusive_renewable_and_expires_at_deadline(self):
        second = self.exchange.create_principal("Second author", ["contribute"])["token"]
        with patch("portbridge.exchange.time.time", return_value=1700000000):
            first = self.exchange.register_work(self.author, "PB-0001", ttl_seconds=60)
            other = self.exchange.register_work(second, "PB-0001", ttl_seconds=120)
            self.assertNotEqual(first["id"], other["id"])
            self.assertEqual(len(self.exchange.active_work(self.reader, problem_id="PB-0001")), 2)
            self.assertFalse(self.exchange.active_work(self.reader, problem_id="PB-0002"))
        with patch("portbridge.exchange.time.time", return_value=1700000060):
            self.assertEqual(self.exchange.active_work(self.reader), [other])
            renewal = self.exchange.register_work(self.author, "PB-0001", ttl_seconds=120)
            self.assertEqual(renewal["id"], first["id"])
            self.assertGreater(renewal["expires_at"], first["expires_at"])
        with self.assertRaises(ValueError):
            self.exchange.register_work(self.author, "PB-0001", ttl_seconds=True)
        with self.assertRaises(ValueError):
            self.exchange.register_work(self.author, "PB-9999")

    def test_result_requires_typed_public_source_and_bounded_text(self):
        changes = (
            {"source_url": "https://github.com.example.com/example/source/pull/12"},
            {"source_url": "https://github.com@example.com/example/source/pull/12"},
            {"source_url": "https://github.com/example/source/releases/download/v1/game.exe"},
            {"source_url": "https://github.com/example/source/actions/runs/12/artifacts/34"},
            {"source_url": "https://github.com//example/source/pull/12"},
            {"source_url": "https://github.com/example/source/pull/12?token=secret"},
            {"source_url": "https://github.com/example/source/pull/12#opaque_secret"},
            {"revision": "a" * 39}, {"platform": ""}, {"evidence_kind": "verified"}, {"outcome": []},
            {"summary": "a" * 601}, {"summary": "multiline\ntext"}, {"summary": "https://example.com/game.zip"},
            {"summary": "Credential copied by mistake: pbx_" + "z" * 43},
            {"author": "Reviewer"},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.exchange.submit_result(self.author, self.proposal(**change))
        self.assertEqual(self.exchange.pending_results(self.reviewer), [])
        submitted = self.exchange.submit_result(self.author, self.proposal(
            revision="B" * 64, source_url="https://github.com/example/source/actions/runs/12/job/34",
        ))
        self.assertEqual(submitted["revision"], "b" * 64)
        self.assertEqual(submitted["author"], "Author")
        self.assertEqual(submitted["status"], "pending")
        self.assertIsNone(submitted["event_id"])

    def test_only_reviewed_results_appear_in_ordered_feed_and_evidence(self):
        first = self.exchange.submit_result(self.author, self.proposal())
        second = self.exchange.submit_result(self.author, self.proposal(problem_id="PB-0002", outcome="passed"))
        third = self.exchange.submit_result(self.author, self.proposal(outcome="mixed"))
        fourth = self.exchange.submit_result(self.author, self.proposal(evidence_kind="simulation"))
        self.assertEqual(self.exchange.poll_events(self.reader), {"events": [], "next_cursor": 0})
        self.assertEqual(self.exchange.evidence(self.reader, "PB-0001"), [])
        self.assertEqual(self.exchange.pending_results(self.reviewer), [first, second, third, fourth])
        with self.assertRaises(PermissionDenied):
            self.exchange.review_result(self.author, first["id"], decision="accepted")
        with self.assertRaises(LookupError):
            self.exchange.review_result(self.reviewer, 999, decision="accepted")

        accepted_second = self.exchange.review_result(self.reviewer, second["id"], decision="accepted")
        rejected = self.exchange.review_result(self.reviewer, third["id"], decision="rejected", reason="Missing test scope")
        accepted_first = self.exchange.review_result(self.reviewer, first["id"], decision="accepted")
        self.assertEqual(accepted_first["reviewer"], "Reviewer")
        self.assertEqual(accepted_first["author"], "Author")
        self.assertEqual(accepted_first["outcome"], "failed")
        self.assertIsNotNone(accepted_first["reviewed_at"])
        self.assertEqual(rejected["reason"], "Missing test scope")
        self.assertIsNone(rejected["event_id"])
        with self.assertRaises(Conflict):
            self.exchange.review_result(self.reviewer, third["id"], decision="accepted")

        event_batch = self.exchange.poll_events(self.reader, limit=1)
        self.assertEqual(event_batch["events"], [{"id": accepted_second["event_id"], "kind": "result_accepted",
                                                   "result": accepted_second}])
        resume = Exchange(self.path).poll_events(self.reader, after=event_batch["next_cursor"])
        self.assertEqual([event["result"] for event in resume["events"]], [accepted_first])
        self.assertGreater(resume["next_cursor"], event_batch["next_cursor"])
        self.assertEqual(self.exchange.evidence(self.reader, "PB-0001"), [accepted_first])
        self.assertEqual(self.exchange.pending_results(self.reviewer), [fourth])
        for args in ({"after": -1}, {"after": 1 << 63}, {"limit": 101}):
            with self.assertRaises(ValueError):
                self.exchange.poll_events(self.reader, **args)

    def test_concurrent_review_creates_one_decision_and_one_event(self):
        other_reviewer = self.exchange.create_principal("Second reviewer", ["review"])["token"]
        result = self.exchange.submit_result(self.author, self.proposal())

        def approve(token):
            try:
                return self.exchange.review_result(token, result["id"], decision="accepted")
            except Conflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(approve, [self.reviewer, other_reviewer]))
        accepted = [outcome for outcome in outcomes if outcome]
        self.assertEqual(len(accepted), 1)
        feed = self.exchange.poll_events(self.reader)
        self.assertEqual([event["result"] for event in feed["events"]], accepted)

    def test_revocation_invalidates_token_and_active_work_but_preserves_attribution(self):
        self.exchange.register_work(self.author, "PB-0001")
        pending = self.exchange.submit_result(self.author, self.proposal())
        approved = self.exchange.review_result(self.reviewer, pending["id"], decision="accepted")
        revoked = self.exchange.revoke_principal("author")
        self.assertEqual(revoked, self.exchange.revoke_principal("Author"))
        self.assertEqual(revoked["name"], "Author")
        self.assertIsNotNone(revoked["revoked_at"])
        with self.assertRaises(AuthError):
            Exchange(self.path).authenticate(self.author)
        with self.assertRaises(AuthError):
            self.exchange.submit_result(self.author, self.proposal())
        with self.assertRaises(LookupError):
            self.exchange.revoke_principal("Unknown")
        self.exchange.revoke_principal("Reviewer")
        with self.assertRaises(AuthError):
            self.exchange.pending_results(self.reviewer)
        self.assertEqual(self.exchange.active_work(self.reader), [])
        self.assertEqual(self.exchange.evidence(self.reader, "PB-0001"), [approved])

    def test_exact_retries_return_same_submission_after_review(self):
        same_result = self.proposal(source_url="https://github.com/Example/SOURCE/pull/12#issuecomment-456",
                                    revision="A" * 40, summary="  The synthetic rectangle remained black.  ")
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(self.exchange.submit_result, self.author, payload)
                       for payload in (self.proposal(), same_result)]
        original, duplicate = (future.result() for future in futures)
        self.assertEqual(original, duplicate)
        self.assertEqual(len(self.exchange.pending_results(self.reviewer)), 1)
        accepted = self.exchange.review_result(self.reviewer, original["id"], decision="accepted")
        self.assertEqual(self.exchange.submit_result(self.author, same_result), accepted)
        other = self.exchange.create_principal("Other author", ["contribute"])["token"]
        self.assertNotEqual(self.exchange.submit_result(other, same_result)["id"], original["id"])
        self.assertEqual(len(self.exchange.poll_events(self.reader)["events"]), 1)


if __name__ == "__main__":
    unittest.main()
