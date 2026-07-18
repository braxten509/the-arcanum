"""The Binder: scoped amendment execution behind explicit job/process services."""
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time

from ..config import BUILD_DIR, ROOT
from ..jobs import JobManager, ProcessStore
from ..ai import AiRequest, AiService
from ..forge import ANSI_RE, notify

AMEND_TIMEOUT = 900  # seconds for one small-change agent run


# An amend job lives in the configured JobStore, so a server restart (or the runner
# dying from lost usage) loses it. We also mirror the essentials to disk so the Binder
# can offer to resume a cut-short amendment. One file per tome — only one amend runs per
# tome at a time. Written running on start; cleared on success/cancel; left on error or a
# server-death-mid-run (status stays "running" on disk, but its id is no live job).
def _amend_state_path(tome):
    return os.path.join(BUILD_DIR, f"{tome}.amend.json")


def save_amend_state(st):
    os.makedirs(BUILD_DIR, exist_ok=True)
    try:
        with open(_amend_state_path(st["tome"]), "w", encoding="utf-8") as f:
            json.dump(st, f)
    except OSError:
        pass


def load_amend_state(tome):
    try:
        with open(_amend_state_path(tome), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def clear_amend_state(tome):
    try:
        os.remove(_amend_state_path(tome))
    except OSError:
        pass


def _checkpoint_path(jid):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(jid or "")):
        raise ValueError("invalid tome id")
    return os.path.join(BUILD_DIR, "binder-checkpoints", jid)


def _tree_signature(root):
    rows = []
    for directory, names, files in os.walk(root):
        names[:] = sorted(name for name in names if name != "save")
        for name in sorted(files):
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, root)
            with open(path, "rb") as handle:
                rows.append((relative, handle.read()))
    return rows


def checkpoint_tome(jid):
    """Copy authored content to a bounded recovery sidecar; never mutate Git state."""
    source, checkpoint = os.path.join(ROOT, "tomes", jid), _checkpoint_path(jid)
    if os.path.isdir(checkpoint):
        shutil.rmtree(checkpoint)
    os.makedirs(os.path.dirname(checkpoint), exist_ok=True)
    shutil.copytree(source, checkpoint, ignore=shutil.ignore_patterns("save"))


def clear_checkpoint(jid):
    shutil.rmtree(_checkpoint_path(jid), ignore_errors=True)


def rollback_tome(jid):
    """Restore authored content from the sidecar while preserving learner save data."""
    target, checkpoint = os.path.join(ROOT, "tomes", jid), _checkpoint_path(jid)
    if not os.path.isdir(checkpoint):
        raise RuntimeError("Binder recovery checkpoint is missing")
    for name in os.listdir(target):
        if name == "save":
            continue
        path = os.path.join(target, name)
        shutil.rmtree(path) if os.path.isdir(path) and not os.path.islink(path) else os.remove(path)
    shutil.copytree(checkpoint, target, dirs_exist_ok=True)
    clear_checkpoint(jid)


def tome_has_changes(jid):
    """Compare authored files against the bounded pre-run checkpoint."""
    return _tree_signature(os.path.join(ROOT, "tomes", jid)) != _tree_signature(
        _checkpoint_path(jid))


def _mark_amend_state(tome, status):
    st = load_amend_state(tome)
    if st:
        st["status"] = status
        save_amend_state(st)


def _run_agent_turn(job_id, cmd, prompt, input_mode, env, cwd,
                    job_manager: JobManager, processes: ProcessStore):
    """Run one scoped Binder turn and stream it to the existing job log."""
    stdin_data = prompt if input_mode == "stdin" else None
    full_cmd = cmd + ([prompt] if input_mode == "arg" else [])
    p = subprocess.Popen(full_cmd,
                         stdin=(subprocess.DEVNULL if stdin_data is None else subprocess.PIPE),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                         env=env, cwd=cwd, start_new_session=True)
    processes.put(job_id, p)
    if stdin_data is not None:
        try:
            p.stdin.write(stdin_data)
            p.stdin.close()
        except BrokenPipeError:
            pass

    timed_out = {"v": False}

    def kill_timeout():
        timed_out["v"] = True
        processes.terminate(job_id, signal.SIGKILL)

    watchdog = threading.Timer(AMEND_TIMEOUT, kill_timeout)
    watchdog.start()

    def pump_output():
        for line in p.stdout:
            line = ANSI_RE.sub("", line.rstrip("\n"))
            try:
                job_manager.append(job_id, "log", line, limit=400)
            except KeyError:
                break

    pump = threading.Thread(target=pump_output, daemon=True)
    pump.start()
    try:
        rc = p.wait()
        pump.join(15)
        if pump.is_alive():
            processes.terminate_process(p, signal.SIGKILL)
            pump.join(5)
    finally:
        watchdog.cancel()
        processes.pop(job_id)
    logtail = list(job_manager.status(job_id).get("log", []))
    return rc, timed_out["v"], logtail


def _validate_amendment(jid):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "validate_tome.py"),
         os.path.join("tomes", jid)], capture_output=True, text=True,
        timeout=900, cwd=ROOT)


def run_amender(job_id, jid, request_text, kind, model, effort="", broad=False, iterate=False, reset_ok=False,
                review=False, review_path="", job_manager: JobManager | None = None,
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
    prior report the agent should read before making a change the player commissioned."""
    if job_manager is None or processes is None or ai is None:
        raise RuntimeError("Binder requires explicit job, process, and AI services")
    checkpointed = False
    req = request_text[:4000]
    report_rel = os.path.join("reviews", f"{jid}-{time.strftime('%Y%m%d-%H%M%S')}.md") if review else ""
    # what the agent may and may not touch. reset_ok lifts ONLY the progress-preserving rules
    # (rename/restructure); the engine/other-tome/generated walls always hold.
    if reset_ok:
        bounds = (f"EDIT only under tomes/{jid}/ (READING anything in the repo is expected — the guides "
                  "live at the root). The player has AUTHORIZED a progress-resetting rework for this "
                  "run: you MAY add, remove, reorder, and renumber sections and lessons and rename ids or "
                  "files as the change needs — this OVERRIDES the guides' rule against renaming ids/files. "
                  "Keep the tome internally consistent (fix every cross-reference, the tome.toml section "
                  "list, badges, and chapter numbers you move). You must STILL never touch engine code, "
                  "skins/, or other tomes, and never edit save/ or generated/.")
    else:
        bounds = (f"EDIT only under tomes/{jid}/ (READING anything in the repo is expected — the guides "
                  "live at the root). Progress is keyed by ids, so ADDING content with new "
                  "tome-unique ids is always allowed and progress-safe — new exercises, new lessons "
                  "(the next lNN.toml), even a new section APPENDED to the end of [content].sections "
                  "with its full kit. But never rename, renumber, remove, or reorder EXISTING ids or "
                  "files (that wipes player progress), never insert a section mid-list, never touch "
                  "engine code, skins/, or other tomes, never edit save/ or generated/.")
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
            f"Write that report to {report_rel} (create the folder if needed) — that report is the "
            "ONLY file you may create or change. Do NOT edit anything else: no course files, no "
            "engine code, nothing under tomes/. Read files with whatever tools your harness provides "
            "(shell reads are fine where shell is your file interface); trusted repository Python "
            "tools may be executed when they help verify a finding. End with one short paragraph "
            "summarizing your top findings.")
    elif iterate:
        focus = f"The player asks you to focus especially on:\n\n{req}\n\n" if req else ""
        prompt = (
            "You are THE BINDER — a maintenance agent for the Arcanum course platform, in "
            f"ITERATE mode on the course (tome) at tomes/{jid}/.\n\n"
            "FIRST read course-improvement-guide.md and course-configuration-guide.md. Consult the "
            "relevant parts of tome-authoring/3-chapters.md before changing lesson or exercise fields; "
            f"it is lookup material, not a mandatory full reread. Then survey tomes/{jid}/ against the rubric, "
            "choose the HIGHEST-VALUE improvements you can make, and apply them, editing as many "
            f"files as it takes. {focus}"
            f"{bounds} Read and edit files with whatever tools your harness provides — if shell "
            "commands are how you read or edit files, use them freely; you may also run trusted "
            "repository Python validators and inspection tools. "
            f"Before returning, run `python3 tools/validate_tome.py tomes/{jid}`, read the complete "
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
            f"field you may touch and the rules that bind them. Then {how}. "
            f"{bounds} Read and edit files with whatever tools your harness provides — if shell "
            "commands are how you read or edit files, use them freely; you may also run trusted "
            "repository Python validators and inspection tools. Before returning, run "
            f"`python3 tools/validate_tome.py tomes/{jid}`, read the complete report, and repair it "
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
            trace={"jobId": job_id, "tome": jid}))
        cmd, input_mode = list(invocation.argv), invocation.input_mode
        if not review:  # review edits nothing under tomes/ — no checkpoint needed
            checkpoint_tome(jid)
            checkpointed = True
        rc, timed_out, logtail = _run_agent_turn(
            job_id, cmd, prompt, input_mode, invocation.environment,
            invocation.cwd, job_manager, processes)
        if job_manager.status(job_id).get("status") == "cancelled":
            clear_amend_state(jid)  # the player stayed the quill; nothing to resume
            if checkpointed:
                rollback_tome(jid)  # discard the half-finished edit
                checkpointed = False
            return  # the kill is not an error
        if timed_out:
            raise RuntimeError(f"timed out after {AMEND_TIMEOUT}s:\n" + "\n".join(logtail[-20:]))
        if rc != 0:
            raise RuntimeError(f"exit {rc}:\n" + "\n".join(logtail[-20:]))
        summary = "\n".join(logtail)[-2000:].strip()
        if review:  # nothing was edited, so no validator — the report IS the result
            report_abs = os.path.join(ROOT, report_rel)
            if not os.path.isfile(report_abs):  # the hand spoke but never inked the ledger — keep its words
                os.makedirs(os.path.dirname(report_abs), exist_ok=True)
                with open(report_abs, "w", encoding="utf-8") as f:
                    f.write("\n".join(logtail).strip() + "\n")
            with open(report_abs, encoding="utf-8") as f:
                report = f.read().strip()
            job_manager.update(job_id, status="done", summary=report[-4000:] or summary,
                               reportPath=report_rel, validatorOk=True)
            clear_amend_state(jid)
            notify("✓ The Binder's survey is done",
                   f"The review of {jid} is inked at {report_rel} — open the Binder to commission changes.")
            return
        if not tome_has_changes(jid):
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
        v = _validate_amendment(jid)
        if v.returncode != 0:
            report = (v.stdout + v.stderr).strip()
            job_manager.append(
                job_id, "log",
                "── exact validator report returned to the hand; one repair turn begins ──",
                limit=400)
            repair_prompt = (prompt + "\n\n===== HARNESS REPAIR TURN =====\n"
                             "The independent validator failed. Read every finding below, repair "
                             "all in-scope failures without undoing the requested amendment, rerun "
                             "the validator yourself until clean, then stop.\n\n" + report)
            rc, timed_out, logtail = _run_agent_turn(
                job_id, cmd, repair_prompt, input_mode, invocation.environment,
                invocation.cwd,
                job_manager, processes)
            cancelled = job_manager.status(job_id).get("status") == "cancelled"
            if cancelled:
                clear_amend_state(jid)
                rollback_tome(jid)
                checkpointed = False
                return
            if timed_out:
                raise RuntimeError(f"repair timed out after {AMEND_TIMEOUT}s:\n"
                                   + "\n".join(logtail[-20:]))
            if rc != 0:
                raise RuntimeError(f"repair exit {rc}:\n" + "\n".join(logtail[-20:]))
            summary = "\n".join(logtail)[-2000:].strip()
            v = _validate_amendment(jid)
        job_manager.append(
            job_id, "log",
            ("── the candle is satisfied: the work holds (validator passed) ──"
             if v.returncode == 0 else
             "── the candle gutters: the validator found flaws (see its report below) ──"),
            limit=400)
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
