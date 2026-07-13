"""Tome-forge build jobs: launching/watching builds, Pushover pings, and
resuming abandoned builds. Build jobs live in the shared config.jobs registry
with "kind": "build"."""
import glob
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request

from .config import BUILD_DIR, CLI_EFFORTS, TOMES_DIR, jobs, jobs_lock, read_settings
from .build_state import (BUILD_PHASE_TITLES, BUILD_TOTAL_PHASES, build_result_status,
                          cancelled_build_status, load_active_owner, record_build_result,
                          remove_active_owner)
from .tomes import load_manifest, resolve_working_tid
from .tool_trace import mirror_tool_trace

# The harness's banner always starts "> Phase N — …"; the ">" is REQUIRED so a worker
# narrating "Phase 3 — s02 complete…" in its own output can't hijack the phase title.
BUILD_PHASE_RE = re.compile(r"^\s*>\s*Phase (\d+)\s*—\s*(.+?)(?:\s+\[runner|$)")
# Worker CLIs color their output; the browser log is plain text, where the ESC byte is
# invisible and leaves "[0m" litter. Strip CSI/OSC sequences and stray control chars.
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.|[\x00-\x08\x0b-\x1f\x7f]")
# Phase 2 renames the tome folder from the launch slug to the themed kebab id
# (build_tome.py maybe_rename prints this). Track it or forge_name reads a dead folder.
BUILD_RENAME_RE = re.compile(r"renamed tomes/\S+ -> tomes/(\S+)")
# Split-sections progress: "· authoring s03 [3/8] on <runner>" / "· resuming s02 [2/8] …"
# / "· section s01 [1/8] already authored — skipping"
BUILD_SECTION_RE = re.compile(r"^\s*·\s+(?:authoring|resuming|section)\s+s\d+\s+\[(\d+)/(\d+)\]")
BUILD_RUNNER_RE = re.compile(r"\[runner: ([^\]]+)\]")
# The runner's stdout also contains patches, generated prose, token counters, and CLI
# narration. Keep that raw tail for failure diagnostics, but give the live terminal only
# harness-authored progress signals. Anchored phrases prevent arbitrary worker prose from
# masquerading as forge status just because it begins with a bullet or punctuation mark.
BUILD_STATUS_RE = re.compile(
    r"^(?:"
    r">\s*Phase\s+\d+\s+—|"
    r"===\s*Phase\s+0\b|"
    r"·\s*(?:AI access Phase 0|forecast:|reset tomes/|split-sections:|"
    r"(?:authoring|resuming|section)\s+s\d+|shrinkage justified|renamed tomes/|liveness ping)|"
    r"(?:ok|FAIL)\s+|"
    r"!\s*(?:runner|worker|section|Phase|naming)\b|"
    r"x\s*(?:gates failed|Phase|section)\b|"
    r"⇒\s+|↻\s+|~\s*student verdict\b|⏸\s*phase\b|"
    r"==\s*all phases complete\b|AI ACCESS PHASE 0 FAILED\b|->\s*wrote\b)"
)


def forge_status_line(line):
    """Return a concise, display-safe forge status line, or None for raw runner chatter."""
    clean = line.strip()
    return clean if clean and BUILD_STATUS_RE.match(clean) else None


def fresh_tome_id(name):
    """Slugify a course name into an unused tomes/<id> — the harness's Phase 2 runs
    new_tome.py, which refuses an existing dir, so the id must be fresh (including
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


# ---- Pushover: ping the operator when a build needs them or ends, so they can wander off
# mid-forge. Creds live in global-configs/settings.toml under [pushover] token/user — the
# same file as the AI API keys — or PUSHOVER_TOKEN/PUSHOVER_USER in the env. No creds → no-op.
def _pushover_creds():
    tok, usr = os.environ.get("PUSHOVER_TOKEN"), os.environ.get("PUSHOVER_USER")
    if not (tok and usr):
        p = read_settings().get("pushover") or {}
        tok, usr = tok or p.get("token"), usr or p.get("user")
    return (tok, usr) if tok and usr else None


def notify(title, message, priority=0):
    """Fire-and-forget Pushover push (own thread, so a slow/failed send never blocks or breaks
    a build). priority=1 bypasses the phone's quiet hours — use it for anything needing a hand."""
    creds = _pushover_creds()
    if not creds:
        return
    tok, usr = creds
    def _send():
        try:
            data = urllib.parse.urlencode({"token": tok, "user": usr, "title": title[:250],
                                           "message": message[:1024], "priority": priority}).encode()
            urllib.request.urlopen("https://api.pushover.net/1/messages.json", data=data, timeout=10)
        except Exception as e:
            print(f"pushover: {e}", file=sys.stderr)
    threading.Thread(target=_send, daemon=True).start()


def watch_build(gid, proc):
    """Reader thread: stream harness stdout into the job, tracking '> Phase N — title' lines."""
    # stdout is the deliberately concise forge narration. The AI CLI's own JSONL is the
    # source of truth for real Bash/read/patch calls, mirrored separately into three UI rows.
    if getattr(proc, "pid", None):
        threading.Thread(target=mirror_tool_trace, args=(gid, proc.pid), daemon=True).start()
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
                job["phaseStartedAt"] = time.time()   # the overlay shows time-in-phase from this
                job.pop("sections", None)             # per-phase; only phase 3 repopulates it
                r = BUILD_RUNNER_RE.search(line)
                if r:
                    job["runner"] = r.group(1)
                _write_progress(job.get("tome"), job["phase"])  # so a later resume restarts here
            sec = BUILD_SECTION_RE.match(line)
            if sec:
                job["sections"] = f"{sec.group(1)}/{sec.group(2)}"
                r = re.search(r"\bon (.+)$", line)    # split workers can differ from the phase runner
                if r:
                    job["runner"] = r.group(1)
            rn = BUILD_RENAME_RE.search(line)
            if rn:
                job["tome"] = rn.group(1)  # follow the Phase 2 rename so the UI picks up the themed meta.name
            pause = line.lstrip().startswith("⏸")  # request_runner blocked for a human pick (death/gate)
            tnow = job.get("tome")
        if pause:  # outside the lock — notify never blocks, forge_name reads a file
            notify(f"⏸ {forge_name(tnow) or tnow or 'A tome'} needs you", line.strip(), priority=1)
    rc = proc.wait()
    tome = tail = final = slug = phase_title = failure = None
    phase = 0
    with jobs_lock:
        job = jobs.get(gid)
        slug = (job.get("slug") or job.get("tome")) if job else None
        if job and job.get("status") == "running":  # cancel sets its own status first
            externally_cancelled = bool(slug and cancelled_build_status(slug))
            job["status"] = "cancelled" if externally_cancelled else ("done" if rc == 0 else "error")
            if rc != 0 and not externally_cancelled:
                job["error"] = "\n".join(job["log"][-30:])
        if job:
            final, tome, tail = job.get("status"), job.get("tome"), "\n".join(job.get("log", [])[-6:])
            phase, phase_title, failure = job.get("phase", 0), job.get("phaseTitle", ""), job.get("error", "")
    if slug:
        remove_active_owner(slug)
        if final in ("done", "error", "cancelled"):
            record_build_result(slug, tome, final, phase, phase_title, failure)
    nm = forge_name(tome) or tome or "The tome"
    if final == "done":
        notify("✓ Tome forged", f"{nm} finished — ready in the Bindery.")
    elif final == "error":  # a user cancel sets status 'cancelled', so this only fires on real failures
        notify("✗ Forge failed", f"{nm} stopped:\n{tail}", priority=1)


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


def _save_launch(tid, body, concept):
    # gate answers ride along so a resume can DISPLAY them (they are fixed once Phase 0
    # ran); a resume POST carries none — keep the ones from the original launch then.
    gate = {k: str(body.get(k) or "").strip()
            for k in ("prior_knowledge", "prior_level", "breadth", "depth", "mastery", "tooling")}
    if not any(gate.values()):
        gate = _load_launch(tid).get("gate") or {}
    try:
        with open(os.path.join(BUILD_DIR, f"{tid}.launch.json"), "w", encoding="utf-8") as f:
            json.dump({"bindery": body.get("bindery") or {}, "concept": concept,
                       "sectionsSplit": bool(body.get("sectionsSplit")), "gate": gate}, f)
    except OSError:
        pass


def _plan_gate(text):
    """Gate answers parsed back out of a plan's '- **Label:** value' lines — the fallback
    for workings launched before launch.json carried them."""
    out = {}
    for key, label in (("prior_knowledge", "Prior knowledge"), ("prior_level", "Starting level"),
                       ("breadth", "Breadth"),
                       ("depth", "(?:Lesson depth|Scope / depth)"), ("mastery", "Mastery"),
                       ("tooling", "Tooling")):
        m = re.search(rf"(?im)^- \*\*{label}[^:]*?:\*\*\s*(.+)$", text)
        if m:
            out[key] = m.group(1).strip()
    return out


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
        local = [{"id": bid, "tome": j.get("tome"), "slug": j.get("slug") or j.get("tome"),
                  "name": forge_name(j.get("tome")), "phase": j.get("phase"),
                  "phaseTitle": j.get("phaseTitle"), "status": j.get("status"),
                  "totalPhases": j.get("totalPhases", BUILD_TOTAL_PHASES), "external": False}
                 for bid, j in jobs.items()
                 if j.get("kind") == "build" and j.get("status") == "running"]
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
        out.append({"id": planid, "tome": tid, "name": forge_name(tid) or tid,
                    "concept": launch.get("concept") or _plan_concept(text),
                    "phase": _resume_phase(planid, tid),
                    "bindery": launch.get("bindery") or {},
                    "gate": launch.get("gate") or _plan_gate(text),
                    "sectionsSplit": bool(launch.get("sectionsSplit")),
                    "updated": os.path.getmtime(pp)})
    out.sort(key=lambda w: w["updated"], reverse=True)
    return out


def _runner_args(body):
    """The bindery's {phase: {kind, model, effort}} picks -> build_tome.py --runner flags
    (effort rides as an @suffix). Malformed entries are dropped rather than failing the build."""
    args = []
    for key, rv in (body.get("runners") or {}).items():
        kind = str((rv or {}).get("kind") or "")
        mdl = str((rv or {}).get("model") or "")
        eff = str((rv or {}).get("effort") or "")
        if eff and eff in CLI_EFFORTS.get(kind, ()):
            mdl += "@" + eff
        if re.fullmatch(r"default|\d", str(key)) and mdl and \
                kind in ("claude-cli", "antigravity-cli", "codex-cli", "opencode-cli"):
            args += ["--runner", f"{key}={kind}:{mdl}"]
    return args


def _clear_runner_handshake(tid):
    for stale in ("runner-request", "runner-reply", "cancelled", "result"):
        try:
            os.remove(os.path.join(BUILD_DIR, f"{tid}.{stale}.json"))
        except OSError:
            pass
