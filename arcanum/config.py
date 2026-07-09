"""Paths, constants, tiny IO helpers, and the shared in-memory job registry.
Everything here is import-safe (no side effects beyond mkdir of cache/tomes)."""
import json
import os
import shutil
import threading
import tomllib

from runtimes.common import atomic_write

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root (arcanum/ lives inside it)
WEB = os.path.join(ROOT, "web")
TOMES_DIR = os.path.join(ROOT, "tomes")
SKINS_DIR = os.path.join(ROOT, "skins")          # global TOML-defined skins (tome-independent)
CACHE_DIR = os.path.join(ROOT, ".cache")         # ephemera only: snippet scratch, server.log
BUILD_DIR = os.path.join(ROOT, ".tome-build")    # build_tome cross-phase state + runner handshake
PORT = 8777

GRADER_MODELS = ["claude-opus-4-8", "opus"]  # first that works wins
CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
AGY_BIN = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")


def agy_print_args(timeout):
    """--print-timeout for agy's headless `-p`/`--print` mode, matching whatever
    timeout the caller enforces — agy's own default poll cap (5m) otherwise kills
    long runs before our timeout does. Use at every agy call site."""
    return ["--print-timeout", f"{timeout}s"]


CODEX_BIN = shutil.which("codex") or os.path.expanduser("~/.local/bin/codex")
OPENCODE_BIN = shutil.which("opencode") or os.path.expanduser("~/.local/bin/opencode")
GRADE_TIMEOUT = 420  # seconds for claude grading
ORACLE_TIMEOUT = 180  # seconds for one oracle question (any backend)

# Models the claude/codex CLIs accept but cannot enumerate (neither has a list
# command); antigravity (`agy models`) and ollama (/api/tags) are listed live in
# /api/models. One source of truth — the browser pickers fetch these.
CLI_MODELS = {
    "claude-cli": ["claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"],
    # gpt-5.4-mini is the cheap/fast coding model (supersedes gpt-4o-mini, which is not in the
    # 2026 codex lineup); gpt-5.3-codex stays available for the coding-optimized cost profile.
    "codex-cli": ["gpt-5.5", "gpt-5.4", "gpt-5.3-codex", "gpt-5.4-mini"],
    "anthropic": ["claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"],
    "openai": ["gpt-5.1", "gpt-5", "gpt-4.1", "o3"],
}
# Reasoning-effort levels each login CLI accepts (claude: `--effort`, per its own
# --help; codex: `-c model_reasoning_effort=`). agy takes none — its Gemini model
# names carry the effort (Low/Medium/High variants). Mirrored in build_tome.py's
# CLI_RUNNERS, which does the actual flag injection.
CLI_EFFORTS = {
    "claude-cli": ["low", "medium", "high", "xhigh", "max"],
    "codex-cli": ["minimal", "low", "medium", "high", "xhigh"],
    # opencode's --variant reasoning effort — a permissive ALLOWLIST here (the real per-model
    # values come from models.dev in the bindery). "none" appears on some models (e.g.
    # north-mini-code-free). Local ollama models take no variant.
    "opencode-cli": ["none", "minimal", "low", "medium", "high", "max"],
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

# Settings that follow the READER, not the tome — audio, pen (handwritten ink), and the
# ai grader/oracle config are the same across every tome; the palette (theme) and all
# progress stay per-tome. Stored beside the runtimes in global-configs/, split out of
# each POSTed save and merged back into each GET.
GLOBAL_STATE_KEYS = ("audio", "pen", "ai")
GLOBAL_SETTINGS = os.path.join(ROOT, "global-configs", "settings.toml")

MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2",
        ".ttf": "font/ttf", ".map": "application/json", ".png": "image/png", ".toml": "text/plain"}

# ---------------------------------------------------------------- shared job registry
# One registry for grading, forge-build, and amend jobs (build jobs carry "kind": "build",
# amend jobs "kind": "amend"). Guarded by jobs_lock everywhere.
jobs = {}  # id -> {status, result, error}
jobs_lock = threading.Lock()
amend_procs = {}  # amend job id -> Popen, kept out of `jobs` so status stays JSON-safe


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


os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(TOMES_DIR, exist_ok=True)
