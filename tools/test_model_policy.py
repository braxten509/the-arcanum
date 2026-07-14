#!/usr/bin/env python3
"""Live Bindery census + quality-preset policy regression checks."""
import os
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcanum.model_policy import (MODEL_POWER, MODEL_ROLES, ROLES,  # noqa: E402
                                  WASTEFUL_ROLES, model_guidance)
from arcanum.routes_get import model_census  # noqa: E402
from tools.buildlib.runners import _spec_to_runner  # noqa: E402


PHASE_ROLES = {"default": "drafter", "1": "writer", "4": "writer",
               "3": "sections", "8": "reviewer"}


def _roles(*roles):
    return frozenset(roles)


# Guard both sides of the recommendation band.  The live-census assertion catches
# new ids; this matrix prevents either an underpowered model or an unjustifiably
# expensive/dominated model from leaking into a bundled hand.
EXPECTED_ROLES = {
    "claude-haiku-4-5": _roles("drafter"),
    "claude-sonnet-5": _roles("writer", "sections", "reviewer"),
    "claude-opus-4-7": _roles(),
    "claude-opus-4-8": _roles("writer", "reviewer"),
    "claude-fable-5": _roles("reviewer"),
    "Gemini 3.5 Flash (Low)": _roles("drafter"),
    "Gemini 3.5 Flash (Medium)": _roles("writer", "sections"),
    "Gemini 3.5 Flash (High)": _roles("writer", "sections", "reviewer"),
    "Gemini 3.1 Pro (Low)": _roles(),
    "Gemini 3.1 Pro (High)": _roles("writer", "reviewer"),
    "GPT-OSS 120B (Medium)": _roles("drafter"),
    "gpt-5.6-sol": _roles("writer", "reviewer"),
    "gpt-5.6-terra": _roles("writer", "sections", "reviewer"),
    "gpt-5.6-luna": _roles("drafter", "writer", "sections"),
    "gpt-5.5": _roles(),
    "gpt-5.4": _roles(),
    "gpt-5.4-mini": _roles("drafter"),
    "opencode-go/deepseek-v4-flash": _roles("drafter"),
    "opencode-go/deepseek-v4-pro": _roles("writer", "sections"),
    "opencode-go/glm-5.1": _roles(),
    "opencode-go/glm-5.2": _roles("writer", "reviewer"),
    "opencode-go/kimi-k2.6": _roles("writer", "reviewer"),
    "opencode-go/kimi-k2.7-code": _roles(),
    "opencode-go/mimo-v2.5": _roles("drafter"),
    "opencode-go/mimo-v2.5-pro": _roles(),
    "opencode-go/minimax-m2.7": _roles(),
    "opencode-go/minimax-m3": _roles("writer", "sections", "reviewer"),
    "opencode-go/qwen3.6-plus": _roles(),
    "opencode-go/qwen3.7-max": _roles("writer", "reviewer"),
    "opencode-go/qwen3.7-plus": _roles("writer"),
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
    assert set(MODEL_POWER) == set(EXPECTED_ROLES)
    assert set(WASTEFUL_ROLES).issubset(EXPECTED_ROLES)
    for row in all_rows:
        assert row[4]["basis"].strip(), f"{row[0]} has no research basis"
        power = row[4]["power"]
        if any(row[4]["advised"].values()):
            assert isinstance(power, int) and 1 <= power <= 10, (row[0], power)
        supported = set(row[3])
        for role in ROLES:
            reason = row[4]["reason"][role]
            if row[4]["advised"][role]:
                assert reason is None, (row[0], role, reason)
            else:
                assert reason in ("insufficient", "wasteful"), (row[0], role, reason)
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
    assert claude["claude-opus-4-8"][4]["efforts"]["writer"] == ["high"]
    assert claude["claude-fable-5"][4]["advised"] == {
        "drafter": False, "writer": False, "sections": False, "reviewer": True}
    assert claude["claude-fable-5"][4]["efforts"]["reviewer"] == ["high"]
    assert not any(claude["claude-opus-4-7"][4]["advised"].values())

    antigravity = {row[0]: row for row in providers["antigravity-cli"]["models"]}
    assert antigravity["Gemini 3.5 Flash (Medium)"][4]["advised"] == {
        "drafter": False, "writer": True, "sections": True, "reviewer": False}
    assert antigravity["Gemini 3.5 Flash (High)"][4]["advised"] == {
        "drafter": False, "writer": True, "sections": True, "reviewer": True}
    assert antigravity["Gemini 3.1 Pro (High)"][4]["advised"] == {
        "drafter": False, "writer": True, "sections": False, "reviewer": True}
    assert antigravity["Gemini 3.5 Flash (High)"][4]["power"] == 9
    assert antigravity["Gemini 3.5 Flash (High)"][4]["reason"]["drafter"] == "wasteful"
    assert antigravity["Gemini 3.5 Flash (Low)"][4]["reason"]["writer"] == "insufficient"

    assert not any(codex["gpt-5.5"][4]["advised"].values())
    assert not any(codex["gpt-5.4"][4]["advised"].values())
    assert codex["gpt-5.6-luna"][4]["efforts"]["drafter"] == ["medium"]
    assert codex["gpt-5.4-mini"][4]["efforts"]["drafter"] == ["high"]
    assert codex["gpt-5.6-sol"][4]["power"] == 10
    assert codex["gpt-5.6-sol"][4]["reason"]["sections"] == "wasteful"
    assert codex["gpt-5.6-luna"][4]["reason"]["reviewer"] == "insufficient"

    opencode = {row[0]: row for row in providers["opencode-cli"]["models"]}
    assert not opencode["opencode-go/kimi-k2.7-code"][4]["advised"]["sections"]
    assert opencode["opencode-go/minimax-m3"][4]["advised"]["reviewer"]
    assert not opencode["opencode-go/qwen3.7-plus"][4]["advised"]["reviewer"]
    assert not opencode["opencode-go/qwen3.7-plus"][4]["advised"]["sections"]
    assert not opencode["opencode-go/deepseek-v4-pro"][4]["advised"]["reviewer"]
    for dominated in ("opencode-go/glm-5.1", "opencode-go/mimo-v2.5-pro",
                      "opencode-go/minimax-m2.7", "opencode-go/qwen3.6-plus"):
        assert not any(opencode[dominated][4]["advised"].values()), dominated
    assert opencode["opencode-go/qwen3.7-max"][4]["advised"] == {
        "drafter": False, "writer": True, "sections": False, "reviewer": True}
    assert opencode["opencode-go/glm-5.1"][4]["reason"]["writer"] == "wasteful"
    assert opencode["opencode/nemotron-3-ultra-free"][4]["reason"]["reviewer"] == "insufficient"

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

    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "global-configs", "harness.toml"), "rb") as handle:
        autonomy = tomllib.load(handle).get("autonomy") or {}
    for phase, specs in autonomy.items():
        role = PHASE_ROLES.get(phase, "drafter")
        for spec in specs:
            kind, separator, raw_model = str(spec).partition(":")
            model, _, effort = raw_model.partition("@")
            assert separator and kind in providers, (phase, spec)
            row = next((item for item in providers[kind]["models"] if item[0] == model), None)
            assert row and row[4]["reason"][role] != "insufficient", (
                f"autonomous phase {phase} uses underpowered {model} for {role}")
            if effort:
                assert effort in row[3], (phase, model, effort)
            _spec_to_runner(str(spec), f"autonomy phase {phase}")

    q1 = quality[0]["phases"]
    assert q1["3"]["model"] != "opencode-go/deepseek-v4-flash"
    assert q1["8"]["model"] not in (q1["1"]["model"], q1["3"]["model"])
    assert all(pick.get("effort") not in ("low", "max", "ultra")
               for tier in quality for pick in tier["phases"].values())

    free_rows = [row for row in all_rows if row[2] == "FREE"]
    assert free_rows and all(not any(row[4]["advised"].values()) for row in free_rows)
    unknown_guidance = model_guidance("future-unknown-model")
    assert not any(unknown_guidance["advised"].values())
    assert unknown_guidance["power"] is None
    assert set(unknown_guidance["reason"].values()) == {"insufficient"}
    assert set(all_rows[0][4]["advised"]) == set(ROLES)
    print(f"model policy: OK ({len(all_rows)} live models, 5 complete quality tiers)")


if __name__ == "__main__":
    main()
