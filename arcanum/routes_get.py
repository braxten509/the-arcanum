"""GET /api/* routes + static file serving. `h` is the live Handler instance."""
import json
import os
import urllib.parse
import urllib.request

from runtimes import get as get_runtime, names as runtime_names

from .amender import load_amend_state
from .config import (AGY_BIN, BUILD_DIR, CLAUDE_BIN, CLI_EFFORTS, CLI_MODELS, CODEX_BIN,
                     GLOBAL_SETTINGS, GLOBAL_STATE_KEYS, MIME, OPENCODE_BIN, ROOT, SKINS_DIR,
                     TOMES_DIR, WEB, jobs, jobs_lock, read_json, read_toml)
from .forge import forge_name, list_workings
from .models import agy_models, ollama_bindery_models, opencode_models
from .tomes import (assemble_tome, list_tomes, project_dir, project_name, runtime_for,
                    state_path)


def handle(h):
    path = urllib.parse.urlparse(h.path).path
    if path == "/api/state":
        data = read_json(state_path(h.query_tome()), {})
        g = read_json(GLOBAL_SETTINGS, {})
        for k in GLOBAL_STATE_KEYS:   # reader-wide settings override the tome's copy
            if k in g:
                data[k] = g[k]
        return h.send_json(data)
    if path == "/api/tomes":
        return h.send_json({"tomes": list_tomes()})
    if path == "/api/tome":
        jid = h.query_tome()
        try:
            return h.send_json(assemble_tome(jid))
        except Exception as e:
            return h.send_json({"error": f"failed to load tome {jid!r}: {e}"}, 500)
    if path == "/api/workspace":
        jid = h.query_tome()
        rt, pdir = runtime_for(jid), project_dir(jid)
        files = []
        if os.path.isdir(pdir):
            for rel, content in rt.collect_code(pdir):
                files.append({"path": rel, "content": content})
        exists = os.path.isfile(os.path.join(pdir, rt.project_file(project_name(jid))))
        return h.send_json({"files": files, "exists": exists})
    if path == "/api/checkdir":
        # validate a student-supplied external-editor folder before they enable it
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
        p = os.path.expanduser((q.get("path") or [""])[0])
        return h.send_json({"abs": os.path.isabs(p), "exists": os.path.exists(p),
                            "isdir": os.path.isdir(p)})
    if path == "/api/starterfile":
        # the starter contents of one required file, for previewing/copying into an external editor
        jid = h.query_tome()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
        rel = (q.get("path") or [""])[0]
        rt = runtime_for(jid)
        if not rt.available():
            return h.send_json({"ok": False, "error": f"{rt.LANGUAGE} toolchain not found on this machine"}, 400)
        try:
            return h.send_json({"ok": True, "path": rel,
                                "content": rt.starter_content(project_name(jid), rel)})
        except Exception as e:
            return h.send_json({"ok": False, "error": str(e)[-500:]}, 500)
    if path.startswith("/api/grade/status"):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
        jid = (q.get("id") or [""])[0]
        with jobs_lock:
            job = jobs.get(jid)
        return h.send_json(job or {"status": "unknown"})
    if path.startswith("/api/buildtome/status"):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
        bid = (q.get("id") or [""])[0]
        with jobs_lock:
            job = jobs.get(bid)
            if not job or job.get("kind") != "build":
                out = {"status": "unknown"}
            else:
                out = {k: job[k] for k in ("status", "kind", "tome", "phase", "phaseTitle",
                                           "totalPhases", "startedAt", "error",
                                           "phaseStartedAt", "runner", "sections") if k in job}
                out["name"] = forge_name(job.get("tome"))
                out["logtail"] = "\n".join(job.get("log", [])[-40:])
                req = os.path.join(BUILD_DIR, f"{job.get('slug') or job.get('tome')}.runner-request.json")
                if os.path.exists(req):  # a worker died; the harness is waiting for a pick
                    try:
                        with open(req, encoding="utf-8") as f:
                            out["awaitingRunner"] = json.load(f)
                    except (OSError, ValueError):
                        pass
        return h.send_json(out)
    if path.startswith("/api/amend/status"):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
        aid = (q.get("id") or [""])[0]
        with jobs_lock:
            job = jobs.get(aid)
            out = dict(job) if job and job.get("kind") == "amend" else {"status": "unknown"}
            if "log" in out:  # ship a trimmed tail for the live terminal, not the whole array each poll
                out["logtail"] = "\n".join(out.pop("log")[-200:])
        return h.send_json(out)
    if path == "/api/amend/current":
        # the running amend job for this tome, if any — lets the Binder's bench reattach
        jid = h.query_tome()
        with jobs_lock:
            for aid0, j in jobs.items():
                if j.get("kind") == "amend" and j.get("status") == "running" and j.get("tome") == jid:
                    return h.send_json({"jobId": aid0, "request": j.get("request", ""),
                                        "broad": bool(j.get("broad")), "review": bool(j.get("review"))})
        return h.send_json({})
    if path == "/api/amend/resumable":
        # an amendment cut short (server or runner died mid-run, or it errored) that no
        # live job is still working — the Binder offers to take it up again with any hand.
        jid = h.query_tome()
        st = load_amend_state(jid)
        if st:
            with jobs_lock:
                live = jobs.get(st.get("id"))
                if live and live.get("status") == "running":
                    st = None  # still running here — the bench reattaches via /current instead
        if not st:
            return h.send_json({})
        return h.send_json({"resumable": {
            "tome": jid, "request": st.get("request", ""),
            "broad": bool(st.get("broad")), "iterate": bool(st.get("iterate")),
            "resetOk": bool(st.get("resetOk")), "review": bool(st.get("review")),
            "status": st.get("status", "interrupted"), "startedAt": st.get("startedAt")}})
    if path == "/api/buildtome/active":
        with jobs_lock:
            act = [{"id": bid, "tome": j.get("tome"), "name": forge_name(j.get("tome")), "phase": j.get("phase"),
                    "phaseTitle": j.get("phaseTitle"), "status": j.get("status")}
                   for bid, j in jobs.items()
                   if j.get("kind") == "build" and j.get("status") == "running"]
        return h.send_json({"jobs": act})
    if path == "/api/buildtome/resumable":
        return h.send_json({"workings": list_workings()})
    if path == "/api/health":
        avail = {n: get_runtime(n).available() for n in runtime_names()}
        for j in list_tomes():  # tomes may declare custom command runtimes
            if j.get("runtime") not in avail:
                try:
                    avail[j["runtime"]] = runtime_for(j["id"]).available()
                except Exception:
                    avail[j["runtime"]] = False
        return h.send_json({
            "claude": os.access(CLAUDE_BIN, os.X_OK),
            "runtimes": avail,
        })
    if path == "/api/models":
        return h.send_json(model_census())
    # static files
    if path == "/":
        path = "/index.html"
    rel = path.lstrip("/")
    if rel.startswith("tomes/"):
        base, rel = TOMES_DIR, rel[len("tomes/"):]
    elif rel.startswith("monaco/") or rel.startswith("skins/") or rel.startswith("sounds/") or rel.startswith("global-configs/"):
        base = ROOT
    else:
        base = WEB
    full = os.path.realpath(os.path.join(base, rel))
    jr = os.path.realpath(TOMES_DIR)
    if full.startswith(jr + os.sep):
        parts = full[len(jr) + 1:].split(os.sep)
        if len(parts) > 1 and parts[1] == "save":  # tomes/<jid>/save/** is user data — never serve
            return h.send_json({"error": "not found"}, 404)
    allowed = [os.path.realpath(x) for x in (WEB, TOMES_DIR, os.path.join(ROOT, "monaco"), SKINS_DIR,
                                             os.path.join(ROOT, "sounds"), os.path.join(ROOT, "global-configs"))]
    if not any(full.startswith(a + os.sep) or full == a for a in allowed) or not os.path.isfile(full):
        h.send_json({"error": "not found"}, 404)
        return
    ext = os.path.splitext(full)[1]
    with open(full, "rb") as f:
        body = f.read()
    h.send_response(200)
    h.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-cache" if ext in (".html", ".js", ".css", ".mp3") else "max-age=86400")
    h.end_headers()
    h.wfile.write(body)


def model_census():
    """The full model census the browser pickers are built from: ollama live,
    agy live (it can enumerate), claude/codex from the curated CLI_MODELS
    lists (they can't). `installed` says which login CLIs exist on this rig."""
    installed = {"claude-cli": os.access(CLAUDE_BIN, os.X_OK),
                 "antigravity-cli": os.access(AGY_BIN, os.X_OK),
                 "codex-cli": os.access(CODEX_BIN, os.X_OK)}
    providers = {k: list(v) for k, v in CLI_MODELS.items()}
    if installed["antigravity-cli"]:
        try:
            providers["antigravity-cli"] = agy_models()
        except Exception:
            providers["antigravity-cli"] = []
    else:
        providers["antigravity-cli"] = []
    out = {"ok": True, "models": [], "providers": providers, "installed": installed,
           "efforts": CLI_EFFORTS}
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            data = json.loads(r.read())
        out["models"] = sorted(({"name": m["name"], "gb": round(m.get("size", 0) / 1e9, 1)}
                                for m in data.get("models", [])), key=lambda m: -m["gb"])
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)
    # `bindery`: the ordered provider list the FORGE-A-TOME pickers build from — each a
    # [PROVIDER][MODEL][EFFORT] triple-box. models are [id, label, tag] triples. Separate
    # from `providers`/`models` above (which the settings grader/oracle pickers still use),
    # so this can carry opencode + local without polluting the grader backends.
    oc_ok = os.access(OPENCODE_BIN, os.X_OK)
    oc_models = opencode_models() if oc_ok else []
    local_models = ollama_bindery_models() if oc_ok else []  # local runs THROUGH opencode
    # each model row is [id, label, tag, efforts]. effort is PER-MODEL: claude/codex
    # take their CLI's effort list on every model; opencode is per-model from
    # models.dev; antigravity/local take none.
    rows = lambda ms, ef: [[m, m, "", list(ef)] for m in ms]
    out["bindery"] = [
        {"id": "claude-cli", "label": "Claude CLI", "kind": "claude-cli",
         "models": rows(CLI_MODELS["claude-cli"], CLI_EFFORTS["claude-cli"]),
         "installed": installed["claude-cli"]},
        {"id": "antigravity-cli", "label": "Antigravity CLI", "kind": "antigravity-cli",
         "models": rows(providers["antigravity-cli"], []),
         "installed": installed["antigravity-cli"]},
        {"id": "codex-cli", "label": "Codex CLI", "kind": "codex-cli",
         "models": rows(CLI_MODELS["codex-cli"], CLI_EFFORTS["codex-cli"]),
         "installed": installed["codex-cli"]},
        {"id": "opencode-cli", "label": "OpenCode CLI", "kind": "opencode-cli",
         "models": oc_models, "installed": oc_ok},
        {"id": "local", "label": "Local", "kind": "opencode-cli",
         "models": local_models, "installed": oc_ok and bool(local_models)},
    ]
    # `quality`: the CHEAP<->QUALITY slider tiers from harness.toml [quality.q1..q5],
    # ordered cheapest first. Each carries a per-phase runner map the browser applies
    # to the hand knobs; missing/broken TOML just hides the slider.
    try:
        q = read_toml(os.path.join(ROOT, "harness.toml")).get("quality") or {}
        out["quality"] = [dict(q[k], id=k) for k in sorted(q)]
    except Exception:
        out["quality"] = []
    return out
