# SPDX-License-Identifier: MIT
import random
import unittest

from emit import emit
from factoring import Instruction, Kind, Region, UINT32, Value, evaluate, factor, structural_limit
from workloads import matrix, pcg32, synthetic


class FactoringTests(unittest.TestCase):
    def test_pattern_with_local_shape_mismatch_limits_suffix(self):
        x = Value(Kind.INPUT, 0)
        prev = Value(Kind.LOCAL, 0)
        arms = ((Instruction("add", x, x), Instruction("add", prev, x),
                 Instruction("xor", x, prev)),
                (Instruction("add", x, x), Instruction("add", prev, x),
                 Instruction("xor", x, Value(Kind.LOCAL, 1))))
        self.assertEqual(structural_limit(arms), 1)
        self.assertIsNone(factor(Region(1, arms)))

    def test_invalid_reference_and_effects_are_rejected(self):
        x = Value(Kind.INPUT, 0)
        for bad in (Instruction("store", x, x), Instruction("add", Value(Kind.LOCAL, 0), x)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Region(1, ((bad,), (bad,)))

    def test_profit_threshold_and_typed_emission(self):
        plan = factor(pcg32(8))
        self.assertEqual(len(plan.body), 9)
        self.assertEqual(plan.parameter_count, 1)
        self.assertGreater(plan.estimated_savings, 0)
        self.assertLess(len(emit(pcg32(8), plan)), len(emit(pcg32(8))))
        self.assertIsNone(factor(synthetic(16, 16, heterogeneous=True)))
        self.assertIsNone(factor(synthetic(4, 0)))

    def test_equal_tail_with_no_edge_parameters_drops_switch(self):
        bit = Value(Kind.INPUT, 0)
        only = (Instruction("xor", bit, bit),)
        region = Region(1, (only, only))
        plan = factor(region)
        self.assertEqual(plan.parameter_count, 0)
        self.assertNotIn("switch", emit(region, plan))
        self.assertEqual(evaluate(region, UINT32, (UINT32,), plan), 0)

    def test_relative_local_alignment_with_different_prefix_lengths(self):
        original = pcg32(2)
        left, right = original.arms

        def shift(value):
            return Value(Kind.LOCAL, value.index + 1) if value.kind == Kind.LOCAL else value

        padded = (Instruction("xor", Value(Kind.INPUT, 0), Value(Kind.LITERAL, 1)),) + tuple(
            Instruction(step.opcode, shift(step.left), shift(step.right)) for step in right
        )
        region = Region(original.input_count, (left, padded))
        plan = factor(region)
        self.assertEqual(tuple(map(len, plan.prefixes)), (2, 3))
        self.assertEqual(len(plan.body), 9)
        for selector in (0, 1, UINT32):
            inputs = (0x235, 0x7fffffff, 0x80000000)
            self.assertEqual(evaluate(region, selector, inputs), evaluate(region, selector, inputs, plan))

    def test_factor_equals_original_across_arms_and_boundary_words(self):
        rng = random.Random(317)
        edge_values = (0, 1, 31, 32, 33, 0x7fff_ffff, 0x8000_0000, UINT32)
        for case, region in matrix().items():
            with self.subTest(case=case):
                plan = factor(region)
                selectors = list(range(len(region.arms))) + [0, 1, UINT32]
                for selector in selectors:
                    for init in edge_values:
                        inputs = [init] + [rng.getrandbits(32) for _ in range(region.input_count - 1)]
                        self.assertEqual(evaluate(region, selector, inputs), evaluate(region, selector, inputs, plan))

    def test_random_structure_and_non_power_of_two_selectors(self):
        rng = random.Random(917)
        x, y = Value(Kind.INPUT, 0), Value(Kind.INPUT, 1)
        for _ in range(200):
            arms = []
            for arm_id in range(3):
                steps = [Instruction("add", x, Value(Kind.LITERAL, arm_id))]
                for index in range(1, 20):
                    if rng.randrange(4) == 0:
                        left = Value(Kind.LOCAL, rng.randrange(index))
                    else:
                        left = Value(Kind.LOCAL, index - 1)
                    steps.append(Instruction("xor", left, y))
                arms.append(tuple(steps))
            region = Region(2, tuple(arms))
            plan = factor(region)
            if plan:
                for selector in [0, 1, 2, UINT32]:
                    inputs = [rng.getrandbits(32), rng.getrandbits(32)]
                    self.assertEqual(evaluate(region, selector, inputs), evaluate(region, selector, inputs, plan))


if __name__ == "__main__":
    unittest.main()
