# SPDX-License-Identifier: MIT
"""Select readbacks for a synchronized, ordered GPU-write and CPU-read trace.

Backings are disjoint, canonical storage allocations. Every supported view is
a fixed, contiguous byte range in one backing. Aliases use the same backing
identity. The host mirror starts current. All writes and observations must be
recorded in their visibility order. Untracked host access and unresolved GPU
dependencies are outside this model.

An observation consumes the ranges it returns. A host adapter must complete
those copies before delivering the read. If a copy fails or visibility order
changes, the adapter must reestablish the shared state before reusing the plan.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class View:
    backing: str
    offset: int
    size: int


@dataclass(frozen=True, slots=True)
class CopyRange:
    backing: str
    offset: int
    size: int


class EpochPlan:
    """Track sorted disjoint dirty byte ranges per canonical backing."""

    def __init__(self, backings: Mapping[str, int], views: Mapping[str, View]):
        self._backings = dict(backings)
        self._views = dict(views)
        for backing, capacity in self._backings.items():
            if not isinstance(backing, str) or not backing or type(capacity) is not int or capacity <= 0:
                raise ValueError("backings need a nonempty identity and a positive integer capacity")
        for name, view in self._views.items():
            if not isinstance(name, str) or not name or not isinstance(view, View):
                raise ValueError("views need a nonempty identity and an explicit View")
            if not isinstance(view.backing, str) or view.backing not in self._backings:
                raise ValueError(f"view {name!r} must refer directly to a known canonical backing")
            if (type(view.offset) is not int or type(view.size) is not int or
                    view.offset < 0 or view.size <= 0 or
                    view.offset + view.size > self._backings[view.backing]):
                raise ValueError(f"view {name!r} lies outside its backing")
        self._dirty: dict[str, list[tuple[int, int]]] = {backing: [] for backing in self._backings}

    def _resolve(self, name: str, offset: int, size: int | None) -> tuple[str, int, int]:
        if not isinstance(name, str) or name not in self._views:
            raise ValueError(f"unknown view {name!r}")
        view = self._views[name]
        if type(offset) is not int or not 0 <= offset <= view.size:
            raise ValueError(f"invalid byte offset for view {name!r}")
        if size is None:
            size = view.size - offset
        if type(size) is not int or not 0 <= size <= view.size - offset:
            raise ValueError(f"invalid byte size for view {name!r}")
        start = view.offset + offset
        return view.backing, start, start + size

    def gpu_write(self, view: str, offset: int = 0, size: int | None = None) -> None:
        """Record newly visible GPU bytes, coalescing overlapping or adjacent writes."""
        backing, start, end = self._resolve(view, offset, size)
        if start == end:
            return

        dirty = self._dirty[backing]
        first = 0
        while first < len(dirty) and dirty[first][1] < start:
            first += 1
        last = first
        while last < len(dirty) and dirty[last][0] <= end:
            left, right = dirty[last]
            start = min(start, left)
            end = max(end, right)
            last += 1
        dirty[first:last] = [(start, end)]

    def observe(self, view: str, offset: int = 0, size: int | None = None) -> tuple[CopyRange, ...]:
        """Consume only the dirty bytes intersecting this exact CPU observation."""
        return self.observe_many(((view, offset, size),))

    def observe_many(self, observations: Iterable[tuple[str, int, int | None]]) -> tuple[CopyRange, ...]:
        """Materialize a same-epoch union of observations, including aliased views."""
        requested: dict[str, list[tuple[int, int]]] = {}
        for view, offset, size in observations:
            backing, start, end = self._resolve(view, offset, size)
            if start != end:
                requested.setdefault(backing, []).append((start, end))

        copies = []
        for backing, intervals in requested.items():
            windows = []
            for start, end in sorted(intervals):
                if windows and windows[-1][1] >= start:
                    windows[-1] = (windows[-1][0], max(windows[-1][1], end))
                else:
                    windows.append((start, end))

            remaining = []
            window = 0
            for start, end in self._dirty[backing]:
                while window < len(windows) and windows[window][1] <= start:
                    window += 1
                current = start
                while window < len(windows) and windows[window][0] < end:
                    left, right = windows[window]
                    first = max(current, left)
                    last = min(end, right)
                    if current < first:
                        remaining.append((current, first))
                    copies.append(CopyRange(backing, first, last - first))
                    current = last
                    if right <= end:
                        window += 1
                    else:
                        break
                if current < end:
                    remaining.append((current, end))
            self._dirty[backing] = remaining
        return tuple(copies)

    def observe_opaque(self, backings: Iterable[str]) -> tuple[CopyRange, ...]:
        """Flush every dirty byte in backings a synchronous opaque read may access."""
        if isinstance(backings, str):
            raise ValueError("opaque observations need an explicit collection of backing identities")
        names = tuple(backings)
        if any(not isinstance(name, str) or name not in self._backings for name in names):
            raise ValueError("opaque observations need known canonical backing identities")
        copies = []
        for backing in dict.fromkeys(names):
            copies.extend(CopyRange(backing, left, right - left) for left, right in self._dirty[backing])
            self._dirty[backing].clear()
        return tuple(copies)
