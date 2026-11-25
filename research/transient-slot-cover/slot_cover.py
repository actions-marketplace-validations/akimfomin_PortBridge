"""Partition equal-capacity transient resources into provably ordered slots."""

from collections import deque
from dataclasses import dataclass
from heapq import heapify, heappop, heappush


@dataclass(frozen=True, order=True)
class AllocationClass:
    """Caller-certified alias compatibility and a whole, aligned allocation extent."""

    compatibility: str
    extent: int
    alignment: int

    def __post_init__(self):
        if (not self.compatibility or self.extent <= 0 or self.alignment <= 0
                or self.alignment & (self.alignment - 1)
                or self.extent % self.alignment):
            raise ValueError("expected a compatibility class and positive aligned extent")


@dataclass(frozen=True)
class Resource:
    """Complete access set and proof that a slot's previous contents are unnecessary."""

    name: str
    allocation: AllocationClass
    accesses: tuple[str, ...]
    initializes: bool = False


@dataclass(frozen=True)
class Handoff:
    previous: str
    following: str
    complete_after: tuple[str, ...]
    initialize_before: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    """Whole-slot payload allocation and the points at which ownership must change."""

    slots: tuple[tuple[str, ...], ...]
    handoffs: tuple[Handoff, ...]
    allocated_bytes: int


class Order:
    """Strict happens-before on accesses, using edges certified by the caller."""

    def __init__(self, passes, dependencies):
        names = tuple(passes)
        if len(set(names)) != len(names) or any(not name for name in names):
            raise ValueError("pass names must be nonempty and unique")
        self.positions = {name: index for index, name in enumerate(names)}
        successors = [set() for _ in names]
        predecessor_count = [0] * len(names)
        for before, after in dependencies:
            source, target = self.positions[before], self.positions[after]
            if target not in successors[source]:
                successors[source].add(target)
                predecessor_count[target] += 1
        ready = [index for index, count in enumerate(predecessor_count) if count == 0]
        heapify(ready)
        topological = []
        while ready:
            source = heappop(ready)
            topological.append(source)
            for target in successors[source]:
                predecessor_count[target] -= 1
                if predecessor_count[target] == 0:
                    heappush(ready, target)
        if len(topological) != len(names):
            raise ValueError("pass dependencies contain a cycle")
        self.rank = {index: rank for rank, index in enumerate(topological)}
        self.reach = [0] * len(names)
        for source in reversed(topological):
            for target in successors[source]:
                self.reach[source] |= (1 << target) | self.reach[target]
        self.names = names

    def frontiers(self, accesses):
        indices = sorted({self.positions[name] for name in accesses}, key=self.rank.__getitem__)
        if not indices:
            raise ValueError("a resource must declare all access passes")
        accessed = sum(1 << index for index in indices)
        reached = 0
        for index in indices:
            reached |= self.reach[index]
        first = tuple(index for index in indices if not (1 << index) & reached)
        last = tuple(index for index in indices if not self.reach[index] & accessed)
        return first, last


def maximum_matching(adjacency):
    """Find vertex-disjoint predecessor/successor pairs by augmenting paths."""

    edges_from = {}
    edges_to = {}
    for start in range(len(adjacency)):
        pending = deque([start])
        visited_left = {start}
        previous_left = {}
        while pending:
            left = pending.popleft()
            for right in adjacency[left]:
                if right in previous_left:
                    continue
                previous_left[right] = left
                owner = edges_to.get(right)
                if owner is None:
                    while right is not None:
                        left = previous_left[right]
                        old_right = edges_from.get(left)
                        edges_from[left] = right
                        edges_to[right] = left
                        right = old_right
                    pending.clear()
                    break
                if owner not in visited_left:
                    pending.append(owner)
                    visited_left.add(owner)
    return edges_from, edges_to


def plan_slots(order, resources):
    """Find a minimum whole-slot cover within each exact allocation class.

    The result describes required alias handoffs. It inserts no waits, API
    barriers, layout transitions, ownership changes, or resource creation.
    """

    groups = {}
    by_name = {}
    for resource in resources:
        if not resource.name or resource.name in by_name:
            raise ValueError("resource names must be nonempty and unique")
        by_name[resource.name] = resource
        groups.setdefault(resource.allocation, []).append(resource)
    slots = []
    handoffs = []
    for allocation in sorted(groups):
        group = sorted(groups[allocation], key=lambda resource: resource.name)
        frontiers = [order.frontiers(resource.accesses) for resource in group]
        first_masks = [sum(1 << index for index in first) for first, _ in frontiers]
        guaranteed_after = []
        for _, last in frontiers:
            common = order.reach[last[0]]
            for index in last[1:]:
                common &= order.reach[index]
            guaranteed_after.append(common)
        adjacency = [
            [target for target, resource in enumerate(group)
             if resource.initializes and after & first_masks[target] == first_masks[target]]
            for after in guaranteed_after
        ]
        next_in_slot, has_predecessor = maximum_matching(adjacency)
        for first in range(len(group)):
            if first in has_predecessor:
                continue
            chain = [group[first].name]
            current = first
            while current in next_in_slot:
                following = next_in_slot[current]
                name = group[following].name
                handoffs.append(Handoff(
                    chain[-1], name,
                    tuple(order.names[index] for index in frontiers[current][1]),
                    tuple(order.names[index] for index in frontiers[following][0]),
                ))
                chain.append(name)
                current = following
            slots.append(tuple(chain))
    return Plan(tuple(slots), tuple(handoffs),
                sum(by_name[chain[0]].allocation.extent for chain in slots))
