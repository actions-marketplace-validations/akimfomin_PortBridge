# SPDX-License-Identifier: MIT
"""Access traces shaped by Halide's public masked relaxation benchmark."""

from compute_schedule import AccessMode, BufferAccess, BufferRange, Operation, Stage, analyze


FIELD_BYTES = 64 * 64 * 4 * 4
MASK_BYTES = 64 * 64


def access(name: str, size: int, mode: AccessMode) -> BufferAccess:
    return BufferAccess(BufferRange(name, 0, size), mode)


def step(stream: str, iteration: int) -> Operation:
    source, target = iteration % 2, (iteration + 1) % 2
    return Operation(f"{stream} relax {iteration}", Stage.COMPUTE, (
        access(f"{stream}/field{source}", FIELD_BYTES, AccessMode.READ),
        access(f"{stream}/field{target}", FIELD_BYTES, AccessMode.WRITE),
        access(f"{stream}/known", FIELD_BYTES, AccessMode.READ),
        access(f"{stream}/mask", MASK_BYTES, AccessMode.READ),
    ))


def checkpoint(stream: str, completed_iteration: int) -> Operation:
    latest = (completed_iteration + 1) % 2
    return Operation(f"{stream} checkpoint", Stage.TRANSFER, (
        access(f"{stream}/field{latest}", FIELD_BYTES, AccessMode.READ),
        access(f"{stream}/checkpoint", FIELD_BYTES, AccessMode.WRITE),
    ))


def mixed_trace(blocks: int = 4) -> tuple[Operation, ...]:
    """Interleave independent ping-pong fields and a real transfer dependency."""
    result = []
    for block in range(blocks):
        first = 3 * block
        result.extend((
            step("A", first),
            step("B", first),
            checkpoint("A", first),
            step("A", first + 1),
            step("A", first + 2),
            step("B", first + 1),
            step("B", first + 2),
            checkpoint("B", first + 2),
        ))
    return tuple(result)


def dependent_trace(steps: int = 12) -> tuple[Operation, ...]:
    return tuple(step("A", index) for index in range(steps))


def main() -> None:
    for name, trace in (("mixed", mixed_trace()), ("dependent", dependent_trace())):
        schedule = analyze(trace, event_budget=4)
        print(f"{name}: {len(trace)} operations, {len(schedule.hazards)} hazards, "
              f"{len(schedule.baseline)} minimum ordinary cuts, {len(schedule.events)} split candidates selected")
        for event in schedule.events:
            print(f"  signal before {event.signal_before}, wait before {event.wait.before}, "
                  f"intervening same-stage operations {event.intervening_source_stage_work}")


if __name__ == "__main__":
    main()
