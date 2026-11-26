"""Regression coverage for evidence and public partner integrations."""
from portbridge.community import Identity, apply_policy, people_profiles, read_data
from portbridge.integrations import digest, projection, select
from portbridge.network import repeat_use
from portbridge.radar_store import epoch
from portbridge.release_gate import audit
from portbridge.export import export

from test_portbridge import CatalogFixture

ORIGIN = "https://github.com/fxceless/victory-fork/pull/265"
NOW = "2026-11-26T17:00:00Z"


class M5Test(CatalogFixture):
    def test_correction_is_scoped_to_the_pr_authorship(self):
        old = {"login": "CoDrift", "user_id": None}
        other = {"login": "Merger", "user_id": 42}
        rows = apply_policy([
            {"id": "author", "source": ORIGIN, "role": "developer", "actor": old},
            {"id": "merger", "source": ORIGIN, "role": "repository_action", "actor": other},
        ], read_data("people_policy.json"))
        self.assertEqual(rows[0]["actor"], {"login": "CDR-0000", "user_id": 69203742})
        self.assertEqual(rows[0]["specialties"], ["graphics", "memory"])
        self.assertEqual(rows[1]["actor"], other)

    def test_digest_keeps_its_cursor_when_stale_and_returns_scoped_removal(self):
        task = {"id": "fresh", "title": "Check queue behavior", "source_url": ORIGIN,
                "projects": ["example"], "workflow_state": "queued", "age_state": "fresh",
                "revisions": [{"sha": "a" * 40}], "participant": "never expose"}
        projects = [{"slug": "example", "repo": "fxceless/victory-fork", "consoles": ["xbox-series"]}]
        feed = projection(projects, {"tasks": [task, task]}, {"stories": []}, as_of=NOW)
        self.assertEqual(len(select(feed, project="example")["items"]), 1)
        self.assertNotIn("participant", feed["items"][0])
        self.assertEqual(select(feed, console="ps5")["items"], [])
        clock = epoch(NOW)
        first, cursor = digest(feed, {}, project="example", now=clock)
        self.assertEqual(len(first["added_or_changed"]), 1)
        same, _ = digest(feed, cursor, project="example", now=clock)
        self.assertEqual(same["added_or_changed"], [])
        stale, saved = digest(feed, cursor, project="example", now=clock + 172801)
        self.assertIsNone(saved)
        self.assertEqual(stale["state"], "stale_or_invalid")
        with self.assertRaises(ValueError):
            digest(feed, cursor, console="ps5", now=clock)
        gone, _ = digest({**feed, "items": []}, cursor, project="example", now=clock)
        self.assertEqual(gone["no_longer_listed"], ["task:fresh"])

    def test_newer_public_receipt_overrides_a_failed_source_check(self):
        row = {"id": "a", "source": "https://github.com/Zettrox/ztrx/pull/63", "role": "developer",
               "actor": {"login": "PublicActor", "user_id": 42}, "checked_at": NOW}
        policy = read_data("people_policy.json")
        self.assertEqual(apply_policy([row], policy)[0]["source_state"], "unavailable")
        newer = {**row, "checked_at": "2026-11-26T18:00:00Z", "source_state": "available"}
        self.assertEqual(apply_policy([newer], policy), [newer])

    def test_playstation_generations_do_not_form_an_xbox_link(self):
        proof = {"id": "one", "source": ORIGIN, "subject": ORIGIN, "repo": "test/ps",
                 "actor": {"login": "PublicActor", "user_id": 42}, "role": "developer",
                 "at": NOW, "basis": "Authored a public PR", "specialties": []}
        identities = Identity([proof], {})
        profile = people_profiles([proof], identities, {"test/ps": ["ps4", "ps5"]}, epoch(NOW))[0]
        self.assertFalse(profile["cross_platform"])
        self.assertIsNone(profile["cross_platform_state"])

    def test_repeated_technical_use_only_counts_separate_tasks_and_days(self):
        task = "https://github.com/external/team/issues/"
        a = {"kind": "technical_trial", "at": NOW, "actor": "member", "reviewed": True,
             "task": task + "1", "proof": task + "1#issuecomment-1"}
        b = {**a, "task": task + "2", "proof": task + "2#issuecomment-2"}
        self.assertEqual(repeat_use([a, a, b])["verified_repeat_teams"], [])
        self.assertEqual(repeat_use([a, {**b, "at": "2026-11-27T12:00:00Z"}])["verified_repeat_teams"], ["external/team"])
        self.assertEqual(repeat_use([{**a, "kind": "listing"}])["single_or_repeat_teams"], [])

    def test_release_gate_rejects_private_database_and_modified_public_feed(self):
        site = self.workspace / "site"
        export(self.catalog, site)
        self.assertEqual(audit(site), [])
        (site / "forbidden.sqlite3").touch()
        (site / "data/partner.json").write_text('{"items":[]}', encoding="utf-8")
        self.assertEqual(set(audit(site)), {"forbidden.sqlite3", "data/partner.json"})
