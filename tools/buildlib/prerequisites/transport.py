"""OpenAI Responses API transport for the Validator AI.

The section reviewer uses this as a no-tools plain-text request. The optional
schema parameters remain available to other direct callers. CLI transport stays
in review.py, where tests rebind its runner seams.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .prompt import DYNAMIC_MARKER, result_schema as _result_schema


# 13: the full semantic authority and calibration are identical for author and validator.
AUDIT_CONTRACT_VERSION = 13
RESPONSES_URL = "https://api.openai.com/v1/responses"
API_TIMEOUT_SECONDS = 900
API_MAX_OUTPUT_TOKENS = 2_500


def _response_text(response):
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    blocks = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                blocks.append(content["text"])
            elif content.get("type") == "refusal":
                raise RuntimeError("Validator AI refused the bounded quality audit")
    if not blocks:
        raise RuntimeError("Responses API returned no output text")
    return "\n".join(blocks)


def _usage(response):
    usage = response.get("usage") or {}
    inputs = usage.get("input_tokens_details") or {}
    outputs = usage.get("output_tokens_details") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    cached_tokens = int(inputs.get("cached_tokens") or 0)
    cache_write_tokens = int(inputs.get("cache_write_tokens") or 0)
    return {
        "inputTokens": input_tokens,
        "freshInputTokens": max(0, input_tokens - cached_tokens - cache_write_tokens),
        "cachedInputTokens": cached_tokens,
        "cacheWriteTokens": cache_write_tokens,
        "outputTokens": int(usage.get("output_tokens") or 0),
        "reasoningTokens": int(outputs.get("reasoning_tokens") or 0),
        "totalTokens": int(usage.get("total_tokens") or 0),
    }


def _openai_key():
    key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if key:
        return key
    try:
        from arcanum.config import read_settings
        return str((((read_settings().get("ai") or {}).get("keys") or {}).get("openai"))
                   or "").strip()
    except (OSError, TypeError, ValueError):
        return ""


def _api_adapter(prompt, validator, key=None, *, schema=None,
                 schema_name="arcanum_section_quality_audit",
                 cache_key=None, max_output_tokens=API_MAX_OUTPUT_TOKENS,
                 plain_text=False):
    key = str(key or _openai_key()).strip()
    if not key:
        raise RuntimeError("no OpenAI API key is configured in Settings or OPENAI_API_KEY")
    static, marker, dynamic = prompt.partition(DYNAMIC_MARKER)
    if not marker:
        raise RuntimeError("Validator AI prompt is missing its stable/dynamic cache boundary")
    effort = str(validator.get("effort") or "medium")
    if effort not in ("none", "minimal", "low", "medium", "high", "xhigh"):
        effort = "medium"
    text_config = {"verbosity": "low"}
    if not plain_text:
        text_config["format"] = {
            "type": "json_schema", "name": schema_name,
            "strict": True, "schema": schema or _result_schema(),
        }
    payload = {
        "model": validator["model"],
        "reasoning": {"effort": effort},
        "input": [
            {"role": "developer", "content": [{
                "type": "input_text", "text": static.strip(),
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }]},
            {"role": "user", "content": [{"type": "input_text", "text": dynamic.strip()}]},
        ],
        "text": text_config,
        "max_output_tokens": int(max_output_tokens),
        "prompt_cache_key": (cache_key
                             or f"arcanum-section-quality-v{AUDIT_CONTRACT_VERSION}"),
        "prompt_cache_options": {"mode": "explicit"},
        "store": False,
    }
    request = urllib.request.Request(
        RESPONSES_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[-1200:]
        raise RuntimeError(f"Responses API HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Responses API request failed: {exc}") from exc
    return _response_text(value), {
        "transport": "responses-api", "kind": "openai-api",
        "model": validator["model"], "effort": effort, "usage": _usage(value),
        "responseId": str(value.get("id") or ""),
    }
