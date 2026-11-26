# SPDX-License-Identifier: MIT
"""Synthetic dispatch families and an open graphics arithmetic workload."""

from factoring import Instruction, Kind, Region, UINT32, Value


def arg(index: int) -> Value:
    return Value(Kind.INPUT, index)


def imm(value: int) -> Value:
    return Value(Kind.LITERAL, value & UINT32)


def append(steps, opcode, left, right):
    steps.append(Instruction(opcode, left, right))
    return Value(Kind.LOCAL, len(steps) - 1)


def pcg32(num_arms: int) -> Region:
    """Seed a published PCG RXS-M-XS graphics hash differently in each mode."""
    arms = []
    for index in range(num_arms):
        steps = []
        seed = append(steps, "xor", arg(index % 2), imm(0x9e3779b9 * index))
        seed = append(steps, ("add", "sub", "xor")[index % 3], seed, arg(2))
        state = append(steps, "mul", seed, imm(747796405))
        state = append(steps, "add", state, imm(2891336453))
        shift = append(steps, "shr", state, imm(28))
        shift = append(steps, "add", shift, imm(4))
        word = append(steps, "shr", state, shift)
        word = append(steps, "xor", word, state)
        word = append(steps, "mul", word, imm(277803737))
        high = append(steps, "shr", word, imm(22))
        append(steps, "xor", word, high)
        arms.append(tuple(steps))
    return Region(3, tuple(arms))


def synthetic(num_arms: int, rounds: int, *, varying: bool = False, heterogeneous: bool = False) -> Region:
    arms = []
    for index in range(num_arms):
        steps = []
        state = append(steps, ("xor", "sub", "add")[index % 3], arg(0), imm(index + 1))
        for step in range(rounds):
            parameter = imm((step + 1) * 0x1234597 + (index * 17 if varying else 0))
            state = append(steps, "xor", state, arg(step % 3 + 1))
            state = append(steps, "add", state, parameter)
            state = append(steps, "mul", state, imm(0x85ebca6b + 2 * step))
            high_bits = append(steps, "shr", state, imm(3 + step % 22))
            state = append(steps, "xor", state, high_bits)
        if heterogeneous and index == num_arms - 1:
            append(steps, "or", state, arg(0))
        arms.append(tuple(steps))
    return Region(4, tuple(arms))


def matrix() -> dict[str, Region]:
    return {
        "pcg-8": pcg32(8),
        "pcg-32": pcg32(32),
        "pure-4x16": synthetic(4, 16),
        "pure-16x16": synthetic(16, 16),
        "pure-64x16": synthetic(64, 16),
        "pure-16x64": synthetic(16, 64),
        "constants-16x16": synthetic(16, 16, varying=True),
        "heterogeneous-16x16": synthetic(16, 16, heterogeneous=True),
    }
