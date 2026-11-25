# SPDX-License-Identifier: MIT
"""Check guard fusion, proof failures, and fail-closed source rewrites."""

import unittest

from lane_contract import Domain, Lowering, Participation
from replay_continued_synthesis import observed_subgroup_width
from spirv_synthesis import UNSAFE_CONTROL, optimize, prove_plan
from test_spirv_transport import MODULE


class SpirvSynthesisTest(unittest.TestCase):
    def test_width_requires_an_actual_supported_layout(self):
        for line, expected in (
            ("compute subgroup size: 32\n", 32),
            ("compute subgroup size: 64 (observed: all 40 invocations of a 40x1x1 group)\r\n", 64),
            ("compute subgroup size: 64 (observed: all 64 invocations of a 64x1x1 group, full subgroups)\n", 64),
            ("compute subgroup size: 64 not available\n", None),
            ("compute subgroup size: 64 observed wrong in 1 of 40 invocations\n", None),
        ):
            with self.subTest(line=line):
                self.assertEqual(observed_subgroup_width(line), expected)

    def test_defaults_keep_host_ballot_and_defined_index(self):
        result, report = optimize(MODULE, participation=Participation.SUPERSET)
        row, = report["reads"]
        self.assertEqual(row["plan"], "host-ballot-self-fallback")
        self.assertEqual(row["removed_operations"], 5)
        self.assertEqual({p["projected_probes"] for p in row["proof"].values()}, {24064})
        self.assertIn("%ballot = OpGroupNonUniformBallot %v4 %scope %always", result)
        self.assertIn("%read = OpGroupNonUniformShuffle %word %scope %input_value %safe_index", result)
        self.assertIn("%read_bits = OpSelect %word %present %read %zero", result)
        self.assertIn("%merge = OpSelect %word %active %read_bits %old", result)
        self.assertNotIn("%exec_mask", result)
        self.assertNotIn("%complement", result)
        self.assertIn("OpStore %slot %merge", result)

    def test_minimum_size_requires_both_explicit_conditions(self):
        for defined, masked_poison, candidate, saving in (
            (False, True, "host-ballot-select", 6),
            (True, False, "exec-ballot-self-fallback", 6),
            (True, True, "exec-ballot-select", 7),
        ):
            with self.subTest(candidate=candidate):
                result, report = optimize(MODULE, participation=Participation.SUPERSET, defined_exec=defined,
                                          allow_masked_poison=masked_poison)
                row, = report["reads"]
                self.assertEqual(row["plan"], candidate)
                self.assertEqual(row["removed_operations"], saving)
                self.assertEqual("%ballot = OpGroupNonUniformBallot %v4 %scope %active" in result, defined)
                self.assertEqual("%safe_index =" in result, not masked_poison)
                self.assertEqual("%input_value =" in result, not defined)

    def test_bitwise_mask_does_not_isolate_poison(self):
        proof = prove_plan(UNSAFE_CONTROL, Lowering(32), Domain(64, 32, Participation.SUPERSET))
        self.assertGreater(proof.failures, 0)
        self.assertEqual(proof.witness.reason, "target returns undefined for a defined guest result")

    def test_independent_host_participation_blocks_rewrite(self):
        result, report = optimize(MODULE, participation=Participation.INDEPENDENT)
        row, = report["reads"]
        self.assertIsNone(row["plan"])
        self.assertEqual(result, MODULE)
        self.assertGreater(row["proof"]["64"]["failures"], 0)

    def test_wrong_half_blocks_rewrite_even_if_wave32_could_pass(self):
        wrong = MODULE.replace("OpBitwiseAnd %word %self %high_mask", "OpBitwiseAnd %word %self %zero")
        result, report = optimize(wrong, participation=Participation.SUPERSET)
        row, = report["reads"]
        self.assertEqual(result, wrong)
        self.assertIsNone(row["plan"])
        self.assertEqual(row["proof"]["32"]["failures"], 0)
        self.assertGreater(row["proof"]["64"]["failures"], 0)

    def test_does_not_change_shared_ballot_or_remove_named_result(self):
        shared = MODULE.replace("%present = ", "%observed = OpCopyObject %v4 %ballot\n%present = ")
        result, report = optimize(shared, participation=Participation.SUPERSET, defined_exec=True)
        self.assertIn("%observed = OpCopyObject %v4 %ballot", result)
        self.assertEqual(report["reads"][0]["plan"], "host-ballot-self-fallback")
        named = MODULE.replace("OpDecorate %lane_input", 'OpName %complement "retained mask"\nOpDecorate %lane_input')
        result, report = optimize(named, participation=Participation.SUPERSET)
        self.assertEqual(result, named)
        self.assertIsNone(report["reads"][0]["plan"])

    def test_guest_ballot_keeps_original_program_point(self):
        ballot = "%ballot = OpGroupNonUniformBallot %v4 %scope %always\n"
        late_active = MODULE.replace(ballot, "").replace("%active =", ballot + "%active =")
        result, report = optimize(late_active, participation=Participation.SUPERSET, defined_exec=True)
        self.assertIn(ballot, result)
        self.assertEqual(report["reads"][0]["plan"], "host-ballot-self-fallback")

    def test_reports_do_not_mutate_cached_proofs(self):
        _, old = optimize(MODULE, participation=Participation.SUPERSET)
        old["reads"][0]["proof"]["32"]["failures"] = 99
        _, new = optimize(MODULE, participation=Participation.SUPERSET)
        self.assertEqual(new["reads"][0]["proof"]["32"]["failures"], 0)


if __name__ == "__main__":
    unittest.main()
