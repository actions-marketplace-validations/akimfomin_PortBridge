"""Adaptive two-level dispatch for independent unsigned 32-bit shader cases."""

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable


U32_MASK = (1 << 32) - 1


def label_bits(value: int) -> int:
    """Accept a uint32 label or an int32 spelling of the same literal."""
    if type(value) is not int or not -(1 << 31) <= value <= U32_MASK:
        raise ValueError("case labels must be uint32 values or int32 spellings")
    return value & U32_MASK


@dataclass(frozen=True, order=True)
class Projection:
    offset: int
    width: int

    def __post_init__(self) -> None:
        if (type(self.width) is not int or type(self.offset) is not int
                or not 1 <= self.width <= 16 or not 0 <= self.offset <= 32 - self.width):
            raise ValueError("projection must be a contiguous 1–16-bit uint32 window")

    @property
    def mask(self) -> int:
        return (1 << self.width) - 1

    def bucket(self, bits: int) -> int:
        return (bits >> self.offset) & self.mask


@dataclass(frozen=True)
class Dispatch:
    projection: Projection | None
    buckets: tuple[tuple[int, tuple[int, ...]], ...]

    @property
    def fanouts(self) -> tuple[int, ...]:
        sizes = tuple(len(labels) + 1 for _, labels in self.buckets)
        return (len(self.buckets) + 1, *sizes) if self.projection else sizes

    def select(self, value: int) -> int | None:
        """Return the matched label's uint32 bits, or None for the default."""
        label = label_bits(value)
        selected_bucket = self.projection.bucket(label) if self.projection else 0
        for bucket, labels in self.buckets:
            if bucket == selected_bucket:
                return label if label in labels else None
        return None


def _partition(labels: tuple[int, ...], projection: Projection | None) -> Dispatch:
    groups: dict[int, list[int]] = {0: []} if not projection else {}
    for label in labels:
        key = projection.bucket(label) if projection else 0
        groups.setdefault(key, []).append(label)
    return Dispatch(projection, tuple((key, tuple(group)) for key, group in sorted(groups.items())))


def partition(labels: Iterable[int], projection: Projection | None = None) -> Dispatch:
    """Materialize a fixed plan, using a flat switch when projection is absent."""
    return _partition(_unique_labels(labels), projection)


def _unique_labels(labels: Iterable[int]) -> tuple[int, ...]:
    known = tuple(sorted(label_bits(label) for label in labels))
    if len(known) != len(set(known)):
        raise ValueError("duplicate uint32 case label")
    return known


def adaptive(labels: Iterable[int], *, minimum_cases: int = 1024) -> Dispatch:
    """Search bounded radix windows for small outer and inner switches.

    The score includes default edges and uses squared fanout as a proxy for
    compilation pressure. The gate requires a 4x score reduction before
    trading the flat switch for a second selection.
    """
    if type(minimum_cases) is not int or minimum_cases < 1:
        raise ValueError("minimum_cases must be a positive integer")
    known = _unique_labels(labels)
    if not known or len(known) < minimum_cases:
        return _partition(known, None)

    center_width = max(1, (len(known) - 1).bit_length() // 2)
    low = max(1, center_width - 2)
    high = min(16, center_width + 2)
    flat_width = len(known) + 1
    best = None
    for width in range(low, high + 1):
        for offset in range(33 - width):
            projection = Projection(offset, width)
            counts = Counter(projection.bucket(label) for label in known)
            fanouts = (len(counts) + 1, *(count + 1 for count in counts.values()))
            rank = sum(size * size for size in fanouts), max(fanouts), len(counts), projection
            if best is None or rank < best:
                best = rank

    projection = best[-1] if best and 4 * best[0] <= flat_width * flat_width else None
    return _partition(known, projection)


def emit(plan: Dispatch, selector: str, arm: Callable[[int], str], default: str) -> str:
    """Emit HLSL for independent statement bodies with no inter-case fallthrough.

    The caller supplies a stable local uint identifier. A miss reaches either
    the inner default in an existing bucket or the outer default.
    The caller supplies convergence-insensitive, per-invocation bodies,
    including the default. Bucket-dependent control flow can change which
    lanes meet at a subgroup operation or derivative.
    """
    if not selector.isascii() or not selector.isidentifier():
        raise ValueError("selector must be a local HLSL identifier")
    lines: list[str] = []

    def switch_cases(labels: tuple[int, ...], indent: str) -> None:
        lines.append(f"{indent}switch ({selector}) {{")
        for label in labels:
            lines.append(f"{indent}  case 0x{label:08x}u: {{ {arm(label)} break; }}")
        lines.append(f"{indent}  default: {{ {default} break; }}")
        lines.append(f"{indent}}}")

    if plan.projection is None:
        switch_cases(plan.buckets[0][1], "")
    else:
        projection = plan.projection
        lines.append(f"switch (({selector} >> {projection.offset}u) & 0x{projection.mask:x}u) {{")
        for bucket, labels in plan.buckets:
            lines.append(f"  case {bucket}u: {{")
            switch_cases(labels, "    ")
            lines.append("    break;")
            lines.append("  }")
        lines.append(f"  default: {{ {default} break; }}")
        lines.append("}")
    return "\n".join(lines)
