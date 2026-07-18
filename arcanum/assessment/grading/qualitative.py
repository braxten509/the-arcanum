"""Assessment prompt and result validation over the role-neutral AI port."""
from __future__ import annotations

import hashlib
import json

from arcanum.ai import AiRequest, AiService
from arcanum.ai.json_response import parse_json_object

from .providers import QualitativeRequest, QualitativeResponse


class AiQualitativeProvider:
    def __init__(self, ai: AiService, provider_id: str, model: str, workspace: str,
                 *, api_key: str = "", custom_command: str = "", timeout: int = 420):
        self.ai = ai
        self.provider_id = provider_id
        self.model = model
        self.workspace = workspace
        self.api_key = api_key
        self.custom_command = custom_command
        self.timeout = timeout

    def score(self, request: QualitativeRequest) -> QualitativeResponse:
        criteria = list(request.criteria)
        safe_report = [{key: row.get(key) for key in
                        ("id", "kind", "requirementIds", "capabilityIds", "passed", "problems")}
                       for row in request.deterministic]
        source = "\n".join(
            f"===== {path} =====\n{content}" for path, content in request.source_files)
        prompt = (
            f"You are the qualitative reviewer for a {request.language} learning assessment. "
            "Executable truth is already owned by the deterministic report. Score only the named "
            "qualitative criteria. Do not infer hidden architecture, compare against a reference "
            "solution, or award executable behavior. Judge the learner's chosen design against the "
            "public requirements and taught language conventions.\n\n"
            "PUBLIC REQUIREMENTS:\n" + json.dumps(list(request.public_requirements), ensure_ascii=False) +
            "\n\nDETERMINISTIC REPORT:\n" + json.dumps(safe_report, ensure_ascii=False) +
            "\n\nQUALITATIVE CRITERIA:\n" + json.dumps(criteria, ensure_ascii=False) +
            "\n\nLEARNER RATIONALE:\n" + request.rationale[:20_000] +
            "\n\nSAFE SOURCE FILES:\n" + source[:1_500_000] +
            '\n\nReturn only JSON: {"scores":[{"id":"criterion-id","score":0-10,'
            '"comment":"specific concise feedback"}],"feedback":"overall feedback"}. '
            "Return every criterion exactly once and no others.")
        response = self.ai.complete(self.provider_id, AiRequest(
            role="qualitative-grader", model=self.model, input=prompt,
            timeout=self.timeout, workspace=self.workspace,
            response_schema={"scores": "criterion scores", "feedback": "text"},
            api_key=self.api_key, custom_command=self.custom_command,
            trace={"tomeId": request.tome_id, "nodeId": request.node_id}))
        parsed = parse_json_object(response.text)
        if set(parsed) != {"scores", "feedback"} or not isinstance(parsed["scores"], list):
            raise ValueError("qualitative grader returned an invalid result shape")
        expected = {row["id"] for row in criteria}
        ids = [str(row.get("id") or "") for row in parsed["scores"]
               if isinstance(row, dict)]
        if len(ids) != len(parsed["scores"]) or len(ids) != len(set(ids)) or set(ids) != expected:
            raise ValueError("qualitative grader criterion IDs do not exactly match the rubric")
        normalized = []
        for row in parsed["scores"]:
            score = row.get("score")
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                raise ValueError(f"qualitative score for {row['id']!r} is not numeric")
            normalized.append({"id": row["id"], "score": max(0.0, min(10.0, float(score))),
                               "comment": str(row.get("comment") or "")[:2_000]})
        binding = json.dumps({"request": request.__dict__, "response": parsed,
                              "provider": response.provider, "model": response.model},
                             default=list, sort_keys=True, separators=(",", ":"))
        evidence_hash = hashlib.sha256(binding.encode("utf-8")).hexdigest()
        return QualitativeResponse(tuple(normalized), response.provider, response.model,
                                   evidence_hash, str(parsed["feedback"])[:8_000])
