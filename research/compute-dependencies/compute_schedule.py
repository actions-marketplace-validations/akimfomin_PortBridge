# SPDX-License-Identifier: MIT
"""Analyze same-queue compute and transfer dependencies on canonical buffer ranges."""

from bisect import bisect_right
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Stage(Enum):
    COMPUTE = "compute"
    TRANSFER = "transfer"


class AccessMode(Enum):
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"

    @property
    def reads(self) -> bool:
        return self is not AccessMode.WRITE

    @property
    def writes(self) -> bool:
        return self is not AccessMode.READ


class HazardKind(Enum):
    RAW = "read_after_write"
    WAR = "write_after_read"
    WAW = "write_after_write"


@dataclass(frozen=True, slots=True)
class BufferRange:
    """An explicit half-open byte range within a canonical buffer identity."""

    buffer: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if (not isinstance(self.buffer, str) or not self.buffer.strip() or
                type(self.start) is not int or type(self.end) is not int or
                not 0 <= self.start < self.end <= (1 << 64) - 1):
            raise ValueError("expected a canonical buffer and a nonempty uint64 byte range")

    def intersection(self, other: "BufferRange") -> "BufferRange | None":
        start, end = max(self.start, other.start), min(self.end, other.end)
        if self.buffer == other.buffer and start < end:
            return BufferRange(self.buffer, start, end)
        return None


@dataclass(frozen=True, slots=True)
class BufferAccess:
    region: BufferRange
    mode: AccessMode

    def __post_init__(self) -> None:
        if not isinstance(self.region, BufferRange) or not isinstance(self.mode, AccessMode):
            raise ValueError("only explicit buffer-range reads and writes are supported")


@dataclass(frozen=True, slots=True)
class Operation:
    name: str
    stage: Stage
    accesses: tuple[BufferAccess, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or not isinstance(self.stage, Stage):
            raise ValueError("expected a named compute or transfer operation")
        if (not isinstance(self.accesses, tuple) or not self.accesses or
                not all(isinstance(access, BufferAccess) for access in self.accesses)):
            raise ValueError("opaque operations and unsupported accesses are outside the model")


@dataclass(frozen=True, slots=True)
class Hazard:
    producer: int
    consumer: int
    source_stage: Stage
    destination_stage: Stage
    kind: HazardKind
    region: BufferRange

    def __post_init__(self) -> None:
        if (type(self.producer) is not int or type(self.consumer) is not int or
                not 0 <= self.producer < self.consumer or
                not isinstance(self.source_stage, Stage) or
                not isinstance(self.destination_stage, Stage) or
                not isinstance(self.kind, HazardKind) or not isinstance(self.region, BufferRange)):
            raise ValueError("expected a typed, forward buffer hazard")

    def covered_by(self, before: int) -> bool:
        return self.producer < before <= self.consumer


@dataclass(frozen=True, slots=True)
class BarrierCut:
    """Ordinary barrier recorded before operation `before`."""

    before: int
    hazards: tuple[Hazard, ...]


@dataclass(frozen=True, slots=True)
class SplitEvent:
    """One event for a whole cut group, with signal recorded before `signal_before`."""

    signal_before: int
    wait: BarrierCut
    intervening_source_stage_work: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Schedule:
    hazards: tuple[Hazard, ...]
    baseline: tuple[BarrierCut, ...]
    ordinary: tuple[BarrierCut, ...]
    events: tuple[SplitEvent, ...]


def find_hazards(operations: Iterable[Operation]) -> tuple[Hazard, ...]:
    """Enumerate ordered RAW, WAR and WAW overlaps between different operations."""
    trace = tuple(operations)
    if not all(isinstance(operation, Operation) for operation in trace):
        raise ValueError("expected only fully specified single-stage operations")

    hazards: dict[Hazard, None] = {}
    for consumer, request in enumerate(trace):
        for producer in range(consumer):
            source = trace[producer]
            for earlier in source.accesses:
                for later in request.accesses:
                    region = earlier.region.intersection(later.region)
                    if region is None:
                        continue
                    kinds = []
                    if earlier.mode.writes and later.mode.reads:
                        kinds.append(HazardKind.RAW)
                    if earlier.mode.reads and later.mode.writes:
                        kinds.append(HazardKind.WAR)
                    if earlier.mode.writes and later.mode.writes:
                        kinds.append(HazardKind.WAW)
                    for kind in kinds:
                        hazards[Hazard(producer, consumer, source.stage, request.stage, kind, region)] = None
    return tuple(hazards)


def minimum_barrier_cuts(hazards: Iterable[Hazard]) -> tuple[BarrierCut, ...]:
    """Find the minimum number of cut points for a fixed operation order.

    For each as-yet-uncovered interval, select its earliest right endpoint.
    The triggering intervals are disjoint, proving no cover uses fewer cuts.
    Assign each hazard to its latest covering cut to keep later dependencies
    out of the earlier groups where possible.
    """
    edges = tuple(hazards)
    if not all(isinstance(edge, Hazard) for edge in edges):
        raise ValueError("expected only typed forward hazards")
    ordered = sorted(edges, key=lambda edge: edge.consumer)
    cuts = []
    for edge in ordered:
        if not cuts or not edge.covered_by(cuts[-1]):
            cuts.append(edge.consumer)

    groups: list[list[Hazard]] = [[] for _ in cuts]
    for edge in ordered:
        index = bisect_right(cuts, edge.consumer) - 1
        groups[index].append(edge)
    return tuple(BarrierCut(cut, tuple(group)) for cut, group in zip(cuts, groups))


def analyze(operations: Iterable[Operation], *, event_budget: int = 0) -> Schedule:
    """Replace up to `event_budget` whole cuts with same-queue split events.

    The score counts source-stage operations between the earliest legal signal
    and the existing wait. It is a count of possible overlap, not a timing.
    Each selected cut needs its own event for this trace.
    """
    if type(event_budget) is not int or event_budget < 0:
        raise ValueError("event budget must be a nonnegative integer")
    trace = tuple(operations)
    hazards = find_hazards(trace)
    baseline = minimum_barrier_cuts(hazards)
    candidates = []
    for cut in baseline:
        signal = max(edge.producer for edge in cut.hazards) + 1
        source_stages = {edge.source_stage for edge in cut.hazards}
        work = tuple(index for index in range(signal, cut.before) if trace[index].stage in source_stages)
        if work:
            candidates.append(SplitEvent(signal, cut, work))
    candidates.sort(key=lambda event: (-len(event.intervening_source_stage_work), event.wait.before))
    chosen = tuple(sorted(candidates[:event_budget], key=lambda event: event.wait.before))
    replaced = {event.wait.before for event in chosen}
    ordinary = tuple(cut for cut in baseline if cut.before not in replaced)
    return Schedule(hazards, baseline, ordinary, chosen)
