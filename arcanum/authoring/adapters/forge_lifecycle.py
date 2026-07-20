"""Interactive single-author tome build lifecycle."""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from ...forge.build_state import (BUILD_TOTAL_PHASES, build_result_status,
                                  load_author_session, load_section_progress,
                                  save_active_owner)
from ...config import BUILD_DIR, CLI_EFFORTS, ROOT
from ...forge import (_clear_build_terminal_state, _plan_concept, _plan_gate,
                      _resume_phase, _save_launch, author_activity_started_at,
                      external_build_process, fresh_tome_id, list_active_builds,
                      watch_build, working_is_active)


AUTHOR_KINDS = ("claude-cli", "antigravity-cli", "codex-cli", "opencode-cli")


def _resume_session_id(previous, author, phase, section=""):
    """Resume only the same model's exact phase/section session."""
    if (previous.get("role") != "author"
            or previous.get("kind") != author.get("kind")
            or previous.get("model") != author.get("model")
            or (previous.get("actualModel")
                and previous.get("actualModel") != author.get("model"))
            or int(previous.get("phase") or 0) != int(phase)):
        return ""
    if int(phase) == 3 and str(previous.get("section") or "") != str(section or ""):
        return ""
    return str(previous.get("sessionId") or "")


def _agent(value, role):
    value = value or {}
    kind = str(value.get("kind") or "")
    model = str(value.get("model") or "").strip()
    effort = str(value.get("effort") or "").strip()
    if kind not in AUTHOR_KINDS or not model:
        raise ValueError(f"choose any installed CLI provider and model for the {role}")
    if effort and effort not in CLI_EFFORTS.get(kind, ()):
        raise ValueError(f"{kind} does not support effort {effort!r}")
    return {"kind": kind, "model": model, "effort": effort}


def _author(body):
    return _agent(body.get("author"), "author")


AUTHOR_PHASE_KEYS = ("phase12", "phase37", "phase8")


def _authors(body):
    """Validate the persisted phase-range author route, with legacy one-author fallback."""
    values = body.get("authors") or (body.get("bindery") or {}).get("authors") or {}
    if not values:
        author = _author(body)
        return {key: dict(author) for key in AUTHOR_PHASE_KEYS}
    return {key: _agent(values.get(key), f"{key} author") for key in AUTHOR_PHASE_KEYS}


def _phase_author(authors, phase):
    key = "phase12" if int(phase) <= 2 else "phase37" if int(phase) <= 7 else "phase8"
    return dict(authors[key])


def _reviewer(body):
    value = body.get("reviewer")
    return _agent(value, "reviewer") if value else None


def _validator(body):
    value = body.get("validator") or (body.get("bindery") or {}).get("validator")
    return _agent(value, "mandatory section validator")


def _agent_spec(agent):
    return f"{agent['kind']}:{agent['model']}" + (
        f"@{agent['effort']}" if agent.get("effort") else "")


def _launch(tid, author, concept, phase, services, gate_json=None, resume_id="",
            reviewer=None, validator=None, authors=None):
    command = [sys.executable, "-u", os.path.join(ROOT, "tools", "build_tome.py"), tid,
               "--author", _agent_spec(author), "--concept", concept,
               "--from-phase", str(max(1, min(8, int(phase or 1))))]
    if authors:
        command += ["--phase-1-2-author", _agent_spec(authors["phase12"]),
                    "--phase-3-7-author", _agent_spec(authors["phase37"]),
                    "--phase-8-author", _agent_spec(authors["phase8"])]
    if reviewer:
        command += ["--reviewer", _agent_spec(reviewer)]
    command += ["--validator", _agent_spec(validator)]
    if gate_json is not None:
        command += ["--gate-json", gate_json]
    if resume_id:
        command += ["--resume-session", resume_id]
    proc = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, start_new_session=True)
    started = time.time()
    job = services.jobs.create(
        "build", interactionState="starting", tome=tid, slug=tid, phase=phase,
        phaseTitle="starting", totalPhases=BUILD_TOTAL_PHASES, log=[], pid=proc.pid,
        startedAt=started, phaseStartedAt=started, activityStartedAt=started,
        # Only this run's lines. The read model already prepends the durable log, and a
        # copy taken at launch would outlive anything that clears it.
        statusLog=[],
        authorSchedule={key: dict(value) for key, value in (authors or {}).items()},
        sessionValidator=dict(validator),
        sessionReviewer=dict(reviewer) if reviewer else None,
        runner=f"{author['kind']} {author['model']}" + (
            f" @{author['effort']}" if author.get("effort") else ""))
    gid = job["id"]
    services.processes.put(gid, proc)
    save_active_owner(tid, gid, proc.pid)
    threading.Thread(target=watch_build,
                     args=(gid, proc, services.jobs, services.processes,
                           services.catalog), daemon=True).start()
    return gid


def start_build(h, body, services):
    if list_active_builds(services.jobs, services.catalog):
        return h.send_json({"ok": False,
                            "error": "finish or abandon the active tome before forging another"},
                           409)
    concept = str(body.get("concept") or "").strip()
    if not concept:
        return h.send_json({"ok": False, "error": "a course concept is required"}, 400)
    tooling = str(body.get("tooling") or "").strip().lower()
    if tooling not in ("internal", "external", "both"):
        return h.send_json({"ok": False,
                            "error": "tooling must be internal, external, or both"}, 400)
    try:
        authors, validator, reviewer = _authors(body), _validator(body), _reviewer(body)
    except ValueError as exc:
        return h.send_json({"ok": False, "error": str(exc)}, 400)
    author = _phase_author(authors, 1)
    tid = fresh_tome_id("untitled", services.jobs, services.catalog)
    _clear_build_terminal_state(tid)
    gate = json.dumps({"prior_knowledge": str(body.get("prior_knowledge") or "").strip(),
                       "prior_level": str(body.get("prior_level") or "").strip(),
                       "project_scope": str(body.get("project_scope") or "").strip(),
                       "depth": str(body.get("depth") or "").strip(),
                       "mastery": str(body.get("mastery") or "").strip(),
                       "tooling": tooling})
    launch = dict(body)
    launch["author"] = author
    launch["authors"] = authors
    launch["validator"] = validator
    launch["reviewer"] = reviewer or {}
    _save_launch(tid, launch, concept)
    gid = _launch(tid, author, concept, 1, services, gate, reviewer=reviewer,
                  validator=validator, authors=authors)
    return h.send_json({"ok": True, "jobId": gid, "tome": tid})


def resume_build(h, body, services):
    rid = str(body.get("id") or "")
    plan = services.catalog.paths.plan(rid)
    if not os.path.exists(plan):
        return h.send_json({"ok": False, "error": "no such working"}, 404)
    with open(plan, encoding="utf-8") as handle:
        text = handle.read()
    tid = services.catalog.resolve_working_id(rid, text)
    if working_is_active(services.jobs, services.catalog, rid, tid):
        return h.send_json({"ok": False, "error": "that working is already active"}, 409)
    phase = _resume_phase(rid, tid, services.catalog)
    try:
        forced = int(body.get("fromPhase") or 0)
    except (TypeError, ValueError):
        forced = 0
    if forced in range(1, 9):
        phase = forced
    if not os.path.isdir(services.catalog.paths.tome(tid)):
        subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "new_tome.py"), tid,
                               "--sections", "2"])
        phase = 1
    try:
        authors, validator, reviewer = _authors(body), _validator(body), _reviewer(body)
    except ValueError as exc:
        return h.send_json({"ok": False, "error": str(exc)}, 400)
    author = _phase_author(authors, phase)
    launch = dict(body)
    launch.update(_plan_gate(text))
    launch["author"] = author
    launch["authors"] = authors
    launch["validator"] = validator
    launch["reviewer"] = reviewer or {}
    _save_launch(rid, launch, _plan_concept(text), text)
    previous = load_author_session(rid) or load_author_session(tid) or {}
    section = (load_section_progress(rid) or {}).get("section", "") if phase == 3 else ""
    resume_id = _resume_session_id(previous, author, phase, section)
    # A resumed build is no longer cancelled: a stale cancel marker here made a later
    # clean finish record as "cancelled" instead of "done" (the untitled-6 loop).
    for key in {rid, tid}:
        for stale in ("cancelled", "result"):
            try:
                os.remove(os.path.join(BUILD_DIR, f"{key}.{stale}.json"))
            except OSError:
                pass
    gid = _launch(rid, author, _plan_concept(text), phase, services,
                  resume_id=resume_id, reviewer=reviewer, validator=validator,
                  authors=authors)
    return h.send_json({"ok": True, "jobId": gid, "tome": tid,
                        "continuedSession": bool(resume_id)})


def control_author(h, body, action, services):
    bid = str(body.get("id") or "")
    job = services.jobs.status(bid)
    proc = services.processes.get(bid)
    if not job or job.get("kind") != "build" or job.get("status") != "running" or not proc:
        return h.send_json({"ok": False, "error": "no live author session"}, 404)
    payload = {"type": action}
    if action == "message":
        payload["text"] = str(body.get("text") or "").strip()
        if not payload["text"]:
            return h.send_json({"ok": False, "error": "a message is required"}, 400)
    if action in ("message", "resume") and body.get("author"):
        try:
            payload["author"] = _author(body)
        except ValueError as exc:
            return h.send_json({"ok": False, "error": str(exc)}, 400)
    try:
        proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        proc.stdin.flush()
    except (BrokenPipeError, OSError):
        return h.send_json({"ok": False, "error": "the author control lane closed"}, 409)
    state = ("pausing" if action == "pause" else
             "resuming" if action == "resume" else "running")
    services.jobs.update(
        bid, activityStartedAt=author_activity_started_at(
            job.get("interactionState"), state, job.get("activityStartedAt", 0)),
        interactionState=state)
    return h.send_json({"ok": True})


def answer_runner_pause(h, body):
    """Legacy endpoint: a model pick is now an ordinary message/resume, never a handoff."""
    return h.send_json({"ok": False, "error": "this build uses one interactive author"}, 410)


def reset_build(h, body, tid, services):
    """Return a completed tome to one exact build phase and erase its learner save."""
    try:
        phase = int(body.get("phase") or 0)
    except (TypeError, ValueError):
        phase = 0
    if phase not in range(1, 9):
        return h.send_json({"ok": False, "error": "phase must be between 1 and 8"}, 400)
    section = str(body.get("section") or "")
    if section and (phase != 3 or not re.fullmatch(r"s[0-9]{2,3}", section)):
        return h.send_json({"ok": False,
                            "error": "a section restart requires phase 3 and a valid section id"},
                           400)
    if (body.get("confirm") != "reset-tome-build"
            or str(body.get("confirmTome") or "") != tid):
        return h.send_json({"ok": False,
                            "error": "the destructive tome and phase confirmation is required"}, 400)
    try:
        build_id, _path, _text = services.phase_reset.find_plan_for_tome(tid)
    except ValueError as exc:
        return h.send_json({"ok": False, "error": str(exc)}, 404)
    if working_is_active(services.jobs, services.catalog, build_id, tid):
        return h.send_json({"ok": False,
                            "error": "cancel the active author before resetting this tome"}, 409)
    busy = any({job.get("tome"), job.get("slug")} & {tid, build_id}
               for job in services.jobs.all(status="running"))
    if busy:
        return h.send_json({"ok": False,
                            "error": "finish or cancel the active tome job before resetting"}, 409)
    try:
        result = services.phase_reset.reset(tid, phase, section)
    except RuntimeError as exc:
        return h.send_json({"ok": False, "error": str(exc)}, 500)
    return h.send_json({"ok": True, **result})


def discard_build(h, body, services):
    rid = str(body.get("id") or "")
    if (body.get("confirm") != "discard-draft"
            or str(body.get("confirmWorking") or "") != rid):
        return h.send_json({"ok": False,
                            "error": "the matching draft deletion confirmation is required"}, 400)
    plan = services.catalog.paths.plan(rid)
    if not os.path.exists(plan):
        return h.send_json({"ok": False, "error": "no such working"}, 404)
    with open(plan, encoding="utf-8") as handle:
        text = handle.read()
    tid = services.catalog.resolve_working_id(rid, text)
    if working_is_active(services.jobs, services.catalog, rid, tid):
        return h.send_json({"ok": False,
                            "error": "cancel the active author before discarding"}, 409)
    tome = os.path.realpath(services.catalog.paths.tome(tid))
    result = build_result_status(rid) or build_result_status(tid)
    for key in {rid, tid}:
        _clear_build_terminal_state(key)
    if ((not result or result.get("status") != "done")
            and os.path.dirname(tome) == os.path.realpath(
                services.settings.tomes_root)):
        shutil.rmtree(tome, ignore_errors=True)
    return h.send_json({"ok": True})
