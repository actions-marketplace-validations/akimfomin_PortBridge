import unittest
from dataclasses import replace

from mipmap_contract import (
    FastPath,
    Rectangle,
    affected_regions,
    lane_counterexample,
    plan_chain,
    required_source,
    rewrite_fast,
)


class DependencyRegions(unittest.TestCase):
    def test_odd_source_tap_crosses_a_two_pixel_boundary(self):
        self.assertEqual(
            affected_regions(5, 5, 3, Rectangle(2, 2, 3, 3)),
            (Rectangle(2, 2, 3, 3), Rectangle(0, 0, 2, 2), Rectangle(0, 0, 1, 1)),
        )
        self.assertEqual(
            affected_regions(6, 6, 2, Rectangle(2, 2, 3, 3))[1],
            Rectangle(1, 1, 2, 2),
        )

    def test_single_axis_footprints_against_direct_tap_intersection(self):
        for size in range(2, 42):
            for lo in range(size):
                for hi in range(lo + 1, size + 1):
                    dirty = set(range(lo, hi))
                    taps = 2 + (size % 2)
                    expected = [i for i in range(size // 2) if dirty.intersection(
                        range(2 * i, 2 * i + taps))]
                    actual = affected_regions(size, 1, 2, Rectangle(lo, 0, hi, 1))[1]
                    self.assertEqual(expected, list(range(actual.x0, actual.x1)))
                    self.assertEqual((actual.y0, actual.y1), (0, 1))

    def test_partial_requires_initialized_lower_levels_and_remains_unfused(self):
        rect = Rectangle(3, 2, 14, 15)
        with self.assertRaisesRegex(ValueError, "retained texels"):
            plan_chain(35, 27, 5, dirty=rect)
        plan, regions = plan_chain(35, 27, 5, dirty=rect, old_chain_valid=True,
                                   intermediate_values_allowed=True, fast=FULL)
        self.assertEqual([entry.path for entry in plan], ["reference"] * 4)
        self.assertEqual(regions[0], rect)
        with self.assertRaises(ValueError):
            affected_regions(16, 16, 3, Rectangle(15, 0, 17, 1))

    def test_destination_read_halo_includes_the_unchanged_neighbor(self):
        destination = affected_regions(9, 7, 2, Rectangle(8, 4, 9, 7))[1]
        self.assertEqual(destination, Rectangle(3, 1, 4, 3))
        self.assertEqual(required_source(9, 7, destination), Rectangle(6, 2, 9, 7))
        with self.assertRaises(ValueError):
            required_source(9, 7, Rectangle(0, 0, 5, 3))


FULL = FastPath(32, True, True, True, True, 65535, 256)


class DispatchChoices(unittest.TestCase):
    def test_reference_plan_requires_an_explicit_numeric_contract_to_fuse(self):
        plan, _ = plan_chain(4096, 4096, 13, fast=FULL)
        self.assertEqual([step.path for step in plan], ["reference"] * 12)
        plan, _ = plan_chain(4096, 4096, 13, intermediate_values_allowed=True, fast=FULL)
        self.assertEqual([(step.source_level, step.levels, step.path) for step in plan],
                         [(0, 6, "shuffle"), (6, 6, "shuffle")])

    def test_unsupported_shapes_and_launch_conditions_never_choose_shuffle(self):
        cases = [
            (4095, 4095, 1, FULL),
            (4096, 4096, 2, FULL),
            (4096, 4096, 1, replace(FULL, subgroup_width=16)),
            (4096, 4096, 1, replace(FULL, full_subgroups=False)),
            (4096, 4096, 1, replace(FULL, logical_lane_indices=False)),
            (4096, 4096, 1, replace(FULL, compatible_image_views=False)),
            (4096, 4096, 1, replace(FULL, shuffle=False)),
            (4096, 4096, 1, replace(FULL, max_local_x=128)),
        ]
        for w, h, layers, profile in cases:
            with self.subTest(shape=(w, h, layers), profile=profile):
                plan, _ = plan_chain(w, h, 12, layers=layers,
                                     intermediate_values_allowed=True, fast=profile)
                self.assertNotIn("shuffle", {step.path for step in plan})

    def test_fast_dispatch_respects_workgroup_count_and_unsigned_source_math(self):
        self.assertFalse(replace(FULL, max_groups_x=1023).admits((4096, 4096), 6))
        self.assertTrue(FULL.admits((4096, 4096), 6))
        self.assertFalse(FULL.admits((65536, 65536), 6))
        self.assertFalse(FULL.admits((4, 4), -1))

    def test_non_power_of_two_can_have_a_divisible_prefix(self):
        plan, _ = plan_chain(1920, 1088, 11, intermediate_values_allowed=True, fast=FULL)
        self.assertEqual([(step.levels, step.path) for step in plan],
                         [(6, "shuffle"), (2, "general"), (2, "general")])


class LaneOrdering(unittest.TestCase):
    def test_stock_shader_can_read_a_texel_from_another_logical_quartet(self):
        physical_order = list(range(256))
        physical_order[1], physical_order[4] = physical_order[4], physical_order[1]
        for width in (32, 64):
            witness = lane_counterexample(physical_order, width=width, levels=2, tiles=2)
            self.assertEqual((witness.stage, witness.physical_lane, witness.actual, witness.expected),
                             ("quartet-shuffle", 0, 4, 1))

    def test_reindexed_full_subgroups_keep_tail_tiles_and_shared_finish_defined(self):
        for width in (32, 64):
            for levels in range(1, 7):
                capacity = 256 >> min(8, 2 * levels - 2)
                for tiles in range(1, capacity + 1):
                    self.assertIsNone(lane_counterexample(range(256), width=width,
                                                         levels=levels, tiles=tiles))

    def test_missing_lane_and_unpinned_source_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "full permutation"):
            lane_counterexample(range(255), width=32, levels=2, tiles=1)
        with self.assertRaisesRegex(ValueError, "pinned"):
            rewrite_fast(b"layout(local_size_x = 256) in;")


if __name__ == "__main__":
    unittest.main()
