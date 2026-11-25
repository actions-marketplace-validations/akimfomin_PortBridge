# SPDX-License-Identifier: MIT
import random
import unittest

from epoch_plan import CopyRange, EpochPlan, View


class EpochPlanTests(unittest.TestCase):
    def test_aliases_share_dirty_bytes_and_other_bytes_remain_pending(self):
        plan = EpochPlan({"storage": 32}, {
            "producer": View("storage", 3, 16),
            "consumer": View("storage", 8, 4),
        })
        plan.gpu_write("producer", 1, 5)
        plan.gpu_write("producer", 6, 6)
        self.assertEqual(plan.observe("consumer"), (CopyRange("storage", 8, 4),))
        self.assertEqual(plan.observe("consumer"), ())
        self.assertEqual(plan.observe("producer"), (
            CopyRange("storage", 4, 4),
            CopyRange("storage", 12, 3),
        ))
        self.assertEqual(plan.observe_opaque(["storage"]), ())

    def test_batched_alias_union_and_all_arguments_validate_before_consumption(self):
        plan = EpochPlan({"state": 32}, {
            "writer": View("state", 0, 32),
            "left": View("state", 0, 24),
            "right": View("state", 8, 24),
        })
        plan.gpu_write("writer", 2, 9)
        plan.gpu_write("writer", 13, 11)
        with self.assertRaises(ValueError):
            plan.observe_many([("left", 3, 7), ("right", 22, 4)])
        self.assertEqual(
            plan.observe_many([("right", 1, 10), ("left", 3, 9), ("right", 15, 2)]),
            (CopyRange("state", 3, 8), CopyRange("state", 13, 6), CopyRange("state", 23, 1)),
        )
        self.assertEqual(
            plan.observe_opaque(["state"]),
            (CopyRange("state", 2, 1), CopyRange("state", 19, 4)),
        )

    def test_opaque_observation_flushes_only_listed_backings(self):
        plan = EpochPlan({"first": 16, "second": 16}, {
            "left": View("first", 1, 6),
            "right": View("second", 2, 7),
        })
        plan.gpu_write("left")
        plan.gpu_write("right", 3, 2)
        with self.assertRaises(ValueError):
            plan.observe_opaque(["first", "right"])
        self.assertEqual(plan.observe_opaque(["second", "second"]), (CopyRange("second", 5, 2),))
        self.assertEqual(plan.observe("left", 3, 1), (CopyRange("first", 4, 1),))
        self.assertEqual(plan.observe_opaque(["first"]), (
            CopyRange("first", 1, 3),
            CopyRange("first", 5, 2),
        ))

    def test_superseded_writes_copy_the_final_bytes_only_once(self):
        plan = EpochPlan({"storage": 12}, {"buffer": View("storage", 0, 12)})
        gpu = bytearray(12)
        host = bytearray(12)
        writes = ((2, b"abcd"), (2, b"1234"), (4, b"WXYZ"))
        for start, data in writes:
            gpu[start:start + len(data)] = data
            plan.gpu_write("buffer", start, len(data))

        copies = plan.observe("buffer", 2, 6)
        self.assertEqual(copies, (CopyRange("storage", 2, 6),))
        self.assertEqual(sum(copy.size for copy in copies), 6)
        self.assertEqual(sum(len(data) for _, data in writes), 12)
        for copy in copies:
            span = slice(copy.offset, copy.offset + copy.size)
            host[span] = gpu[span]
        self.assertEqual(host[2:8], b"12WXYZ")
        self.assertEqual(plan.observe("buffer", 2, 6), ())

    def test_rejects_unknown_backings_nested_views_and_out_of_range_access(self):
        with self.assertRaisesRegex(ValueError, "canonical backing"):
            EpochPlan({"storage": 12}, {"first": View("storage", 0, 12), "other": View("first", 0, 2)})
        for capacity in (0, -1, 1.5, True):
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                EpochPlan({"storage": capacity}, {})
        for view in (View("storage", -1, 1), View("storage", 5, 8), View("storage", 0, 0)):
            with self.subTest(view=view), self.assertRaises(ValueError):
                EpochPlan({"storage": 12}, {"bad": view})

        plan = EpochPlan({"storage": 12}, {"buffer": View("storage", 2, 6)})
        for operation in (plan.gpu_write, plan.observe):
            for offset, size in ((-1, 1), (7, 0), (1, -1), (5, 2), (True, 2), (2, 1.5)):
                with self.subTest(offset=offset, size=size), self.assertRaises(ValueError):
                    operation("buffer", offset, size)
        with self.assertRaises(ValueError):
            plan.observe("storage")
        with self.assertRaises(ValueError):
            plan.observe_opaque("storage")
        plan.gpu_write("buffer", 6)
        self.assertEqual(plan.observe("buffer", 6), ())
        self.assertEqual(plan.observe_opaque(["storage"]), ())

    def test_randomized_traces_match_an_eager_byte_mirror(self):
        backings = {"left": 24, "right": 19, "other": 12}
        views = {
            "base": View("left", 0, 24),
            "small": View("left", 3, 14),
            "tail": View("left", 10, 14),
            "alias": View("right", 7, 8),
            "whole": View("right", 0, 19),
            "extra": View("other", 0, 12),
        }
        for seed in range(40):
            randomizer = random.Random(seed)
            plan = EpochPlan(backings, views)
            initial = {key: randomizer.randbytes(length) for key, length in backings.items()}
            gpu = {key: bytearray(value) for key, value in initial.items()}
            eager = {key: bytearray(value) for key, value in initial.items()}
            deferred = {key: bytearray(value) for key, value in initial.items()}
            dirty_bytes = {key: set() for key in backings}
            for event in range(300):
                name = randomizer.choice(tuple(views))
                view = views[name]
                offset = randomizer.randint(0, view.size)
                size = randomizer.randint(0, view.size - offset)
                span = slice(view.offset + offset, view.offset + offset + size)
                roll = randomizer.randrange(8)
                if roll < 4:
                    written = randomizer.randbytes(size)
                    gpu[view.backing][span] = written
                    eager[view.backing][span] = written
                    dirty_bytes[view.backing].update(range(span.start, span.stop))
                    plan.gpu_write(name, offset, size)
                    continue

                if roll == 7:
                    observed = {key: slice(0, backings[key])
                                for key in randomizer.sample(tuple(backings), randomizer.randrange(4))}
                    copies = plan.observe_opaque(observed)
                else:
                    observed = {view.backing: span}
                    copies = plan.observe(name, offset, size)

                expected = {(key, index) for key, interval in observed.items()
                            for index in range(interval.start, interval.stop) if index in dirty_bytes[key]}
                copied = [(copy.backing, index) for copy in copies
                          for index in range(copy.offset, copy.offset + copy.size)]
                self.assertEqual(len(copied), len(set(copied)), (seed, event))
                self.assertEqual(set(copied), expected, (seed, event))
                for copy in copies:
                    interval = slice(copy.offset, copy.offset + copy.size)
                    deferred[copy.backing][interval] = gpu[copy.backing][interval]
                    dirty_bytes[copy.backing].difference_update(range(interval.start, interval.stop))
                for key, interval in observed.items():
                    self.assertEqual(deferred[key][interval], eager[key][interval], (seed, event, key))


if __name__ == "__main__":
    unittest.main()
