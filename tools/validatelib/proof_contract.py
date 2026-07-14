"""Proof-v1 lifecycle, acceptance, and delivery schema gates.

The replay engine proves behavior. This module proves that the authored metadata cannot
silently retire an earlier milestone or replace a planned acceptance journey with a smaller
one before execution begins.
"""
import os
import re

from tome_proof import (ACCEPTANCE_ARTIFACTS, ACCEPTANCE_CONTROLS,
                        ACCEPTANCE_MODES, PROOF_MODES, active_proofs,
                        safe_project_path, section_capabilities)

from . import err


_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _string_list(value, *, nonempty=False):
    return (isinstance(value, list) and (bool(value) or not nonempty)
            and all(isinstance(item, str) and item.strip() for item in value))


def _check_lifecycle(sections):
    known, active = set(), {}
    all_capabilities = set()
    for section in sections:
        sid = str(section.get("id") or "")
        proof = section.get("proof") if isinstance(section.get("proof"), dict) else {}
        introduced = set(section_capabilities(section))
        all_capabilities.update(introduced)
        supersedes = proof.get("supersedes") or []
        protects = proof.get("protects")
        if not _string_list(supersedes):
            err("proof", f"{sid}: proof supersedes must be an array of earlier section ids")
            supersedes = []
        if len(set(supersedes)) != len(supersedes):
            err("proof", f"{sid}: proof supersedes contains duplicate ids")
        if protects is not None and not _string_list(protects, nonempty=True):
            err("proof", f"{sid}: proof protects must be a non-empty string array")
            protects = None
        inherited = set()
        for retired in supersedes:
            if retired not in known:
                err("proof", f"{sid}: proof supersedes {retired!r}, which is not an earlier proof")
            elif retired not in active:
                err("proof", f"{sid}: proof supersedes {retired!r}, which is already retired")
            else:
                inherited.update(active[retired])
        if supersedes and protects is None:
            err("proof", f"{sid}: a superseding proof needs explicit protects covering every "
                "retired capability")
        protected = set(protects) if protects is not None else set(introduced)
        missing = (introduced | inherited) - protected
        if missing:
            err("proof", f"{sid}: replacement proof drops active capabilities: {sorted(missing)}")
        unknown = protected - (all_capabilities | inherited)
        if unknown:
            err("proof", f"{sid}: proof protects capabilities not taught through this section: "
                f"{sorted(unknown)}")
        for retired in supersedes:
            active.pop(retired, None)
        active[sid] = protected
        known.add(sid)

    final_protected = set().union(*active.values()) if active else set()
    missing = all_capabilities - final_protected
    if missing:
        err("proof", "ship-lifecycle capability ledger has no active proof for: "
            + ", ".join(sorted(missing)))


def _check_package(proof, sid, runtime):
    for field in ("requirementsFile", "artifactPath"):
        if not safe_project_path(proof.get(field)):
            err("proof", f"{sid}: package proof {field} must be a safe project-relative path")
    args = proof.get("packageArgs")
    if not _string_list(args, nonempty=True) or any(any(ord(ch) < 32 for ch in arg) for arg in args):
        err("proof", f"{sid}: package proof packageArgs must be non-empty safe argv strings")
    for key in ("deliveryCreateCommand", "deliveryInstallCommand", "deliveryBuildCommand"):
        value = runtime.get(key)
        if not _string_list(value, nonempty=True):
            err("proof", f"{sid}: package proof requires the selected runtime to define {key}")


def _check_acceptance(manifest, sections, plan_path, allow_guided, course_complete):
    acceptance = manifest.get("acceptance")
    if not isinstance(acceptance, dict):
        err("proof", "proof-v1 tome needs an [acceptance] executable journey")
        return
    if acceptance.get("version") != 1:
        err("proof", "[acceptance] version must be 1")
    mode = acceptance.get("mode")
    artifact = acceptance.get("artifact")
    if mode not in ACCEPTANCE_MODES:
        err("proof", f"[acceptance] mode must be one of {', '.join(sorted(ACCEPTANCE_MODES))}")
    if artifact not in ACCEPTANCE_ARTIFACTS:
        err("proof", "[acceptance] artifact must be exactly runtime or package")
    scenarios = acceptance.get("scenarios")
    if (not _string_list(scenarios, nonempty=True) or len(scenarios) < 2
            or len(set(scenarios)) != len(scenarios)
            or any(not _ID.fullmatch(item) for item in scenarios)):
        err("proof", "[acceptance] scenarios needs at least two unique kebab-case ids")
        scenarios = []
    if plan_path:
        try:
            from buildlib.checkpoints import acceptance_scenarios
        except ModuleNotFoundError:  # package import from repository root
            from tools.buildlib.checkpoints import acceptance_scenarios
        planned = acceptance_scenarios(os.path.abspath(plan_path))
        if not planned:
            err("proof", "the build plan has no valid **Acceptance scenarios:** contract")
        elif scenarios != planned:
            err("proof", f"[acceptance] scenarios do not exactly match the Phase-1 journey; "
                f"planned={planned}, authored={scenarios}")
    controls = acceptance.get("controls")
    if (not _string_list(controls) or len(set(controls or [])) != len(controls or [])
            or set(controls or []) - ACCEPTANCE_CONTROLS):
        err("proof", "[acceptance] controls must be unique values from input, clock, seed, "
            "and frame-limit")
    if mode == "run":
        if not _string_list(acceptance.get("runArgs"), nonempty=True):
            err("proof", "run acceptance needs a non-empty runArgs array")
    elif mode == "guided":
        if not allow_guided:
            err("proof", "guided acceptance is allowed only for runtime.externalWorkspace")
        checks = acceptance.get("guidedChecks")
        if (not _string_list(checks, nonempty=True) or len(checks) < 2
                or any(len(item.strip()) < 12 for item in checks)):
            err("proof", "guided acceptance needs at least two substantive guidedChecks")
    if not sections:
        return
    final = sections[-1]
    final_proof = final.get("proof") if isinstance(final.get("proof"), dict) else {}
    if artifact == "package" and course_complete:
        if mode != "run":
            err("proof", "package acceptance must be executable, not guided")
        if final_proof.get("mode") != "package":
            err("proof", "package acceptance requires the final section proof mode = package")


def check_proof_contract(manifest, sections, plan_path=None, allow_guided=False,
                         course_complete=True):
    """Append lifecycle/acceptance/delivery findings to the shared validator registry."""
    ids = [str(section.get("id") or "") for section in sections]
    for index, section in enumerate(sections):
        sid = ids[index]
        proof = section.get("proof") if isinstance(section.get("proof"), dict) else {}
        mode = proof.get("mode")
        if mode == "package":
            if not course_complete or index != len(sections) - 1:
                err("proof", f"{sid}: package proof is allowed only in the final section")
            try:
                from runtimes import resolve_config
                runtime = resolve_config(manifest.get("runtime") or {})
            except (OSError, TypeError, ValueError):
                runtime = manifest.get("runtime") or {}
            _check_package(proof, sid, runtime)
        elif mode not in PROOF_MODES:
            continue  # the section-local checker emits the precise mode error
    _check_lifecycle(sections)
    _check_acceptance(manifest, sections, plan_path, allow_guided, course_complete)

    if course_complete and sections and not allow_guided:
        final_mode = ((sections[-1].get("proof") or {}).get("mode")
                      if isinstance(sections[-1].get("proof"), dict) else None)
        if final_mode not in ("run", "package"):
            err("proof", "the final section of a non-external tome must use a deterministic "
                "run or package milestone; build-only proof cannot certify the artifact")

    # Materialize this during validation too: malformed supersession must never make a
    # reviewer and runtime disagree about which proofs remain active.
    active_proofs(sections)
