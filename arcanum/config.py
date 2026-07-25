"""Stable path/config constants and small configuration codecs."""
import json
import os
import shutil
import tomllib

from runtimes.common import atomic_write

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root (arcanum/ lives inside it)
WEB = os.path.join(ROOT, "web")
TOMES_DIR = os.path.join(ROOT, "tomes")
SKINS_DIR = os.path.join(ROOT, "skins")          # global TOML-defined skins (tome-independent)
CACHE_DIR = os.path.join(ROOT, ".cache")         # ephemera only: snippet scratch, server.log
BUILD_DIR = os.path.join(ROOT, ".tome-build")    # build_tome cross-phase state + runner handshake
PORT = 8777

GRADER_MODELS = ["claude-opus-5", "claude-opus-4-8", "opus"]  # first that works wins
CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
AGY_BIN = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")


def agy_print_args(timeout):
    """--print-timeout for agy's headless `-p`/`--print` mode, matching whatever
    timeout the caller enforces — agy's own default poll cap (5m) otherwise kills
    long runs before our timeout does. Use at every agy call site."""
    return ["--print-timeout", f"{timeout}s"]


# prefer the npm install: the Arch openai-codex package omits codex-code-mode-host,
# which gpt-5.6 models need — /usr/bin/codex dies with "failed to spawn code-mode host"
_NPM_CODEX = os.path.expanduser("~/.local/bin/codex")
CODEX_BIN = _NPM_CODEX if os.access(_NPM_CODEX, os.X_OK) else (shutil.which("codex") or _NPM_CODEX)


def codex_no_mcp_args():
    """-c overrides disabling every MCP server in ~/.codex/config.toml by name.
    (`-c mcp_servers={}` MERGES with the file instead of clearing it, so each server
    must be switched off individually. codex-desktop's node_repl hangs headless.)"""
    try:
        with open(os.path.expanduser("~/.codex/config.toml"), "rb") as f:
            servers = tomllib.load(f).get("mcp_servers", {})
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [a for n in servers for a in ("-c", f"mcp_servers.{n}.enabled=false")]
OPENCODE_BIN = shutil.which("opencode") or os.path.expanduser("~/.local/bin/opencode")
GRADE_TIMEOUT = 420  # seconds for claude grading
ORACLE_TIMEOUT = 180  # seconds for one oracle question (any backend)

# Models the claude/codex CLIs accept but cannot enumerate (neither has a list
# command); antigravity (`agy models`) and ollama (/api/tags) are listed live in
# /api/models. One source of truth — the browser pickers fetch these.
CLI_MODELS = {
    "claude-cli": ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-7",
                   "claude-opus-4-8", "claude-opus-5", "claude-fable-5"],
    # Fallback only: /api/models normally reads the installed Codex CLI's live catalog.
    # Keep this cheapest-to-frontier list current enough for an offline CLI startup.
    "codex-cli": ["gpt-5.4-mini", "gpt-5.6-luna", "gpt-5.4", "gpt-5.6-terra",
                  "gpt-5.5", "gpt-5.6-sol"],
    "anthropic": ["claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-5",
                  "claude-haiku-4-5", "claude-fable-5"],
    "openai": ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.1", "gpt-5", "gpt-4.1", "o3"],
}
# Reasoning-effort levels each login CLI accepts (claude: `--effort`, per its own
# --help; codex: `-c model_reasoning_effort=`). agy takes none — its Gemini model
# names carry the effort (Low/Medium/High variants). Mirrored in build_tome.py's
# CLI_RUNNERS, which does the actual flag injection.
CLI_EFFORTS = {
    "claude-cli": ["low", "medium", "high", "xhigh", "max"],
    "codex-cli": ["low", "medium", "high", "xhigh", "max", "ultra"],
    # opencode's --variant reasoning effort — a permissive ALLOWLIST here (the real per-model
    # values come from models.dev in the bindery). "none" appears on some models (e.g.
    # north-mini-code-free). Local ollama models take no variant.
    "opencode-cli": ["none", "minimal", "low", "medium", "high", "xhigh", "max"],
}

# Claude Code accepts one provider-wide --effort flag, but the API support is
# model-specific. Haiku 4.5, for example, has no effort control. The Bindery uses
# these rows rather than falsely offering every provider effort on every model.
CLI_MODEL_EFFORTS = {
    "claude-cli": {
        "claude-fable-5": CLI_EFFORTS["claude-cli"],
        "claude-opus-5": CLI_EFFORTS["claude-cli"],
        "claude-opus-4-8": CLI_EFFORTS["claude-cli"],
        "claude-opus-4-7": CLI_EFFORTS["claude-cli"],
        "claude-sonnet-5": CLI_EFFORTS["claude-cli"],
        "claude-haiku-4-5": [],
    },
}

# OpenCode Go (opencode.ai/go) — the low-cost coding gateway. Its lineup rotates, so we
# list it live from `opencode models` (opencode-go/*), falling back to this snapshot when
# opencode is absent or slow. The FREE ids are opencode-hosted launch-window models at $0.
OPENCODE_GO_FALLBACK = [
    "opencode-go/glm-5.2", "opencode-go/glm-5.1", "opencode-go/kimi-k2.7-code",
    "opencode-go/kimi-k2.6", "opencode-go/mimo-v2.5", "opencode-go/mimo-v2.5-pro",
    "opencode-go/minimax-m3", "opencode-go/minimax-m2.7", "opencode-go/qwen3.7-max",
    "opencode-go/qwen3.7-plus", "opencode-go/qwen3.6-plus", "opencode-go/deepseek-v4-pro",
    "opencode-go/deepseek-v4-flash",
]
OPENCODE_FREE_IDS = [
    "opencode/big-pickle", "opencode/deepseek-v4-flash-free", "opencode/mimo-v2.5-free",
    "opencode/north-mini-code-free", "opencode/nemotron-3-ultra-free",
]
# Maple AI (mapleai/*) — a separate OpenCode provider gateway. Surfaced by ID (not
# prefix-wide) so each model gets an explicit policy assessment, matching the FREE
# list's known-ID-filtered-by-live-availability pattern.
OPENCODE_MAPLE_IDS = [
    "mapleai/glm-5-2",
]
# OpenRouter (openrouter/*) via the OpenCode CLI. Routing is pinned to Novita in
# ~/.config/opencode/opencode.jsonc; here we only choose which ids to surface.
OPENROUTER_IDS = [
    "openrouter/deepseek/deepseek-v4-pro",
    "openrouter/minimax/minimax-m3",
    "openrouter/openai/gpt-5.6-luna",
    "openrouter/openai/gpt-5.6-terra",
    "openrouter/thinkingmachines/inkling",
]


def tome_opencode_model(model):
    """Whether an OpenCode model belongs to a Tome-supported hosted gateway."""
    value = str(model or "").strip()
    return (value in OPENROUTER_IDS
            or value.startswith("opencode-go/") and len(value) > len("opencode-go/"))


# Settings that follow the READER, not the tome — audio, pen (handwritten ink), and the
# ai grader/oracle config are the same across every tome; the palette (theme) and all
# progress stay per-tome. Stored beside the runtimes in global-configs/, split out of
# each POSTed save and merged back into each GET.
GLOBAL_STATE_KEYS = ("audio", "pen", "ai")
GLOBAL_SETTINGS = os.path.join(ROOT, "global-configs", "settings.toml")

MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2",
        ".ttf": "font/ttf", ".map": "application/json", ".png": "image/png", ".toml": "text/plain"}

def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def read_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def read_settings():
    """global-configs/settings.toml — {} before the reader has saved one."""
    try:
        return read_toml(GLOBAL_SETTINGS)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def openai_api_configured():
    """Whether Forge can use its explicit Codex API validator transport."""
    if str(os.environ.get("OPENAI_API_KEY") or "").strip():
        return True
    try:
        return bool(str(((((read_settings().get("ai") or {}).get("keys") or {})
                          .get("openai")) or "")).strip())
    except (OSError, TypeError, ValueError):
        return False


def _toml_value(v):
    if isinstance(v, bool):          # before int: bool is an int subclass
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return json.dumps(str(v))        # JSON string escaping == TOML basic-string escaping


def dump_toml(d, prefix=""):
    """Write a dict of scalars/lists/nested dicts as TOML. tomllib reads but cannot write.

    Scalars before sub-tables at every level — that ordering is the whole contract, since
    any key trailing a [table] header belongs to that table.
    ponytail: bare keys only, which is all settings.toml ever holds. Quote them if a key
    ever needs a dot or a space."""
    out = "".join(f"{k} = {_toml_value(v)}\n" for k, v in d.items() if not isinstance(v, dict))
    for k, v in d.items():
        if isinstance(v, dict):
            out += f"\n[{prefix}{k}]\n" + dump_toml(v, f"{prefix}{k}.")
    return out


SETTINGS_HEADER = ("# global-configs/settings.toml — the reader-wide settings (audio, pen, AI\n"
                   "# models and keys, Pushover creds). Hand-edit it; the study's settings panel\n"
                   "# rewrites it on save, keeping your values and dropping your comments.\n")


def write_settings(d):
    os.makedirs(os.path.dirname(GLOBAL_SETTINGS), exist_ok=True)
    atomic_write(GLOBAL_SETTINGS, SETTINGS_HEADER + dump_toml(d))
