"""Dependency and lane contracts for the pinned NVIDIA mipmap fast path."""

import argparse
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


PINNED_SOURCE = "11eeb2346da6db04307919b2e83a9c618b09cb2ef8231f251524ce9fc0617058"
FAST_START = "layout(local_size_x = 256) in;"
FAST_END = "#endif /* !NVPRO_USE_FAST_PIPELINE_ALTERNATIVE_ */"
WORKGROUP_SIZE = 256


@dataclass(frozen=True)
class Rectangle:
    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self):
        if not (0 <= self.x0 < self.x1 and 0 <= self.y0 < self.y1):
            raise ValueError("a dirty region must be a nonempty half-open rectangle")


@dataclass(frozen=True)
class FastPath:
    subgroup_width: int
    full_subgroups: bool
    shuffle: bool
    logical_lane_indices: bool
    compatible_image_views: bool
    max_groups_x: int
    max_local_x: int

    def admits(self, size, depth):
        if (not 1 <= depth <= 6 or self.subgroup_width not in (32, 64)
                or not self.full_subgroups or not self.shuffle
                or not self.logical_lane_indices or not self.compatible_image_views
                or self.max_local_x < WORKGROUP_SIZE):
            return False
        w, h = size
        divisor = max(4, 1 << depth)
        samples_per_group = 4096 if depth == 6 else 1024
        dispatch_numerator = w * h + samples_per_group - 1
        return (min(w, h) >= divisor and w % divisor == h % divisor == 0
                and dispatch_numerator < 1 << 32
                and dispatch_numerator // samples_per_group <= self.max_groups_x)


@dataclass(frozen=True)
class Dispatch:
    source_level: int
    levels: int
    path: str


def _next_axis(lo, hi, size):
    # An output j reads [2*j, 2*j+taps). A size-one axis is unchanged.
    if size == 1:
        return 0, 1
    taps = 3 if size & 1 else 2
    return max(0, (lo - taps) // 2 + 1), min(size // 2, (hi + 1) // 2)


def _required_axis(lo, hi, size):
    if size == 1:
        return 0, 1
    return 2 * lo, 2 * hi + (size & 1)


def required_source(width, height, destination):
    """Return the source rectangle required to recompute the requested output."""
    if (min(width, height) < 1 or destination.x1 > max(1, width // 2)
            or destination.y1 > max(1, height // 2)):
        raise ValueError("destination rectangle is outside the next mip level")
    x0, x1 = _required_axis(destination.x0, destination.x1, width)
    y0, y1 = _required_axis(destination.y0, destination.y1, height)
    return Rectangle(x0, y0, x1, y1)


def affected_regions(width, height, mip_levels, dirty=None):
    """Track exactly which coordinates may change under the separable footprint."""
    if min(width, height) < 1 or not 1 <= mip_levels <= max(width, height).bit_length():
        raise ValueError("invalid image extent or mip level count")
    rectangle = dirty or Rectangle(0, 0, width, height)
    if rectangle.x1 > width or rectangle.y1 > height:
        raise ValueError("the dirty rectangle is outside the base level")
    regions = [rectangle]
    for _ in range(mip_levels - 1):
        x0, x1 = _next_axis(rectangle.x0, rectangle.x1, width)
        y0, y1 = _next_axis(rectangle.y0, rectangle.y1, height)
        rectangle = Rectangle(x0, y0, x1, y1)
        regions.append(rectangle)
        width, height = max(1, width // 2), max(1, height // 2)
    return tuple(regions)


def plan_chain(width, height, mip_levels, *, dirty=None, layers=1,
               old_chain_valid=False, intermediate_values_allowed=False, fast=None):
    """Minimize logical passes per layer under the stated geometry and numeric premises."""
    regions = affected_regions(width, height, mip_levels, dirty)
    full = regions[0] == Rectangle(0, 0, width, height)
    if layers < 1:
        raise ValueError("a texture must have at least one layer")
    if not full and not old_chain_valid:
        raise ValueError("partial updates require valid retained texels in the old mip chain")
    fused = full and intermediate_values_allowed
    best = [()] * mip_levels
    for level in range(mip_levels - 2, -1, -1):
        size = max(1, width >> level), max(1, height >> level)
        remaining = mip_levels - level - 1
        choices = [Dispatch(level, 1, "reference")]
        if fused and remaining >= 2:
            choices.append(Dispatch(level, 2, "general"))
        if fused and fast is not None and layers == 1 and mip_levels <= 16:
            choices.extend(Dispatch(level, depth, "shuffle")
                           for depth in range(3, min(6, remaining) + 1)
                           if fast.admits(size, depth))
        paths = ((choice,) + best[level + choice.levels] for choice in choices)
        best[level] = min(paths, key=lambda path: (len(path),
                                                  sum(item.path == "shuffle" for item in path)))
    return best[0], regions


@dataclass(frozen=True)
class Counterexample:
    stage: str
    physical_lane: int
    actual: int
    expected: int


def lane_counterexample(logical_at_physical, *, width, levels, tiles):
    """Return a witness for the stock shader's assignments in one full workgroup.

    The supplied tuple maps each subgroup-ordered invocation to the native local
    index used to assign its tile. The rewritten shader uses the identity tuple
    under all such physical permutations, by construction.
    """
    if width not in (32, 64) or not 1 <= levels <= 6:
        raise ValueError("unsupported subgroup width or fast-dispatch depth")
    if len(logical_at_physical) != WORKGROUP_SIZE or set(logical_at_physical) != set(range(WORKGROUP_SIZE)):
        raise ValueError("the workgroup requires a full permutation of local indices")
    team_size = 1 << min(8, 2 * levels - 2)
    if not 1 <= tiles <= WORKGROUP_SIZE // team_size:
        raise ValueError("active tile count is outside the workgroup")
    active = tiles * team_size
    stages = []
    if levels >= 2:
        stages.append(("quartet", 4, (1, 2, 3)))
    if levels >= 3:
        stages.append(("sixteen", 16, (4, 8, 12)))
    for stage, group_size, masks in stages:
        for physical, logical in enumerate(logical_at_physical):
            if logical >= active:
                continue
            physical_leader = physical % group_size == 0
            logical_leader = logical % group_size == 0
            if physical_leader != logical_leader:
                return Counterexample(stage + "-leader", physical, int(physical_leader),
                                      int(logical_leader))
            if physical_leader:
                for mask in masks:
                    actual = logical_at_physical[physical ^ mask]
                    expected = logical ^ mask
                    if actual != expected:
                        return Counterexample(stage + "-shuffle", physical, actual, expected)
    if levels == 6:
        # The shared-memory finish uses exactly logical invocations 0 through 3.
        leader = logical_at_physical.index(0)
        for mask in (1, 2, 3):
            actual = logical_at_physical[leader ^ mask]
            if actual != mask:
                return Counterexample("shared-finish", leader, actual, mask)
    return None


def rewrite_fast(source: bytes) -> bytes:
    """Replace implicit lane numbering, for a full fixed-width subgroup pipeline."""
    source = source.replace(b"\r\n", b"\n")
    if sha256(source).hexdigest() != PINNED_SOURCE:
        raise ValueError("expected the pinned nvpro_pyramid.glsl")
    original = source.decode("utf-8")
    start = original.index(FAST_START)
    end = original.index(FAST_END, start)
    fast = original[start:end].replace("gl_LocalInvocationIndex", "pbLogicalLocalIndex()")
    fast = fast.replace("gl_GlobalInvocationID.x", "pbLogicalGlobalIndex()")
    logical_indices = """layout(local_size_x = 256) in;

// Requires full subgroups and the pipeline's fixed subgroup size.
uint pbLogicalLocalIndex()
{
  return gl_SubgroupID * gl_SubgroupSize + gl_SubgroupInvocationID;
}

uint pbLogicalGlobalIndex()
{
  return gl_WorkGroupID.x * gl_WorkGroupSize.x + pbLogicalLocalIndex();
}"""
    return (original[:start] + fast.replace(FAST_START, logical_indices, 1) + original[end:]).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("rewrite",))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("use a separate destination for the patched shader")
    args.output.write_bytes(rewrite_fast(args.source.read_bytes()))


if __name__ == "__main__":
    main()
