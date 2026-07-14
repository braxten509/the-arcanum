"""Split-mode Phase 3: author bounded section batches in warm workers.

The filesystem checkpoints remain per-section, but one provider process owns a small
Arc-ordered batch. That keeps its reasoning warm across adjacent sections without making
the build depend on any provider's undocumented compaction threshold.
"""
import json
import os
import shlex
import shutil
import time
import tomllib

from . import BUILD_DIR, REPO, retries_for
from .continuity import (continuity_prompt, prepare_handoff, reset_handoffs,
                         validate_handoff)
from .liveness import preflight_runners, run_agent
from .measure import (blocking_report, section_validator_shell_command,
                      section_window_validator_shell_command, validate_section)
from .prompts import build_prompt, read_tooling
from .runners import _implicit_fallback, request_runner
from .agent_runtime import scoped_runner_command
from .workflow import support_prompt
from .validation_env import validation_subprocess_env
from validatelib.phase3 import load_section_completion


SECTION_BATCH_SIZE = 3
WARM_CHECKPOINT_SIZE = 3
SECTION_PROGRESS_STATES = ("authoring", "repairing", "validating", "complete")


def section_progress_path(tid):
    return os.path.join(BUILD_DIR, f"{tid}.section-progress.json")


def write_section_progress(tid, sid, index, total, state, batch=0, batches=0):
    """Write the exact live position shared by the worker, harness, and Bindery UI.

    The file itself is mounted writable into a batch sandbox, so writes intentionally
    target this already-created path instead of replacing it through its read-only parent.
    """
    if state not in SECTION_PROGRESS_STATES:
        raise ValueError(f"unknown section progress state: {state}")
    payload = {"section": str(sid), "index": int(index), "total": int(total),
               "state": state, "batch": int(batch), "batches": int(batches),
               "updatedAt": time.time()}
    path = section_progress_path(tid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
        handle.write("\n")
    return path


def clear_section_progress(tid):
    try:
        os.remove(section_progress_path(tid))
    except OSError:
        pass


def section_progress_shell_command(tid, sid, index, total, state, batch, batches):
    argv = ["python3", os.path.join(REPO, "tools", "report_section_progress.py"),
            tid, sid, str(index), str(total), state,
            "--batch", str(batch), "--batches", str(batches)]
    return shlex.join(argv)


def section_ids(tid):
    """Ordered section ids from tome.toml [content].sections — the validator's source of truth,
    and (once Phase 2 scaffolds it) the list a split Phase 3 authors one worker at a time."""
    try:
        with open(os.path.join(REPO, "tomes", tid, "tome.toml"), "rb") as f:
            d = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(s) for s in ((d.get("content") or {}).get("sections") or [])]


def phase3_pending_sections(tid, plan_path, ids=None):
    """Return sections whose authored-content or exact handoff gate is not yet clean."""
    ids = list(ids or section_ids(tid))
    tome_path = os.path.join(REPO, "tomes", tid)
    pending, reports = [], {}
    for sid in ids:
        problems = load_section_completion(tome_path, sid)
        handoff_clean, handoff_report = validate_handoff(tid, sid, ids, plan_path)
        if problems or not handoff_clean:
            pending.append(sid)
            handoff_lines = ([f"ERROR handoff: {line}" for line in handoff_report.splitlines()]
                             if not handoff_clean else [])
            reports[sid] = "\n".join(
                [*(f"ERROR section-complete: {problem}" for problem in problems),
                 *handoff_lines]).strip()
    return pending, reports


def prepare_whole_tome_warm_worker(tid, plan_rel, tooling, resume=False,
                                   checkpoint_size=WARM_CHECKPOINT_SIZE, pending_ids=None):
    """Prepare one unsplit Phase-3 worker's in-context section checkpoint protocol.

    The provider process remains alive for the entire phase. It authors one section,
    runs the same fast gate used by split workers, repairs it, and only then advances.
    Every few sections a prefix-only continuity/anti-template gate stops a bad pattern
    from propagating. Exact writable handoff/progress sidecars are returned for bwrap.
    """
    ids = section_ids(tid)
    if not ids:
        return "", []
    pending_set = set(pending_ids or ())
    assigned = ids if pending_ids is None else [sid for sid in ids if sid in pending_set]
    checkpoint_size = max(2, int(checkpoint_size or WARM_CHECKPOINT_SIZE))
    plan_path = os.path.join(REPO, plan_rel)
    handoffs = [prepare_handoff(tid, sid, reset=not resume, ids=ids,
                                plan_path=plan_path) for sid in ids]
    if not assigned:
        return "", handoffs
    first_index = ids.index(assigned[0]) + 1
    progress_path = write_section_progress(
        tid, assigned[0], first_index, len(ids), "authoring", 1, 1)

    lines = [
        "\n\n===== ONE WARM WORKER: SECTION CHECKPOINT PROTOCOL =====",
        "Keep this same provider session for every section; do not spawn subagents or hand "
        "sections to other workers. More context does not replace feedback: complete exactly "
        "one section, repair its gate to exit 0, and only then move to the next.",
        "",
        "DEPENDENCY PREFLIGHT — before editing the first section, read the plan's Tooling fit, "
        "acceptance proof, install steps, and [runtime].validationDependencies. The harness has "
        "already provisioned those dependencies in an isolated validation environment shared by "
        "your gates and the harness-owned gates. Probe them with non-mutating version/import "
        "checks. Never run pip/npm/cargo/system package installs from this worker, never alter the "
        "isolated environment, and never rewrite course requirements to hide a dependency failure.",
        "",
        "For every section, reopen the actual earlier owner files and completed handoffs before "
        "reusing a contract. The precreated handoff JSON already contains Phase-1 obligations; "
        "fill its artifact_state, exact public contracts, future obligations, temporary artifacts, "
        "and evidence for obligations due here. Do not replace its schema or omit planned edges.",
    ]
    if assigned != ids:
        complete = [sid for sid in ids if sid not in assigned]
        lines += ["", "RECOVERY SCOPE — the harness independently proved these sections clean: "
                  + (", ".join(complete) or "none") + ". Preserve them. Author or repair only: "
                  + ", ".join(assigned) + ". Adding lessons/exercises is allowed when an exact "
                  "authored-completion blocker requires it."]
    for sid in assigned:
        index = ids.index(sid) + 1
        authoring = section_progress_shell_command(tid, sid, index, len(ids),
                                                   "authoring", 1, 1)
        repairing = section_progress_shell_command(tid, sid, index, len(ids),
                                                   "repairing", 1, 1)
        validating = section_progress_shell_command(tid, sid, index, len(ids),
                                                    "validating", 1, 1)
        complete = section_progress_shell_command(tid, sid, index, len(ids),
                                                  "complete", 1, 1)
        gate = section_validator_shell_command(tid, sid, tooling, plan_rel)
        lines += [
            "",
            f"--- {sid} ({index} of {len(ids)}) ---",
            f"Handoff: {os.path.relpath(handoffs[index - 1], REPO)}",
            f"BEFORE editing: {authoring}",
            f"BEFORE each gate attempt: {validating}",
            f"If its gate fails: {repairing}",
            f"Section code gate — executes this section's snippets/write labs; fix every ERROR "
            f"and rerun until exit 0: {gate}",
        ]
        if index % checkpoint_size == 0 or index == len(ids):
            window = section_window_validator_shell_command(tid, sid, plan_rel)
            lines += [
                f"BEFORE its quality window: {validating}",
                f"QUALITY WINDOW through {sid} — run after its section gate is clean: {window}",
                "Treat every quality-window finding as blocking. Repair the completed prefix and "
                "rerun both the affected section gate(s) and this window until it exits 0 before "
                "authoring the next section.",
                f"If its quality window fails: {repairing}",
                f"ONLY after both gates exit 0: {complete}",
            ]
        else:
            lines.append(f"ONLY after its section gate exits 0: {complete}")
    final_sid = assigned[-1]
    final_index = ids.index(final_sid) + 1
    final_validating = section_progress_shell_command(
        tid, final_sid, final_index, len(ids), "validating", 1, 1)
    final_repairing = section_progress_shell_command(
        tid, final_sid, final_index, len(ids), "repairing", 1, 1)
    final_complete = section_progress_shell_command(
        tid, final_sid, final_index, len(ids), "complete", 1, 1)
    lines += [
        "",
        "After the final assigned section gate (and any quality window) exits 0, run the full "
        "warm-context validator from the "
        "phase preamble, read its complete unfiltered report, repair every ERROR, and rerun it "
        "until clean. Do not pipe validator output through grep/head and do not install missing "
        "dependencies from inside the worker.",
        f"BEFORE the full validator: {final_validating}",
        f"If the full validator fails: {final_repairing}",
        f"ONLY after the full validator exits 0: {final_complete}",
    ]
    writable_handoffs = (handoffs if pending_ids is None
                         else [handoffs[ids.index(sid)] for sid in assigned])
    return "\n".join(lines), writable_handoffs + [progress_path]


def wipe_sections(tid):
    """A resume that re-runs Phase 2 or earlier rebuilds the skeleton — sections on disk are
    the OLD run's output (possibly authored against no arc at all). Remove them, plus the
    split-mode resume manifest, so nothing downstream resumes on trash. Returns how many
    section dirs were removed."""
    sec = os.path.join(REPO, "tomes", tid, "sections")
    n = len([d for d in (os.listdir(sec) if os.path.isdir(sec) else [])
             if os.path.isdir(os.path.join(sec, d))])
    if os.path.isdir(sec):
        shutil.rmtree(sec)
    try:
        os.remove(_sections_done_path(tid))
    except OSError:
        pass
    clear_section_progress(tid)
    reset_handoffs(tid)
    return n


def _author_batch(chain, ri, prompt, batch_ids, num, cfg, overrides,
                  ping, dead, cap, ask_on_death, interactive, tome_id, batch_root,
                  writable_paths, preflighted):
    """Run one warm batch with liveness and provider fallback.

    A replacement provider resumes the same bounded batch from its per-section disk
    checkpoints. The command shape is deliberately provider-neutral: Claude, Codex, AGY,
    and OpenCode all receive one ordinary headless prompt and need no resume/compact flag.
    """
    label = ", ".join(batch_ids)
    while True:
        name, cmd, im = chain[ri]
        worker_env = validation_subprocess_env(os.path.basename(batch_root))
        worker_env["ARCANUM_REPO_ROOT"] = REPO
        worker_env["ARCANUM_TOME_ROOT"] = batch_root
        worker_env["ARCANUM_SECTION_BATCH"] = ",".join(batch_ids)
        # Avoid harmless __pycache__ write attempts when a worker executes trusted Python
        # elsewhere in the read-only repository.
        worker_env["PYTHONDONTWRITEBYTECODE"] = "1"
        scoped = scoped_runner_command(name, cmd, batch_root, writable_paths, REPO)
        # A runner selected after a death (human choice or implicit default) was not present
        # during the build's initial census. Never let it start authoring without Phase 0.
        if tuple(cmd) not in preflighted:
            preflight_runners([(name, scoped, im)])
            preflighted.add(tuple(cmd))
        rc = run_agent(scoped, im, prompt, ping, dead, cap,
                       cwd=batch_root, env=worker_env)
        if rc == 0:
            return ri, True
        reason = "hung/timeout" if rc == 124 else f"exit {rc}"
        print(f"  ! warm batch {label}: runner {name} exited {rc}"
              + (" (hung/timeout)" if rc == 124 else ""))
        nxt = chain[ri + 1] if ri + 1 < len(chain) else None
        if nxt is None and (ask_on_death or interactive):
            nxt, _ = request_runner(tome_id, num, name, reason, interactive)
            if nxt is not None:
                chain.append(nxt)
        elif nxt is None:
            imp = _implicit_fallback(cfg, overrides, chain[ri])
            if imp and imp[0][1] not in [c[1] for c in chain]:
                chain.append(imp[0])
                nxt = imp[0]
        if nxt is None:
            return ri, False
        ri += 1
        print(f"  ⇒ continuing warm batch {label} on {chain[ri][0]}")


# Which sections Phase 3 has finished, persisted so a resume skips them without re-running a
# worker. Recorded per section on a clean exit; the id is the FINAL tome id, since Phase 3 runs
# after the Phase-2 rename. This is the reliable completion signal — file content can't be trusted
# (authored exercises legitimately contain `# TODO:` fill-in markers, so a placeholder sweep gives
# false "stub" hits). Lesson-level continuation inside the one interrupted section is delegated to
# the worker: it reads what's on disk, keeps the finished lessons, and authors the rest.
def _sections_done_path(tid):
    return os.path.join(BUILD_DIR, f"{tid}.sections-done")


def _load_sections_done(tid):
    try:
        with open(_sections_done_path(tid), encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def _mark_section_done(tid, sid):
    done = _load_sections_done(tid)
    done.add(sid)
    try:
        with open(_sections_done_path(tid), "w", encoding="utf-8") as f:
            json.dump(sorted(done), f)
    except OSError:
        pass


def author_sections_split(tid, num, title, chain, refs, cfg, overrides,
                          ping, dead, cap, ask_on_death, interactive, tome_id, resume=False,
                          preflighted=None, batch_size=SECTION_BATCH_SIZE):
    """Author Arc-ordered sections in bounded warm batches.

    Each worker must finish and self-validate every assigned section before moving to the
    next one. The harness independently repeats each gate, checkpoints clean sections, and
    retries only failures. A resume therefore skips clean work without relying on a provider
    session database. Returns the active runner-chain index after the final batch.
    """
    plan_rel, verdict_rel, findings_rel = refs
    plan_path = os.path.join(REPO, plan_rel)
    tooling = read_tooling(plan_path)
    worker_body = support_prompt("section-author")
    preflighted = preflighted if preflighted is not None else set()
    ids = section_ids(tid)
    done = _load_sections_done(tid) if resume else set()
    batch_size = max(1, int(batch_size or SECTION_BATCH_SIZE))
    batches = [ids[start:start + batch_size] for start in range(0, len(ids), batch_size)]
    print(f"  · split-sections: {len(ids)} sections, {len(batches)} warm batch(es) of up to "
          f"{batch_size} — {', '.join(ids)}"
          + (f"  (resume: {len(done)} already done)" if resume and done else ""))
    ri = 0
    tome_root = os.path.join(REPO, "tomes", tid)
    positions = {sid: i for i, sid in enumerate(ids)}
    for batch_number, batch in enumerate(batches, 1):
        pending, handoffs = [], {}
        for sid in batch:
            i = positions[sid]
            handoff = prepare_handoff(tid, sid, reset=not resume, ids=ids,
                                      plan_path=plan_path)
            handoffs[sid] = handoff
            handoff_clean, _ = validate_handoff(tid, sid, ids, plan_path)
            if sid in done and handoff_clean:
                print(f"    · section {sid} [{i + 1}/{len(ids)}] already authored — skipping (resume)")
                continue
            if sid in done:
                print(f"    · section {sid} [{i + 1}/{len(ids)}] content is checkpointed, but its "
                      "continuity handoff is missing/invalid — rebuilding the handoff")
            section_dir = os.path.join(tome_root, "sections", sid)
            os.makedirs(section_dir, exist_ok=True)
            pending.append(sid)
        if not pending:
            continue

        attempts = 0
        reports = {}
        while pending:
            first = positions[pending[0]] + 1
            last = positions[pending[-1]] + 1
            verb = "resuming" if resume or attempts else "authoring"
            write_section_progress(
                tid, pending[0], first, len(ids),
                "repairing" if reports else "authoring", batch_number, len(batches))
            print(f"    · {verb} warm batch {batch_number}/{len(batches)} "
                  f"[{first}-{last}/{len(ids)}] {', '.join(pending)} on {chain[ri][0]}")

            checks = [section_validator_shell_command(tid, sid, tooling, plan_rel)
                      for sid in pending]
            combined_check = " && ".join(f"({command})" for command in checks)
            focus = (f"\n\n===== WARM SECTION BATCH {batch_number} OF {len(batches)} =====\n"
                     f"You own exactly these sections, in this order: {', '.join(pending)}. "
                     "Complete ONE section at a time. For each: preserve any fully correct work "
                     "already on disk, author its brief, lessons/exercises, and freestyle, finish "
                     "its exact handoff, run that section's validator shown below, and fix it until "
                     "it exits 0 BEFORE moving to the next section. After writing an earlier section "
                     "in this same batch, reopen its files and handoff before authoring the next; the "
                     "warm context is useful, but the files remain the source of truth. Do not spawn "
                     "subagents and do not edit a section outside this list.\n")
            continuity_blocks = []
            for sid, check in zip(pending, checks):
                i = positions[sid]
                authoring_progress = section_progress_shell_command(
                    tid, sid, i + 1, len(ids),
                    "repairing" if reports else "authoring", batch_number, len(batches))
                validating_progress = section_progress_shell_command(
                    tid, sid, i + 1, len(ids), "validating", batch_number, len(batches))
                complete_progress = section_progress_shell_command(
                    tid, sid, i + 1, len(ids), "complete", batch_number, len(batches))
                previous = (f"Read section {ids[i - 1]} plus any older canonical owner reused here."
                            if i else "This is the first section and opens the course.")
                focus += (f"\n--- {sid} ({i + 1} of {len(ids)}) ---\n{previous}\n"
                          "Mandatory live progress markers (run each at the stated transition):\n"
                          f"  BEFORE editing: {authoring_progress}\n"
                          f"  BEFORE its gate: {validating_progress}\n"
                          f"  AFTER its gate exits 0: {complete_progress}\n"
                          f"Write only tomes/{tid}/sections/{sid}/ and its supplied handoff.\n"
                          "Warm-context code gate (executes this section's snippets/write labs; "
                          f"must exit 0 before the next section):\n  {check}\n")
                continuity_blocks.append(continuity_prompt(tid, sid, ids, plan_path))

            writable = [os.path.join(tome_root, "sections", sid) for sid in pending]
            writable += [handoffs[sid] for sid in pending]
            writable.append(section_progress_path(tid))
            boundary = (f"\n\n===== BATCH WORKER SECURITY BOUNDARY =====\n"
                        f"The repository root is {REPO}; the process cwd is {tome_root}. The only "
                        f"writable section directories are {', '.join(writable[:len(pending)])}. "
                        "The only other writable project files are their exact continuity handoffs "
                        "and the harness-owned live section-progress marker. "
                        "You may read the whole repository, execute trusted repository Python, and "
                        "use WebSearch/WebFetch. The plan and every other section are read-only.")
            repair = ""
            if reports:
                repair = "\n\n===== BATCH GATES STILL FAIL =====\n"
                for sid in pending:
                    repair += f"\n--- {sid} blockers ---\n{blocking_report(reports.get(sid, ''))}\n"
            prompt = (build_prompt(
                tid, num, title, worker_body, plan_rel, verdict_rel, findings_rel,
                tooling=tooling, validation_run=False, repair_only=bool(reports),
                validation_command=combined_check)
                + focus + "".join(continuity_blocks) + boundary + repair)

            ri, ok = _author_batch(
                chain, ri, prompt, pending, num, cfg, overrides, ping, dead, cap,
                ask_on_death, interactive, tome_id, tome_root, writable, preflighted)
            if not ok:
                break

            failed, reports = [], {}
            for sid in pending:
                i = positions[sid]
                write_section_progress(tid, sid, i + 1, len(ids), "validating",
                                       batch_number, len(batches))
                clean, report = validate_section(tid, sid, tooling, plan_rel)
                if clean:
                    _mark_section_done(tid, sid)
                    write_section_progress(tid, sid, i + 1, len(ids), "complete",
                                           batch_number, len(batches))
                    print(f"    ok section {sid}: checkpointed")
                else:
                    write_section_progress(tid, sid, i + 1, len(ids), "repairing",
                                           batch_number, len(batches))
                    failed.append(sid)
                    reports[sid] = report
            if not failed:
                break
            attempts += 1
            if attempts > retries_for(chain[ri][0]):
                print(f"    ! warm batch {', '.join(failed)}: validator still fails after "
                      f"{attempts} repair attempt(s); leaving it uncheckpointed for recovery")
                break
            print(f"    x warm batch gates failed for {', '.join(failed)} -> focused repair "
                  f"(attempt {attempts + 1})")
            pending = failed
    return ri
