"""The validator gate, the cross-phase no-silent-shrinkage contract, and
ground-truth content measuring (forecast + end-of-run plan reconciliation)."""
import os
import re
import shlex
import subprocess
import time
import tomllib

from .. import REPO, VALIDATOR
from ..status_log import emit_status_line
from .inventory import (
    RUNTIME_CONFIG_DIR,
    inventory,
    review_changes,
    review_inventory,
    runtime_config_inventory,
    runtime_config_scope_violations,
    selected_runtime_config,
    shrink_marks,
    shrinkage,
)
from runtimes.validation_environment import ensure_validation_environment, validation_subprocess_env

PHASE3_VALIDATOR = os.path.join(REPO, "tools", "validate_phase3.py")
LIVE_SMOKE = os.path.join(REPO, "tools", "smoke_tome.py")


class ValidatorInfrastructureError(RuntimeError):
    """A deterministic gate failed before it could report authored findings."""

    def __init__(self, command, detail):
        self.command = str(command)
        self.detail = str(detail or "no diagnostic").strip()
        super().__init__(
            f"validator infrastructure failure while running `{self.command}`: "
            f"{self.detail}")


def _validator_report(process):
    return ((process.stdout or "") + (process.stderr or "")).strip()


def _has_authored_findings(report):
    """Content gates fail through structured findings, never raw tracebacks.

    Treating every nonzero process as author-repairable caused an import traceback to
    be sent through dozens of paid repair turns.  ERROR/WARN lines are the validator's
    contract for authored work; an unstructured nonzero result is a harness failure.
    """
    lines = str(report or "").splitlines()
    raw_exception = re.compile(
        r"^(?:Traceback \(most recent call last\):|"
        r"[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception):)")
    if any(raw_exception.match(line.strip()) for line in lines):
        return False
    return any(line.startswith(("ERROR ", "WARN ")) for line in lines)


def _run_harness_command(cmd, tid, announce=True):
    """Run a deterministic validator command and expose its lifecycle.

    The anchored messages are deliberately emitted by this orchestration seam, not by
    validator prose, so ordinary worker narration cannot be mistaken for harness output.
    """
    rendered = shlex.join(cmd)
    if announce:
        emit_status_line(f"VALIDATOR COMMAND START [{time.time():.3f}] › {rendered}")
    try:
        # The author can introduce or change validationDependencies while writing the
        # Phase-2 manifest.  Provision at the harness boundary, after those declarations
        # exist and before asking for the ready-only subprocess environment.
        ensure_validation_environment(tid)
        process = subprocess.run(
            cmd, cwd=REPO, env=validation_subprocess_env(tid),
            capture_output=True, text=True)
    except Exception as exc:
        if announce:
            emit_status_line(f"VALIDATOR COMMAND FAILED [{time.time():.3f}] "
                             f"(exit unavailable) › {rendered}")
        raise ValidatorInfrastructureError(
            rendered, f"{type(exc).__name__}: {exc}") from exc
    if announce:
        state = "COMPLETE" if process.returncode == 0 else "FAILED"
        emit_status_line(f"VALIDATOR COMMAND {state} [{time.time():.3f}] "
                         f"(exit {process.returncode}) › {rendered}")
    report = _validator_report(process)
    if process.returncode != 0 and not _has_authored_findings(report):
        detail = f"exit {process.returncode}: {report or '(no output)'}"
        raise ValidatorInfrastructureError(rendered, detail)
    return process


def run_harness_command(cmd, tid, announce=True):
    """Run one trusted deterministic check with standard finding classification."""
    return _run_harness_command(cmd, tid, announce=announce)


def preflight_validator_runtime(tid, entrypoints):
    """Import each exact CLI entrypoint before a paid author turn starts.

    ``--help`` exercises module bootstrap and argument-parser construction without
    validating incomplete authored content.  Once a tome manifest exists, this also
    proves its declared dependency environment is ready.
    """
    scripts = tuple(dict.fromkeys(str(path) for path in entrypoints if path))
    if not scripts:
        return
    rendered = "validator preflight: " + ", ".join(scripts)
    try:
        manifest = os.path.join(REPO, "tomes", tid, "tome.toml")
        if os.path.isfile(manifest):
            ensure_validation_environment(tid)
            env = validation_subprocess_env(tid)
        else:
            env = os.environ.copy()
        for script in scripts:
            command = ["python3", script, "--help"]
            process = subprocess.run(
                command, cwd=REPO, env=env, capture_output=True, text=True)
            if process.returncode != 0:
                report = _validator_report(process)
                raise ValidatorInfrastructureError(
                    shlex.join(command),
                    f"exit {process.returncode}: {report or '(no output)'}")
    except ValidatorInfrastructureError:
        raise
    except Exception as exc:
        raise ValidatorInfrastructureError(
            rendered, f"{type(exc).__name__}: {exc}") from exc


def validator_argv(tid, phase=None, tooling=None, run=None, strict=None, plan_rel=None,
                   run_section=None, phase_only=False, source_only=False):
    """Return the canonical validator command used by the author and final gate.

    Keeping this as argv (rather than a hand-built flags string) makes command parity
    testable and keeps paths safely quoted when the same command is rendered into a
    worker prompt. ``phase`` selects only genuinely phase-specific gates; explicit
    ``run``/``strict`` overrides are retained for the split-Section fast checkpoint.
    """
    cmd = ["python3", os.path.relpath(VALIDATOR, REPO), f"tomes/{tid}"]
    if phase == 1:
        if not plan_rel:
            raise ValueError("Phase 1 validator command needs plan_rel")
        return cmd + ["--phase-1-plan", plan_rel]

    if phase == 2:
        cmd.append("--phase-2-skeleton")
    if phase is not None and phase >= 2:
        cmd += ["--build-phase", str(phase)]
    strict = (phase is not None and phase >= 7) if strict is None else strict
    if phase_only:
        if phase is None or phase < 2:
            raise ValueError("phase-only validation needs phase >= 2")
        if strict:
            raise ValueError("phase-only validation cannot be strict")
        cmd.append("--phase-only")
    if source_only:
        if not run_section or not phase_only:
            raise ValueError("source-only validation needs a phase-only section gate")
        cmd.append("--source-only")
    if phase is not None and phase >= 2 and os.environ.get("ARCANUM_REQUIRE_PROOF_V1") == "1":
        cmd.append("--require-proof-v1")
    run = (phase != 2) if run is None else run
    if strict:
        cmd.append("--strict")
    if not run:
        cmd.append("--no-run")
    if tooling:
        cmd += ["--tooling", tooling]  # enforce the gate's internal/external/both choice
    if run_section:
        cmd += ["--run-section", str(run_section)]
    if plan_rel and phase is not None and phase >= 2:
        cmd += ["--build-plan", plan_rel]
    return cmd


def validator_shell_command(tid, phase=None, tooling=None, run=None, strict=None,
                            plan_rel=None, run_section=None, phase_only=False,
                            source_only=False):
    """The canonical argv rendered exactly as the worker should run it."""
    return ('cd "$ARCANUM_REPO_ROOT" && '
            + shlex.join(validator_argv(
                tid, phase, tooling, run, strict, plan_rel, run_section, phase_only,
                source_only)))


def phase3_validator_argv(tid, tooling, plan_rel, run=True, strict=False):
    if not plan_rel:
        raise ValueError("complete Phase-3 validator command needs plan_rel")
    cmd = ["python3", os.path.relpath(PHASE3_VALIDATOR, REPO), f"tomes/{tid}",
           "--plan", plan_rel]
    if tooling:
        cmd += ["--tooling", tooling]
    if strict:
        cmd.append("--strict")
    if not run:
        cmd.append("--no-run")
    return cmd


def phase3_validator_shell_command(tid, tooling, plan_rel, run=True, strict=False):
    """The exact complete Phase-3/shipping gate shared by worker and harness."""
    return ('cd "$ARCANUM_REPO_ROOT" && '
            + shlex.join(phase3_validator_argv(tid, tooling, plan_rel, run, strict)))


def section_validator_argv(tid, sid, tooling, plan_rel):
    """Return the complete fast Phase-3 gate for one section and its handoff."""
    if not plan_rel:
        raise ValueError("split-section validator command needs plan_rel")
    cmd = ["python3", "tools/validate_section.py", f"tomes/{tid}", sid,
           "--plan", plan_rel]
    if tooling:
        cmd += ["--tooling", tooling]
    return cmd


def section_validator_shell_command(tid, sid, tooling, plan_rel):
    """Render the exact complete section gate for a warm worker prompt."""
    return ('cd "$ARCANUM_REPO_ROOT" && '
            + shlex.join(section_validator_argv(tid, sid, tooling, plan_rel)))


def section_source_validator_argv(tid, sid, tooling, plan_rel):
    """Fast reconstructed-source checkpoint used inside a focused repair turn."""
    return [*section_validator_argv(tid, sid, tooling, plan_rel), "--source-only"]


def section_source_validator_shell_command(tid, sid, tooling, plan_rel):
    return ('cd "$ARCANUM_REPO_ROOT" && '
            + shlex.join(section_source_validator_argv(tid, sid, tooling, plan_rel)))


def section_window_validator_argv(tid, through, plan_rel):
    """Return the continuity + anti-template checkpoint for an authored prefix."""
    if not plan_rel:
        raise ValueError("section-window validator command needs plan_rel")
    return ["python3", "tools/workflow/validate_section_window.py", f"tomes/{tid}",
            "--through", through, "--plan", plan_rel]


def section_window_validator_shell_command(tid, through, plan_rel):
    """Render the periodic same-worker quality checkpoint."""
    return ('cd "$ARCANUM_REPO_ROOT" && '
            + shlex.join(section_window_validator_argv(tid, through, plan_rel)))


def validate(tid, phase=None, strict=None, tooling=None, run=None, plan_rel=None,
             run_section=None, phase_only=False, source_only=False, announce=True):
    cmd = validator_argv(
        tid, phase, tooling, run, strict, plan_rel, run_section, phase_only,
        source_only)
    p = _run_harness_command(cmd, tid, announce=announce)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def validate_section(tid, sid, tooling, plan_rel):
    """Repeat the worker's exact combined content + continuity command independently."""
    cmd = section_validator_argv(tid, sid, tooling, plan_rel)
    p = _run_harness_command(cmd, tid)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def validate_section_window(tid, through, plan_rel):
    """Run a cross-section quality window independently of the author worker."""
    cmd = section_window_validator_argv(tid, through, plan_rel)
    p = _run_harness_command(cmd, tid)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def validate_phase3(tid, tooling, plan_rel, _sections):
    """Repeat the worker's complete executable/authorship/continuity command."""
    cmd = phase3_validator_argv(tid, tooling, plan_rel)
    process = _run_harness_command(cmd, tid)
    return process.returncode == 0, (process.stdout + process.stderr).strip()


def validate_shipping(tid, tooling, plan_rel):
    """Strict tome validation plus Phase-3 completion and continuity invariants."""
    cmd = phase3_validator_argv(tid, tooling, plan_rel, strict=True)
    process = _run_harness_command(cmd, tid)
    return process.returncode == 0, (process.stdout + process.stderr).strip()


def validate_live_smoke(tid):
    """Exercise loader, runtime, and grader-status routes after strict validation."""
    process = _run_harness_command(
        ["python3", os.path.relpath(LIVE_SMOKE, REPO), tid], tid)
    return process.returncode == 0, (process.stdout + process.stderr).strip()


def blocking_report(report, strict=False):
    """Trim validator output to findings that can actually fail the current gate.

    A non-strict phase exits nonzero only for ``ERROR``. Strict phases additionally
    fail on non-advisory ``WARN`` findings. If the process crashed or returned some
    unexpected format, preserve the full report so diagnostics are never hidden.
    """
    lines = str(report or "").splitlines()
    blockers = []
    for line in lines:
        if line.startswith("ERROR "):
            blockers.append(line)
        elif (strict and line.startswith("WARN ")
              and not line.startswith("WARN advisory:")):
            blockers.append(line)
    summaries = [line for line in lines if line.startswith("-- ")]
    return "\n".join(blockers + summaries) if blockers else str(report or "").strip()


def blocker_signature(report, strict=False):
    """Stable blocker shape for detecting a repair hand that made no gate progress."""
    focused = blocking_report(report, strict=strict)
    lines = [line for line in focused.splitlines()
             if line.startswith("ERROR ") or (strict and line.startswith("WARN "))]
    return tuple(re.sub(r"\d+", "#", re.sub(r"\s+", " ", line)).strip()
                 for line in lines)


def measure(tid):
    """Ground-truth counts: content/bank sizes, fixed rewards, and repeatable hex range.
    Feeds the pre-build forecast (#23) and the post-build plan reconciliation (#11) — the plan
    is prose and 'claims are not evidence', so the harness writes the real numbers itself."""
    root = os.path.join(REPO, "tomes", tid)
    out = {"sections": 0, "lessons": 0, "exercises": 0, "ex_points": 0,
           "fs_reward": 0, "bounty": 0, "bounty_min": 0, "bounty_max": 0,
           "badges": 0, "themes": 0, "shop": 0}
    if not os.path.isdir(root):
        return out

    def load(*parts):
        p = os.path.join(root, *parts)
        try:
            with open(p, "rb") as f:
                return tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    manifest = load("tome.toml")
    for bank, key in (("themes", "themes"), ("shop", "shop"), ("badges", "badges")):
        data = load(f"{bank}.toml") or manifest
        out[key] = len(data.get(key, []) or [])
    tiers = (load("intrusions.toml").get("tiers")
             or (manifest.get("progression", {}) or {}).get("intrusionTiers") or [])
    bounties = [t.get("bounty") for t in tiers if isinstance(t, dict)
                and isinstance(t.get("bounty"), (int, float))
                and not isinstance(t.get("bounty"), bool)]
    out["bounty"] = sum(bounties)
    out["bounty_min"] = min(bounties, default=0)
    out["bounty_max"] = max(bounties, default=0)
    sids = (manifest.get("content", {}) or {}).get("sections") or []
    for sid in sids:
        sd = None
        for cand in ((f"sections/{sid}", "section.toml"), (f"sections/{sid}.toml",)):
            d = load(*cand)
            if d:
                sd = d if len(cand) == 1 else d
                break
        # in split layout the section keys + freestyle + lessons live in sibling files;
        # count lessons/exercises/freestyle across whichever files exist
        out["sections"] += 1
        fdir = os.path.join(root, "sections", str(sid))
        fs = load(f"sections/{sid}", "freestyle.toml").get("freestyle") or (sd or {}).get("freestyle") or {}
        out["fs_reward"] += fs.get("reward", 0) or 0
        les_list = []
        ldir = os.path.join(fdir, "lessons")
        if os.path.isdir(ldir):
            for ln in sorted(os.listdir(ldir)):
                les_list += load(f"sections/{sid}", "lessons", ln).get("lessons", []) or []
        else:
            les_list = (sd or {}).get("lessons", []) or []
        out["lessons"] += len(les_list)
        for les in les_list:
            exs = les.get("exercises", []) or []
            out["exercises"] += len(exs)
            out["ex_points"] += sum(e.get("points", 0) or 0 for e in exs if isinstance(e, dict))
    # Hex defenses repeat every 10–15 minutes and may be won zero or many times.
    # Their tier schedule is useful balance context, but it is not a finite base total.
    out["base_earnable"] = out["ex_points"] + out["fs_reward"]
    return out


def forecast_line(mv):
    """One rough line: content size + a crude token estimate (lessons/exercises are the bulk).
    Deliberately a heuristic, not a promise — it's a 'how big is this getting' gut-check."""
    est_k = round((mv["lessons"] * 1.2 + mv["exercises"] * 0.4) )  # ~KB of TOML, order-of-magnitude
    hex_part = (f" · repeatable hex bounty {mv['bounty_min']}–{mv['bounty_max']}/win"
                if mv.get("bounty_max") else "")
    return (f"{mv['sections']} sections · {mv['lessons']} lessons · {mv['exercises']} exercises "
            f"· fixed face-value {mv['base_earnable']}{hex_part} · ~{est_k}KB content (rough)")
