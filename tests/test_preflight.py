import unittest
from unittest.mock import patch

from portbridge.preflight import assess, preflight, public_preflight
from test_portbridge import CatalogFixture


class PreflightTest(CatalogFixture):
    def test_one_url_returns_provenance_and_backend_limits(self):
        url = "https://github.com/ubiquitarianism/leonida/pull/207"
        report = preflight(self.catalog, url=url)
        case = report["problems"][0]
        comparison = next(row for row in case["solutions"] if row["project"] == "victory")
        self.assertEqual(case["id"], "PB-0001")
        self.assertEqual(comparison["applicability"], "test_reference_across_stacks")
        self.assertEqual(report["first_check"]["project"], "victory")
        self.assertIn("7120734503", report["first_check"]["url"])
        self.assertTrue(report["first_check"]["revision"])

    def test_copied_revision_is_one_source_even_when_titles_differ(self):
        sha = "a" * 40
        left = self.observation("continued", "pr", 772, "Enable compatibility",
                                "https://github.com/ubiquitarianism/leonida/pull/772", {"head_sha": sha})
        right = self.observation("reforge", "commit", sha, "Follow-up staged",
                                 f"https://github.com/LeonidaReforge/Leonida/commit/{sha}", {"sha": sha})
        self.catalog.record_sync({"items": [left, right]})
        report = preflight(self.catalog, q=left["url"])
        self.assertEqual([row["relationship"] for row in report["matches"]], ["same_revision"])
        self.assertEqual(report["matches"][0]["applicability"], "shared_commit_check_adoption_separately")

    def test_public_uses_same_rules_without_token_or_local_db(self):
        frozen = {"projects": {"projects": self.catalog.projects()}, "problems": {"problems": self.catalog.problems()},
                  "observations": {"observations": []}, "health": self.catalog.health()}
        with patch("portbridge.preflight.snapshot", side_effect=lambda resource, **_: frozen[resource]):
            report = public_preflight(q="#20")
        self.assertEqual(report["problems"][0]["relationship"], "source_port")
        snapshots = report["problems"][0]["solutions"][0]["evidence"]
        self.assertEqual(snapshots[0]["outcome"], "failed")
        self.assertEqual(snapshots[0]["kind"], "automated_test")

    def test_we_do_not_fetch_a_supplied_url(self):
        with self.assertRaisesRegex(ValueError, "public GitHub"):
            assess([], [], [], {}, url="https://example.com/issue/1")


if __name__ == "__main__":
    unittest.main()
