# SPDX-License-Identifier: MIT
"""Prove full participation through a restricted compute control-flow prefix."""

from collections import defaultdict

from spirv_transport import Module


# Extension operations and calls are outside the local control-flow proof.
UNKNOWN_PARTICIPATION = {
    "OpFunctionCall", "OpDemoteToHelperInvocation", "OpDemoteToHelperInvocationEXT",
    "OpKill", "OpTerminateInvocation", "OpExtInst", "OpExtInstWithForwardRefsKHR",
}


def covers_full_launch(module: Module, entry: str, widths: tuple[int, ...]) -> bool:
    sizes = [insn.args[2:] for insn in module.instructions
             if insn.opcode == "OpExecutionMode" and insn.args[:2] == (entry, "LocalSize")]
    if len(sizes) != 1 or len(sizes[0]) != 3:
        return False
    if any(insn.opcode == "OpDecorate" and insn.args[1:] == ("BuiltIn", "WorkgroupSize")
           for insn in module.instructions):
        # The Vulkan built-in can override the literal execution mode.
        return False
    try:
        x = int(sizes[0][0], 0)
    except ValueError:
        return False
    return x > 0 and all(x % width == 0 for width in widths)


def converged_prefix(module: Module, entry: str) -> dict[str, int]:
    """Map proved blocks to the first instruction line that invalidates the proof.

    A selection entered uniformly reconverges at its declared merge if every
    invocation exits through it. This walk handles straight-line blocks and
    selections with direct or one-block arms. It does not need branch uniformity.
    """
    blocks = defaultdict(list)
    for insn in module.instructions:
        if (module.block_functions.get(insn.block) == entry
                and insn.opcode not in ("OpLine", "OpNoLine")):
            blocks[insn.block].append(insn)
    block = next(iter(blocks), None)
    proved = {}
    while block in blocks and block not in proved:
        body = blocks[block]
        terminator = body[-1]
        if any(insn.opcode == "OpLoopMerge" for insn in body):
            # A later visit to this same static header need not remain converged.
            break
        stop = next((insn.line for insn in body if insn.opcode in UNKNOWN_PARTICIPATION), None)
        proved[block] = terminator.line if stop is None else stop
        if stop is not None:
            break
        if terminator.opcode == "OpBranch":
            block = terminator.args[0]
            continue
        if terminator.opcode != "OpBranchConditional" or body[-2].opcode != "OpSelectionMerge":
            break
        merge = body[-2].args[0]
        for arm in terminator.args[1:3]:
            if arm == merge:
                continue
            arm_body = blocks.get(arm)
            if (not arm_body or arm_body[-1].opcode != "OpBranch" or arm_body[-1].args != (merge,)
                    or any(insn.opcode in UNKNOWN_PARTICIPATION for insn in arm_body)):
                return proved
        block = merge
    return proved
