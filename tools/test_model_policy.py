#!/usr/bin/env python3
"""Live Bindery census + quality-preset policy regression checks."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcanum.model_policy import ALL_ROLES, MODEL_ROLES, ROLES, model_guidance  # noqa: E402
from arcanum.routes_get import model_census  # noqa: E402
from tools.buildlib.runners import _spec_to_runner  # noqa: E402


PHASE_ROLES = {"default": "drafter", "1": "writer", "4": "writer",
               "3": "sections", "8": "reviewer"}


def _roles(*roles):
    return frozenset(roles)


# Guard the conservative decisions that prompted this audit.  The live-census
# assertion below catches new ids; this matrix catches accidental promotion of a
# small/code-specialized/low-effort model into a whole authorship hand.
EXPECTED_ROLES = {
    "claude-haiku-4-5": _roles("drafter"),
    "claude-sonnet-5": ALL_ROLES,
    "claude-opus-4-7": ALL_ROLES,
    "claude-opus-4-8": ALL_ROLES,
    "claude-fable-5": ALL_ROLES,
    "Gemini 3.5 Flash (Low)": _roles("drafter"),
    "Gemini 3.5 Flash (Medium)": _roles("drafter", "writer", "sections"),
    "Gemini 3.5 Flash (High)": ALL_ROLES,
    "Gemini 3.1 Pro (Low)": _roles("drafter"),
    "Gemini 3.1 Pro (High)": ALL_ROLES,
    "GPT-OSS 120B (Medium)": _roles("drafter"),
    "gpt-5.6-sol": ALL_ROLES,
    "gpt-5.6-terra": ALL_ROLES,
    "gpt-5.6-luna": _roles("drafter", "writer", "sections"),
    "gpt-5.5": ALL_ROLES,
    "gpt-5.4": ALL_ROLES,
    "gpt-5.4-mini": _roles("drafter"),
    "opencode-go/deepseek-v4-flash": _roles("drafter"),
    "opencode-go/deepseek-v4-pro": ALL_ROLES,
    "opencode-go/glm-5.1": ALL_ROLES,
    "opencode-go/glm-5.2": ALL_ROLES,
    "opencode-go/kimi-k2.6": ALL_ROLES,
    "opencode-go/kimi-k2.7-code": _roles("drafter"),
    "opencode-go/mimo-v2.5": _roles("drafter"),
    "opencode-go/mimo-v2.5-pro": _roles("drafter", "writer", "sections"),
    "opencode-go/minimax-m2.7": _roles("drafter", "writer", "sections"),
    "opencode-go/minimax-m3": ALL_ROLES,
    "opencode-go/qwen3.6-plus": _roles("drafter", "writer", "sections"),
    "opencode-go/qwen3.7-max": ALL_ROLES,
    "opencode-go/qwen3.7-plus": _roles("drafter", "writer", "sections"),
    "opencode/big-pickle": _roles(),
    "opencode/deepseek-v4-flash-free": _roles(),
    "opencode/mimo-v2.5-free": _roles(),
    "opencode/north-mini-code-free": _roles(),
    "opencode/nemotron-3-ultra-free": _roles(),
    "ollama/qwen3:32b-q8_0": _roles("drafter"),
    "ollama/qwen3:32b": _roles("drafter"),
    "ollama/qwen3-coder:30b": _roles(),
    "ollama/devstral:latest": _roles(),
    "ollama/qwen2.5:14b": _roles(),
    "ollama/llama3.1:8b": _roles(),
    "ollama/llama3.2:3b": _roles(),
}


def main():
    census = model_census()
    providers = {provider["id"]: provider for provider in census["bindery"]
                 if provider.get("installed") is not False}
    all_rows = [row for provider in providers.values() for row in provider["models"]]
    assert all_rows, "live Bindery census is empty"
    assert all(len(row) == 5 for row in all_rows), "model guidance missing from a row"
    unknown = [row[0] for row in all_rows if not row[4]["known"]]
    assert not unknown, f"new models need an explicit policy assessment: {unknown}"
    live_ids = {row[0] for row in all_rows}
    assert live_ids == set(EXPECTED_ROLES), (
        f"role fixture does not match live census: missing={live_ids - set(EXPECTED_ROLES)}, "
        f"stale={set(EXPECTED_ROLES) - live_ids}")
    assert MODEL_ROLES == EXPECTED_ROLES
    for row in all_rows:
        assert row[4]["basis"].strip(), f"{row[0]} has no research basis"
        supported = set(row[3])
        for role in ROLES:
            advised_efforts = row[4]["efforts"][role]
            assert set(advised_efforts).issubset(supported), (row[0], role, advised_efforts)
            if row[4]["advised"][role] and supported:
                assert advised_efforts, f"{row[0]} needs a recommended {role} effort"

    codex = {row[0]: row for row in providers["codex-cli"]["models"]}
    assert "gpt-5.3-codex" not in codex, "stale Codex model leaked past the live catalog"
    assert codex["gpt-5.6-sol"][3] == ["low", "medium", "high", "xhigh", "max", "ultra"]
    assert "minimal" not in codex["gpt-5.6-luna"][3]
    claude = {row[0]: row for row in providers["claude-cli"]["models"]}
    assert claude["claude-haiku-4-5"][3] == [], "Haiku does not support effort control"
    assert claude["claude-haiku-4-5"][4]["advised"] == {
        "drafter": True, "writer": False, "sections": False, "reviewer": False}
    assert claude["claude-opus-4-8"][4]["efforts"]["writer"] == ["high", "xhigh"]

    antigravity = {row[0]: row for row in providers["antigravity-cli"]["models"]}
    assert not antigravity["Gemini 3.5 Flash (Medium)"][4]["advised"]["reviewer"]
    assert antigravity["Gemini 3.5 Flash (High)"][4]["advised"]["reviewer"]

    opencode = {row[0]: row for row in providers["opencode-cli"]["models"]}
    assert not opencode["opencode-go/kimi-k2.7-code"][4]["advised"]["sections"]
    assert opencode["opencode-go/minimax-m3"][4]["advised"]["reviewer"]
    assert not opencode["opencode-go/qwen3.7-plus"][4]["advised"]["reviewer"]

    quality = census["quality"]
    assert [tier["id"] for tier in quality] == ["q1", "q2", "q3", "q4", "q5"]
    assert all(tier.get("split") is True for tier in quality)
    for tier in quality:
        phases = tier.get("phases") or {}
        assert set(PHASE_ROLES).issubset(phases), f"{tier['id']} is missing a hand"
        for phase, role in PHASE_ROLES.items():
            pick = phases[phase]
            provider = providers.get(pick["kind"])
            assert provider, f"{tier['id']} needs unavailable provider {pick['kind']}"
            row = next((r for r in provider["models"] if r[0] == pick["model"]), None)
            assert row, f"{tier['id']} needs unavailable model {pick['model']}"
            assert row[4]["advised"][role], f"{tier['id']} uses {pick['model']} for {role}"
            if pick.get("effort"):
                assert pick["effort"] in row[4]["efforts"][role], (
                    tier["id"], role, pick["model"], pick["effort"])
            spec = f'{pick["kind"]}:{pick["model"]}'
            if pick.get("effort"):
                spec += f'@{pick["effort"]}'
            _spec_to_runner(spec, f'{tier["id"]} {role}')

    q1 = quality[0]["phases"]
    assert q1["3"]["model"] != "opencode-go/deepseek-v4-flash"
    assert q1["8"]["model"] not in (q1["1"]["model"], q1["3"]["model"])
    assert all(pick.get("effort") not in ("low", "max", "ultra")
               for tier in quality for pick in tier["phases"].values())

    free_rows = [row for row in all_rows if row[2] == "FREE"]
    assert free_rows and all(not any(row[4]["advised"].values()) for row in free_rows)
    assert not any(model_guidance("future-unknown-model")["advised"].values())
    assert set(all_rows[0][4]["advised"]) == set(ROLES)
    print(f"model policy: OK ({len(all_rows)} live models, 5 complete quality tiers)")


if __name__ == "__main__":
    main()
