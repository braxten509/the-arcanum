#!/usr/bin/env python3
"""ARCANUM server — stdlib only. Serves the game, discovers/assembles Tomes,
persists per-tome state, runs code via pluggable runtimes, grades via claude CLI."""
import difflib
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tome_layout  # shared split-tome layout, kept in lockstep with tools/validate_tome.py

from runtimes import (common as rt_common, for_config as runtime_for_config, get as get_runtime,
                      names as runtime_names, resolve_config as resolve_runtime_config)
from runtimes.common import atomic_write, clip

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
TOMES_DIR = os.path.join(ROOT, "tomes")
SKINS_DIR = os.path.join(ROOT, "skins")          # global TOML-defined skins (tome-independent)
CACHE_DIR = os.path.join(ROOT, ".cache")         # ephemera only: snippet scratch, server.log
PORT = 8777

GRADER_MODELS = ["claude-opus-4-8", "opus"]  # first that works wins
CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
GEMINI_BIN = shutil.which("gemini") or os.path.expanduser("~/.local/bin/gemini")
CODEX_BIN = shutil.which("codex") or os.path.expanduser("~/.local/bin/codex")
GRADE_TIMEOUT = 420  # seconds for claude grading

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(TOMES_DIR, exist_ok=True)

# ---------------------------------------------------------------- utilities


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def read_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------- tomes

_manifest_cache = {}  # jid -> (mtime, manifest dict)


def tome_dir(jid):
    jid = (jid or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", jid):
        raise ValueError("bad tome id")
    return os.path.join(TOMES_DIR, jid)


def load_manifest(jid):
    path = os.path.join(tome_dir(jid), "tome.toml")
    mt = os.path.getmtime(path)
    cached = _manifest_cache.get(jid)
    if not cached or cached[0] != mt:
        m = read_toml(path)
        _manifest_cache[jid] = (mt, m)
        return m
    return cached[1]


def list_tomes():
    out = []
    for path in sorted(glob.glob(os.path.join(TOMES_DIR, "*", "tome.toml"))):
        jid = os.path.basename(os.path.dirname(path))
        try:
            m = read_toml(path)
        except Exception:
            continue
        meta = dict(m.get("meta", {}))
        meta.setdefault("id", jid)
        meta["id"] = jid
        meta["runtime"] = m.get("runtime", {}).get("name", "custom")
        meta["sectionCount"] = len(m.get("content", {}).get("sections", []))
        out.append(meta)
    return out


def list_skins():
    """skins/<id>/skin.toml → [{id, name, desc, vars, css}]. A skin is a global
    palette + optional structural CSS; assets beside it are served at /skins/<id>/."""
    out = []
    for path in sorted(glob.glob(os.path.join(SKINS_DIR, "*", "skin.toml"))):
        try:
            s = read_toml(path)
        except Exception:
            continue
        s["id"] = os.path.basename(os.path.dirname(path))
        out.append(s)
    return out


def resolve_tome(hint):
    """Return a valid tome id: the requested one if it exists, else the first installed."""
    try:
        if hint and os.path.isfile(os.path.join(tome_dir(hint), "tome.toml")):
            return hint
    except ValueError:
        pass
    js = list_tomes()
    return js[0]["id"] if js else "verisearch"


def assemble_tome(jid):
    """Manifest + ordered section TOMLs + attacks TOML → one JSON payload for the client."""
    m = load_manifest(jid)
    if not str(m.get("narrative", {}).get("objective", "")).strip():
        raise ValueError(f"tome {jid!r}: [narrative] objective is required — "
                         "state what the whole tome builds toward (shown on the Operative File)")
    jdir = tome_dir(jid)
    sections = []
    for sid in m.get("content", {}).get("sections", []):
        sections.append(tome_layout.load_section(jdir, sid))  # folder or flat section
    attacks = []
    ap = os.path.join(jdir, m.get("content", {}).get("attacks", "generated/attacks.toml"))
    if os.path.isfile(ap):
        attacks = read_toml(ap).get("tiers", [])
    payload = tome_layout.merge_banks(dict(m), jdir)  # fold in themes/shop/badges/intrusions siblings
    payload["runtime"] = resolve_runtime_config(m.get("runtime", {}))  # language-toml defaults merged in
    payload["sections"] = sections
    payload["attacks"] = attacks
    payload["skins"] = list_skins()
    return payload


def runtime_for(jid):
    return runtime_for_config(load_manifest(jid).get("runtime", {}))


def project_name(jid):
    return load_manifest(jid).get("runtime", {}).get("project", "Project")


def save_dir(jid):
    """tomes/<jid>/save — ALL user progress for a tome. Recreated on demand,
    so deleting it (even while the server runs) resets that course. Never served."""
    d = os.path.join(tome_dir(jid), "save")
    os.makedirs(d, exist_ok=True)
    return d


def external_workspace(jid):
    """An ABSOLUTE path to a project the player manages with their OWN tools
    (IntelliJ, a Gradle mod project…). Two sources, author wins: a tome's
    [runtime] workspaceDir (course-designed external mode), else the student's
    own opt-in stored in state.json (any tome can be switched to their editor via
    the workbench). Runs, diagnostics and grading operate on it; the engine never
    scaffolds or resets it. Empty string = use the engine's scaffolded workspace."""
    p = load_manifest(jid).get("runtime", {}).get("workspaceDir", "")
    if p:
        p = os.path.expanduser(p)
        if not os.path.isabs(p):
            raise ValueError("[runtime] workspaceDir must be an absolute path")
        return p
    # student opt-in — defensive: a bad saved path must not brick the tome, so a
    # non-absolute or missing directory silently falls back to the scaffolded one.
    ws = read_json(state_path(jid), {}).get("workspace") or {}
    if ws.get("enabled"):
        d = os.path.expanduser(ws.get("dir") or "")
        if os.path.isabs(d) and os.path.isdir(d):
            return d
    return ""


def project_dir(jid):
    return external_workspace(jid) or os.path.join(save_dir(jid), "workspace", project_name(jid))


def state_path(jid):
    return os.path.join(save_dir(jid), "state.json")


def has_progress(s):
    """True if a save holds real play, not just settings. `earned` is cumulative
    (never spent down), so it survives even a broke wizard; the collections cover
    a save that only read a chapter or graded a working."""
    if not isinstance(s, dict):
        return False
    if s.get("earned") or s.get("credits"):
        return True
    return any(s.get(k) for k in ("ex", "read", "badges", "fs"))


def grades_dir(jid):
    d = os.path.join(save_dir(jid), "grades")
    os.makedirs(d, exist_ok=True)
    return d


def scratch_base(rt_name):
    return os.path.join(CACHE_DIR, "snippet", rt_name)


def write_files(jid, files):
    """Persist [{path,content}] into a tome's workspace project, refusing path escapes."""
    pdir = project_dir(jid)
    for f in files or []:
        full = rt_common.safe_join(pdir, f["path"])
        os.makedirs(os.path.dirname(full), exist_ok=True)
        atomic_write(full, f["content"])


# ---------------------------------------------------------------- grading jobs

jobs = {}  # id -> {status, result, error}
jobs_lock = threading.Lock()


def extract_json(text):
    """Pull the first JSON object out of possibly-noisy LLM text."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in grader output")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced JSON in grader output")


def build_grade_prompt(payload, files, prev, rt, pdir):
    section = payload.get("sectionTitle", "")
    brief = payload.get("brief", "")
    rubric = payload.get("rubric", [])
    language = payload.get("language") or getattr(rt, "LANGUAGE", None) or rt.NAME
    persona = payload.get("persona") or "THE MAGISTER"
    student = payload.get("studentTerm") or "apprentice"
    scale = payload.get("gradeScale") or "S|A|B|C|D|F"
    build_label = payload.get("buildLabel") or f"{rt.NAME} build"  # no per-language branch; the runtime names itself
    build_out = rt.try_build(pdir)

    parts = [
        f"You are the grader inside a {language} learning game. A student learning {language} submitted their "
        "freestyle project for the section below. Grade it strictly against the rubric.",
        "",
        f"SECTION: {section}",
        f"ASSIGNMENT BRIEF: {brief}",
        "",
        "HOW TO READ THE BRIEF: it is written in the game's in-world, themed voice. Grade every "
        "requirement by its INTENT, not its literal flavor wording. A requirement is a hard, exact "
        "spec ONLY when it is stated concretely — an exact output string in quotes or code font, a "
        "named command/token, or an explicit word like 'exactly'. Where wording is atmospheric or "
        "vague, accept any reasonable implementation and do NOT dock points for not matching the "
        "flavor. Resolve ambiguity in the student's favor and lean on the rubric below.",
        "",
    ]
    parts.append("RUBRIC (score each criterion 0-10; weights sum to 100):")
    for r in rubric:
        parts.append(f"- [{r['weight']}%] {r['criterion']}: {r['desc']}")
    parts.append("")
    parts.append(
        f"CONVENTIONS & IDIOM: where a criterion concerns style, readability, or craft, judge it against "
        f"real-world {language} conventions — idiomatic naming and casing, brace/layout style, consistent "
        "formatting, and idiomatic use of the constructs this section teaches. Anchor these judgments in "
        f"the language's official or de-facto community style guide (for example: Microsoft's C# Coding "
        "Conventions, PEP 8 for Python, gofmt for Go, the Ruby Style Guide) — recall that guide and apply "
        "it. Judge only conventions you are certain that guide states; never invent house rules or import "
        "another language's style. Name each convention breach concretely in that criterion's comment and "
        "state the pattern to follow, so the student learns the convention, not just the score. Expect "
        "only the conventions a learner at this section could know.")
    parts.append("")
    parts.append(f"COMPILER OUTPUT of `{build_label}`:\n{build_out[:4000]}")
    parts.append("")
    parts.append("STUDENT CODE (entire workspace):")
    for rel, content in files:
        parts.append(f"\n===== FILE: {rel} =====\n{content[:20000]}")
    if prev and prev.get("result", {}).get("scores"):
        parts.append("\nPREVIOUS SUBMISSION: this student already had this project graded. Previous scores:")
        for s in prev["result"]["scores"]:
            parts.append(f"- {s.get('criterion')}: {s.get('score')}/10 — {s.get('comment', '')}")
        old, cur = prev.get("files", {}), dict(files)
        diff = []
        for name in sorted(set(old) | set(cur)):
            if old.get(name, "") != cur.get(name, ""):
                diff += difflib.unified_diff(old.get(name, "").splitlines(), cur.get(name, "").splitlines(),
                                             fromfile="previous/" + name, tofile="current/" + name, lineterm="")
        parts.append("\nDIFF since the previously graded submission:")
        parts.append("\n".join(diff)[:20000] or "(no changes)")
        parts.append(
            "\nSCORE STABILITY RULE (mandatory): a criterion's score MUST be exactly the previous score "
            "unless the diff above changes code relevant to that criterion. Never raise or lower a criterion "
            "the diff does not touch. Only re-judge what actually changed.")
    parts.append("""
Respond with ONLY a JSON object, no prose before or after, exactly this shape:
{
  "scores": [{"criterion": "<name>", "score": <0-10>, "comment": "<1-2 sentences, direct, specific>"}],
  "total": <0-100 weighted total>,
  "grade": "<%SCALE%>",  // S=flawless+elegant, A>=90, B>=80, C>=70, D>=60, F<60
  "feedback": "<3-6 sentences of overall feedback in the voice of a gruff but fair ops mentor codenamed %PERSONA%. Address the student as '%STUDENT%'. Be specific about what to improve. No spoiler solutions.>",
  "bestLine": "<quote the single best line/idea in their code, or empty string>"
}
Grade honestly. A beginner who met every goal with working, readable code deserves an A.
Reserve S for code that would pass review from a senior %LANG% dev. Do not inflate.
Grade code and observable behavior ONLY. Do NOT deduct for tone, phrasing, verbosity, or stylistic
wording of the program's output text (e.g. a message feeling "redundant" or off-tone versus the brief) —
if the required output elements are present and correct, that aspect earns full marks. Deduct only for
missing or broken functionality, bugs, or code-quality issues the rubric explicitly names."""
                 .replace("%SCALE%", scale).replace("%PERSONA%", persona)
                 .replace("%STUDENT%", student).replace("%LANG%", language))
    return "\n".join(parts)


FALLBACK_GRADER = "qwen2.5:14b"  # strongest installed Ollama model; overridable per-request from settings


def grade_with_ollama(prompt, model):
    """Local grading fallback when the claude CLI is unavailable or out of usage."""
    body = json.dumps({
        "model": model,
        "prompt": prompt + "\n\nRespond with ONLY the JSON grade object — no prose before or after.",
        "stream": False, "keep_alive": 0,
        "options": {"temperature": 0.2, "num_ctx": 16384},
    }).encode()
    req = urllib.request.Request(ORACLE_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=GRADE_TIMEOUT) as r:
        data = json.loads(r.read())
    return extract_json(data.get("response", ""))


def grade_with_claude_cli(prompt, model):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    p = subprocess.run(
        [CLAUDE_BIN, "-p", "--model", model, "--tools", ""],
        input=prompt, capture_output=True, text=True,
        timeout=GRADE_TIMEOUT, env=env, cwd=CACHE_DIR)
    if p.returncode != 0:
        raise RuntimeError(f"exit {p.returncode}: {p.stderr[:500]}")
    return extract_json(p.stdout)


def grade_with_gemini_cli(prompt, model):
    """Gemini CLI in headless mode: prompt piped to stdin, JSON parsed from stdout.
    Uses the user's `gemini` login — no API key, mirroring the claude CLI path."""
    args = [GEMINI_BIN, "-p", ""] + (["-m", model] if model else [])
    p = subprocess.run(args, input=prompt, capture_output=True, text=True,
                       timeout=GRADE_TIMEOUT, cwd=CACHE_DIR)
    if p.returncode != 0:
        raise RuntimeError(f"exit {p.returncode}: {p.stderr[:500]}")
    return extract_json(p.stdout)


def grade_with_codex_cli(prompt, model):
    """Codex CLI (ChatGPT login) non-interactively: prompt on stdin, JSON from stdout.
    Read-only sandbox so the grading agent can't touch the disk; empty model uses the
    user's ~/.codex config default."""
    args = [CODEX_BIN, "exec", "--skip-git-repo-check", "-s", "read-only"] + \
        (["-m", model] if model else []) + ["-"]
    p = subprocess.run(args, input=prompt, capture_output=True, text=True,
                       timeout=GRADE_TIMEOUT, cwd=CACHE_DIR)
    if p.returncode != 0:
        raise RuntimeError(f"exit {p.returncode}: {p.stderr[:500]}")
    return extract_json(p.stdout)


def grade_with_command(prompt, command):
    """Any AI CLI the user configures ('Other' provider): the grading prompt is piped
    to the command's stdin, the JSON grade is parsed from its stdout. Runs via the
    shell so the user can supply flags/pipes; cwd is the isolated cache dir."""
    if not command.strip():
        raise ValueError("no command configured")
    p = subprocess.run(command, shell=True, input=prompt, capture_output=True, text=True,
                       timeout=GRADE_TIMEOUT, cwd=CACHE_DIR)
    if p.returncode != 0:
        raise RuntimeError(f"exit {p.returncode}: {p.stderr[:500]}")
    return extract_json(p.stdout)


def grade_with_anthropic(prompt, model, key):
    body = json.dumps({"model": model, "max_tokens": 4096,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=GRADE_TIMEOUT) as r:
        data = json.loads(r.read())
    return extract_json("".join(b.get("text", "") for b in data.get("content", [])))


def grade_with_openai(prompt, model, key):
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=GRADE_TIMEOUT) as r:
        data = json.loads(r.read())
    return extract_json(data["choices"][0]["message"]["content"])


def run_grader(job_id, payload, jid):
    # jid comes from the request handler (query param) — the body has no tome key,
    # so resolving here again would misroute grading to the first installed tome
    rt = runtime_for(jid)
    pdir = project_dir(jid)
    gdir = grades_dir(jid)
    sid = payload.get("sectionId", "x")
    files = rt.collect_code(pdir)
    ws_hash = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    last_path = os.path.join(gdir, f"last-{sid}.json")
    last = read_json(last_path, None)

    g = payload.get("grader") or {}
    kind, model, key = g.get("kind", "claude-cli"), g.get("model", ""), g.get("key", "")
    command = g.get("command", "")  # only used by the "other" (custom CLI) provider
    grader_sig = f"{kind}/{model}"  # recorded with the judgement; NOT part of the cache key

    # identical code to the last judged submission → the same grade stands, even if the
    # selected grader changed since: re-judging unchanged work would only churn scores.
    # (the card labels these "the prior judgement stands", naming the model that judged.
    # to force a second opinion, edit the code or delete save/grades/last-<sid>.json)
    if last and last.get("hash") == ws_hash and last.get("result"):
        result = dict(last["result"])
        result["cached"] = True
        with jobs_lock:
            jobs[job_id] = {"status": "done", "result": result}
        return

    prompt = build_grade_prompt(payload, files, last, rt, pdir)
    last_err = "no model attempted"

    def finish(result, model):
        result["model"] = model
        result["gradedAt"] = time.time()
        with jobs_lock:
            jobs[job_id] = {"status": "done", "result": result}
        atomic_write(os.path.join(gdir, f"{sid}-{int(time.time())}.json"),
                     json.dumps(result, indent=2))
        atomic_write(last_path, json.dumps(
            {"hash": ws_hash, "grader": grader_sig, "files": dict(files), "result": result}, indent=2))

    if kind == "claude-cli":
        attempts = [("claude-cli", m, "") for m in ([model] if model else GRADER_MODELS)]
    else:
        attempts = [(kind, model, key)]

    graders = {"claude-cli": lambda: grade_with_claude_cli(prompt, model),
               "gemini-cli": lambda: grade_with_gemini_cli(prompt, model),
               "codex-cli": lambda: grade_with_codex_cli(prompt, model),
               "anthropic": lambda: grade_with_anthropic(prompt, model, key),
               "openai": lambda: grade_with_openai(prompt, model, key),
               "ollama": lambda: grade_with_ollama(prompt, model),
               "other": lambda: grade_with_command(prompt, command)}
    for kind, model, key in attempts:
        try:
            if kind not in graders:
                raise ValueError(f"unknown grader kind {kind!r}")
            return finish(graders[kind](), model)
        except subprocess.TimeoutExpired:
            last_err = f"{kind}/{model}: timed out after {GRADE_TIMEOUT}s"
        except Exception as e:
            last_err = f"{kind}/{model}: {str(e)[:500]}"

    # main grader failed — fall back to the local model (unless that IS what just failed)
    fb = payload.get("fallbackModel") or FALLBACK_GRADER
    if not (kind == "ollama" and model == fb):
        try:
            return finish(grade_with_ollama(prompt, fb), fb + " (local fallback)")
        except Exception as e:
            last_err += f"; ollama {fb}: {str(e)[:300]}"
    with jobs_lock:
        jobs[job_id] = {"status": "error", "error": last_err}


# ---------------------------------------------------------------- oracle

ORACLE_MODEL = "llama3.1:8b"
ORACLE_URL = "http://localhost:11434/api/generate"


def ask_oracle(question, context, model=None, language="code"):
    """One question to the locally-running Ollama model. Returns text or a friendly error."""
    model = model or ORACLE_MODEL
    prompt = (
        f"You are the ORACLE, a terse mentor spirit dwelling in a crystal ball inside an arcane {language} learning game. "
        f"The student is learning {language} by building a CLI tool. Answer their question clearly and "
        "concisely (a few short paragraphs max, code snippets welcome). Do NOT write whole "
        "solutions to their assignments — explain concepts and point them the right way.\n"
        f"CURRENT LESSON CONTEXT: {context[:12000]}\n\nSTUDENT QUESTION (they are programming in {language}): {question[:2000]}"
    )
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "keep_alive": 0, "options": {"temperature": 0.4}}).encode()
    req = urllib.request.Request(ORACLE_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
        return {"ok": True, "answer": data.get("response", "").strip() or "(the oracle said nothing)",
                "model": model}
    except Exception as e:
        return {"ok": False, "answer": f"THE ORB IS DARK — is Ollama running? ({e})"}


# ---------------------------------------------------------------- HTTP

MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2",
        ".ttf": "font/ttf", ".map": "application/json", ".png": "image/png", ".toml": "text/plain"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if "/api/state" not in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def query_tome(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return resolve_tome((q.get("tome") or [""])[0])

    # ---- GET
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/state":
            return self.send_json(read_json(state_path(self.query_tome()), {}))
        if path == "/api/tomes":
            return self.send_json({"tomes": list_tomes()})
        if path == "/api/tome":
            jid = self.query_tome()
            try:
                return self.send_json(assemble_tome(jid))
            except Exception as e:
                return self.send_json({"error": f"failed to load tome {jid!r}: {e}"}, 500)
        if path == "/api/workspace":
            jid = self.query_tome()
            rt, pdir = runtime_for(jid), project_dir(jid)
            files = []
            if os.path.isdir(pdir):
                for rel, content in rt.collect_code(pdir):
                    files.append({"path": rel, "content": content})
            exists = os.path.isfile(os.path.join(pdir, rt.project_file(project_name(jid))))
            return self.send_json({"files": files, "exists": exists})
        if path == "/api/checkdir":
            # validate a student-supplied external-editor folder before they enable it
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            p = os.path.expanduser((q.get("path") or [""])[0])
            return self.send_json({"abs": os.path.isabs(p), "exists": os.path.exists(p),
                                   "isdir": os.path.isdir(p)})
        if path == "/api/starterfile":
            # the starter contents of one required file, for previewing/copying into an external editor
            jid = self.query_tome()
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            rel = (q.get("path") or [""])[0]
            rt = runtime_for(jid)
            if not rt.available():
                return self.send_json({"ok": False, "error": f"{rt.LANGUAGE} toolchain not found on this machine"}, 400)
            try:
                return self.send_json({"ok": True, "path": rel,
                                       "content": rt.starter_content(project_name(jid), rel)})
            except Exception as e:
                return self.send_json({"ok": False, "error": str(e)[-500:]}, 500)
        if path.startswith("/api/grade/status"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            jid = (q.get("id") or [""])[0]
            with jobs_lock:
                job = jobs.get(jid)
            return self.send_json(job or {"status": "unknown"})
        if path == "/api/health":
            avail = {n: get_runtime(n).available() for n in runtime_names()}
            for j in list_tomes():  # tomes may declare custom command runtimes
                if j.get("runtime") not in avail:
                    try:
                        avail[j["runtime"]] = runtime_for(j["id"]).available()
                    except Exception:
                        avail[j["runtime"]] = False
            return self.send_json({
                "claude": os.access(CLAUDE_BIN, os.X_OK),
                "runtimes": avail,
            })
        if path == "/api/models":
            try:
                with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
                    data = json.loads(r.read())
                models = sorted(({"name": m["name"], "gb": round(m.get("size", 0) / 1e9, 1)}
                                 for m in data.get("models", [])), key=lambda m: -m["gb"])
                return self.send_json({"ok": True, "models": models})
            except Exception as e:
                return self.send_json({"ok": False, "models": [], "error": str(e)})
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
                return self.send_json({"error": "not found"}, 404)
        allowed = [os.path.realpath(x) for x in (WEB, TOMES_DIR, os.path.join(ROOT, "monaco"), SKINS_DIR,
                                                 os.path.join(ROOT, "sounds"), os.path.join(ROOT, "global-configs"))]
        if not any(full.startswith(a + os.sep) or full == a for a in allowed) or not os.path.isfile(full):
            self.send_json({"error": "not found"}, 404)
            return
        ext = os.path.splitext(full)[1]
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache" if ext in (".html", ".js", ".css", ".mp3") else "max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    # ---- POST
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self.read_body()
        except (ValueError, json.JSONDecodeError):
            return self.send_json({"error": "bad json"}, 400)
        # tome scoping: prefer the ?tome= query param (added by the client fetch shim),
        # fall back to a "tome" key in the body (used by tools like gen_attacks.py)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        hint = (q.get("tome") or [None])[0] or (body.get("tome") if isinstance(body, dict) else None)
        jid = resolve_tome(hint)
        try:
            if path == "/api/state":
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
                    return self.send_json({"ok": False, "error": "refused: would erase progress", "kept": True}, 409)
                if has_progress(old):
                    atomic_write(p + ".bak", json.dumps(old, indent=1))
                atomic_write(p, json.dumps(body, indent=1))
                return self.send_json({"ok": True, "savedAt": time.time()})
            if path == "/api/workspace":
                write_files(jid, body.get("files", []))
                return self.send_json({"ok": True})
            if path == "/api/scaffold":
                if external_workspace(jid):  # the player's own tools own that directory
                    return self.send_json({"ok": True, "result": "external workspace — managed by your own tools"})
                pdir = project_dir(jid)
                os.makedirs(os.path.dirname(pdir), exist_ok=True)
                return self.send_json({"ok": True, "result": runtime_for(jid).scaffold(pdir, project_name(jid))})
            if path == "/api/seedworkspace":
                # place the tome's starter files into a student's OWN external folder
                # (explicit action). Non-destructive unless force; refuses a bad path.
                d = os.path.expanduser(body.get("dir", ""))
                if not (os.path.isabs(d) and os.path.isdir(d)):
                    return self.send_json({"ok": False, "error": "not an existing absolute folder"}, 400)
                rt = runtime_for(jid)
                if not rt.available():
                    return self.send_json({"ok": False, "error": f"{rt.LANGUAGE} toolchain not found on this machine"}, 400)
                mode = body.get("mode", "")  # "" = check, "missing" = add absent only, "force" = overwrite
                try:
                    return self.send_json(rt.seed_workspace(d, project_name(jid),
                                                            force=(mode == "force"), only_missing=(mode == "missing")))
                except Exception as e:
                    return self.send_json({"ok": False, "error": str(e)[-500:]}, 500)
            if path == "/api/openpath":
                # open the student's external project folder in their OS file explorer
                # (server shares their machine — localhost single-user tool)
                d = os.path.expanduser(body.get("dir", ""))
                if not (os.path.isabs(d) and os.path.isdir(d)):
                    return self.send_json({"ok": False, "error": "not an existing absolute folder"}, 400)
                try:
                    if sys.platform == "win32":
                        os.startfile(d)  # type: ignore[attr-defined]  # noqa: only exists on Windows
                    else:
                        opener = "open" if sys.platform == "darwin" else "xdg-open"
                        subprocess.Popen([opener, d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return self.send_json({"ok": True})
                except Exception as e:
                    return self.send_json({"ok": False, "error": str(e)}, 500)
            if path == "/api/oracle":
                lang = body.get("language") or load_manifest(jid).get("runtime", {}).get("language") or "code"
                return self.send_json(ask_oracle(body.get("question", ""), body.get("context", ""),
                                                 body.get("model"), lang))
            if path == "/api/runsnippet":
                rt = runtime_for(jid)
                return self.send_json(rt.run_snippet(scratch_base(rt.NAME), body.get("code", ""), body.get("stdin", "")))
            if path == "/api/snippetdiag":
                rt = runtime_for(jid)
                return self.send_json(rt.snippet_diagnostics(scratch_base(rt.NAME), body.get("code", "")))
            if path == "/api/run":
                write_files(jid, body.get("files", []))
                return self.send_json(runtime_for(jid).run_project(project_dir(jid), body.get("stdin", "")))
            if path == "/api/runcancel":
                return self.send_json({"ok": True, "cancelled": rt_common.cancel_current()})
            if path == "/api/diagnostics":
                write_files(jid, body.get("files", []))
                return self.send_json(runtime_for(jid).build_diagnostics(project_dir(jid)))
            if path == "/api/addpackage":
                return self.send_json(runtime_for(jid).add_package(project_dir(jid), body.get("package", "")))
            if path == "/api/grade":
                write_files(jid, body.get("files", []))
                sid = body.get("sectionId", "x")
                with jobs_lock:
                    for jid0, j in jobs.items():
                        if j.get("status") == "running" and j.get("section") == sid and j.get("tome") == jid:
                            return self.send_json({"ok": True, "jobId": jid0, "existing": True})
                    gid = uuid.uuid4().hex[:12]
                    jobs[gid] = {"status": "running", "section": sid, "tome": jid}
                threading.Thread(target=run_grader, args=(gid, body, jid), daemon=True).start()
                return self.send_json({"ok": True, "jobId": gid})
        except Exception as e:  # surface errors to the UI rather than 500-ing silently
            return self.send_json({"ok": False, "error": str(e)}, 500)
        self.send_json({"error": "unknown endpoint"}, 404)


if __name__ == "__main__":
    for j in list_tomes():
        save_dir(j["id"])  # regenerate any deleted save/ dir → fresh course
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}"
    print(f"The candle is lit → {url}")
    if os.environ.get("ARCANUM_NO_OPEN") != "1":  # cross-platform auto-open; set =1 to suppress
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
