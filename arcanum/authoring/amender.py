"""The Binder: scoped amendment execution behind explicit job/process services."""
import os
import time

from ..config import BUILD_DIR, ROOT
from ..jobs import JobManager, ProcessStore
from ..ai import AiRequest, AiService
from ..forge import notify
from ..platform.agent_scratch import remove as remove_agent_scratch
from ..platform.permission_profiles import profile_paths
from .amendment import gate
from .amendment import prompts
from .amendment import storage as amendment_storage
from .amendment.activity import activity_rows as _activity_rows
from .amendment.runner import (
    activity_summary as _activity_summary,
    failure_summary as _failure_summary,
    run_agent_turn,
)

# A broad whole-tome remediation is hours of honest work, so nothing here is bounded by
# how long the Binder takes. AMEND_STALL ends a turn that is provably doing nothing; the
# far-off AMEND_TIMEOUT only catches a CLI wedged while still holding its connection open.
AMEND_STALL = 300  # seconds of no CPU, no provider connection, and no output
AMEND_TIMEOUT = 4 * 3600  # backstop ceiling for one turn
AMEND_CONTINUATIONS = 3  # times a cut-short turn is resumed from the work already on disk


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
    """Run one turn, taking it up again in place when the CLI dies before finishing.

    The Binder edits the tome directly, so a turn cut short leaves real, paid-for work
    on disk. Failing the job at that point throws the work away and buys it twice. The
    continuation reads what is already there instead, so a long amendment finishes
    across as many turns as it needs.
    """
    text = prompt
    for attempt in range(AMEND_CONTINUATIONS + 1):
        rc, cut_short, logtail = run_agent_turn(
            job_id, cmd, text, input_mode, env, cwd, provider_kind,
            provider_model, job_manager, processes,
            timeout=AMEND_TIMEOUT, stall=AMEND_STALL)
        if (rc == 0 and not cut_short) or attempt == AMEND_CONTINUATIONS \
                or job_manager.status(job_id).get("status") == "cancelled":
            return rc, cut_short, logtail
        why = (f"it went idle for {AMEND_STALL}s with no CPU and no provider connection"
               if cut_short else f"the CLI exited {rc}: {_failure_summary(logtail)}")
        job_manager.append(
            job_id, "log", f"── the hand faltered ({why}); it takes the work up again ──",
            limit=400)
        job_manager.append(
            job_id, "activity",
            {"kind": "harness", "at": time.time(),
             "text": f"The turn ended early ({why}). Continuing from the work already on disk "
                     f"— attempt {attempt + 2} of {AMEND_CONTINUATIONS + 1}."},
            limit=200)
        text = prompts.continuation(prompt, why)


def _validate_amendment(jid, *, strict=False):
    return gate.validate_amendment(jid, strict=strict)


def _note(job_manager, job_id, text):
    job_manager.append(job_id, "log", f"── {text} ──", limit=400)
    job_manager.append(
        job_id, "activity",
        {"kind": "harness", "at": time.time(), "text": text}, limit=200)


def _record_amendment(job_manager, job_id, jid, started, mode):
    """Write what this run did where a server restart cannot take it.

    The job store is in memory. Twice now the question "did it retry, and what did that
    cost?" has been unanswerable an hour later, so the answer goes on disk beside the
    tome. The continuation count is read back out of the activity the run already
    published rather than threaded through every call -- same fact, no new plumbing.
    """
    st = job_manager.status(job_id) or {}
    rows = st.get("activity") or []
    amendment_storage.save_amend_record(BUILD_DIR, jid, {
        "version": 1,
        "tome": jid,
        "jobId": job_id,
        "startedAt": started,
        "finishedAt": time.time(),
        "mode": mode,
        "status": st.get("status", "unknown"),
        "continuations": sum(
            1 for row in rows
            if str(row.get("text", "")).startswith("The turn ended early")),
        "summary": str(st.get("summary") or "")[:2000],
        "error": str(st.get("error") or "")[:2000],
        "validatorOk": st.get("validatorOk"),
        "validator": str(st.get("validator") or "")[:8000],
        "usage": st.get("usage"),
        "apiCostEstimate": st.get("apiCostEstimate"),
    })


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
    started = time.time()
    req = request_text[:4000]
    update_standard = bool(update_standard and broad and not review)
    report_rel = os.path.join("reviews", f"{jid}-{time.strftime('%Y%m%d-%H%M%S')}.md") if review else ""
    # Contracts first: the handoff files have to exist before the sandbox is built, or the
    # profile drops a mount that points at nothing and the Binder cannot write them at all.
    contract_notes, contract_error = ([], "") if review else gate.sync_contracts("adopt", jid)
    handoffs = "" if review else gate.handoff_dir(jid)
    prompt = prompts.amend_prompt(
        jid, req, review=review, iterate=iterate, broad=broad, reset_ok=reset_ok,
        update_standard=update_standard, review_path=review_path,
        report_rel=report_rel, plan_rel=gate.plan_rel(jid), handoffs=handoffs)
    try:
        tome_root = os.path.join(ROOT, "tomes", jid)
        if review:
            report_abs = os.path.join(ROOT, report_rel)
            os.makedirs(os.path.dirname(report_abs), exist_ok=True)
            open(report_abs, "a", encoding="utf-8").close()
            writable = [report_abs]
        else:
            writable = [tome_root] + ([handoffs] if handoffs else [])
        for line in contract_notes:
            _note(job_manager, job_id, f"the harness prepared the tome's contracts: {line}")
        if contract_error:
            # Not fatal: a tome with no build plan has no contracts to prepare, and that is
            # a fact about the tome, not a reason to refuse the amendment.
            _note(job_manager, job_id,
                  f"the tome's contracts could not be prepared: {contract_error[:300]}")
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
        rc, cut_short, logtail = _run_agent_turn(
            job_id, cmd, prompt, input_mode, invocation.environment,
            invocation.cwd, kind, model, job_manager, processes)
        if job_manager.status(job_id).get("status") == "cancelled":
            clear_amend_state(jid)  # the player stayed the quill; nothing to resume
            if checkpointed:
                rollback_tome(jid)  # discard the half-finished edit
                checkpointed = False
            return  # the kill is not an error
        if cut_short:
            raise RuntimeError(
                f"the hand stalled and {AMEND_CONTINUATIONS} continuation turns did not "
                f"finish the work: {_failure_summary(logtail)}")
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
        # An adopted map was only ever a photograph of the tome, so re-photograph it now that
        # the tome has legitimately changed. A PLANNED map is deliberately left alone: re-sealing
        # a promise to match whatever happened would make the promise unfalsifiable, so there the
        # drift stays a gate failure below and the repair turn (or a person) answers for it.
        resealed, reseal_error = gate.sync_contracts(
            "reseal", jid, reason=f"Binder job {job_id}: {req or 'requested amendment'}"[:200])
        for line in resealed:
            _note(job_manager, job_id, line)
        if reseal_error:
            _note(job_manager, job_id,
                  f"the course map could not be re-sealed: {reseal_error[:300]}")
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
            rc, cut_short, logtail = _run_agent_turn(
                job_id, cmd, prompts.repair(prompt, report), input_mode, invocation.environment,
                invocation.cwd, kind, model,
                job_manager, processes)
            cancelled = job_manager.status(job_id).get("status") == "cancelled"
            if cancelled:
                clear_amend_state(jid)
                rollback_tome(jid)
                checkpointed = False
                return
            if cut_short:
                raise RuntimeError(
                    f"the repair turn stalled and {AMEND_CONTINUATIONS} continuations "
                    f"did not finish it: {_failure_summary(logtail)}")
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
        if not review:  # a review already persists its own metadata beside the report
            _record_amendment(
                job_manager, job_id, jid, started,
                "iterate" if iterate else "broad" if broad else "small")
        # Binder retries start a fresh job rather than resuming a provider session. Remove
        # this job's isolated CLI state so no tome transcript or scratch survives the run.
        try:
            remove_agent_scratch(job_id)
        except OSError:
            pass
