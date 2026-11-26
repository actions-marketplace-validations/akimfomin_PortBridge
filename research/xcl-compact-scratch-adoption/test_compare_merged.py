# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from compare_merged import BUILDS, CASES


SCRIPT = Path(__file__).with_name("compare_merged.py")
BASELINE = "082944135cd2b96288470a595861fa608eee08dc"
CANDIDATE = "b3f7ab5574c4489761141e2de0ce31d2eb216412"


class CompareRevisionTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.measurements = Path(directory.name) / "measurements.jsonl"
        with self.measurements.open("w", encoding="utf-8") as output:
            for case, kind in CASES:
                for build in BUILDS:
                    scratch = 288 if build == "baseline" else 256
                    output.write(json.dumps({
                        "case": case,
                        "input": kind,
                        "build": build,
                        "grid": [1, 1, 1],
                        "pieces": 3,
                        "scratch_dwords_per_group": scratch,
                        "words_checked": 128,
                        "different_words": 0,
                        "gpu_us_rounds": [[10.0] * 20] * 4,
                    }) + "\n")

    def run_comparator(self, *args):
        return subprocess.run(
            [sys.executable, "-I", "-B", SCRIPT, self.measurements, *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_summary_records_both_measured_revisions(self):
        result = self.run_comparator(
            "--baseline-revision", BASELINE, "--candidate-revision", CANDIDATE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["baseline_xcl_revision"], BASELINE)
        self.assertEqual(summary["candidate_xcl_revision"], CANDIDATE)
        self.assertEqual(len(summary["results"]), len(CASES))
        self.assertNotIn("gpu_us_rounds", result.stdout)

    def test_rejects_missing_short_or_identical_baseline(self):
        valid_candidate = ("--candidate-revision", CANDIDATE)
        for options in ((), ("--baseline-revision", BASELINE[:7]), ("--baseline-revision", CANDIDATE)):
            with self.subTest(options=options):
                result = self.run_comparator(*valid_candidate, *options)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
