"""Repeatable model workloads for a transient whole-slot allocator."""

from collections import Counter
import json
import random
from statistics import median
from time import perf_counter

from slot_cover import AllocationClass, Order, Resource, plan_slots


UNIT = AllocationClass("illustrative compatible buffer", 65536, 65536)


def first_fit(order, resources, queues=None):
    def starts(resource):
        return min(order.rank[order.positions[name]] for name in resource.accesses)

    tails = []
    for resource in sorted(resources, key=lambda item: (starts(item), item.name)):
        for index, previous in enumerate(tails):
            if previous.allocation != resource.allocation or not resource.initializes:
                continue
            if queues and set(queues[name] for name in previous.accesses + resource.accesses) not in (
                    {"graphics"}, {"compute"}):
                continue
            if all(order.reach[order.positions[a]] & (1 << order.positions[b])
                   for a in previous.accesses for b in resource.accesses):
                tails[index] = resource
                break
        else:
            tails.append(resource)
    return sum(resource.allocation.extent for resource in tails)


def crossed_chain_groups(count):
    passes, edges, resources, queues = [], [], [], {}
    for group in range(count):
        a, b, c, d = (f"{group:03}-{name}" for name in "abcd")
        passes.extend((a, b, c, d))
        edges.extend(((a, c), (a, d), (b, c)))
        resources.extend(Resource(name, UNIT, (name,), True) for name in (a, b, c, d))
        queues.update({a: "graphics", b: "compute", c: "compute", d: "graphics"})
    return passes, edges, resources, queues


def single_queue(count):
    passes = tuple(f"pass-{i:03}" for i in range(count + 1))
    return (passes, list(zip(passes, passes[1:])),
            [Resource(str(i), UNIT, (a, b), True) for i, (a, b) in enumerate(zip(passes, passes[1:]))],
            dict.fromkeys(passes, "graphics"))


def bloom_projection():
    # Readme-level topology; compatible extents and strict queue edges are study assumptions.
    passes = ("threshold", "downsample", "exposure", "blur_coarse", "blur_fine", "tonemap")
    edges = [("threshold", "downsample"), ("downsample", "exposure"), ("downsample", "blur_coarse"),
             ("blur_coarse", "blur_fine"), ("blur_fine", "tonemap"), ("exposure", "tonemap")]
    coarse = AllocationClass("projected coarse images", 1048576, 65536)
    fine = AllocationClass("projected fine images", 4194304, 65536)
    exposure = AllocationClass("projected exposure storage", 65536, 65536)
    resources = [
        Resource("threshold-image", fine, ("threshold", "downsample"), True),
        Resource("downsample-image", coarse, ("downsample", "exposure", "blur_coarse"), True),
        Resource("blur-coarse-image", coarse, ("blur_coarse", "blur_fine"), True),
        Resource("blur-fine-image", fine, ("blur_fine", "tonemap"), True),
        Resource("exposure-values", exposure, ("exposure", "tonemap"), True),
    ]
    queues = dict.fromkeys(passes, "graphics") | {"exposure": "compute"}
    return passes, edges, resources, queues


def varied(seed, pass_count, resource_count):
    rng = random.Random(seed)
    passes = tuple(f"p{i:03}" for i in range(pass_count))
    queues = {name: rng.choice(("graphics", "compute")) for name in passes}
    edges = [(name, other) for i, name in enumerate(passes) for other in passes[i + 1:]
             if rng.random() < 0.05]
    for queue in ("graphics", "compute"):
        same_queue = [name for name in passes if queues[name] == queue]
        edges.extend(zip(same_queue, same_queue[1:]))
    resources = []
    for i in range(resource_count):
        start = rng.randrange(len(passes))
        nearby = passes[start:min(start + 7, len(passes))]
        accesses = rng.sample(nearby, rng.randint(1, min(3, len(nearby))))
        resources.append(Resource(f"r{i:03}", UNIT, tuple(accesses), rng.random() < 0.95))
    return passes, edges, resources, queues


def check(workload, *, timing_rounds=9):
    passes, edges, resources, queues = workload
    costs = {}
    for name, operation in (
        ("same_queue_first_fit", lambda: first_fit(Order(passes, edges), resources, queues)),
        ("safe_cross_queue_first_fit", lambda: first_fit(Order(passes, edges), resources)),
        ("maximum_matching", lambda: plan_slots(Order(passes, edges), resources).allocated_bytes),
    ):
        durations = []
        for _ in range(timing_rounds):
            start = perf_counter()
            planned = operation()
            durations.append((perf_counter() - start) * 1000)
        costs[name] = {"bytes": planned, "planning_median_ms": round(median(durations), 4)}
    assert costs["maximum_matching"]["bytes"] <= costs["safe_cross_queue_first_fit"]["bytes"]
    return costs


def main():
    cases = {
        "single_queue_96": single_queue(96),
        "granite_bloom_topology_projection": bloom_projection(),
        "crafted_crossed_64": crossed_chain_groups(16),
    }
    results = {name: check(workload) for name, workload in cases.items()}
    sample = Counter()
    for seed in range(64):
        measurements = check(varied(seed, 48, 64), timing_rounds=1)
        before = measurements["safe_cross_queue_first_fit"]["bytes"]
        after = measurements["maximum_matching"]["bytes"]
        sample["cases"] += 1
        sample["strict_improvements"] += after < before
        sample["first_fit_bytes"] += before
        sample["matching_bytes"] += after
    print(json.dumps({"cases": results, "varied_seeded_48_passes_64_resources": dict(sample)}, indent=2))


if __name__ == "__main__":
    main()
