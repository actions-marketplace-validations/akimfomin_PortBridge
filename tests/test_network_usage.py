"""Historical imports and reviewed relaunch activity must never satisfy each other's goal."""
import json
from contextlib import redirect_stdout
from io import StringIO
import subprocess
import sys
import unittest
from unittest.mock import patch

from portbridge.network import CHANNELS, main
from portbridge.network_usage import outcomes
from portbridge.radar_store import epoch
from test_portbridge import CatalogFixture

REV = "0738093add1ed01dad89c4bdcb6df74eb8891701"
NOW = epoch("2026-12-05T00:00:00Z")


def event(number=1, day=1, repo="example/engine"):
    task = f"https://github.com/{repo}/issues/{number}"
    return {"kind": "technical_reuse", "actor": "ExternalDev", "reviewed": True,
            "at": f"2026-12-{day:02}T08:15:00Z", "task": task,
            "proof": f"{task}#issuecomment-{number}", "portbridge_revision": REV,
            "version_evidence": f"Used PortBridge@{REV} to check this PR."}


class NetworkUsageTest(unittest.TestCase):
    def setUp(self):
        self.public = json.loads(CHANNELS.read_bytes())
        self.public["relaunch_usage"] = []
        self.public["relaunch_teams"] = {"example/engine": "example/engine"}

    def outcome(self, *events, history=()):
        return outcomes(self.public, {"usage": history, "relaunch_usage": events}, as_of=NOW)

    def test_relaunch_accepts_published_m52_reference_on_new_receipts_only(self):
        revision = "e1c3f840df2ab4456b7348f4ce8b5b576ed474db"
        fresh = [{**event(i, i), "version_evidence": "We used PortBridge M5.2.", "portbridge_revision": revision}
                 for i in (1, 2)]
        self.assertEqual(self.outcome(*fresh)["relaunch"]["verified_repeat_teams"], ["example/engine"])
        self.assertEqual(self.outcome(history=fresh)["relaunch"]["single_or_repeat_team_count"], 0)

    def test_continued_advisory_two_people_one_task_no_claim_of_tool_or_repeat_use(self):
        public = json.loads(CHANNELS.read_bytes())
        offer, = public["relaunch_advisories"]
        response, other = offer["responses"]
        # Re-imports, invitation-only links and technical feedback predating the offer do not add receipts.
        offer["responses"].extend([response, {**other, "proof": offer["offer"]},
                                   {**other, "at": "2026-11-26T20:00:00Z"}])
        current = outcomes(public, {}, as_of=NOW)["relaunch"]
        self.assertEqual(current["single_or_repeat_team_count"], 0)
        applied = current["advisory_handoffs"]
        self.assertEqual(applied["single_or_repeat_teams"], ["ubiquitarianism/leonida"])
        self.assertEqual((applied["receipt_count"], applied["participant_count"], applied["task_count"]), (2, 2, 1))
        self.assertEqual(applied["verified_repeat_team_count"], 0)
        self.assertFalse(applied["reached"])
        self.assertEqual(outcomes(public, {}, as_of=epoch(offer["offered_at"]))["relaunch"]
                         ["advisory_handoffs"]["receipt_count"], 0)
        for override in ({"reviewed": False}, {"portbridge_revision": REV}, {"version_link": offer["offer"]},
                         {"offer": "https://github.com/ubiquitarianism/leonida/pull/2198#issuecomment-12"}):
            public["relaunch_advisories"] = [{**offer, **override}]
            self.assertEqual(outcomes(public, {}, as_of=NOW)["relaunch"]["advisory_handoffs"]["receipt_count"], 0)

    def test_historical_framelab_and_three_receiving_repositories_remain_visible(self):
        result = self.outcome()
        self.assertIn("5headsmartbtw/leonida-framelab", result["historical"]["verified_repeat_teams"])
        self.assertTrue({"5headsmartbtw/leonida-framelab", "loopersalty/anyxboxx", "ubiquitarianism/leonida"}
                        <= set(result["historical"]["single_or_repeat_teams"]))
        self.assertEqual(result["relaunch"]["single_or_repeat_team_count"], 0)
        # An untagged local entry must also stay historical, regardless of date.
        self.assertEqual(self.outcome(history=[event(), event(2, 2)])["relaunch"], result["relaunch"])

    def test_historical_receipts_with_new_dates_and_version_labels_stay_historical(self):
        team = "5headsmartbtw/leonida-framelab"
        self.public["relaunch_teams"][team] = team
        cloned = [{**row, "at": event(day=day)["at"], "portbridge_revision": REV,
                   "version_evidence": event()["version_evidence"],
                   "proof": row["proof"].replace("leonida-framelab", "LEONIDA-FRAMELAB")}
                  for day, row in enumerate(self.public["usage"][1:3], 1)]
        self.assertEqual(self.outcome(*cloned)["relaunch"]["single_or_repeat_team_count"], 0)
        self.assertEqual(self.outcome(*cloned, event(99, 3, team))["relaunch"]["verified_repeat_teams"], [])

    def test_reviewed_public_revision_and_external_technical_proof_required(self):
        first = event()
        for changed in ({"kind": "listing"}, {"reviewed": False}, {"actor": "AKIMFOMIN"},
                        {"actor": "test[bot]"}, {"actor": {}}, {"portbridge_revision": "0" * 40},
                        {"version_evidence": None}, {"version_evidence": "Used the published version"},
                        {"proof": "https://github.com/example/engine"}, {"proof": event(2)["proof"]},
                        {"proof": event(repo="other/engine")["proof"]}, {"task": "http://localhost/1"},
                        {"at": "2026-11-26T18:48:32Z"}, {"at": "2026-12-06T00:00:00Z"}):
            with self.subTest(changed=changed):
                self.assertEqual(self.outcome({**first, **changed})["relaunch"]["single_or_repeat_teams"], [])
        self.public["relaunch_teams"]["akimfomin/fork"] = "example/engine"
        self.assertEqual(self.outcome(event(repo="akimfomin/fork"))["relaunch"]["single_or_repeat_teams"], [])
        self.assertEqual(self.outcome(first)["relaunch"]["single_or_repeat_teams"], ["example/engine"])

    def test_two_receipts_on_separate_tasks_and_utc_days_required(self):
        first = {**event(), "at": "2026-12-01T23:30:00Z"}
        same_day = {**event(2), "at": "2026-12-02T00:45:00+02:00"}
        same_task = {**event(day=2), "task": first["task"].replace("/issues/", "/pull/"),
                     "proof": first["task"] + "#issuecomment-19"}
        for other in (first, same_day, same_task):
            self.assertEqual(self.outcome(first, other)["relaunch"]["verified_repeat_teams"], [])
        self.assertEqual(self.outcome(first, event(2, 2))["relaunch"]["verified_repeat_teams"], ["example/engine"])

    def test_public_version_name_is_sufficient_and_generic_or_partial_names_do_not_match(self):
        first = {**event(), "version_evidence": "We ran PortBridge M5.1."}
        self.assertEqual(self.outcome(first)["relaunch"]["single_or_repeat_team_count"], 1)
        self.assertEqual(self.outcome({**first, "portbridge_revision": "a9fcf3ecda9dd5e7db769080c9b83aa626931414"})
                         ["relaunch"]["single_or_repeat_team_count"], 0)
        for mention in ("We ran PortBridge M5.10", "PortBridge M5", "PortBridge M5.1-preview"):
            self.assertEqual(self.outcome({**first, "version_evidence": mention})["relaunch"]["single_or_repeat_team_count"], 0)

    def test_disputed_commit_receipt_cannot_seed_repeat_use(self):
        proof = "https://github.com/example/engine/commit/" + "a" * 40
        first = {**event(), "proof": proof}
        other = {**event(2, 2), "proof": proof + "#diff-context"}
        for rows in ((first, other), (other, first)):
            self.assertEqual(self.outcome(*rows, event(3, 3))["relaunch"]["verified_repeat_teams"], [])

    def test_goal_needs_three_receiving_teams_with_repeated_use(self):
        self.public["relaunch_teams"] = {"one/engine": "one/engine", "other-owner/plugin": "one/engine",
                                        "two/engine": "two/engine", "three/port": "three/port"}
        rows = [event(n, n, repo) for repo in self.public["relaunch_teams"] if repo != "three/port"
                for n in (1, 2)]
        self.public["relaunch_usage"] = rows[:2]
        result = self.outcome(*rows, *rows)["relaunch"]
        self.assertEqual(result["verified_repeat_teams"], ["one/engine", "two/engine"])
        self.assertFalse(result["reached"])
        result = self.outcome(*rows, event(1, 2, "three/port"), event(3, 4, "three/port"))["relaunch"]
        self.assertEqual(result["verified_repeat_team_count"], 3)
        self.assertTrue(result["reached"])

    def test_unconfirmed_or_conflicting_team_attribution_does_not_create_new_teams(self):
        local = {"relaunch_usage": [event(), event(2, 2), event(repo="unknown/repo")],
                 "relaunch_teams": {"Example/Engine": "another/team"}}
        self.assertEqual(outcomes(self.public, local, as_of=NOW)["relaunch"]["single_or_repeat_teams"], [])


class NetworkCliTest(CatalogFixture):
    def test_cli_reads_and_deduplicates_new_receipts_from_a_local_ledger(self):
        path = self.workspace / "ledger.json"
        path.write_text(json.dumps({"relaunch_teams": {"example/engine": "example/engine"},
                                    "relaunch_usage": [event(), event(2, 2), event(2, 2)]}), encoding="utf-8")
        output = StringIO()
        with patch("portbridge.network_usage.time.time", return_value=NOW), redirect_stdout(output):
            main(["--outcomes-only", "--ledger", str(path)])
        self.assertEqual(json.loads(output.getvalue())["outcome"]["relaunch"]["verified_repeat_teams"], ["example/engine"])

    def test_full_cli_and_outcomes_only_show_the_same_two_measures(self):
        command = [sys.executable, "-B", "-m", "portbridge.network"]
        receipt = json.loads(subprocess.check_output([*command, "--outcomes-only"]))
        full = json.loads(subprocess.check_output([*command, "--db", str(self.db_path)]))
        self.assertIn("categories", full)
        self.assertEqual(receipt, {"outcome": full["outcome"]})
        self.assertEqual(set(receipt["outcome"]), {"historical", "relaunch"})
