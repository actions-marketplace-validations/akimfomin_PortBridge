import random
import unittest

from benchmark import table_body, workload
from dispatch import Projection, U32_MASK, adaptive, emit, partition


class DispatchTests(unittest.TestCase):
    def test_unsigned_and_signed_spellings_alias(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            adaptive([U32_MASK, -1])
        values = [-1, -(1 << 31), 0, 7]
        dispatch = partition(values, Projection(28, 4))
        self.assertEqual([dispatch.select(v) for v in values], [U32_MASK, 1 << 31, 0, 7])
        for invalid in (True, 2.0, U32_MASK + 1, -(1 << 31) - 1):
            with self.assertRaises(ValueError):
                dispatch.select(invalid)

    def test_missing_outer_and_inner_cases_both_use_default(self):
        plan = partition([2, 4, 0x80000002], Projection(28, 4))
        for value in (3, 0x70000002, 0x80000003):
            self.assertIsNone(plan.select(value))
        code = emit(plan, "tag", lambda label: f"result = {label}u;", "result = 999u;")
        self.assertEqual(code.count("result = 999u"), 3)
        self.assertIn("case 0x80000002u", code)
        self.assertEqual(len(plan.fanouts), 3)

    def test_flat_until_enough_cases(self):
        self.assertIsNone(adaptive([]).projection)
        self.assertEqual(adaptive(workload("small")), partition(workload("small")))

    def test_bit_windows_avoid_both_fixed_failures(self):
        def score(layout):
            return sum(size * size for size in layout.fanouts)

        for name in ("dense", "strided"):
            labels = workload(name)
            self.assertIsNone(adaptive(labels).projection)
            best = adaptive(labels, minimum_cases=1)
            fixed_low = partition(labels, Projection(6, 10))
            fixed_high = partition(labels, Projection(24, 8))
            self.assertLessEqual(score(best), min(score(fixed_low), score(fixed_high)))
            self.assertIsNotNone(best.projection)

    def test_exact_partition_on_seeded_sparse_and_boundary_inputs(self):
        generator = random.Random(2322)
        for n in (0, 1, 24, 64, 130, 512, 2048):
            labels = sorted(generator.sample(range(1 << 31), n))
            labels = [value | ((value & 1) << 31) for value in labels]
            expected = set(labels)
            probes = labels + [generator.getrandbits(32) for _ in range(5000)]
            probes += [(value + delta) & U32_MASK for value in labels for delta in (-1, 1)]
            for plan in (partition(labels), partition(labels, Projection(6, 10)), adaptive(labels)):
                for label in probes:
                    self.assertEqual(plan.select(label), label if label in expected else None)

    def test_emitter_and_projection_validation(self):
        for args in ((32, 1), (25, 8), (0, 0), (-1, 4), (0, 17), (0.5, 1), (True, 1)):
            with self.assertRaises(ValueError):
                Projection(*args)
        with self.assertRaises(ValueError):
            emit(partition([1]), "tag + 1", str, "ignored")
        with self.assertRaises(ValueError):
            adaptive([1], minimum_cases=0)
        self.assertIn("if (lo < 24u)", table_body(24))


if __name__ == "__main__":
    unittest.main()
