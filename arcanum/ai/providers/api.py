"""Anthropic Messages and OpenAI Responses API transport adapters."""
from __future__ import annotations

import json
import urllib.request

from ..access import ensure_remote_access
from ..repository_tools import anthropic_tools, execute as execute_tool, openai_tools
from ..models import AiRequest, AiResponse


class AnthropicProvider:
    provider_id = "anthropic"

    def complete(self, request: AiRequest) -> AiResponse:
        ensure_remote_access(self.provider_id, request.model, request.api_key)
        messages = [{"role": "user", "content": request.input}]
        tools = []
        if request.web_allowed:
            tools += [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5},
                      {"type": "web_fetch_20250910", "name": "web_fetch"}]
        if request.allowed_tools:
            tools += [row for row in anthropic_tools()
                      if row.get("name") in request.allowed_tools]
        for _ in range(8):
            payload = {"model": request.model, "max_tokens": 4096, "messages": messages}
            if tools:
                payload["tools"] = tools
            call = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode(),
                headers={"x-api-key": request.api_key, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(call, timeout=request.timeout) as response:
                data = json.loads(response.read())
            pending = [item for item in data.get("content", []) if item.get("type") == "tool_use"]
            if not pending:
                text = "".join(item.get("text", "") for item in data.get("content", []))
                return AiResponse(self.provider_id, request.model, text, request.trace)
            messages.append({"role": "assistant", "content": data["content"]})
            results = []
            for item in pending:
                try:
                    output = execute_tool(item["name"], item.get("input") or {}, request.workspace)
                    results.append({"type": "tool_result", "tool_use_id": item["id"],
                                    "content": output})
                except Exception as exc:
                    results.append({"type": "tool_result", "tool_use_id": item["id"],
                                    "content": str(exc), "is_error": True})
            messages.append({"role": "user", "content": results})
        raise RuntimeError("Anthropic provider exceeded eight tool rounds")


class OpenAiProvider:
    provider_id = "openai"

    def complete(self, request: AiRequest) -> AiResponse:
        ensure_remote_access(self.provider_id, request.model, request.api_key)
        next_input, previous = request.input, None
        tools = []
        if request.web_allowed:
            tools.append({"type": "web_search"})
        if request.allowed_tools:
            tools += [row for row in openai_tools()
                      if row.get("name") in request.allowed_tools]
        for _ in range(8):
            payload = {"model": request.model, "input": next_input}
            if tools:
                payload["tools"] = tools
            if previous:
                payload["previous_response_id"] = previous
            call = urllib.request.Request(
                "https://api.openai.com/v1/responses", data=json.dumps(payload).encode(),
                headers={"Authorization": "Bearer " + request.api_key,
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(call, timeout=request.timeout) as response:
                data = json.loads(response.read())
            pending = [item for item in data.get("output", [])
                       if item.get("type") == "function_call"]
            if not pending:
                text = "".join(str(part.get("text") or "") for item in data.get("output", [])
                               if item.get("type") == "message"
                               for part in item.get("content", [])
                               if part.get("type") in ("output_text", "text"))
                return AiResponse(self.provider_id, request.model, text, request.trace)
            next_input = []
            for item in pending:
                try:
                    output = execute_tool(item["name"],
                                          json.loads(item.get("arguments") or "{}"),
                                          request.workspace)
                except Exception as exc:
                    output = json.dumps({"error": str(exc)})
                next_input.append({"type": "function_call_output", "call_id": item["call_id"],
                                   "output": output})
            previous = data["id"]
        raise RuntimeError("OpenAI provider exceeded eight tool rounds")
