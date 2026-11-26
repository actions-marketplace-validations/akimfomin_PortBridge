# SPDX-License-Identifier: MIT
"""Find existing planner opportunities in conservative, direct SPIR-V switch tails."""

from collections import Counter, defaultdict
from dataclasses import dataclass
import re

from factoring import Instruction, Kind, Region, Value, factor


OPCODES = {
    "OpIAdd": "add", "OpISub": "sub", "OpIMul": "mul",
    "OpBitwiseAnd": "and", "OpBitwiseOr": "or", "OpBitwiseXor": "xor",
    "OpShiftLeftLogical": "shl", "OpShiftRightLogical": "shr",
}
IGNORE = {"OpLine", "OpNoLine"}
ROW = re.compile(r"(?:(%\d+)\s*=\s*)?(Op\w+)(?:\s+([^;]*))?")


@dataclass(frozen=True)
class Op:
    result: str | None
    code: str
    args: tuple[str, ...]


def parse(assembly):
    for line in assembly.splitlines():
        if match := ROW.match(line.strip()):
            result, code, args = match.groups()
            if code not in IGNORE:
                yield Op(result, code, tuple((args or "").split()))


def successors(op):
    if op.code == "OpSwitch":
        return set(op.args[1::2])
    if op.code == "OpBranchConditional":
        return set(op.args[1:3])
    if op.code == "OpBranch":
        return {op.args[0]}
    return set()


def phi_inputs(merge, targets, unsigned_types):
    for op in merge:
        if op.code != "OpPhi":
            break
        incoming = dict(zip(op.args[2::2], op.args[1::2]))
        if op.args[0] in unsigned_types and targets == incoming.keys():
            yield incoming


def candidate_plan(arms, final_values, types, definitions, uses, decorations):
    def legal(op):
        if op.result in decorations or op.code not in OPCODES or op.args[0] not in types:
            return False
        if op.code not in {"OpShiftLeftLogical", "OpShiftRightLogical"}:
            return True
        count = definitions[op.args[2]]
        if count.code == "OpConstant":
            return 0 <= int(count.args[1], 0) < 32
        return (count.code == "OpBitwiseAnd"
                and any(definitions[var].code == "OpConstant" and
                        int(definitions[var].args[1], 0) == 31 for var in count.args[1:]))

    available = []
    for arm, final in zip(arms, final_values):
        tail = []
        for op in reversed(arm[:-1]):
            if not legal(op):
                break
            tail.append(op)
        if not tail or tail[0].result != final:
            return None
        available.append(tuple(reversed(tail)))

    external = {}
    blocks = []
    for tail in available:
        locals_ = {}

        def value(name):
            if name in locals_:
                return Value(Kind.LOCAL, locals_[name])
            return Value(Kind.INPUT, external.setdefault(name, len(external)))

        block = []
        for op in tail:
            block.append(Instruction(OPCODES[op.code], value(op.args[1]), value(op.args[2])))
            locals_[op.result] = len(block) - 1
        blocks.append(tuple(block))
    plan = factor(Region(len(external), tuple(blocks)))
    if plan is None:
        return None

    length = len(plan.body)
    for tail in available:
        tail = tail[-length:]
        consumed = Counter(arg for op in tail for arg in op.args[1:])
        consumed[tail[-1].result] += 1  # The return or the single merge PHI.
        if any(uses[op.result] != consumed[op.result] for op in tail):
            return None
    return {"arms": len(arms), "body": length,
            "parameters": plan.parameter_count, "estimated_savings": plan.estimated_savings}


def census(assembly):
    ops = list(parse(assembly))
    types = {op.result for op in ops if op.code == "OpTypeInt" and op.args == ("32", "0")}
    definitions = {op.result: op for op in ops if op.result}
    decorations = {op.args[0] for op in ops if op.code.startswith("OpDecorate")}
    for op in ops:
        if op.code == "OpGroupDecorate":
            decorations.update(op.args[1:])
    uses = Counter(arg for op in ops if op.code not in {"OpName", "OpMemberName"}
                   for arg in op.args if arg.startswith("%"))
    blocks = {}
    current = None
    for op in ops:
        if op.code == "OpLabel":
            current = op.result
            blocks[current] = []
        elif op.code == "OpFunctionEnd":
            current = None
        elif current:
            blocks[current].append(op)

    predecessors = defaultdict(set)
    for label, block in blocks.items():
        for target in successors(block[-1]):
            predecessors[target].add(label)

    stats = Counter(switches=0, direct_switches=0)
    plans = []
    for header, block in blocks.items():
        if block[-1].code != "OpSwitch":
            continue
        stats["switches"] += 1
        targets = sorted(successors(block[-1]))
        if len(targets) < 2 or len(block) < 2 or block[-2].code != "OpSelectionMerge":
            continue
        merge = block[-2].args[0]
        if merge in targets or any(predecessors[target] != {header} for target in targets):
            continue
        arms = [blocks[target] for target in targets]
        final_codes = {arm[-1].code for arm in arms}
        if final_codes == {"OpReturnValue"}:
            final_values = [tuple(arm[-1].args[0] for arm in arms)]
        elif all(arm[-1] == Op(None, "OpBranch", (merge,)) for arm in arms):
            final_values = [tuple(incoming[label] for label in targets)
                            for incoming in phi_inputs(blocks[merge], set(targets), types)]
        else:
            continue
        stats["direct_switches"] += 1
        for values in final_values:
            if plan := candidate_plan(arms, values, types, definitions, uses, decorations):
                plans.append({"header": header, **plan})
                break
    return {"switches": stats["switches"], "direct_switches": stats["direct_switches"],
            "plans": plans}
