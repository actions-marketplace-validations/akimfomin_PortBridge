# SPDX-License-Identifier: MIT
"""Extract a parameterized, side-effect-free tail from a structured u32 switch."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
import operator


UINT32 = 0xffff_ffff
OPERATOR: dict[str, Callable[[int, int], int]] = {
    "add": operator.add, "and": operator.and_, "mul": operator.mul,
    "or": operator.or_, "sub": operator.sub, "xor": operator.xor,
    "shl": operator.lshift, "shr": operator.rshift,
}


class Kind(StrEnum):
    INPUT = "input"
    LITERAL = "literal"
    LOCAL = "local"
    PARAMETER = "parameter"


@dataclass(frozen=True, slots=True)
class Value:
    kind: Kind
    index: int


@dataclass(frozen=True, slots=True)
class Instruction:
    opcode: str
    left: Value
    right: Value


Block = tuple[Instruction, ...]


@dataclass(frozen=True, slots=True)
class Region:
    input_count: int
    arms: tuple[Block, ...]

    def __post_init__(self):
        if self.input_count < 1 or len(self.arms) < 2 or any(not arm for arm in self.arms):
            raise ValueError("a region needs inputs and at least two nonempty arms")
        for arm in self.arms:
            for location, instruction in enumerate(arm):
                if instruction.opcode not in OPERATOR:
                    raise ValueError(f"unsupported operation {instruction.opcode!r}")
                for operand in (instruction.left, instruction.right):
                    limit = {
                        Kind.INPUT: self.input_count,
                        Kind.LITERAL: UINT32 + 1,
                        Kind.LOCAL: location,
                    }.get(operand.kind, 0)
                    if not 0 <= operand.index < limit:
                        raise ValueError(f"invalid value {operand!r} at operation {location}")


@dataclass(frozen=True, slots=True)
class Factored:
    prefixes: tuple[Block, ...]
    incoming: tuple[tuple[Value, ...], ...]
    body: Block
    estimated_savings: int

    @property
    def parameter_count(self) -> int:
        return len(self.incoming)


def structural_limit(arms: Sequence[Block]) -> int:
    """Find the largest compatible suffix without constructing each candidate."""
    limit = min(map(len, arms))
    for distance in range(1, limit + 1):
        if distance > limit:
            break
        aligned = tuple(arm[-distance] for arm in arms)
        if len({step.opcode for step in aligned}) != 1:
            return distance - 1
        for operands in zip(*((step.left, step.right) for step in aligned)):
            distances = tuple(len(arm) - value.index if value.kind == Kind.LOCAL else None
                              for arm, value in zip(arms, operands))
            available = [item for item in distances if item is not None]
            if available and len(set(distances)) != 1:
                limit = min(limit, min(available) - 1)
    return limit


def build_candidate(arms: tuple[Block, ...], suffix: int) -> Factored:
    begins = tuple(len(arm) - suffix for arm in arms)
    columns: dict[tuple[Value, ...], int] = {}

    def merge(values: tuple[Value, ...]) -> Value:
        first = values[0]
        if first.kind == Kind.LOCAL and first.index >= begins[0]:
            return Value(Kind.LOCAL, first.index - begins[0])
        if first.kind != Kind.LOCAL and all(value == first for value in values):
            return first
        return Value(Kind.PARAMETER, columns.setdefault(values, len(columns)))

    body = []
    for aligned in zip(*(arm[begin:] for arm, begin in zip(arms, begins))):
        body.append(Instruction(
            aligned[0].opcode,
            merge(tuple(step.left for step in aligned)),
            merge(tuple(step.right for step in aligned)),
        ))
    incoming = tuple(columns)
    # Count one phi and one incoming edge per arm. This avoids treating a
    # large set of case constants as free, even if a backend later folds it.
    saved = (len(arms) - 1) * suffix - (len(arms) + 1) * len(incoming)
    return Factored(tuple(arm[:begin] for arm, begin in zip(arms, begins)),
                    incoming, tuple(body), saved)


def factor(region: Region, *, candidate_budget: int = 32) -> Factored | None:
    """Return a smaller plan under a static size model, or keep the region."""
    if candidate_budget < 1:
        raise ValueError("candidate budget must be positive")
    top = structural_limit(region.arms)
    best = None
    for suffix in range(top, max(0, top - candidate_budget), -1):
        if best is not None and (len(region.arms) - 1) * suffix <= best.estimated_savings:
            break
        candidate = build_candidate(region.arms, suffix)
        if candidate.estimated_savings > (best.estimated_savings if best else 0):
            best = candidate
    return best


def resolve(value: Value, inputs: Sequence[int], locals_: Sequence[int], parameters: Sequence[int]) -> int:
    if value.kind == Kind.LITERAL:
        return value.index
    if value.kind == Kind.INPUT:
        return inputs[value.index]
    if value.kind == Kind.PARAMETER:
        return parameters[value.index]
    return locals_[value.index]


def execute(block: Block, inputs: Sequence[int], parameters: Sequence[int] = ()) -> list[int]:
    locals_ = []
    for instruction in block:
        left = resolve(instruction.left, inputs, locals_, parameters)
        right = resolve(instruction.right, inputs, locals_, parameters)
        if instruction.opcode in ("shl", "shr"):
            right &= 31
        locals_.append(OPERATOR[instruction.opcode](left, right) & UINT32)
    return locals_


def evaluate(region: Region, selector: int, inputs: Sequence[int], factored: Factored | None = None) -> int:
    if not 0 <= selector <= UINT32:
        raise ValueError("selector must fit unsigned 32 bits")
    if len(inputs) != region.input_count or any(not 0 <= value <= UINT32 for value in inputs):
        raise ValueError("expected one unsigned 32-bit value per input")
    index = selector % len(region.arms)
    if factored is None:
        return execute(region.arms[index], inputs)[-1]
    prefix = execute(factored.prefixes[index], inputs)
    arguments = tuple(resolve(column[index], inputs, prefix, ()) for column in factored.incoming)
    return execute(factored.body, inputs, arguments)[-1]
