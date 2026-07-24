"""The Binder: scoped amendment execution behind explicit job/process services."""
import os
import re
import subprocess
import sys
import time

from ..config import BUILD_DIR, ROOT
from ..jobs import JobManager, ProcessStore
from ..ai import AiRequest, AiService
from ..forge import notify
from ..platform.agent_scratch import remove as remove_agent_scratch
from ..platform.permission_profiles import profile_paths
from .amendment import storage as amendment_storage
from .amendment.activity import activity_rows as _activity_rows
from .amendment.runner import (
    activity_summary as _activity_summary,
    failure_summary as _failure_summary,
    run_agent_turn,
)

AMEND_TIMEOUT = 900  # seconds for one small-change agent run


# An amend job lives in the configured JobStore, so a server restart (or the runner
# dying from lost usage) loses it. We also mirror the essentials to disk so the Binder
# can offer to resume a cut-short amendment. One file per tome — only one amend runs per
# tome at a time. Written running on start; cleared on success/cancel; left on error or a
# server-death-mid-run (status stays "running" on disk, but its id is no live job).
def _amend_state_path(tome):
    return amendment_storage.amend_state_path(BUILD_DIR, tome)


def save_amend_state(st):
    amendment_storage.save_amend_state(BUILD_DIR, st)


def load_amend_state(tome):
    return amendment_storage.load_amend_state(BUILD_DIR, tome)


def clear_amend_state(tome):
    amendment_storage.clear_amend_state(BUILD_DIR, tome)


def _review_metadata_path(report_rel):
    return amendment_storage.review_metadata_path(ROOT, report_rel)


def _save_review_metadata(report_rel, metadata):
    amendment_storage.save_review_metadata(ROOT, report_rel, metadata)


def review_history(tome, report_path=""):
    """List or load Binder review reports for one active tome."""
    return amendment_storage.review_history(ROOT, tome, report_path)


def _checkpoint_path(jid):
    return amendment_storage.checkpoint_path(BUILD_DIR, jid)


def checkpoint_tome(jid):
    """Copy authored content to a bounded recovery sidecar; never mutate Git state."""
    amendment_storage.checkpoint_tome(ROOT, BUILD_DIR, jid)


def clear_checkpoint(jid):
    amendment_storage.clear_checkpoint(BUILD_DIR, jid)


def rollback_tome(jid):
    """Restore authored content from the sidecar while preserving learner save data."""
    amendment_storage.rollback_tome(ROOT, BUILD_DIR, jid)


def tome_has_changes(jid):
    """Compare authored files against the bounded pre-run checkpoint."""
    return amendment_storage.tome_has_changes(ROOT, BUILD_DIR, jid)


def _mark_amend_state(tome, status):
    st = load_amend_state(tome)
    if st:
        st["status"] = status
        save_amend_state(st)


def _review_verdict(report):
    return amendment_storage.review_verdict(report)


def _run_agent_turn(job_id, cmd, prompt, input_mode, env, cwd, provider_kind,
                    provider_model,
                    job_manager: JobManager, processes: ProcessStore):
    return run_agent_turn(
        job_id, cmd, prompt, input_mode, env, cwd, provider_kind,
        provider_model, job_manager, processes, timeout=AMEND_TIMEOUT)


def _validate_amendment(jid, *, strict=False):
    command = [
        sys.executable, os.path.join(ROOT, "tools", "validate_tome.py"),
        os.path.join("tomes", jid),
    ]
    if strict:
        command.append("--strict")
    return subprocess.run(
        command, capture_output=True, text=True,
        timeout=900, cwd=ROOT)


def run_amender(job_id, jid, request_text, kind, model, effort="", broad=False, iterate=False, reset_ok=False,
                review=False, review_path="", update_standard=False,
                job_manager: JobManager | None = None,
                processes: ProcessStore | None = None, ai: AiService | None = None):
    """Background worker: a headless CLI edits tomes/<jid>/ under the configuration
    guide, then validate_tome.py checks it and may trigger one bounded repair turn.
    The agent edits with whatever file tools its CLI has (codex reads/edits THROUGH
    shell, so the prompt must never ban shell outright — gpt-5.6 obeys the ban
    literally and aborts unable to read a single file); the server runs the validator.
    broad=True lets it make a larger, multi-file rework instead of the smallest edit.
    iterate=True (implies broad): survey the tome against course-improvement-guide.md
    and apply the highest-value improvements; request_text is an optional focus.
    reset_ok=True: the player accepts a progress wipe, so the agent may restructure —
    add/remove/reorder/renumber sections and lessons, rename ids and files.
    review=True: read-only survey — the agent writes a findings report to reviews/
    and changes nothing else; request_text is an optional focus. review_path names a
    prior report the agent should read before making a change the player commissioned.
    update_standard=True (broad changes only): also bring the tome into line with the
    repository's current validator and Markdown authoring instructions."""
    if job_manager is None or processes is None or ai is None:
        raise RuntimeError("Binder requires explicit job, process, and AI services")
    checkpointed = False
    req = request_text[:4000]
    update_standard = bool(update_standard and broad and not review)
    report_rel = os.path.join("reviews", f"{jid}-{time.strftime('%Y%m%d-%H%M%S')}.md") if review else ""
    standard_instruction = (
        "\n\nSTANDARD UPDATE: Compare this tome with the CURRENT repository standards: the "
        "validator implementation used by tools/validate_tome.py and all applicable Markdown "
        "authoring instructions at the repository root and under tome-authoring/. Bring forward "
        "any file versions, fields, structures, or instructions that have changed since this tome "
        "was authored. Use the current validator and current Markdown instructions as authoritative. "
        "Make only the compatibility changes actually needed; if the tome is already current in a "
        "given regard, leave it unchanged in that regard. Do not rewrite correct content merely for "
        "style. Never add or partially imitate an opt-in contract such as [mastery] evidenceVersion "
        "when the tome does not already declare it. Do not relax any progress-preservation boundary "
        "below.\n\n"
        if update_standard else "")
    validation_command = (
        f"`python3 tools/validate_tome.py tomes/{jid} --strict`"
        if update_standard else
        f"`python3 tools/validate_tome.py tomes/{jid}`")
    # what the agent may and may not touch. reset_ok lifts ONLY the progress-preserving rules
    # (rename/restructure); the engine/other-tome/generated walls always hold.
    if reset_ok:
        bounds = (f"EDIT only under tomes/{jid}/ (READING anything in the repo is expected — the guides "
                  "live at the root). The player has AUTHORIZED a progress-resetting rework for this "
                  "run: you MAY add, remove, reorder, and renumber sections and lessons and rename ids or "
                  "files as the change needs — this OVERRIDES the guides' rule against renaming ids/files. "
                  "Keep the tome internally consistent (fix every cross-reference, the tome.toml section "
                  "list, badges, and chapter numbers you move). You must STILL never touch engine code, "
                  "skins/, or other tomes, and never edit save/ or hand-edit generated/. A trusted "
                  "repository generator may update its own generated output when an in-scope source "
                  "change requires it; inspect and validate that output.")
    else:
        bounds = (f"EDIT only under tomes/{jid}/ (READING anything in the repo is expected — the guides "
                  "live at the root). Progress is keyed by ids, so ADDING content with new "
                  "tome-unique ids is always allowed and progress-safe — new exercises, new lessons "
                  "(the next lNN.toml), even a new section APPENDED to the end of [content].sections "
                  "with its full kit. But never rename, renumber, remove, or reorder EXISTING ids or "
                  "files (that wipes player progress), never insert a section mid-list, never touch "
                  "engine code, skins/, or other tomes, never edit save/ or hand-edit generated/. "
                  "A trusted repository generator may update its own generated output when an in-scope "
                  "source change requires it; inspect and validate that output.")
    if review:
        focus = f"The player asks the review to focus especially on:\n\n{req}\n\n" if req else ""
        prompt = (
            "You are THE BINDER — a maintenance agent for the Arcanum course platform, in "
            f"REVIEW mode on the course (tome) at tomes/{jid}/.\n\n"
            "FIRST read BOTH guides at the repo root: course-configuration-guide.md (the file/"
            "field map and hard rules) and course-improvement-guide.md (the rubric for what makes "
            f"a tome strong and where weaknesses hide). Then survey tomes/{jid}/ against them and "
            "write a well-organized markdown report of everything you find — flaws, weak spots, "
            f"inconsistencies, and the changes you would recommend, most important first. {focus}"
            "After the title and brief review metadata, the FIRST substantive section MUST be "
            "`## Recommendation and implementation order`. Make that one section self-contained: "
            "state the tome's important strengths and validator status without letting a clean "
            "validator minimize substantive weaknesses; name EVERY material recommended workstream "
            "(all Critical and High findings, plus any Medium or Low work that belongs in the plan); "
            "and give one numbered, dependency-aware implementation order. Rank learner privacy, "
            "correctness, teaching integrity, and valid assessment evidence above compatibility or "
            "cosmetic conservatism. Recommend broad correction when the evidence warrants it. "
            "Progress-safety constraints should shape implementation, not suppress or downgrade a "
            "real finding. Do not split the overall recommendation into a later `Top findings`, "
            "`Recommended implementation order`, or closing-summary section. In the detailed "
            "findings below it, label finding-specific actions `Remediation`, never `Recommended "
            "change`, so they cannot be mistaken for the report's overall recommendation. "
            f"Write that report to {report_rel} (create the folder if needed) — that report is the "
            "ONLY file you may create or change. Do NOT edit anything else: no course files, no "
            "engine code, nothing under tomes/. Read files with whatever tools your harness provides "
            "(shell reads are fine where shell is your file interface); trusted repository Python "
            "tools may be executed when they help verify a finding.")
    elif iterate:
        focus = f"The player asks you to focus especially on:\n\n{req}\n\n" if req else ""
        prompt = (
            "You are THE BINDER — a maintenance agent for the Arcanum course platform, in "
            f"ITERATE mode on the course (tome) at tomes/{jid}/.\n\n"
            "FIRST read course-improvement-guide.md and course-configuration-guide.md. Follow the "
            "improvement guide's conditional reference routing and consult the relevant tome-authoring/ "
            f"documents for the fields and contracts you touch. Then survey tomes/{jid}/ against the rubric, "
            "choose the HIGHEST-VALUE improvements you can make, and apply them, editing as many "
            f"files as it takes. {focus}{standard_instruction}"
            f"{bounds} Read and edit files with whatever tools your harness provides — if shell "
            "commands are how you read or edit files, use them freely; you may also run trusted "
            "repository Python validators and inspection tools. "
            f"Before returning, run {validation_command}, read the complete "
            "report, and repair it until it exits cleanly with no new warnings. The harness repeats "
            "that check independently after you return. "
            "End with one short paragraph naming exactly the file(s) you changed and what you improved.")
    else:
        ask = ("requests a broad change — a larger rework you can iterate on"
               if broad else "requests one small change")
        how = ("make the changes needed to fulfil the request, editing as many files as it takes"
               if broad else "make the SMALLEST edit that fulfils the request")
        ledger = (f"A review of this tome was just written to {review_path} — read it first; "
                  "the request may refer to its findings.\n\n" if review_path else "")
        prompt = (
            "You are THE BINDER — a maintenance agent for the Arcanum course platform. "
            f"The player of the course (tome) at tomes/{jid}/ {ask}:\n\n"
            f"REQUEST: {req}\n\n{ledger}"
            "If the request is actually a QUESTION — asking for information, an explanation, or "
            "advice, rather than instructing a change — answer it in your final message and make "
            "NO edits to the tome. Only proceed to change files if the request asks for a change.\n\n"
            "FIRST read course-configuration-guide.md at the repo root — it maps every file and "
            f"field you may touch and the rules that bind them. Then {how}. {standard_instruction}"
            f"{bounds} Read and edit files with whatever tools your harness provides — if shell "
            "commands are how you read or edit files, use them freely; you may also run trusted "
            "repository Python validators and inspection tools. Before returning, run "
            f"{validation_command}, read the complete report, and repair it "
            "until it exits cleanly with no new warnings; the harness repeats the check independently. End with one "
            "short paragraph naming exactly the file(s) and field(s) you changed.")
    prompt += (f"\n\nAI ACCESS: The repository root is {ROOT}. You may read files and execute trusted "
               "Python anywhere in this repository, use web search/fetch for current sources, and "
               "use /tmp freely. Project writes are enforced by the harness: "
               + (f"only {report_rel} is writable for this review."
                  if review else f"the complete tome at tomes/{jid}/ is writable; other project paths are read-only."))
    try:
        tome_root = os.path.join(ROOT, "tomes", jid)
        if review:
            report_abs = os.path.join(ROOT, report_rel)
            os.makedirs(os.path.dirname(report_abs), exist_ok=True)
            open(report_abs, "a", encoding="utf-8").close()
            writable = [report_abs]
        else:
            writable = [tome_root]
        invocation = ai.invocation(kind, AiRequest(
            role="binder-review" if review else "binder-amend",
            model=model, input=prompt, timeout=AMEND_TIMEOUT, workspace=tome_root,
            allowed_tools=("read", "write", "shell"), web_allowed=True,
            effort=effort, writable_paths=tuple(writable),
            trace={"jobId": job_id, "tome": jid},
            permission_paths=profile_paths(
                "binder", build_id=job_id, tome_id=jid, phase=7),
            state_scope={
                "build_id": job_id,
                "role": "binder-review" if review else "binder-amend",
                "phase": 7,
                "section": "",
            },
            stream_events=True))
        cmd, input_mode = list(invocation.argv), invocation.input_mode
        if not review:  # review edits nothing under tomes/ — no checkpoint needed
            checkpoint_tome(jid)
            checkpointed = True
        rc, timed_out, logtail = _run_agent_turn(
            job_id, cmd, prompt, input_mode, invocation.environment,
            invocation.cwd, kind, model, job_manager, processes)
        if job_manager.status(job_id).get("status") == "cancelled":
            clear_amend_state(jid)  # the player stayed the quill; nothing to resume
            if checkpointed:
                rollback_tome(jid)  # discard the half-finished edit
                checkpointed = False
            return  # the kill is not an error
        if timed_out:
            raise RuntimeError(
                f"timed out after {AMEND_TIMEOUT}s: {_failure_summary(logtail)}")
        if rc != 0:
            raise RuntimeError(f"exit {rc}: {_failure_summary(logtail)}")
        summary = _activity_summary(
            job_manager, job_id, "The Binder completed its turn without a final message.")
        if review:  # nothing was edited, so no validator — the report IS the result
            report_abs = os.path.join(ROOT, report_rel)
            if not os.path.isfile(report_abs):  # the hand spoke but never inked the ledger — keep its words
                os.makedirs(os.path.dirname(report_abs), exist_ok=True)
                with open(report_abs, "w", encoding="utf-8") as f:
                    f.write(summary + "\n")
            with open(report_abs, encoding="utf-8") as f:
                report = f.read().strip()
            completed = job_manager.update(
                job_id, status="done", summary=_review_verdict(report) or summary,
                reportPath=report_rel, validatorOk=True)
            _save_review_metadata(report_rel, {
                "version": 1,
                "tome": jid,
                "path": report_rel,
                "completedAt": time.time(),
                "providerKind": kind,
                "providerModel": model,
                "effort": effort,
                "usage": completed.get("usage"),
                "apiCostEstimate": completed.get("apiCostEstimate"),
            })
            clear_amend_state(jid)
            notify("✓ The Binder's survey is done",
                   f"The review of {jid} is inked at {report_rel} — open the Binder to commission changes.")
            return
        if not tome_has_changes(jid) and not update_standard:
            # The request may have been a question, or the requested state already held.
            # Do not turn an unrelated pre-existing validator finding into an unsolicited edit.
            job_manager.update(job_id, status="done", summary=summary,
                               validator="No tome files changed.", validatorOk=True)
            clear_checkpoint(jid)
            checkpointed = False
            clear_amend_state(jid)
            return
        job_manager.append(
            job_id, "log",
            "── the hand rests; the candle now inspects the work (validator — a few minutes) ──",
            limit=400)
        job_manager.append(
            job_id, "activity",
            {"kind": "harness", "at": time.time(),
             "text": "The hand rests; the validator now inspects the work."},
            limit=200)
        v = _validate_amendment(jid, strict=update_standard)
        if v.returncode != 0:
            report = (v.stdout + v.stderr).strip()
            job_manager.append(
                job_id, "log",
                "── exact validator report returned to the hand; one repair turn begins ──",
                limit=400)
            job_manager.append(
                job_id, "activity",
                {"kind": "harness", "at": time.time(),
                 "text": "The validator found flaws. A bounded repair turn has begun."},
                limit=200)
            repair_prompt = (prompt + "\n\n===== HARNESS REPAIR TURN =====\n"
                             "The independent validator failed. Read every finding below, repair "
                             "all in-scope failures without undoing the requested amendment, rerun "
                             "the validator yourself until clean, then stop.\n\n" + report)
            rc, timed_out, logtail = _run_agent_turn(
                job_id, cmd, repair_prompt, input_mode, invocation.environment,
                invocation.cwd, kind, model,
                job_manager, processes)
            cancelled = job_manager.status(job_id).get("status") == "cancelled"
            if cancelled:
                clear_amend_state(jid)
                rollback_tome(jid)
                checkpointed = False
                return
            if timed_out:
                raise RuntimeError(
                    f"repair timed out after {AMEND_TIMEOUT}s: "
                    f"{_failure_summary(logtail)}")
            if rc != 0:
                raise RuntimeError(
                    f"repair exit {rc}: {_failure_summary(logtail)}")
            summary = _activity_summary(
                job_manager, job_id, "The Binder completed its repair turn.")
            v = _validate_amendment(jid, strict=update_standard)
        if update_standard and v.returncode != 0:
            report = (v.stdout + v.stderr).strip()
            raise RuntimeError(
                "strict standard validator still fails after the repair turn; "
                "the amendment cannot pass:\n" + report[-4000:])
        job_manager.append(
            job_id, "log",
            ("── the candle is satisfied: the work holds (validator passed) ──"
             if v.returncode == 0 else
             "── the candle gutters: the validator found flaws (see its report below) ──"),
            limit=400)
        job_manager.append(
            job_id, "activity",
            {"kind": "harness", "at": time.time(),
             "text": ("The validator passed."
                      if v.returncode == 0 else
                      "The validator finished with findings.")},
            limit=200)
        job_manager.update(job_id, status="done", summary=summary,
                           validator=(v.stdout + v.stderr).strip()[-2000:],
                           validatorOk=v.returncode == 0)
        clear_checkpoint(jid)
        checkpointed = False
        clear_amend_state(jid)  # the run finished; the edit is on disk, nothing to resume
        if broad:  # broad runs are long/unattended — ping the operator on the outcome
            if v.returncode == 0:
                notify("✓ The Binder finished", f"Broad change to {jid} is done — reopen the tome to see it.")
            else:
                notify(f"⚠ The Binder needs you — {jid}",
                       "The broad change finished but the validator found flaws. Open the Binder to mend them.", priority=1)
    except Exception as e:
        recovery_error = ""
        if checkpointed:
            try:
                rollback_tome(jid)  # a half-finished tome is worse than none
            except Exception as rollback_error:
                recovery_error = f"\n\nCheckpoint recovery also failed: {rollback_error}"
        stopped = job_manager.status(job_id).get("status") == "running"
        if stopped:
            job_manager.update(
                job_id, status="error",
                error=(str(e)[:800] +
                       ("\n\nThe tome was restored to its pre-Binder checkpoint."
                        if checkpointed and not recovery_error else recovery_error)))
        if stopped:
            _mark_amend_state(jid, "error")  # left on disk so the Binder can offer to resume it
        if stopped:  # a real failure/timeout, not a user cancel — you may be away, so ping to retry
            # Brief on purpose: the full error stays in the job for the Binder's bench.
            cause = (str(e).splitlines() or ["unknown error"])[0][:120]
            notify(f"✗ The Binder stopped — {jid}",
                   f"{cause} — the tome was rolled back. Reopen the Binder to retry, or pick a different hand.",
                   priority=1)
    finally:
        # Binder retries start a fresh job rather than resuming a provider session. Remove
        # this job's isolated CLI state so no tome transcript or scratch survives the run.
        try:
            remove_agent_scratch(job_id)
        except OSError:
            pass
