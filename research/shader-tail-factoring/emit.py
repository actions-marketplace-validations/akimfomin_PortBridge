# SPDX-License-Identifier: MIT
"""Simple HLSL and C emitters for the structured region interface."""

from factoring import Block, Factored, Kind, Region, Value


SYMBOL = {"add": "+", "and": "&", "mul": "*", "or": "|", "sub": "-", "xor": "^", "shl": "<<", "shr": ">>"}


def value_text(value: Value, local_stem: str) -> str:
    if value.kind == Kind.LITERAL:
        return f"{value.index}u"
    stem = {Kind.INPUT: "x", Kind.LOCAL: local_stem, Kind.PARAMETER: "p"}[value.kind]
    return f"{stem}{value.index}"


def body_lines(block: Block, word: str, stem: str, indent: str):
    for index, instruction in enumerate(block):
        left = value_text(instruction.left, stem)
        right = value_text(instruction.right, stem)
        if instruction.opcode in ("shl", "shr"):
            right = f"({right} & 31u)"
        yield f"{indent}{word} {stem}{index} = {left} {SYMBOL[instruction.opcode]} {right};"


def region_body(region: Region, plan: Factored | None, word: str):
    if plan:
        for index in range(plan.parameter_count):
            yield f"    {word} p{index};"
    if plan is None or plan.parameter_count:
        yield f"    switch (selector % {len(region.arms)}u) {{"
        for index, arm in enumerate(plan.prefixes if plan else region.arms):
            label = f"case {index}u" if index + 1 < len(region.arms) else "default"
            yield f"    {label}: {{"
            yield from body_lines(arm, word, "v", "        ")
            if plan:
                for column, values in enumerate(plan.incoming):
                    yield f"        p{column} = {value_text(values[index], 'v')};"
                yield "        break;"
            else:
                yield f"        return v{len(arm) - 1};"
            yield "    }"
        yield "    }"
    if plan:
        yield from body_lines(plan.body, word, "v", "    ")
        yield f"    return v{len(plan.body) - 1};"


def core(region: Region, plan: Factored | None, word: str, name: str):
    arguments = ", ".join([f"{word} selector"] + [f"{word} x{i}" for i in range(region.input_count)])
    return [
        f"{word} {name}({arguments}) {{",
        *region_body(region, plan, word),
        "}",
    ]


def emit(region: Region, plan: Factored | None = None, language: str = "hlsl") -> str:
    if language == "c":
        lines = ["#include <stdint.h>",
                 "#if defined(_WIN32)", "__declspec(dllexport)", "#endif",
                 *core(region, plan, "uint32_t", "run_region")]
    elif language == "hlsl":
        loads = ", ".join(f"inputData.Load(address + {4 * i}u)" for i in range(region.input_count + 1))
        lines = [
            "ByteAddressBuffer inputData : register(t0);",
            "RWByteAddressBuffer outputData : register(u0);",
            *core(region, plan, "uint", "run_region"),
            "[numthreads(64, 1, 1)]",
            "void main(uint3 id : SV_DispatchThreadID) {",
            f"    uint address = {4 * (region.input_count + 1)}u * id.x;",
            f"    outputData.Store(4u * id.x, run_region({loads}));",
            "}",
        ]
    else:
        raise ValueError(f"unsupported language {language!r}")
    return "\n".join(lines) + "\n"
