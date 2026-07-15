"""Interactive single-author tome build lifecycle."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid

from ..build_state import (BUILD_TOTAL_PHASES, build_result_status, load_author_session,
                           save_active_owner)
from ..config import (BUILD_DIR, CLI_EFFORTS, ROOT, TOMES_DIR, build_procs, jobs,
                      jobs_lock)
from ..forge import (_clear_build_terminal_state, _plan_concept, _plan_gate, _resume_phase,
                     _save_launch, external_build_process, fresh_tome_id, watch_build,
                     working_is_active)
from ..tomes import plan_path, resolve_working_tid


AUTHOR_KINDS = ("claude-cli", "antigravity-cli", "codex-cli", "opencode-cli")


def _author(body):
    value = body.get("author") or {}
    kind = str(value.get("kind") or "")
    model = str(value.get("model") or "").strip()
    effort = str(value.get("effort") or "").strip()
    if kind not in AUTHOR_KINDS or not model:
        raise ValueError("choose any installed CLI provider and model for the author")
    if effort and effort not in CLI_EFFORTS.get(kind, ()):
        raise ValueError(f"{kind} does not support effort {effort!r}")
    return {"kind": kind, "model": model, "effort": effort}


def _author_spec(author):
    return f"{author['kind']}:{author['model']}" + (
        f"@{author['effort']}" if author.get("effort") else "")


def _launch(tid, author, concept, phase, gate_json=None, resume_id=""):
    command = [sys.executable, "-u", os.path.join(ROOT, "tools", "build_tome.py"), tid,
               "--author", _author_spec(author), "--concept", concept,
               "--from-phase", str(max(1, min(8, int(phase or 1))))]
    if gate_json is not None:
        command += ["--gate-json", gate_json]
    if resume_id:
        command += ["--resume-session", resume_id]
    proc = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, start_new_session=True)
    gid = uuid.uuid4().hex[:12]
    started = time.time()
    with jobs_lock:
        jobs[gid] = {"status": "running", "interactionState": "starting",
                     "kind": "build", "tome": tid, "slug": tid, "phase": phase,
                     "phaseTitle": "starting", "totalPhases": BUILD_TOTAL_PHASES,
                     "log": [], "pid": proc.pid, "startedAt": started,
                     "phaseStartedAt": started,
                     "runner": f"{author['kind']} {author['model']}" + (
                         f" @{author['effort']}" if author.get("effort") else "")}
        build_procs[gid] = proc
    save_active_owner(tid, gid, proc.pid)
    threading.Thread(target=watch_build, args=(gid, proc), daemon=True).start()
    return gid


def start_build(h, body):
    concept = str(body.get("concept") or "").strip()
    if not concept:
        return h.send_json({"ok": False, "error": "a course concept is required"}, 400)
    tooling = str(body.get("tooling") or "").strip().lower()
    if tooling not in ("internal", "external", "both"):
        return h.send_json({"ok": False,
                            "error": "tooling must be internal, external, or both"}, 400)
    try:
        author = _author(body)
    except ValueError as exc:
        return h.send_json({"ok": False, "error": str(exc)}, 400)
    tid = fresh_tome_id("untitled")
    _clear_build_terminal_state(tid)
    gate = json.dumps({"prior_knowledge": str(body.get("prior_knowledge") or "").strip(),
                       "prior_level": str(body.get("prior_level") or "").strip(),
                       "breadth": str(body.get("breadth") or "").strip(),
                       "depth": str(body.get("depth") or "").strip(),
                       "mastery": str(body.get("mastery") or "").strip(),
                       "tooling": tooling})
    launch = dict(body)
    launch["author"] = author
    _save_launch(tid, launch, concept)
    gid = _launch(tid, author, concept, 1, gate)
    return h.send_json({"ok": True, "jobId": gid, "tome": tid})


def resume_build(h, body):
    rid = str(body.get("id") or "")
    plan = plan_path(rid)
    if not os.path.exists(plan):
        return h.send_json({"ok": False, "error": "no such working"}, 404)
    with open(plan, encoding="utf-8") as handle:
        text = handle.read()
    tid = resolve_working_tid(rid, text)
    if working_is_active(rid, tid):
        return h.send_json({"ok": False, "error": "that working is already active"}, 409)
    try:
        author = _author(body)
    except ValueError as exc:
        return h.send_json({"ok": False, "error": str(exc)}, 400)
    phase = _resume_phase(rid, tid)
    try:
        forced = int(body.get("fromPhase") or 0)
    except (TypeError, ValueError):
        forced = 0
    if forced in range(1, 9):
        phase = forced
    if not os.path.isdir(os.path.join(TOMES_DIR, tid)):
        subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "new_tome.py"), tid])
        phase = 1
    launch = dict(body)
    launch.update(_plan_gate(text))
    launch["author"] = author
    _save_launch(rid, launch, _plan_concept(text), text)
    previous = load_author_session(rid) or load_author_session(tid) or {}
    same_cli = (previous.get("kind") == author["kind"]
                and previous.get("model") == author["model"])
    resume_id = str(previous.get("sessionId") or "") if same_cli else ""
    gid = _launch(rid, author, _plan_concept(text), phase, resume_id=resume_id)
    return h.send_json({"ok": True, "jobId": gid, "tome": tid,
                        "continuedSession": bool(resume_id)})


def control_author(h, body, action):
    bid = str(body.get("id") or "")
    with jobs_lock:
        job = jobs.get(bid)
        proc = build_procs.get(bid)
    if not job or job.get("kind") != "build" or job.get("status") != "running" or not proc:
        return h.send_json({"ok": False, "error": "no live author session"}, 404)
    payload = {"type": action}
    if action == "message":
        payload["text"] = str(body.get("text") or "").strip()
        if not payload["text"]:
            return h.send_json({"ok": False, "error": "a message is required"}, 400)
    try:
        proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        proc.stdin.flush()
    except (BrokenPipeError, OSError):
        return h.send_json({"ok": False, "error": "the author control lane closed"}, 409)
    with jobs_lock:
        job["interactionState"] = ("pausing" if action == "pause" else
                                   "resuming" if action == "resume" else "running")
    return h.send_json({"ok": True})


def answer_runner_pause(h, body):
    """Legacy endpoint: a model pick is now an ordinary message/resume, never a handoff."""
    return h.send_json({"ok": False, "error": "this build uses one interactive author"}, 410)


def discard_build(h, body):
    rid = str(body.get("id") or "")
    plan = plan_path(rid)
    if not os.path.exists(plan):
        return h.send_json({"ok": False, "error": "no such working"}, 404)
    with open(plan, encoding="utf-8") as handle:
        text = handle.read()
    tid = resolve_working_tid(rid, text)
    if working_is_active(rid, tid):
        return h.send_json({"ok": False,
                            "error": "cancel the active author before discarding"}, 409)
    for key in {rid, tid}:
        for suffix in ("plan.md", "launch.json", "progress", "section-progress.json",
                       "active.json", "cancelled.json", "result.json", "session.json",
                       "conversation.jsonl"):
            try:
                os.remove(os.path.join(BUILD_DIR, f"{key}.{suffix}"))
            except OSError:
                pass
    tome = os.path.realpath(os.path.join(TOMES_DIR, tid))
    result = build_result_status(rid) or build_result_status(tid)
    if ((not result or result.get("status") != "done")
            and os.path.dirname(tome) == os.path.realpath(TOMES_DIR)):
        shutil.rmtree(tome, ignore_errors=True)
    return h.send_json({"ok": True})
