"""Read-only discovery of locally available AI models and effort levels."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request

from arcanum.config import (AGY_BIN, CLI_EFFORTS, CLI_MODELS, CODEX_BIN,
                            OPENCODE_BIN, OPENCODE_FREE_IDS,
                            OPENCODE_GO_FALLBACK, OPENCODE_MAPLE_IDS)


def models_dev_efforts():
    output = {}
    try:
        with open(os.path.expanduser("~/.cache/opencode/models.json")) as handle:
            providers = json.load(handle)
        for provider_id, provider in providers.items():
            for model_id, model in (provider.get("models") or {}).items():
                for option in model.get("reasoning_options") or []:
                    if (isinstance(option, dict) and option.get("type") == "effort"
                            and option.get("values")):
                        output[f"{provider_id}/{model_id}"] = list(option["values"])
    except (OSError, ValueError, TypeError):
        pass
    return output


def opencode_models():
    lines = []
    try:
        process = subprocess.run([OPENCODE_BIN, "models"], capture_output=True,
                                 text=True, timeout=20)
        lines = [line.strip() for line in process.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        pass
    go = [line for line in lines if line.startswith("opencode-go/")] \
        or list(OPENCODE_GO_FALLBACK)
    maple = [model for model in OPENCODE_MAPLE_IDS if not lines or model in lines]
    free = [model for model in OPENCODE_FREE_IDS if not lines or model in lines]
    efforts = models_dev_efforts()

    def row(model, label):
        return [model, model.split("/", 1)[-1], label, efforts.get(model, [])]

    return ([row(model, "") for model in go]
            + [row(model, "Maple") for model in maple]
            + [row(model, "FREE") for model in free])


def ollama_bindery_models():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as response:
            data = json.loads(response.read())
        return [["ollama/" + model["name"], model["name"], "local", []]
                for model in data.get("models", [])]
    except (OSError, ValueError, TypeError):
        return []


_agy_cache = {"time": 0.0, "models": []}
_codex_cache = {"time": 0.0, "models": []}


def codex_models():
    if time.time() - _codex_cache["time"] > 600:
        try:
            process = subprocess.run([CODEX_BIN, "debug", "models"],
                                     capture_output=True, text=True, timeout=30)
            if process.returncode:
                raise RuntimeError(process.stderr[:300])
            rows = []
            for model in json.loads(process.stdout).get("models", []):
                if model.get("visibility") != "list" or not model.get("slug"):
                    continue
                efforts = [level.get("effort") for level in
                           model.get("supported_reasoning_levels") or []
                           if level.get("effort")]
                rows.append([model["slug"], model.get("display_name") or model["slug"],
                             "", efforts])
            if rows:
                _codex_cache.update(time=time.time(), models=rows)
        except (OSError, ValueError, TypeError, RuntimeError, subprocess.TimeoutExpired):
            pass
    if _codex_cache["models"]:
        return [list(row) for row in _codex_cache["models"]]
    return [[model, model, "", list(CLI_EFFORTS["codex-cli"])]
            for model in CLI_MODELS["codex-cli"]]


def agy_models():
    if time.time() - _agy_cache["time"] > 600:
        process = subprocess.run([AGY_BIN, "models"], capture_output=True,
                                 text=True, timeout=30)
        if process.returncode:
            raise RuntimeError(f"`agy models` failed: {process.stderr[:300]}")
        _agy_cache.update(
            time=time.time(),
            models=[line.strip() for line in process.stdout.splitlines()
                    if line.strip() and not line.strip().startswith("Claude")])
    return list(_agy_cache["models"])
