"""The Binder (amend a tome): one headless CLI agent edits tomes/<jid>/, then
validate_tome.py checks the result. Amend jobs live in the shared config.jobs
registry with "kind": "amend"."""
import json
import os
import signal
import subprocess
import sys
import threading
import time

from .config import (AGY_BIN, BUILD_DIR, CLAUDE_BIN, CODEX_BIN, OPENCODE_BIN, ROOT,
                     agy_print_args, amend_procs, codex_no_mcp_args, jobs, jobs_lock)
from .forge import ANSI_RE, notify

AMEND_TIMEOUT = 900  # seconds for one small-change agent run


# An amend job lives in the in-memory `jobs` dict, so a server restart (or the runner
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


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None


def checkpoint_tome(jid):
    """Commit tomes/<jid> as-is before the Binder touches it (no-op if clean), so a
    failed run can be rolled back completely. save/ is gitignored and unaffected."""
    _git("add", "-A", "--", f"tomes/{jid}")
    _git("commit", "-m", f"Binder checkpoint: {jid}", "--", f"tomes/{jid}")  # exits non-zero if nothing changed — fine


def rollback_tome(jid):
    """Restore tomes/<jid> to the checkpoint: revert tracked edits, drop new files."""
    _git("checkout", "HEAD", "--", f"tomes/{jid}")
    _git("clean", "-fd", "--", f"tomes/{jid}")


def _mark_amend_state(tome, status):
    st = load_amend_state(tome)
    if st:
        st["status"] = status
        save_amend_state(st)


def run_amender(job_id, jid, request_text, kind, model, effort="", broad=False, iterate=False, reset_ok=False,
                review=False, review_path=""):
    """Background worker: ONE headless CLI agent makes an edit to tomes/<jid>/
    guided by course-configuration-guide.md, then validate_tome.py checks the result.
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
            "(shell reads are fine where shell is your file interface); run no validators or "
            "generators. End with one short paragraph summarizing your top findings.")
    elif iterate:
        focus = f"The player asks you to focus especially on:\n\n{req}\n\n" if req else ""
        prompt = (
            "You are THE BINDER — a maintenance agent for the Arcanum course platform, in "
            f"ITERATE mode on the course (tome) at tomes/{jid}/.\n\n"
            "FIRST read THREE guides: course-configuration-guide.md (the file/field map and hard "
            "rules), course-improvement-guide.md (the rubric for what makes a tome strong and where "
            "weaknesses hide), and tome-authoring/3-chapters.md (the pedagogy spec — its anti-template "
            f"and learning-design rules bind every addition you make). Then survey tomes/{jid}/ against that rubric, "
            "choose the HIGHEST-VALUE improvements you can make, and apply them, editing as many "
            f"files as it takes. {focus}"
            f"{bounds} Read and edit files with whatever tools your harness provides — if shell "
            "commands are how you read or edit files, use them freely for that; just do NOT run "
            "validators, builds, or generators yourself. "
            f"The harness runs `python3 tools/validate_tome.py tomes/{jid}` the moment you finish, and "
            "your work MUST leave it with ZERO errors and no new warnings — reason through that "
            "validator's rules as you edit, and if a change would break it, fix it or don't make it. "
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
            "commands are how you read or edit files, use them freely for that; just do NOT run "
            "validators, builds, or generators yourself. The harness runs "
            f"`python3 tools/validate_tome.py tomes/{jid}` the moment you finish, and your work MUST "
            "leave it with ZERO errors and no new warnings — reason through that validator's rules as "
            "you edit, and if a change would break it, fix it or don't make it. End with one "
            "short paragraph naming exactly the file(s) and field(s) you changed.")
    # same headless postures + effort switches as tools/build_tome.py CLI_RUNNERS
    cmds = {
        "claude-cli": [CLAUDE_BIN, "-p", "--permission-mode", "acceptEdits"]
                      + (["--model", model] if model else [])
                      + (["--effort", effort] if effort else []),
        "antigravity-cli": [AGY_BIN, "--print", "--dangerously-skip-permissions"]
                           + agy_print_args(AMEND_TIMEOUT)
                           + (["--model", model] if model else []),  # agy: model name carries effort
        # personal MCP servers off (codex-desktop's node_repl hangs headless) — the Binder needs none
        "codex-cli": [CODEX_BIN, "exec", "--skip-git-repo-check", "-s", "workspace-write", *codex_no_mcp_args()]
                     + (["-m", model] if model else [])
                     + (["-c", f"model_reasoning_effort={effort}"] if effort else []) + ["-"],
        "opencode-cli": [OPENCODE_BIN, "run", "--dangerously-skip-permissions"]
                        + (["-m", model] if model else [])
                        + (["--variant", effort] if effort else []) + [prompt],
    }
    try:
        cmd = cmds.get(kind)
        if not cmd:
            raise ValueError(f"unknown binder kind {kind!r}")
        if not review:  # review edits nothing under tomes/ — no checkpoint needed
            checkpoint_tome(jid)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        stdin_data = None if kind == "opencode-cli" else prompt
        p = subprocess.Popen(cmd, stdin=(subprocess.DEVNULL if stdin_data is None else subprocess.PIPE),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                             env=env, cwd=ROOT, start_new_session=True)  # own group, so cancel kills CLI children too
        with jobs_lock:
            amend_procs[job_id] = p
        if stdin_data is not None:
            try:
                p.stdin.write(stdin_data)
                p.stdin.close()
            except BrokenPipeError:
                pass
        # Stream the agent's output live into the job log (stderr merged into stdout) so a broad
        # run shows a terminal like the forge does. A watchdog kills the group on timeout.
        timed_out = {"v": False}
        def _kill_timeout():
            timed_out["v"] = True
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        wd = threading.Timer(AMEND_TIMEOUT, _kill_timeout)
        wd.start()
        # stdout is pumped on a side thread: a lingering CLI child (e.g. a stuck MCP server)
        # inherits the pipe and blocks a plain read-to-EOF forever, even after codex exits —
        # the job then never leaves "running". Wait on the process, then sever stragglers.
        def _pump():
            for line in p.stdout:
                line = ANSI_RE.sub("", line.rstrip("\n"))
                with jobs_lock:
                    job = jobs.get(job_id)
                    if not job:
                        break
                    job["log"].append(line)
                    del job["log"][:-400]
        pump = threading.Thread(target=_pump, daemon=True)
        pump.start()
        try:
            rc = p.wait()
            pump.join(15)  # grace for trailing output
            if pump.is_alive():  # something still holds the pipe — kill the group and move on
                try:
                    os.killpg(p.pid, signal.SIGKILL)  # pgid == pid (start_new_session)
                except (ProcessLookupError, PermissionError):
                    pass
                pump.join(5)
        finally:
            wd.cancel()
            with jobs_lock:
                amend_procs.pop(job_id, None)
        with jobs_lock:
            if jobs.get(job_id, {}).get("status") == "cancelled":
                clear_amend_state(jid)  # the player stayed the quill; nothing to resume
                if not review:
                    rollback_tome(jid)  # discard the half-finished edit
                return  # the kill is not an error
            logtail = list(jobs.get(job_id, {}).get("log", []))
        if timed_out["v"]:
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
            with jobs_lock:
                job = jobs.get(job_id)
                if job:
                    job.update(status="done", summary=report[-4000:] or summary,
                               reportPath=report_rel, validatorOk=True)
            clear_amend_state(jid)
            notify("✓ The Binder's survey is done",
                   f"The review of {jid} is inked at {report_rel} — open the Binder to commission changes.")
            return
        with jobs_lock:  # the log streams to the bench — say the agent is done, the wait is the candle's
            job = jobs.get(job_id)
            if job:
                job["log"].append("── the hand rests; the candle now inspects the work (validator — a few minutes) ──")
        v = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "validate_tome.py"),
                            os.path.join("tomes", jid)], capture_output=True, text=True,
                           timeout=900, cwd=ROOT)  # this tome already validates in ~4.5min — 300s would kill good runs
        with jobs_lock:
            job = jobs.get(job_id)
            if job:
                job["log"].append("── the candle is satisfied: the work holds (validator passed) ──"
                                  if v.returncode == 0 else
                                  "── the candle gutters: the validator found flaws (see its report below) ──")
                job.update(status="done", summary=summary,
                           validator=v.stdout.strip()[-2000:], validatorOk=v.returncode == 0)
        clear_amend_state(jid)  # the run finished; the edit is on disk, nothing to resume
        if broad:  # broad runs are long/unattended — ping the operator on the outcome
            if v.returncode == 0:
                notify("✓ The Binder finished", f"Broad change to {jid} is done — reopen the tome to see it.")
            else:
                notify(f"⚠ The Binder needs you — {jid}",
                       "The broad change finished but the validator found flaws. Open the Binder to mend them.", priority=1)
    except Exception as e:
        if not review:
            rollback_tome(jid)  # a half-finished tome is worse than none — back to the checkpoint
        with jobs_lock:
            job = jobs.get(job_id)
            stopped = bool(job and job.get("status") == "running")
            if stopped:
                job.update(status="error", error=(str(e)[:800] + "\n\nThe tome was restored to its pre-Binder checkpoint."))
        if stopped:
            _mark_amend_state(jid, "error")  # left on disk so the Binder can offer to resume it
        if stopped:  # a real failure/timeout, not a user cancel — you may be away, so ping to retry
            notify(f"✗ The Binder stopped — {jid}",
                   f"The amendment failed and the tome was rolled back — reopen the Binder to retry it on a different hand:\n{str(e)[:360]}",
                   priority=1)
