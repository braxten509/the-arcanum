"""Prompt-state decisions for the one-provider warm Phase-3 path.

The provider process stays alive while it authors the Arc. If that process ends, this
module reconstructs the smallest safe disk-backed assignment for a replacement: unfinished
sections when any remain, otherwise whole-tome reconciliation against the final gate.
"""
import os
from dataclasses import dataclass

from . import REPO
from .continuity import reconciliation_prompt
from .measure import blocking_report, validate_phase3
from .prompts import build_prompt
from .sections import (phase3_pending_sections, prepare_whole_tome_warm_worker,
                       section_ids)
from .workflow import support_prompt


@dataclass
class WarmPhase3State:
    prompt: str
    context: str
    sidecars: list
    body: str
    pending: list
    gate: tuple | None = None
    notice: str = ""


def uses_whole_warm_worker(phase, split_sections, ids):
    """Single-section builds still need the warm protocol to create/test their handoff."""
    return phase == 3 and bool(ids) and (not split_sections or len(ids) < 2)


def _prompt(tid, title, body, refs, tooling, context, access, repair_only, feedback=""):
    plan_rel, verdict_rel, findings_rel = refs
    return (build_prompt(tid, 3, title, body, plan_rel, verdict_rel, findings_rel,
                         tooling=tooling, validation_run=repair_only,
                         repair_only=repair_only)
            + context + access + feedback)


def prepare_warm_phase3_start(tid, title, body, refs, tooling, access, resume=False):
    """Build the fresh/resume prompt and optionally prove a resume needs no worker."""
    plan_rel, _, _ = refs
    plan_path = plan_rel if os.path.isabs(plan_rel) else os.path.join(REPO, plan_rel)
    ids = section_ids(tid)
    pending, reports = phase3_pending_sections(tid, plan_path) if resume else (ids, {})
    context, sidecars = prepare_whole_tome_warm_worker(
        tid, plan_rel, tooling, resume=resume,
        pending_ids=pending if resume else None)
    gate = None
    if resume:
        gate = ((False, "\n".join(reports[sid] for sid in pending)) if pending
                else validate_phase3(tid, tooling, plan_rel, ids))
    active_body = body
    repair_only = False
    feedback = ""
    notice = ""
    if gate and gate[0]:
        notice = "Phase 3 resume gate is already clean — worker not needed"
    elif gate and pending:
        feedback = ("\n\n===== INCOMPLETE PHASE-3 RESUME =====\n"
                    + blocking_report(gate[1]))
        notice = f"Phase 3 resume: {len(pending)} incomplete section(s) assigned"
    elif gate:
        active_body = support_prompt("phase-3-reconcile")
        context = reconciliation_prompt(tid, ids, plan_path)
        repair_only = True
        feedback = ("\n\n===== EXISTING PHASE-3 BLOCKERS — REPAIR, DO NOT REDO =====\n"
                    + blocking_report(gate[1]))
        notice = "Phase 3 resume is final-gate repair only; authored sections stay intact"
    return WarmPhase3State(
        _prompt(tid, title, active_body, refs, tooling, context, access,
                repair_only, feedback),
        context, sidecars, active_body, pending, gate, notice)


def prepare_warm_phase3_recovery(tid, title, phase_body, refs, tooling, access,
                                 feedback=""):
    """Rebuild a replacement prompt from independently measured disk state."""
    plan_rel, _, _ = refs
    plan_path = plan_rel if os.path.isabs(plan_rel) else os.path.join(REPO, plan_rel)
    ids = section_ids(tid)
    pending, _ = phase3_pending_sections(tid, plan_path)
    if pending:
        context, sidecars = prepare_whole_tome_warm_worker(
            tid, plan_rel, tooling, resume=True, pending_ids=pending)
        active_body, repair_only = phase_body, False
    else:
        # An empty pending list means authored completion/handoffs are intact. The only
        # remaining work is the cross-section executable/quality gate, so expose all
        # handoffs but send the narrow reconciliation contract.
        _, sidecars = prepare_whole_tome_warm_worker(
            tid, plan_rel, tooling, resume=True, pending_ids=[])
        context = reconciliation_prompt(tid, ids, plan_path)
        active_body, repair_only = support_prompt("phase-3-reconcile"), True
    return WarmPhase3State(
        _prompt(tid, title, active_body, refs, tooling, context, access,
                repair_only, feedback),
        context, sidecars, active_body, pending)
