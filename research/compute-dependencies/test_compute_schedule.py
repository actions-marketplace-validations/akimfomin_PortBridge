# SPDX-License-Identifier: MIT
from itertools import combinations
import unittest

from compute_schedule import (
    AccessMode,
    BufferAccess,
    BufferRange,
    Hazard,
    HazardKind,
    Operation,
    Stage,
    analyze,
    find_hazards,
    minimum_barrier_cuts,
)
from halide_trace import dependent_trace, mixed_trace


class ComputeScheduleTests(unittest.TestCase):
    def test_half_open_intersection_and_three_conflict_kinds(self):
        left = BufferRange("shared", 0, 32)
        right = BufferRange("shared", 16, 48)
        operations = (
            Operation("compute", Stage.COMPUTE, (BufferAccess(left, AccessMode.READ_WRITE),)),
            Operation("transfer", Stage.TRANSFER, (BufferAccess(right, AccessMode.READ_WRITE),)),
            Operation("different buffer", Stage.COMPUTE, (
                BufferAccess(BufferRange("other", 0, 32), AccessMode.WRITE),
            )),
            Operation("touching only", Stage.COMPUTE, (
                BufferAccess(BufferRange("shared", 48, 60), AccessMode.WRITE),
            )),
        )
        hazards = find_hazards(operations)
        self.assertEqual(len(hazards), 3)
        self.assertEqual({edge.kind for edge in hazards}, set(HazardKind))
        for edge in hazards:
            self.assertEqual((edge.producer, edge.consumer), (0, 1))
            self.assertIs(edge.source_stage, Stage.COMPUTE)
            self.assertIs(edge.destination_stage, Stage.TRANSFER)
            self.assertEqual(edge.region, BufferRange("shared", 16, 32))

    def test_read_only_pair_needs_no_cut(self):
        view = BufferAccess(BufferRange("shared", 4, 10), AccessMode.READ)
        trace = (
            Operation("compute reads", Stage.COMPUTE, (view,)),
            Operation("transfer reads", Stage.TRANSFER, (view,)),
        )
        proof = analyze(trace, event_budget=1)
        self.assertEqual((proof.hazards, proof.baseline, proof.events), ((), (), ()))

    def test_minimum_cuts_against_exhaustive_small_oracle(self):
        for length in range(2, 6):
            combinations_of_cuts = [
                subset
                for size in range(length)
                for subset in combinations(range(1, length), size)
            ]
            hazards = [
                Hazard(left, right, Stage.COMPUTE, Stage.TRANSFER, HazardKind.RAW,
                       BufferRange("buffer", 0, 1))
                for left, right in combinations(range(length), 2)
            ]
            for mask in range(1 << len(hazards)):
                edges = [edge for index, edge in enumerate(hazards) if mask & (1 << index)]
                reference = next(
                    subset for subset in combinations_of_cuts
                    if all(any(edge.producer < cut <= edge.consumer for cut in subset)
                           for edge in edges)
                )
                cuts = minimum_barrier_cuts(edges)
                self.assertEqual(len(cuts), len(reference))
                self.assertCountEqual([edge for cut in cuts for edge in cut.hazards], edges)
                self.assertTrue(all(edge.covered_by(cut.before) for cut in cuts for edge in cut.hazards))

    def test_events_represent_whole_cut_groups_and_keep_all_hazards(self):
        trace = mixed_trace(blocks=4)
        schedule = analyze(trace, event_budget=2)
        self.assertEqual(len(trace), 32)
        self.assertEqual(len(schedule.baseline), 16)
        self.assertEqual(len(schedule.events), 2)
        self.assertEqual(len(schedule.ordinary), 14)
        assigned = schedule.ordinary + tuple(event.wait for event in schedule.events)
        self.assertCountEqual(assigned, schedule.baseline)
        self.assertCountEqual([edge for cut in assigned for edge in cut.hazards], schedule.hazards)

        checkpoint_raw = False
        for event in schedule.events:
            self.assertLess(event.signal_before, event.wait.before)
            source_stages = {edge.source_stage for edge in event.wait.hazards}
            self.assertEqual(event.intervening_source_stage_work, tuple(
                i for i in range(event.signal_before, event.wait.before)
                if trace[i].stage in source_stages
            ))
            for edge in event.wait.hazards:
                self.assertLess(edge.producer, event.signal_before)
                self.assertLessEqual(event.wait.before, edge.consumer)
                if edge.kind is HazardKind.RAW and edge.destination_stage is Stage.TRANSFER:
                    checkpoint_raw = True
        self.assertTrue(checkpoint_raw)
        self.assertTrue(any(
            edge.kind is HazardKind.WAR and edge.source_stage is Stage.TRANSFER
            for edge in schedule.hazards
        ))
        self.assertEqual(len(analyze(trace, event_budget=4).events), 4)
        self.assertFalse(analyze(trace, event_budget=0).events)

    def test_single_dependent_stream_has_no_split_window(self):
        trace = dependent_trace()
        schedule = analyze(trace, event_budget=10)
        self.assertEqual([cut.before for cut in schedule.ordinary], list(range(1, len(trace))))
        self.assertEqual(schedule.events, ())

    def test_unsupported_or_opaque_accesses_are_rejected(self):
        valid = BufferAccess(BufferRange("buffer", 0, 1), AccessMode.READ)
        for start, end in ((-1, 1), (2, 2), (0, 1 << 64), (False, 4)):
            with self.assertRaises(ValueError):
                BufferRange("buffer", start, end)
        with self.assertRaises(ValueError):
            BufferRange(" ", 0, 1)
        with self.assertRaises(ValueError):
            BufferAccess(valid.region, "unknown")
        with self.assertRaises(ValueError):
            Operation("empty", Stage.COMPUTE, ())
        with self.assertRaises(ValueError):
            Operation("unsupported", "graphics", (valid,))
        with self.assertRaises(ValueError):
            Operation("opaque access", Stage.TRANSFER, (None,))
        with self.assertRaises(ValueError):
            analyze((object(),))
        for budget in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                analyze((), event_budget=budget)


if __name__ == "__main__":
    unittest.main()
