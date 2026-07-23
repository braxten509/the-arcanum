"""Live and curated model catalog read adapter."""
from __future__ import annotations

import json
import os
import urllib.request

from arcanum.config import (AGY_BIN, CLAUDE_BIN, CLI_EFFORTS, CLI_MODEL_EFFORTS,
                            CLI_MODELS, CODEX_BIN, OPENCODE_BIN)
from .providers.discovery import (agy_models, codex_models, ollama_bindery_models,
                                  opencode_models, opencode_zen_models,
                                  openrouter_models)


def model_census() -> dict:
    installed = {"claude-cli": os.access(CLAUDE_BIN, os.X_OK),
                 "antigravity-cli": os.access(AGY_BIN, os.X_OK),
                 "codex-cli": os.access(CODEX_BIN, os.X_OK),
                 "opencode-cli": os.access(OPENCODE_BIN, os.X_OK)}
    providers = {key: list(value) for key, value in CLI_MODELS.items()}
    if installed["antigravity-cli"]:
        try:
            providers["antigravity-cli"] = agy_models()
        except Exception:
            providers["antigravity-cli"] = []
    else:
        providers["antigravity-cli"] = []
    providers["opencode-cli"] = ([row[0] for row in opencode_models()]
                                  if installed["opencode-cli"] else [])
    codex_rows = codex_models() if installed["codex-cli"] else []
    providers["codex-cli"] = [row[0] for row in codex_rows]
    output = {"ok": True, "models": [], "providers": providers,
              "installed": installed, "efforts": CLI_EFFORTS}
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as response:
            data = json.loads(response.read())
        output["models"] = sorted(
            ({"name": row["name"], "gb": round(row.get("size", 0) / 1e9, 1)}
             for row in data.get("models", [])), key=lambda row: -row["gb"])
    except Exception as exc:
        output["ok"], output["error"] = False, str(exc)

    def rows(models, kind):
        efforts = CLI_MODEL_EFFORTS.get(kind, {})
        return [[model, model, "", efforts.get(model, [])] for model in models]

    if not codex_rows:
        codex_rows = [[model, model, "", list(CLI_EFFORTS["codex-cli"])]
                      for model in CLI_MODELS["codex-cli"]]
        providers["codex-cli"] = [row[0] for row in codex_rows]
    opencode_ok = installed["opencode-cli"]
    opencode_rows = opencode_models() if opencode_ok else []
    zen_rows = opencode_zen_models() if opencode_ok else []
    local_rows = ollama_bindery_models() if opencode_ok else []
    router_rows = openrouter_models() if opencode_ok else []
    # the grader/oracle picker lists by kind, so OpenRouter ids join the opencode-cli pool
    providers["opencode-cli"] += [row[0] for row in router_rows]
    tome_cli_roles = ["author", "validator", "reviewer"]
    # Tome creation/resume is intentionally narrower than the reader's general AI
    # catalog. Keep unsupported pools out of the payload so stale browser state cannot
    # rediscover OpenCode, OpenRouter, Antigravity, Zen, or local models.
    output["bindery"] = [
        {"id": "claude-cli", "label": "Claude CLI", "kind": "claude-cli",
         "models": rows(CLI_MODELS["claude-cli"], "claude-cli"),
         "installed": installed["claude-cli"], "roles": tome_cli_roles},
        {"id": "codex-cli", "label": "Codex CLI", "kind": "codex-cli",
         "models": codex_rows, "installed": installed["codex-cli"],
         "roles": tome_cli_roles},
        {"id": "openrouter", "label": "OpenRouter · OpenCode CLI", "kind": "opencode-cli",
         "models": router_rows, "installed": installed["opencode-cli"],
         "roles": tome_cli_roles},
    ]
    return output
