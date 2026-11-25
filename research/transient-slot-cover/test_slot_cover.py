import random
import unittest
from itertools import permutations

from slot_cover import AllocationClass, Order, Resource, plan_slots


BLOCK = AllocationClass("heap0:buffer", 65536, 65536)


def makes_resource(name, *passes, initializes=True, allocation=BLOCK):
    return Resource(name, allocation, passes, initializes)


def legal_edges_by_schedules(passes, dependencies, resources):
    edges = {(a.name, b.name) for a in resources for b in resources
             if a != b and a.allocation == b.allocation and b.initializes}
    by_name = {resource.name: resource for resource in resources}
    schedules = 0
    for sequence in permutations(passes):
        indices = {name: index for index, name in enumerate(sequence)}
        if not all(indices[a] < indices[b] for a, b in dependencies):
            continue
        schedules += 1
        ends = {name: max(indices[p] for p in item.accesses) for name, item in by_name.items()}
        starts = {name: min(indices[p] for p in item.accesses) for name, item in by_name.items()}
        edges = {(a, b) for a, b in edges if ends[a] < starts[b]}
    return edges, schedules


def enumerated_minimum(resources, edges):
    by_name = {resource.name: resource for resource in resources}
    best = sum(resource.allocation.extent for resource in resources)
    for sequence in permutations(by_name):
        def partitions(index, tails, bytes_used):
            nonlocal best
            if bytes_used >= best:
                return
            if index == len(sequence):
                best = bytes_used
                return
            name = sequence[index]
            for tail_index, tail in enumerate(tails):
                if (tail, name) in edges:
                    partitions(index + 1, tails[:tail_index] + (name,) + tails[tail_index + 1:],
                               bytes_used)
            partitions(index + 1, tails + (name,), bytes_used + by_name[name].allocation.extent)

        partitions(0, (), 0)
    return best


class SlotCoverTests(unittest.TestCase):
    def test_augmenting_path_beats_first_fit(self):
        passes = ("a", "b", "c", "d")
        order = Order(passes, [("a", "c"), ("a", "d"), ("b", "c")])
        resources = [makes_resource(name, name) for name in passes]
        plan = plan_slots(order, resources)
        self.assertEqual(plan.slots, (("a", "d"), ("b", "c")))
        self.assertEqual(plan.allocated_bytes, 2 * BLOCK.extent)
        self.assertEqual([(h.complete_after, h.initialize_before) for h in plan.handoffs],
                         [(("a",), ("d",)), (("b",), ("c",))])

    def test_every_frontier_endpoint_must_be_ordered(self):
        passes = ("producer", "left", "right", "x", "y")
        base = [("producer", "left"), ("producer", "right"), ("left", "x"),
                ("left", "y"), ("right", "x")]
        resources = (makes_resource("first", "producer", "left", "right"),
                     makes_resource("next", "x", "y"))
        self.assertEqual(len(plan_slots(Order(passes, base), resources).slots), 2)
        complete = plan_slots(Order(passes, base + [("right", "y")]), resources)
        self.assertEqual(complete.slots, (("first", "next"),))
        self.assertEqual(complete.handoffs[0].complete_after, ("left", "right"))
        self.assertEqual(complete.handoffs[0].initialize_before, ("x", "y"))

    def test_rejects_or_separates_incompatible_inputs(self):
        order = Order(("x", "y"), [("x", "y")])
        ordered = (
            makes_resource("a", "x"), makes_resource("b", "y", initializes=False),
            makes_resource("c", "y", allocation=AllocationClass("heap1:buffer", 65536, 65536)),
        )
        self.assertEqual(len(plan_slots(order, ordered).slots), 3)
        self.assertEqual(len(plan_slots(order, [makes_resource("a", "x"), makes_resource("b", "x")]).slots), 2)
        for resources in ([makes_resource("a")], [ordered[0], ordered[0]]):
            with self.assertRaises(ValueError):
                plan_slots(order, resources)
        with self.assertRaises(ValueError):
            Order(("a", "b"), [("a", "b"), ("b", "a")])
        with self.assertRaises(ValueError):
            AllocationClass("heap", 1024, 1023)

    def test_exhaustive_schedule_and_cover_oracles_on_small_seeded_graphs(self):
        rng = random.Random(2322)
        schedules = 0
        for _ in range(400):
            passes = tuple("abcdef"[:rng.randrange(2, 7)])
            dependencies = [(a, b) for i, a in enumerate(passes) for b in passes[i + 1:]
                            if rng.random() < 0.32]
            resources = [makes_resource(str(i), *rng.sample(passes, rng.randint(1, min(3, len(passes)))),
                                        initializes=(rng.random() < 0.85))
                         for i in range(rng.randint(1, 5))]
            edges, checked = legal_edges_by_schedules(passes, dependencies, resources)
            schedules += checked
            shuffled_passes = list(passes)
            rng.shuffle(shuffled_passes)
            plan = plan_slots(Order(shuffled_passes, dependencies), resources)
            self.assertEqual(sorted(name for slot in plan.slots for name in slot),
                             sorted(resource.name for resource in resources))
            for slot in plan.slots:
                for a, b in zip(slot, slot[1:]):
                    self.assertIn((a, b), edges)
            self.assertEqual(plan.allocated_bytes, enumerated_minimum(resources, edges))
        self.assertGreater(schedules, 5000)


if __name__ == "__main__":
    unittest.main()
