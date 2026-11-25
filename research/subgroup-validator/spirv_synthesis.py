# SPDX-License-Identifier: MIT
"""Select and emit a cheaper lowering for the recognized Continued SPIR-V read."""

from dataclasses import dataclass
from functools import lru_cache
from itertools import product

from lane_contract import (
    Domain, Guest, Lowering, Mismatch, Participation, Probe, Value, active, compare_values, guest_value, project,
    target_source, validate,
)
from spirv_participation import converged_prefix, covers_full_launch
from spirv_transport import Module, Transport, UnsupportedPattern, compute_entry, recognize, require


@dataclass(frozen=True)
class Plan:
    name: str
    ballot_exec: bool = False
    fallback: bool = True
    mask_input: bool = True
    scalar_selects: bool = True
    host_membership: bool = True

    @property
    def operations(self) -> int:
        # Ballot, bit lookup and shuffle, plus optional input/index preparation and result/write merging.
        if not self.host_membership:
            return 3  # Masked source, shuffle, conditional destination write.
        return 3 + self.fallback + self.mask_input + (2 if self.scalar_selects else 7)


REFERENCE = Plan("reference", scalar_selects=False)
FULL_SUBGROUP = Plan("full-subgroup-direct", fallback=False, host_membership=False)
CANDIDATES = (
    Plan("exec-ballot-select", ballot_exec=True, fallback=False, mask_input=False),
    Plan("exec-ballot-self-fallback", ballot_exec=True, mask_input=False),
    Plan("host-ballot-select", fallback=False),
    Plan("host-ballot-self-fallback"),
)
# Removing the safe index without changing the bitwise masks can propagate poisoned shuffle results.
UNSAFE_CONTROL = Plan("no-fallback-bitmasks", fallback=False, scalar_selects=False)


@dataclass(frozen=True)
class Proof:
    projected_probes: int
    failures: int
    witness: Mismatch | None

    def record(self) -> dict:
        return {"projected_probes": self.projected_probes, "failures": self.failures,
                "witness": self.witness.record() if self.witness else None}


def plan_value(plan: Plan, lower: Lowering, domain: Domain, probe: Probe) -> tuple[Value, int]:
    lane = probe.destination
    if not active(probe.host_mask, lane):
        return Value.OLD, lane
    desired = target_source(lower, domain, lane, probe.selector)
    physically_present = active(probe.host_mask, desired) and desired // domain.physical == lane // domain.physical
    present = physically_present or not plan.host_membership
    if plan.ballot_exec:
        present = present and active(probe.exec_mask, desired)
    carrier = lane if plan.fallback and not present else desired
    if not active(probe.host_mask, carrier) or carrier // domain.physical != lane // domain.physical:
        raw = Value.UNDEFINED, -1
    elif plan.mask_input and not active(probe.exec_mask, carrier):
        raw = Value.ZERO, -1
    else:
        raw = Value.CURRENT, carrier
    if raw[0] == Value.UNDEFINED and not plan.scalar_selects:
        return raw
    if not active(probe.exec_mask, lane):
        return Value.OLD, lane
    return raw if present else (Value.ZERO, -1)


@lru_cache(maxsize=32)
def prove_plan(plan: Plan, lower: Lowering, domain: Domain) -> Proof:
    guest = Guest(32)
    validate(guest, lower, domain)
    total = failures = 0
    witness = None
    for lane, selector in product(range(domain.wave), repeat=2):
        for probe in project(guest, lower, domain, lane, selector):
            result = plan_value(plan, lower, domain, probe)
            total += 1
            if mismatch := compare_values(probe, guest_value(guest, probe), result):
                failures += 1
                if witness is None:
                    witness = mismatch
    return Proof(total, failures, witness)


def edits_for(module: Module, read: Transport, plan: Plan) -> dict[int, str]:
    defs = module.definitions
    uint, scope, _, _ = read.shuffle.args
    active_id = read.bindings["guest_active"]
    ballot = defs[read.ballot]
    blocked = {"OpFunctionCall", "OpDemoteToHelperInvocation", "OpDemoteToHelperInvocationEXT",
               "OpKill", "OpTerminateInvocation"}
    require(not any(insn.opcode in blocked for insn in module.instructions
                    if ballot.line < insn.line < read.shuffle.line),
            "unmodeled participation change between ballot and shuffle")

    change = {
        defs[read.received].line: f"{read.received} = OpSelect {uint} {read.present} {read.shuffle.ident} {read.zero}",
        defs[read.merge].line: f"{read.merge} = OpSelect {uint} {active_id} {read.received} "
                              f"{read.bindings['old_value']}",
    }
    if not (plan.mask_input and plan.fallback):
        input_value = read.source_mask if plan.mask_input else read.bindings["data_input"]
        index = read.safe_index if plan.fallback else read.desired
        change[read.shuffle.line] = f"{read.shuffle.ident} = OpGroupNonUniformShuffle {uint} {scope} {input_value} {index}"
    if plan.ballot_exec:
        active_def = defs[active_id]
        require(active_def.block == ballot.block and active_def.line < ballot.line,
                "guest EXEC does not precede the original ballot in its block")
        require({user.ident for user in module.users[read.ballot]} == {read.present}
                and {user.ident for user in module.users[read.present]} == {read.result_mask, read.safe_index},
                "another instruction observes the original participation bits")
        change[ballot.line] = f"{read.ballot} = OpGroupNonUniformBallot {ballot.args[0]} {scope} {active_id}"

    remove = [read.result_mask, *read.write_masks]
    if not plan.host_membership:
        require(all(insn.ident in (read.present, read.safe_index)
                    or insn.opcode in ("OpLine", "OpNoLine")
                    for insn in module.instructions if ballot.line < insn.line < read.shuffle.line),
                "cannot remove a ballot across an unrelated operation")
        remove.extend((read.ballot, read.present, read.received))
        change[defs[read.merge].line] = (
            f"{read.merge} = OpSelect {uint} {active_id} {read.shuffle.ident} {read.bindings['old_value']}"
        )
    if not plan.fallback:
        remove.append(read.safe_index)
    if not plan.mask_input:
        remove.append(read.source_mask)
    for ident in remove:
        change[defs[ident].line] = ""
    require(all(user.line in change for ident in remove for user in module.users[ident]),
            "removed instruction has another use or decoration")
    return change


def optimize(assembly: str, *, participation: Participation, defined_exec: bool = False,
             allow_masked_poison: bool = False, full_subgroups_at_launch: bool = False) -> tuple[str, dict]:
    """Rewrite matched reads in structurally valid compute SPIR-V assembly.

    Caller declares the existing participation, layout and binding assumptions. The default
    does not create an inactive-lane shuffle or place guest EXEC in a subgroup collective.
    Only set full_subgroups_at_launch for a Vulkan pipeline guaranteeing full physical
    subgroups with allowed widths restricted to 32 and 64. The pass independently verifies
    literal workgroup alignment and a converged control-flow prefix at each rewritten site.
    """
    module = Module(assembly)
    entry = compute_entry(module)
    widths = (32, 64)
    domains = [Domain(64, width, Participation(participation)) for width in widths]
    full_domains = [Domain(64, width, Participation.FULL) for width in widths]
    full_prefix = {}
    if full_subgroups_at_launch and covers_full_launch(module, entry, widths):
        full_prefix = converged_prefix(module, entry)
    changes = {}
    reports = []
    for insn in module.instructions:
        if insn.opcode != "OpGroupNonUniformShuffle" or len(insn.args) != 4:
            continue
        row = {"shuffle": insn.ident, "line": insn.line, "plan": None}
        reports.append(row)
        try:
            require(module.block_functions.get(insn.block) == entry, "shuffle outside the compute entry")
            read = recognize(module, insn)
            full_site = insn.line < full_prefix.get(insn.block, 0)
            site_domains = full_domains if full_site else domains
            reference_checks = {str(d.physical): prove_plan(REFERENCE, read.lowering, d).record()
                                for d in site_domains}
            if any(case["failures"] for case in reference_checks.values()):
                row.update({"reason": "original lowering is refuted under the declared contract",
                            "proof": reference_checks})
                continue
            rejected = []
            candidates = (FULL_SUBGROUP, *CANDIDATES) if full_site else CANDIDATES
            for plan in candidates:  # Ascending size, with safe fallback preferred on ties.
                if ((plan.ballot_exec and not defined_exec)
                        or (plan.host_membership and not plan.fallback and not allow_masked_poison)):
                    continue
                try:
                    proposed = edits_for(module, read, plan)
                    require(not changes.keys() & proposed.keys(), "matched sequences overlap")
                except UnsupportedPattern as exc:
                    rejected.append(str(exc))
                    continue
                proof = {str(d.physical): prove_plan(plan, read.lowering, d).record() for d in site_domains}
                if any(case["failures"] for case in proof.values()):
                    rejected.extend(case["witness"] for case in proof.values() if case["failures"])
                    continue
                changes.update(proposed)
                row.update({"plan": plan.name, "removed_operations": REFERENCE.operations - plan.operations,
                            "proof": proof, "fully_participating": full_site})
                break
            else:
                row["reason"] = rejected or ["no supported cheaper lowering"]
        except UnsupportedPattern as exc:
            row["reason"] = str(exc)

    lines = []
    for number, original in enumerate(assembly.splitlines(keepends=True), 1):
        if number not in changes:
            lines.append(original)
        elif replacement := changes[number]:
            indent = original[:len(original) - len(original.lstrip())]
            suffix = original[len(original.rstrip("\r\n")):]
            lines.append(indent + replacement + suffix)
    return "".join(lines), {"participation": Participation(participation), "defined_exec": defined_exec,
                            "allow_masked_poison": allow_masked_poison,
                            "full_subgroups_at_launch": full_subgroups_at_launch, "reads": reports}
