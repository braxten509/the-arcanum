"""Tome-forge build jobs: launching/watching builds, Pushover pings, and
resuming abandoned builds. Build jobs live in the shared config.jobs registry
with "kind": "build"."""
import glob
import json
import os
import re
import shutil
import threading
import time

from ..config import BUILD_DIR, CLI_EFFORTS, TOMES_DIR, build_procs, jobs, jobs_lock
from .build_state import (BUILD_PHASE_TITLES, BUILD_TOTAL_PHASES, build_result_status,
                          cancelled_build_status, load_active_owner, load_build_progress,
                          record_build_result, remove_active_owner)
from ..tomes import load_manifest, resolve_working_tid
from .tool_trace import mirror_tool_trace
from .notify import notify

BUILD_PHASE_RE = re.compile(r"^\s*>\s*Phase (\d+)\s*—\s*(.+?)(?:\s+\[runner|$)")
# Worker CLIs color their output; the browser log is plain text, where the ESC byte is
# invisible and leaves "[0m" litter. Strip CSI/OSC sequences and stray control chars.
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.|[\x00-\x08\x0b-\x1f\x7f]")
AUTHOR_SESSION_RE = re.compile(
    r"^AUTHOR SESSION (starting|running|validating|paused|complete|stopped)$")
ACTIVE_AUTHOR_STATES = frozenset(("starting", "running", "resuming"))
BUILD_STATUS_RE = re.compile(
    r"^(?:>\s*Phase\s+\d+\s+—|AUTHOR SESSION\s+|"
    r"(?:VALIDATOR COMMAND|AI VALIDATOR CALL) (?:START|COMPLETE|FAILED)\b)"
)


def forge_status_line(line):
    """Return a concise, display-safe forge status line, or None for raw runner chatter."""
    clean = line.strip()
    return clean if clean and BUILD_STATUS_RE.match(clean) else None


def author_activity_started_at(previous, current, started=0, now=None):
    """Clock only the current author work interval, never paused/harness time."""
    if current not in ACTIVE_AUTHOR_STATES:
        return 0
    if current == "starting" or previous not in ACTIVE_AUTHOR_STATES or not started:
        return time.time() if now is None else now
    return started


def fresh_tome_id(name):
    """Slugify a course name into an unused tomes/<id>. The setup creates the initial
    scaffold, and new_tome.py refuses an existing dir, so the id must be fresh (including
    ids claimed by builds still running that haven't scaffolded yet)."""
    s = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "-", name.lower().strip())).strip("-")[:32].strip("-") or "tome"
    with jobs_lock:
        claimed = {j.get("tome") for j in jobs.values()
                   if j.get("kind") == "build" and j.get("status") == "running"}
    tid, n = s, 1  # untitled, then untitled-1, untitled-2, … on collision
    # A prior build's plan under this slug also blocks it: Phase 2 renames the tome dir
    # but leaves the plan under the launch slug, and reusing it would OVERWRITE that
    # record (this clobbered writforge's plan when a second "untitled" launch reused it).
    while (os.path.exists(os.path.join(TOMES_DIR, tid)) or tid in claimed
           or os.path.exists(os.path.join(BUILD_DIR, f"{tid}.plan.md"))):
        tid, n = f"{s}-{n}", n + 1
    return tid


def forge_name(tid):
    """The themed name the author-AI chose — meta.name, once Phase 2 has written
    tome.toml. None before that (the overlay then falls back to the folder id)."""
    try:
        return (load_manifest(tid).get("meta") or {}).get("name") or None
    except Exception:
        return None


def watch_build(gid, proc):
    """Reader thread: stream harness stdout into the job, tracking '> Phase N — title' lines."""
    # stdout is the deliberately concise forge narration. The AI CLI's own JSONL is the
    # source of truth for real Bash/read/patch calls, mirrored separately into three UI rows.
    if getattr(proc, "pid", None):
        with jobs_lock:
            trace_build_id = (jobs.get(gid) or {}).get("slug") or ""
        threading.Thread(target=mirror_tool_trace,
                         args=(gid, proc.pid, trace_build_id), daemon=True).start()
    for line in proc.stdout:
        line = ANSI_RE.sub("", line.rstrip("\n"))
        m = BUILD_PHASE_RE.match(line)
        with jobs_lock:
            job = jobs.get(gid)
            if not job:
                break
            job["log"].append(line)
            del job["log"][:-400]
            status_line = forge_status_line(line)
            if status_line:
                job.setdefault("statusLog", []).append(status_line)
                del job["statusLog"][:-120]
            if m:
                job["phase"] = int(m.group(1))
                job["phaseTitle"] = m.group(2).strip()
                job["phaseStartedAt"] = time.time()   # durable time-in-phase; UI uses activity clock
                job.pop("sections", None)             # per-phase; only phase 3 repopulates it
            session = AUTHOR_SESSION_RE.match(line)
            if session:
                state = session.group(1)
                job["activityStartedAt"] = author_activity_started_at(
                    job.get("interactionState"), state, job.get("activityStartedAt", 0))
                job["interactionState"] = state
    rc = proc.wait()
    tome = final = slug = phase_title = failure = None
    phase = 0
    with jobs_lock:
        job = jobs.get(gid)
        build_procs.pop(gid, None)
        slug = (job.get("slug") or job.get("tome")) if job else None
        if job and job.get("status") == "running":  # cancel sets its own status first
            externally_cancelled = bool(slug and cancelled_build_status(slug))
            job["status"] = "cancelled" if externally_cancelled else ("done" if rc == 0 else "error")
            if rc != 0 and not externally_cancelled:
                job["error"] = "\n".join(job["log"][-30:])
            job["activityStartedAt"] = 0
        if job:
            final, tome = job.get("status"), job.get("tome")
            phase, phase_title, failure = job.get("phase", 0), job.get("phaseTitle", ""), job.get("error", "")
    if slug:
        try:
            with open(os.path.join(BUILD_DIR, f"{slug}.plan.md"), encoding="utf-8") as handle:
                tome = resolve_working_tid(slug, handle.read())
        except OSError:
            pass
        remove_active_owner(slug)
        if final in ("done", "error", "cancelled"):
            record_build_result(slug, tome, final, phase, phase_title, failure)
    nm = forge_name(tome) or tome or "The tome"
    if final == "done":
        notify("✓ Tome forged", f"{nm} finished — ready in the Bindery.")
    elif final == "error":  # a user cancel sets status 'cancelled', so this only fires on real failures
        # Brief on purpose: the full log tail stays in the job/result for the UI.
        where = f"in Phase {phase} — {phase_title}" if phase_title else f"in Phase {phase}" if phase else "while building"
        notify("✗ Forge failed",
               f"{nm} failed {where}. Resume it from Unfinished Workings — you can pick a different AI.",
               priority=1)


# ---------------------------------------------------------------- resuming abandoned builds
# A build writes its plan to .tome-build/<id>.plan.md and its tome to tomes/<id>/. A build
# that stopped before the end (crash, cancel, closed laptop) leaves both on disk; "resume"
# re-launches build_tome from where it left off. Two facts make the id bookkeeping fiddly:
# Phase 2 may RENAME the tome (untitled -> writforge) while leaving the plan under the old
# id, and the phase reached is only known from the live job — so we persist it to a sidecar.

def _plan_concept(text):
    m = re.search(r"(?ms)^## Concept\n(.+?)\n\n", text)
    return (m.group(1).strip().replace("\n", " ") if m else "")[:280]


def _load_launch(*ids):
    for i in ids:
        try:
            with open(os.path.join(BUILD_DIR, f"{i}.launch.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}


def _save_launch(tid, body, concept, plan_text=""):
    # gate answers ride along so a resume can DISPLAY them (they are fixed once Phase 0
    # ran); a resume POST carries none — keep the ones from the original launch then.
    previous = _load_launch(tid)
    gate = {k: str(body.get(k) or "").strip()
            for k in ("prior_knowledge", "prior_level", "project_scope", "depth", "mastery", "tooling")}
    if not gate["project_scope"] and body.get("breadth"):
        try:
            gate["project_scope"] = str(max(1, min(5, (int(body["breadth"]) + 1) // 2)))
        except (TypeError, ValueError):
            pass
    if not any(gate.values()):
        gate = previous.get("gate") or (_plan_gate(plan_text) if plan_text else {})
    try:
        with open(os.path.join(BUILD_DIR, f"{tid}.launch.json"), "w", encoding="utf-8") as f:
            json.dump({"bindery": body.get("bindery") or previous.get("bindery") or {},
                       "author": body.get("author") or previous.get("author") or {},
                       "authors": body.get("authors") or previous.get("authors") or {},
                       "validator": body.get("validator") or previous.get("validator") or {},
                       "reviewer": (body.get("reviewer") or {}) if "reviewer" in body
                       else previous.get("reviewer") or {},
                       "concept": concept, "gate": gate}, f)
    except OSError:
        pass


def _plan_gate(text):
    """Gate answers parsed back out of a plan's '- **Label:** value' lines — the fallback
    for workings launched before launch.json carried them."""
    out = {}
    for key, label in (("prior_knowledge", "Prior knowledge"), ("prior_level", "Starting level"),
                       ("project_scope", "Project scope"),
                       ("depth", "(?:Lesson depth|Scope / depth)"), ("mastery", "Mastery"),
                       ("tooling", "Tooling")):
        m = re.search(rf"(?im)^- \*\*{label}[^:]*?:\*\*\s*(.+)$", text)
        if m:
            out[key] = m.group(1).strip()
    if "project_scope" not in out:
        legacy = re.search(r"(?im)^- \*\*Breadth[^:]*?:\*\*\s*([0-9]+)\s*$", text)
        if legacy:
            out["project_scope"] = str(max(1, min(5, (int(legacy.group(1)) + 1) // 2)))
    return out


def tooling_conflict_details(text, failure=""):
    """Structured Phase-1 conflict data for the approval UI and resume endpoint."""
    fit = re.search(
        r"(?im)^\*\*Tooling fit:\*\*\s*(internal|external|both)\s*[—-]\s*"
        r"BLOCKED\s*:\s*(.+)$", text)
    conflict = bool(fit or "TOOLING_CONFLICT:" in failure)
    if not conflict:
        return {"conflict": False, "current": "", "required": "", "reason": ""}
    current = (fit.group(1).lower() if fit
               else str(_plan_gate(text).get("tooling") or "").lower())
    detail = fit.group(2).strip() if fit else failure.split("TOOLING_CONFLICT:", 1)[-1].strip()
    required_match = re.search(
        r"(?i)(?:REQUIRED_TOOLING\s*=|REQUIRED\s*:)\s*(internal|external|both)",
        detail + " " + failure)
    required = required_match.group(1).lower() if required_match else ""
    reason = re.split(
        r"(?i)\s+(?:[—-]\s*)?(?:REQUIRED_TOOLING\s*=|REQUIRED\s*:)",
        detail, maxsplit=1)[0].strip().rstrip(".;")
    # Legacy conflicts predate the structured REQUIRED marker. BOTH is the safe widening
    # for an internal/external-only plan; new conflicts always carry the exact recommendation.
    if not required and current in ("internal", "external"):
        required = "both"
    return {"conflict": True, "current": current, "required": required,
            "reason": reason or "The selected Tooling cannot deliver the promised artifact."}


def replace_plan_tooling(text, tooling):
    """Apply a human tooling-conflict resolution without changing any other gate answer."""
    policies = {
        "internal": ("INTERNAL (in-browser only)",
                     "Use the browser workbench only; do not require downloads or set `externalWorkspace`."),
        "external": ("EXTERNAL (teach the real tools)",
                     "Teach the real toolchain from install through diagnostics and final delivery; use `externalWorkspace` when the real work cannot run in-browser."),
        "both": ("BOTH (internal + external available)",
                 "Support the browser workbench and teach the complete real-tool path through final delivery."),
    }
    if tooling not in policies:
        raise ValueError("tooling must be internal, external, or both")
    label, meaning = policies[tooling]
    updated, gate_count = re.subn(
        r"(?im)^- \*\*Tooling:\*\*\s*(?:internal|external|both)\s*$",
        f"- **Tooling:** {tooling}", text, count=1)
    updated, policy_count = re.subn(
        r"(?im)^- \*\*Tooling — .*?$",
        f"- **Tooling — {label}:** {meaning}", updated, count=1)
    if gate_count != 1 or policy_count != 1:
        raise ValueError("the build plan's Tooling gate or calibration line is missing")
    return updated


def _write_progress(tome, phase):
    if not tome:
        return
    try:
        with open(os.path.join(BUILD_DIR, f"{tome}.progress"), "w", encoding="utf-8") as f:
            json.dump({"phase": phase}, f)
    except OSError:
        pass


def _resume_phase(planid, tid):
    """Which phase to restart at. Prefer the sidecar the live build wrote; for a legacy build
    with none, infer from disk (a scaffolded tome.toml means Phase 2 finished → resume Phase 3)."""
    for key in (tid, planid):
        try:
            with open(os.path.join(BUILD_DIR, f"{key}.progress"), encoding="utf-8") as f:
                return max(1, min(8, int(json.load(f).get("phase", 1))))
        except (OSError, ValueError):
            continue
    tdir = os.path.join(TOMES_DIR, tid)
    if os.path.isfile(os.path.join(tdir, "tome.toml")):
        return 3
    return 2 if os.path.isdir(tdir) else 1


def _live_build_processes(proc_root="/proc"):
    """Return live build_tome.py harnesses visible to this host.

    The web server's jobs registry is intentionally in-memory, so a second server process
    cannot see builds launched by the first one. /proc is the shared source of truth on the
    Linux host: a live harness command carries the original plan id immediately after
    tools/build_tome.py. Keep this parser exact so worker prompts that merely mention the
    script cannot masquerade as a build.
    """
    found = []
    try:
        pids = os.listdir(proc_root)
    except OSError:
        return found
    for entry in pids:
        if not entry.isdigit():
            continue
        pdir = os.path.join(proc_root, entry)
        try:
            with open(os.path.join(pdir, "cmdline"), "rb") as f:
                argv = [part.decode("utf-8", "replace") for part in f.read().split(b"\0") if part]
        except OSError:  # process exited, or proc entry is not readable
            continue
        for i, arg in enumerate(argv[:-1]):
            if os.path.basename(arg) != "build_tome.py":
                continue
            planid = argv[i + 1]
            if not re.fullmatch(r"[A-Za-z0-9_-]+", planid):
                break
            try:
                started = os.stat(pdir).st_ctime
            except OSError:
                started = None
            found.append({"pid": int(entry), "planid": planid, "startedAt": started})
            break
    return found


def _live_trace_jobs(proc_root="/proc"):
    """Map build harness pid -> owning forge job id for legacy/live processes."""
    found = {}
    try:
        pids = os.listdir(proc_root)
    except OSError:
        return found
    for entry in pids:
        if not entry.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, entry, "cmdline"), "rb") as f:
                argv = [part.decode("utf-8", "replace") for part in f.read().split(b"\0") if part]
        except OSError:
            continue
        if not any(os.path.basename(arg) == "forge_tool_trace.py" for arg in argv):
            continue
        try:
            job_id = argv[argv.index("--job") + 1]
            build_pid = int(argv[argv.index("--pid") + 1])
        except (ValueError, IndexError):
            continue
        if re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
            found[build_pid] = job_id
    return found


def list_active_builds(proc_root="/proc"):
    """All live tome builds, including harnesses owned by another server process."""
    with jobs_lock:
        snapshots = [(bid, dict(j)) for bid, j in jobs.items()
                     if j.get("kind") == "build" and j.get("status") == "running"]
    local = []
    for bid, job in snapshots:
        slug, tid = job.get("slug") or job.get("tome"), job.get("tome")
        try:
            with open(os.path.join(BUILD_DIR, f"{slug}.plan.md"), encoding="utf-8") as handle:
                tid = resolve_working_tid(slug, handle.read())
        except OSError:
            pass
        progress = load_build_progress(slug) or load_build_progress(tid) or {}
        local.append({"id": bid, "tome": tid, "slug": slug, "name": forge_name(tid),
                      "phase": progress.get("phase", job.get("phase")),
                      "phaseTitle": progress.get("phaseTitle", job.get("phaseTitle")),
                      "status": job.get("status"),
                      "totalPhases": job.get("totalPhases", BUILD_TOTAL_PHASES),
                      "external": False})
    claimed = {value for j in local for value in (j.get("slug"), j.get("tome")) if value}
    external = []
    legacy_traces = _live_trace_jobs(proc_root)
    for proc in _live_build_processes(proc_root):
        planid = proc["planid"]
        pp = os.path.join(BUILD_DIR, f"{planid}.plan.md")
        try:
            with open(pp, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        tid = resolve_working_tid(planid, text)
        if planid in claimed or tid in claimed:
            continue
        phase = _resume_phase(planid, tid)
        row = {"id": planid, "tome": tid, "slug": planid,
               "name": forge_name(tid) or tid, "phase": phase,
               "phaseTitle": BUILD_PHASE_TITLES[phase], "status": "running",
               "totalPhases": BUILD_TOTAL_PHASES, "external": True}
        trace_id = load_active_owner(planid, proc["pid"]) or legacy_traces.get(proc["pid"])
        if trace_id:
            row["traceId"] = trace_id
        if proc.get("startedAt") is not None:
            row["startedAt"] = proc["startedAt"]
        external.append(row)
        claimed.update((planid, tid))
    return local + external


def working_is_active(*ids):
    wanted = {i for i in ids if i}
    return any(wanted.intersection((j.get("slug"), j.get("tome")))
               for j in list_active_builds())


def external_build_process(planid, proc_root="/proc"):
    return next((proc for proc in _live_build_processes(proc_root)
                 if proc.get("planid") == planid), None)


def list_workings():
    """Stopped, failed, or cancelled builds worth resuming.

    Durable results are authoritative; Harness ground truth remains only as the legacy
    completion marker for builds that predate result sidecars.
    """
    active = {value for j in list_active_builds()
              for value in (j.get("slug"), j.get("tome")) if value}
    out = []
    for pp in glob.glob(os.path.join(BUILD_DIR, "*.plan.md")):
        planid = os.path.basename(pp)[:-len(".plan.md")]
        try:
            with open(pp, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        result = build_result_status(planid)
        if result and result.get("status") == "done":
            continue
        if not result and "Harness ground truth" in text:  # legacy completed run
            continue
        tid = resolve_working_tid(planid, text)
        if tid in active or planid in active:         # currently being forged, not abandoned
            continue
        launch = _load_launch(tid, planid)
        durable = result or build_result_status(tid) or {}
        failure = str(durable.get("error") or "")
        tooling = tooling_conflict_details(text, failure)
        resume_phase = _resume_phase(planid, tid)
        authors = launch.get("authors") or {}
        phase_key = "phase12" if resume_phase <= 2 else "phase37" if resume_phase <= 7 else "phase8"
        author = authors.get(phase_key) or launch.get("author") or (launch.get("runners") or {}).get(
            str(resume_phase)) or (launch.get("runners") or {}).get("default") or {}
        out.append({"id": planid, "tome": tid, "name": forge_name(tid) or tid,
                    "concept": launch.get("concept") or _plan_concept(text),
                    "phase": resume_phase,
                    "bindery": launch.get("bindery") or {},
                    "author": author,
                    "authors": authors,
                    "validator": launch.get("validator") or {},
                    "reviewer": launch.get("reviewer") or {},
                    "gate": launch.get("gate") or _plan_gate(text),
                    "toolingConflict": tooling["conflict"],
                    "requiredTooling": tooling["required"],
                    "toolingConflictReason": tooling["reason"],
                    "updated": os.path.getmtime(pp)})
    out.sort(key=lambda w: w["updated"], reverse=True)
    return out


def _clear_build_terminal_state(tid):
    """Remove an entire abandoned build namespace before its id is reused."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(tid or "")):
        raise ValueError(f"invalid build id {tid!r}")
    for path in glob.glob(os.path.join(BUILD_DIR, f"{tid}.*")):
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
