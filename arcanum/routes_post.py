"""POST /api/* routes. `h` is the live Handler instance."""
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

from runtimes import common as rt_common
from runtimes.common import atomic_write

from .amender import clear_amend_state, load_amend_state, run_amender, save_amend_state
from .build_state import (BUILD_TOTAL_PHASES, build_result_status,
                          record_cancelled_build, save_active_owner)
from .config import (BUILD_DIR, CLI_EFFORTS, GLOBAL_STATE_KEYS, ROOT,
                     TOMES_DIR, amend_procs, jobs, jobs_lock, read_settings, write_settings)
from .forge import (_clear_runner_handshake, _plan_concept,
                    _resume_phase, _runner_args, _save_launch, _write_progress,
                    external_build_process, fresh_tome_id, watch_build,
                    working_is_active)
from .grader import ask_oracle, run_grader
from .tomes import (external_workspace, has_progress, load_manifest, plan_path, project_dir,
                    project_name, resolve_tome, resolve_working_tid, runtime_for,
                    save_dir, scratch_base, state_path, tome_dir, write_files)


def handle(h):
    path = urllib.parse.urlparse(h.path).path
    try:
        body = h.read_body()
    except (ValueError, json.JSONDecodeError):
        return h.send_json({"error": "bad json"}, 400)
    # tome scoping: prefer the ?tome= query param (added by the client fetch shim),
    # fall back to a "tome" key in the body (used by tools like gen_attacks.py)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    hint = (q.get("tome") or [None])[0] or (body.get("tome") if isinstance(body, dict) else None)
    jid = resolve_tome(hint)
    try:
        if path == "/api/state":
            return save_state(h, body, jid)
        if path == "/api/state/reset":
            return reset_state(h, body, jid)
        if path == "/api/workspace":
            write_files(jid, body.get("files", []))
            return h.send_json({"ok": True})
        if path == "/api/scaffold":
            if external_workspace(jid):  # the player's own tools own that directory
                return h.send_json({"ok": True, "result": "external workspace — managed by your own tools"})
            pdir = project_dir(jid)
            os.makedirs(os.path.dirname(pdir), exist_ok=True)
            return h.send_json({"ok": True, "result": runtime_for(jid).scaffold(pdir, project_name(jid))})
        if path == "/api/seedworkspace":
            # place the tome's starter files into a student's OWN external folder
            # (explicit action). Non-destructive unless force; refuses a bad path.
            d = os.path.expanduser(body.get("dir", ""))
            if not (os.path.isabs(d) and os.path.isdir(d)):
                return h.send_json({"ok": False, "error": "not an existing absolute folder"}, 400)
            rt = runtime_for(jid)
            if not rt.available():
                return h.send_json({"ok": False, "error": f"{rt.LANGUAGE} toolchain not found on this machine"}, 400)
            mode = body.get("mode", "")  # "" = check, "missing" = add absent only, "force" = overwrite
            try:
                return h.send_json(rt.seed_workspace(d, project_name(jid),
                                                     force=(mode == "force"), only_missing=(mode == "missing")))
            except Exception as e:
                return h.send_json({"ok": False, "error": str(e)[-500:]}, 500)
        if path == "/api/openpath":
            # open the student's external project folder in their OS file explorer
            # (server shares their machine — localhost single-user tool)
            d = os.path.expanduser(body.get("dir", ""))
            if not (os.path.isabs(d) and os.path.isdir(d)):
                return h.send_json({"ok": False, "error": "not an existing absolute folder"}, 400)
            try:
                if sys.platform == "win32":
                    os.startfile(d)  # type: ignore[attr-defined]  # noqa: only exists on Windows
                else:
                    opener = "open" if sys.platform == "darwin" else "xdg-open"
                    subprocess.Popen([opener, d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return h.send_json({"ok": True})
            except Exception as e:
                return h.send_json({"ok": False, "error": str(e)}, 500)
        if path == "/api/oracle":
            lang = body.get("language") or load_manifest(jid).get("runtime", {}).get("language") or "code"
            return h.send_json(ask_oracle(body.get("question", ""), body.get("context", ""),
                                          body.get("model"), lang,
                                          body.get("kind") or "ollama", jid))
        if path == "/api/runsnippet":
            rt = runtime_for(jid)
            return h.send_json(rt.run_snippet(scratch_base(rt.NAME), body.get("code", ""), body.get("stdin", "")))
        if path == "/api/snippetdiag":
            rt = runtime_for(jid)
            return h.send_json(rt.snippet_diagnostics(scratch_base(rt.NAME), body.get("code", "")))
        if path == "/api/run":
            write_files(jid, body.get("files", []))
            return h.send_json(runtime_for(jid).run_project(project_dir(jid), body.get("stdin", "")))
        if path == "/api/runcancel":
            return h.send_json({"ok": True, "cancelled": rt_common.cancel_current()})
        if path == "/api/diagnostics":
            write_files(jid, body.get("files", []))
            return h.send_json(runtime_for(jid).build_diagnostics(project_dir(jid)))
        if path == "/api/addpackage":
            return h.send_json(runtime_for(jid).add_package(project_dir(jid), body.get("package", "")))
        if path == "/api/grade":
            write_files(jid, body.get("files", []))
            sid = body.get("sectionId", "x")
            with jobs_lock:
                for jid0, j in jobs.items():
                    if j.get("status") == "running" and j.get("section") == sid and j.get("tome") == jid:
                        return h.send_json({"ok": True, "jobId": jid0, "existing": True})
                gid = uuid.uuid4().hex[:12]
                jobs[gid] = {"status": "running", "section": sid, "tome": jid}
            threading.Thread(target=run_grader, args=(gid, body, jid), daemon=True).start()
            return h.send_json({"ok": True, "jobId": gid})
        if path == "/api/amend":
            return start_amend(h, body, jid)
        if path == "/api/amend/cancel":
            aid = str(body.get("id") or "")
            with jobs_lock:
                job = jobs.get(aid)
                proc = amend_procs.get(aid)
                if not (job and job.get("kind") == "amend" and job.get("status") == "running"):
                    return h.send_json({"ok": False, "error": "no running amendment with that id"}, 404)
                job["status"] = "cancelled"
            if proc:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)  # the CLI and every child it spawned
                except (ProcessLookupError, PermissionError):
                    proc.kill()
            return h.send_json({"ok": True})
        if path == "/api/amend/dismiss":
            # forget a cut-short amendment so the Binder stops offering to resume it
            jid = h.query_tome()
            st = load_amend_state(jid)
            with jobs_lock:
                live = jobs.get(st.get("id")) if st else None
                if live and live.get("status") == "running":
                    return h.send_json({"ok": False, "error": "that amendment is still running"}, 409)
            clear_amend_state(jid)
            return h.send_json({"ok": True})
        if path == "/api/buildtome":
            return start_build(h, body)
        if path == "/api/buildtome/runner":
            return answer_runner_pause(h, body)
        if path == "/api/buildtome/cancel":
            bid = str(body.get("id") or "")
            with jobs_lock:
                job = jobs.get(bid)
                is_build = bool(job) and job.get("kind") == "build"
                running = is_build and job.get("status") == "running"
                pid = job.get("pid") if is_build else None
                slug = (job.get("slug") or job.get("tome")) if is_build else bid
                tome = job.get("tome") if is_build else None
                phase = job.get("phase", 0) if is_build else 0
                if running:
                    job["status"] = "cancelled"  # before the kill, so watch_build won't flag "error"
            if not is_build:
                proc = external_build_process(bid)
                if not proc:
                    return h.send_json({"ok": False, "error": "no such build"}, 404)
                pid, running = proc["pid"], True
                pp = plan_path(bid)
                try:
                    with open(pp, encoding="utf-8") as f:
                        plan_text = f.read()
                    tome = resolve_working_tid(bid, plan_text)
                except OSError:
                    tome = bid
                phase = _resume_phase(bid, tome)
            if running:
                record_cancelled_build(slug, tome, phase)
            if running and pid:
                try:
                    if hasattr(os, "killpg"):
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                    else:  # windows: no process groups — best effort on the harness itself
                        os.kill(pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    pass  # already exited
            return h.send_json({"ok": True, "status": "cancelled" if running else job.get("status")})
        if path == "/api/buildtome/resume":
            return resume_build(h, body)
        if path == "/api/buildtome/discard":
            return discard_build(h, body)
    except Exception as e:  # surface errors to the UI rather than 500-ing silently
        return h.send_json({"ok": False, "error": str(e)}, 500)
    h.send_json({"error": "unknown endpoint"}, 404)


def save_state(h, body, jid):
    # peel the reader-wide settings off into global-configs/settings.toml;
    # the tome's save keeps only what is truly its own (palette + progress)
    if isinstance(body, dict):
        g = read_settings()
        took = {k: body.pop(k) for k in GLOBAL_STATE_KEYS if k in body}
        if took:
            g.update(took)
            write_settings(g)
    p = state_path(jid)
    # never let a fresh default silently erase real progress. if the
    # save on disk has progress and the incoming one doesn't, refuse
    # (a genuine reset deletes the save dir, it doesn't POST empty).
    # otherwise keep the last progress-bearing save as state.json.bak.
    old = None
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f: old = json.load(f)
        except (OSError, json.JSONDecodeError): old = None
    if has_progress(old) and not has_progress(body):
        return h.send_json({"ok": False, "error": "refused: would erase progress", "kept": True}, 409)
    if has_progress(old):
        atomic_write(p + ".bak", json.dumps(old, indent=1))
    atomic_write(p, json.dumps(body, indent=1))
    return h.send_json({"ok": True, "savedAt": time.time()})


def reset_state(h, body, jid):
    """Erase one tome's private save tree, never its authored content or external folder."""
    if not isinstance(body, dict) or body.get("confirm") != "reset-progress":
        return h.send_json({"ok": False, "error": "reset confirmation is required"}, 400)
    with jobs_lock:
        busy = any(j.get("status") == "running" and j.get("tome") == jid for j in jobs.values())
    if busy:
        return h.send_json({"ok": False, "error": "finish or cancel the active tome job before resetting"}, 409)

    root = os.path.realpath(save_dir(jid))
    expected_parent = os.path.realpath(tome_dir(jid))
    if os.path.basename(root) != "save" or os.path.dirname(root) != expected_parent:
        raise ValueError("refused unsafe save path")
    shutil.rmtree(root)
    os.makedirs(root, exist_ok=True)
    return h.send_json({"ok": True})


def start_amend(h, body, jid):
    req_text = str(body.get("request") or "").strip()
    iterate = bool(body.get("iterate"))
    review = bool(body.get("review"))  # read-only survey → findings land in reviews/
    review_path = str(body.get("reviewPath") or "")[:200]  # prior report the change should read
    if not req_text and not iterate and not review:
        return h.send_json({"ok": False, "error": "an amendment request is required"}, 400)
    kind = str(body.get("kind") or "claude-cli")
    model = str(body.get("model") or "")
    effort = str(body.get("effort") or "")
    broad = bool(body.get("broad")) or iterate  # iterate is always a broad, multi-file pass
    reset_ok = bool(body.get("resetOk"))  # player accepts a progress wipe → agent may restructure
    if effort and effort not in CLI_EFFORTS.get(kind, ()):
        effort = ""  # drop an effort this kind doesn't accept rather than fail
    with jobs_lock:
        for aid0, j in jobs.items():
            if j.get("kind") == "amend" and j.get("status") == "running" and j.get("tome") == jid:
                return h.send_json({"ok": True, "jobId": aid0, "existing": True})
        aid = uuid.uuid4().hex[:12]
        started = time.time()
        jobs[aid] = {"status": "running", "kind": "amend", "tome": jid,
                     "request": req_text[:300], "broad": broad, "review": review, "log": [],
                     "startedAt": started}
    # mirror to disk (full request) so a lost server/runner can be resumed from the Binder
    save_amend_state({"id": aid, "tome": jid, "request": req_text[:4000],
                      "broad": broad, "iterate": iterate, "resetOk": reset_ok, "review": review, "kind": kind,
                      "model": model, "effort": effort, "startedAt": started, "status": "running"})
    threading.Thread(target=run_amender,
                     args=(aid, jid, req_text, kind, model, effort, broad, iterate, reset_ok, review, review_path),
                     daemon=True).start()
    return h.send_json({"ok": True, "jobId": aid})


def start_build(h, body):
    concept = str(body.get("concept") or "").strip()
    if not concept:
        return h.send_json({"ok": False, "error": "a course concept is required"}, 400)
    # The harness owns the folder name: it launches as untitled[-N] and
    # build_tome.py scaffolds tomes/<tid>/ after Phase 0; Phase 2 renames it
    # from the [runtime] project the author-AI chooses.
    tid = fresh_tome_id("untitled")
    # a prior failed run of this slug may have left a runner-request behind;
    # stale files would make the new job's status report the old pause
    _clear_runner_handshake(tid)
    tooling = str(body.get("tooling") or "").strip().lower()
    if tooling not in ("internal", "external", "both"):
        return h.send_json({"ok": False, "error": "tooling must be internal, external, or both"}, 400)
    gate = json.dumps({"prior_knowledge": str(body.get("prior_knowledge") or "").strip(),
                       "prior_level": str(body.get("prior_level") or "").strip(),
                       "breadth": str(body.get("breadth") or "").strip(),
                       "depth": str(body.get("depth") or "").strip(),
                       "mastery": str(body.get("mastery") or "").strip(),
                       "tooling": tooling})
    # optional per-agent AI picks from the bindery modal: {"default": {kind,
    # model, effort?}, "8": {kind, model, effort?}} → build_tome.py --runner overrides.
    runner_args = _runner_args(body)
    _save_launch(tid, body, concept)  # so a later resume can pre-fill the pickers
    # -u: unbuffered, so phase lines reach the reader as they happen.
    # start_new_session=True: its own process group, so cancel can kill
    # the harness AND the agent children it spawns.
    split_args = ["--split-sections"] if body.get("sectionsSplit") else []
    proc = subprocess.Popen([sys.executable, "-u", os.path.join(ROOT, "tools", "build_tome.py"),
                             tid, "--gate-json", gate, "--concept", concept,
                             "--ask-on-death"] + split_args + runner_args,
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=True)
    gid = uuid.uuid4().hex[:12]
    with jobs_lock:
        # slug: the launch id build_tome keys its .tome-build sidecars on. Phase 2
        # renames the tome dir and we follow it in "tome" (for forge_name), but the
        # runner handshake files stay under this slug — never mutate it.
        jobs[gid] = {"status": "running", "kind": "build", "tome": tid, "slug": tid,
                     "phase": 0, "phaseTitle": "starting", "totalPhases": BUILD_TOTAL_PHASES,
                     "log": [], "pid": proc.pid, "startedAt": time.time()}
    save_active_owner(tid, gid, proc.pid)
    threading.Thread(target=watch_build, args=(gid, proc), daemon=True).start()
    return h.send_json({"ok": True, "jobId": gid, "tome": tid})


def answer_runner_pause(h, body):
    # Answer a build pause: write the reply file build_tome.py is polling. Two pauses:
    # a dead runner (pick a new one) and a phase that exhausted its gate retries (switch
    # model and/or grant `retries` more tries). Empty kind+model keeps the current model;
    # for a death that means abort, for a gate pause it means "same model, N more tries".
    bid = str(body.get("id") or "")
    with jobs_lock:
        job = jobs.get(bid)
        # reply under the launch slug build_tome polls, not the renamed tome dir
        tome = (job.get("slug") or job.get("tome")) if job and job.get("kind") == "build" else None
    if not tome:
        return h.send_json({"ok": False, "error": "no such build"}, 404)
    kind = str(body.get("kind") or "")
    mdl = str(body.get("model") or "")
    eff = str(body.get("effort") or "")
    if mdl and kind not in ("claude-cli", "antigravity-cli", "codex-cli", "opencode-cli"):
        return h.send_json({"ok": False, "error": "unknown runner kind"}, 400)
    if eff and eff not in CLI_EFFORTS.get(kind, ()):
        eff = ""  # drop an effort this kind doesn't accept rather than fail
    try:
        retries = max(0, int(body.get("retries") or 0))
    except (TypeError, ValueError):
        retries = 0
    with open(os.path.join(BUILD_DIR, f"{tome}.runner-reply.json"), "w", encoding="utf-8") as f:
        json.dump({"kind": kind, "model": mdl, "effort": eff, "retries": retries}, f)
    # This is a new attempt at the paused phase. Restart its visible clock now rather
    # than carrying over the time spent before the runner/gate pause.
    with jobs_lock:
        j = jobs.get(bid)
        if j:
            j["phaseStartedAt"] = time.time()
            if mdl:  # the harness re-emits [runner: …] only at the next phase banner
                j["runner"] = f"{kind} {mdl}" + (f" @{eff}" if eff else "")
    return h.send_json({"ok": True})


def resume_build(h, body):
    rid = str(body.get("id") or "")
    pp = plan_path(rid)
    if not os.path.exists(pp):
        return h.send_json({"ok": False, "error": "no such working"}, 404)
    with open(pp, encoding="utf-8") as f:
        text = f.read()
    tid = resolve_working_tid(rid, text)
    if working_is_active(rid, tid):
        return h.send_json({"ok": False, "error": "that working is already being forged"}, 409)
    frm = _resume_phase(rid, tid)
    # optional operator override: the resume modal's "restart from" picker forces a
    # phase instead of the auto-detected one. Phase 3 skips sections in the done-set,
    # so a forced restart at/before it must drop that set to re-author every section
    # (e.g. section 2 failed but got recorded done — this is how you redo it).
    try:
        forced = int(body.get("fromPhase"))
    except (TypeError, ValueError):
        forced = 0
    if 1 <= forced <= 8:
        frm = forced
        _write_progress(tid, frm)
        if frm <= 3:
            for k in {rid, tid}:
                try:
                    os.remove(os.path.join(BUILD_DIR, f"{k}.sections-done"))
                except OSError:
                    pass
    # A renamed tome kept its plan under the old id; build_tome wants both under the
    # id it's launched with, so align the plan file name to the current tome id.
    if tid != rid and not os.path.exists(plan_path(tid)):
        try:
            os.rename(pp, plan_path(tid))
        except OSError:
            pass
    # Died before Phase 2 scaffolded the folder (--from-phase >0 skips Phase 0's
    # scaffold step): create it, then resume from the first content phase.
    if not os.path.isdir(os.path.join(TOMES_DIR, tid)):
        subprocess.call([sys.executable, os.path.join(ROOT, "tools", "new_tome.py"), tid])
        frm = 1
    _clear_runner_handshake(tid)
    _save_launch(tid, body, _plan_concept(text))
    split_args = ["--split-sections"] if body.get("sectionsSplit") else []
    proc = subprocess.Popen([sys.executable, "-u", os.path.join(ROOT, "tools", "build_tome.py"),
                             tid, "--from-phase", str(frm), "--ask-on-death"]
                            + split_args + _runner_args(body),
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=True)
    gid = uuid.uuid4().hex[:12]
    resumed_at = time.time()
    with jobs_lock:
        jobs[gid] = {"status": "running", "kind": "build", "tome": tid, "slug": tid,
                     "phase": frm, "phaseTitle": "resuming", "totalPhases": BUILD_TOTAL_PHASES,
                     "log": [], "pid": proc.pid, "startedAt": resumed_at,
                     "phaseStartedAt": resumed_at}
    save_active_owner(tid, gid, proc.pid)
    threading.Thread(target=watch_build, args=(gid, proc), daemon=True).start()
    return h.send_json({"ok": True, "jobId": gid, "tome": tid})


def discard_build(h, body):
    rid = str(body.get("id") or "")
    pp = plan_path(rid)
    if not os.path.exists(pp):
        return h.send_json({"ok": False, "error": "no such working"}, 404)
    with open(pp, encoding="utf-8") as f:
        text = f.read()
    tid = resolve_working_tid(rid, text)
    if working_is_active(rid, tid):
        return h.send_json({"ok": False, "error": "cancel the running forge before discarding it"}, 409)
    for key in {rid, tid}:  # plan + every per-build sidecar, both ids if renamed
        for suff in ("plan.md", "launch.json", "progress", "sections-done", "verdict", "active.json", "cancelled.json", "result.json",
                     "findings.json", "runner-request.json", "runner-reply.json"):
            try:
                os.remove(os.path.join(BUILD_DIR, f"{key}.{suff}"))
            except OSError:
                pass
        shutil.rmtree(os.path.join(BUILD_DIR, f"{key}.handoffs"), ignore_errors=True)
    # The partial tome itself — only when incomplete, and only if the path really is a
    # direct child of tomes/ (never let a crafted id escape the folder). Durable terminal
    # state overrides the legacy Harness-ground-truth proxy.
    tdir = os.path.realpath(os.path.join(TOMES_DIR, tid))
    result = build_result_status(rid) or build_result_status(tid)
    incomplete = (result.get("status") != "done" if result
                  else "Harness ground truth" not in text)
    if (tid and incomplete
            and os.path.dirname(tdir) == os.path.realpath(TOMES_DIR)
            and os.path.isdir(tdir)):
        shutil.rmtree(tdir, ignore_errors=True)
    return h.send_json({"ok": True})
