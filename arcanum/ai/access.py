"""Bounded, cached accessibility checks for every AI provider adapter."""
import json
import hashlib
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

_CACHE_TTL = 600
_cache = {}
_lock = threading.Lock()
_AUTH_MARKERS = ("not logged in", "you are not logged into", "authentication required",
                 "please visit", "please log in", "please sign in", "not authenticated",
                 "authentication interrupted", "oauth")


def _preflight_cli(command, input_mode):
    ping = "Reply with the single word READY and nothing else."
    full = [*command, ping] if input_mode == "arg" else list(command)
    try:
        process = subprocess.Popen(
            full, text=True,
            stdin=(subprocess.DEVNULL if input_mode == "arg" else subprocess.PIPE),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as exc:
        return False, f"could not launch {command[0]!r}: {exc}"
    if input_mode != "arg":
        try:
            process.stdin.write(ping)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    watchdog = threading.Timer(45, process.kill)
    watchdog.start()
    output = []
    try:
        for line in process.stdout:
            output.append(line)
            if any(marker in line.lower() for marker in _AUTH_MARKERS):
                process.kill()
                break
    finally:
        watchdog.cancel()
    code = process.wait()
    text = "".join(output)
    if code != 0 or any(marker in text.lower() for marker in _AUTH_MARKERS):
        tail = " | ".join(text.strip().splitlines()[-4:]) or "(no output)"
        return False, tail
    return True, "ok"


def _cached(key):
    with _lock:
        return time.monotonic() - _cache.get(key, 0) < _CACHE_TTL


def _mark(key):
    with _lock:
        _cache[key] = time.monotonic()


def ensure_cli_access(label, cmd, input_mode):
    """Prove the exact scoped CLI/model command answers before starting real work."""
    key = ("cli", tuple(cmd), input_mode)
    if _cached(key):
        return
    ok, detail = _preflight_cli(cmd, input_mode)
    if not ok:
        raise RuntimeError(f"AI ACCESS PHASE 0 failed for {label}: {detail}")
    _mark(key)


def ensure_remote_access(kind, model, key=""):
    """Cheap authenticated endpoint checks for non-agentic API/Ollama backends."""
    key_fingerprint = hashlib.sha256(key.encode()).hexdigest()[:16] if key else ""
    cache_key = (kind, model, key_fingerprint)
    if _cached(cache_key):
        return
    if kind == "ollama":
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=15) as r:
            models = {m.get("name") for m in json.loads(r.read()).get("models", [])}
        if model and model not in models:
            raise RuntimeError(f"AI ACCESS PHASE 0: Ollama model {model!r} is not installed")
    elif kind in ("openai", "anthropic"):
        if not key:
            raise RuntimeError(f"AI ACCESS PHASE 0: no {kind} API key is configured")
        quoted = urllib.parse.quote(model, safe="")
        if kind == "openai":
            req = urllib.request.Request(f"https://api.openai.com/v1/models/{quoted}",
                                         headers={"Authorization": "Bearer " + key})
        else:
            req = urllib.request.Request(f"https://api.anthropic.com/v1/models/{quoted}",
                                         headers={"x-api-key": key,
                                                  "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=20):
                pass
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"AI ACCESS PHASE 0: {kind}/{model} returned HTTP {exc.code}: {detail}") from exc
    else:
        raise RuntimeError(f"AI ACCESS PHASE 0 has no probe for backend {kind!r}")
    _mark(cache_key)


def ensure_command_access(command, cwd):
    """Bound a user-configured grader command's accessibility check to 45 seconds."""
    key = ("command", tuple(command) if isinstance(command, list) else command, cwd)
    if _cached(key):
        return
    try:
        p = subprocess.run(command, shell=isinstance(command, str), input="Reply READY only.", capture_output=True,
                           text=True, timeout=45, cwd=cwd)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("AI ACCESS PHASE 0: custom grader command timed out after 45s") from exc
    if p.returncode != 0:
        raise RuntimeError(f"AI ACCESS PHASE 0: custom grader exited {p.returncode}: {p.stderr[:300]}")
    _mark(key)
