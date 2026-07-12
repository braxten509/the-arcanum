"""Bounded, cached Phase-0 accessibility checks for every AI workflow."""
import json
import hashlib
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from tools.buildlib.liveness import preflight_auth


_CACHE_TTL = 600
_cache = {}
_lock = threading.Lock()


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
    ok, detail = preflight_auth(cmd, input_mode, label)
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
