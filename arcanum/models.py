"""AI model census + the shared one-shot CLI text call (grading and oracle both use it)."""
import json
import os
import subprocess
import time
import urllib.request

from .config import (AGY_BIN, CLAUDE_BIN, CLI_EFFORTS, CLI_MODELS, CODEX_BIN,
                     OPENCODE_BIN, ROOT, agy_print_args, codex_no_mcp_args,
                     OPENCODE_FREE_IDS, OPENCODE_GO_FALLBACK, OPENCODE_MAPLE_IDS)
from .authoring.ai_access import ensure_cli_access
from tools.buildlib.runtime.agent_runtime import scoped_runner_command


class GraderConfigError(Exception):
    """A grader misconfiguration (e.g. a model that doesn't exist) — fatal, surfaced
    to the user as-is instead of silently retried on the local fallback grader."""


def models_dev_efforts():
    """'provider/model' -> [effort values] from opencode's models.dev cache. Reasoning effort
    is PER-MODEL and not uniform: some Go models expose ["high","max"], some a toggle only,
    many none — so the picker must offer the right values per model, not a blanket list."""
    out = {}
    try:
        with open(os.path.expanduser("~/.cache/opencode/models.json")) as f:
            d = json.load(f)
        for pid, prov in d.items():
            for mid, m in (prov.get("models") or {}).items():
                for ro in (m.get("reasoning_options") or []):
                    if isinstance(ro, dict) and ro.get("type") == "effort" and ro.get("values"):
                        out[f"{pid}/{mid}"] = list(ro["values"])
    except Exception:
        pass
    return out


def opencode_models():
    """OpenCode Go + Maple AI + free models as [id, label, tag, efforts] rows (tag "FREE"
    flags the $0 ones, "Maple" the Maple AI gateway; efforts is that model's
    reasoning-effort values, or [] if it has none). Live from `opencode models` when
    available, else the static snapshot. label = id sans prefix."""
    lines = []
    try:
        p = subprocess.run([OPENCODE_BIN, "models"], capture_output=True, text=True, timeout=20)
        lines = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    except Exception:
        pass
    go = [ln for ln in lines if ln.startswith("opencode-go/")] or list(OPENCODE_GO_FALLBACK)
    maple = [i for i in OPENCODE_MAPLE_IDS if (not lines or i in lines)]
    free = [i for i in OPENCODE_FREE_IDS if (not lines or i in lines)]
    eff = models_dev_efforts()
    short = lambda mid: mid.split("/", 1)[-1]
    return ([[m, short(m), "", eff.get(m, [])] for m in go]
            + [[m, short(m), "Maple", eff.get(m, [])] for m in maple]
            + [[m, short(m), "FREE", eff.get(m, [])] for m in free])


def ollama_bindery_models():
    """Local ollama models as [ollama/<name>, <name>, "local", []] rows — run THROUGH the
    opencode agent. Local models aren't in models.dev, so they carry no effort variant."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            data = json.loads(r.read())
        return [["ollama/" + m["name"], m["name"], "local", []] for m in data.get("models", [])]
    except Exception:
        return []


_agy_cache = {"t": 0.0, "models": []}
_codex_cache = {"t": 0.0, "models": []}


def codex_models():
    """Visible models and per-model efforts from the installed Codex catalog.

    Unlike a static slug list, `codex debug models` tracks removals and exposes
    model-specific levels such as max/ultra. Cache it for the same reason as agy:
    the browser asks on every Bindery open.
    """
    if time.time() - _codex_cache["t"] > 600:
        try:
            p = subprocess.run([CODEX_BIN, "debug", "models"], capture_output=True,
                               text=True, timeout=30)
            if p.returncode != 0:
                raise RuntimeError(p.stderr[:300])
            rows = []
            for model in json.loads(p.stdout).get("models", []):
                if model.get("visibility") != "list" or not model.get("slug"):
                    continue
                efforts = [level.get("effort") for level in
                           (model.get("supported_reasoning_levels") or [])
                           if level.get("effort")]
                rows.append([model["slug"], model.get("display_name") or model["slug"],
                             "", efforts])
            if rows:
                _codex_cache.update(t=time.time(), models=rows)
        except Exception:
            pass
    if _codex_cache["models"]:
        return [list(row) for row in _codex_cache["models"]]
    return [[model, model, "", list(CLI_EFFORTS["codex-cli"])]
            for model in CLI_MODELS["codex-cli"]]


def agy_models():
    """Model display names `agy --model` accepts, one per line from `agy models`.
    Cached 10 min — the settings modal refetches on every open and the list is
    a subprocess away."""
    if time.time() - _agy_cache["t"] > 600:
        p = subprocess.run([AGY_BIN, "models"], capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            raise RuntimeError(f"`agy models` failed: {p.stderr[:300]}")
        # agy lists Claude models it won't actually serve on this plan — hide them
        _agy_cache.update(t=time.time(),
                          models=[ln.strip() for ln in p.stdout.splitlines()
                                  if ln.strip() and not ln.strip().startswith("Claude")])
    return _agy_cache["models"]


def cli_text(kind, prompt, model, timeout, tome_root):
    """One prompt through a login-based CLI, plain text back. Shared by grading
    (which parses JSON out of it) and the oracle (which shows it as-is).
    Every provider runs behind the shared read-only project boundary: it can read the
    whole repository, execute trusted repo Python, use the web, and write system temp.
    - claude: prompt as an argument; CLAUDECODE is stripped so a nested CLI behaves.
    - agy: `-p` takes the prompt as an ARGUMENT (not stdin), and `--model` wants a
      display name from `agy models` (e.g. "Gemini 3.1 Pro (High)"). agy silently
      ignores an unknown model, so validate up front rather than answer under the
      wrong model.
    - codex: prompt on stdin; empty model uses the user's ~/.codex config default.
    - opencode: prompt as an argument; supports Go, free hosted, and Ollama models."""
    if kind == "claude-cli":
        cmd = [CLAUDE_BIN, "-p", "--permission-mode", "auto"]
        if model:
            cmd += ["--model", model]
        input_mode = "arg"
    elif kind == "antigravity-cli":
        if model and model not in agy_models():
            raise GraderConfigError(
                f"model {model!r} does not exist in agy — run `agy models` for valid names "
                "(agy would otherwise silently answer with its default)")
        cmd = [AGY_BIN, "--dangerously-skip-permissions", *agy_print_args(timeout)]
        if model:
            cmd += ["--model", model]
        cmd += ["--print"]
        input_mode = "arg"
    elif kind == "codex-cli":
        cmd = [CODEX_BIN, "--search", "exec", "--skip-git-repo-check", "-s", "read-only",
               *codex_no_mcp_args()]
        if model:
            cmd += ["-m", model]
        cmd += ["-"]
        input_mode = "stdin"
    elif kind == "opencode-cli":
        cmd = [OPENCODE_BIN, "run", "--auto"]
        if model:
            cmd += ["-m", model]
        input_mode = "arg"
    else:
        raise ValueError(f"unknown CLI kind {kind!r}")
    cmd = scoped_runner_command(kind, cmd, tome_root, [], ROOT)
    ensure_cli_access(f"{kind} {model}".strip(), cmd, input_mode)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    env.update(ARCANUM_REPO_ROOT=ROOT, ARCANUM_TOME_ROOT=tome_root,
               PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run(cmd + ([prompt] if input_mode == "arg" else []),
                       input=(prompt if input_mode == "stdin" else None),
                       capture_output=True, text=True, timeout=timeout, env=env, cwd=tome_root)
    if p.returncode != 0:
        raise RuntimeError(f"exit {p.returncode}: {p.stderr[:500]}")
    return p.stdout
