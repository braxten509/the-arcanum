"""Provider-neutral prompts for the mandatory section-quality audit."""
from __future__ import annotations

import json

from arcanum.ai import NO_TOME_MEMORY_POLICY

from ..section_quality_contract import section_quality_authority


DYNAMIC_MARKER = "===== DYNAMIC AUDIT INPUT ====="


def result_schema():
    citation = {
        "type": "object", "additionalProperties": False,
        "properties": {"path": {"type": "string"}, "node": {"type": "string"}},
        "required": ["path", "node"],
    }
    finding = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "id": {"type": "string"}, "label": {"type": "string"},
            "kind": {"type": "string"}, "owner": {"type": "string"},
            "detect": {"type": "array", "items": {"type": "string"}},
            "demands": {"type": "array", "items": {"type": "string"},
                        "minItems": 1},
            "closestExisting": {"type": "array", "items": {"type": "string"},
                                "minItems": 1, "maxItems": 3},
            "semanticDelta": {"type": "string"},
        },
        "required": ["id", "label", "kind", "owner", "detect", "demands",
                     "closestExisting", "semanticDelta"],
    }
    node_review = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "path": {"type": "string"}, "node": {"type": "string"},
            "judgment": {"type": "string", "enum": ["PASS", "FAIL"]},
            "evidenceLines": {
                "type": "array", "items": {"type": "integer", "minimum": 1},
                "minItems": 2, "maxItems": 2,
            },
            "evidence": {"type": "string", "minLength": 12},
        },
        "required": ["path", "node", "judgment", "evidenceLines", "evidence"],
    }
    quality_finding = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "path": {"type": "string"}, "node": {"type": "string"},
            "category": {"type": "string", "enum": [
                "teaching-depth", "technical-correctness", "practice-quality",
                "hint-leakage", "learner-independence", "working-quality",
                "continuity", "source-quality", "template-or-filler",
            ]},
            "evidenceLines": {
                "type": "array", "items": {"type": "integer", "minimum": 1},
                "minItems": 2, "maxItems": 2,
            },
            "evidence": {"type": "string", "minLength": 12},
            "requiredRepair": {"type": "string", "minLength": 12},
        },
        "required": ["path", "node", "category", "evidenceLines", "evidence",
                     "requiredRepair"],
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "outcome": {"type": "string", "enum": ["PASS", "FAIL"]},
            "citations": {"type": "array", "items": citation},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "missingMechanisms": {"type": "array", "items": finding},
            "nodeReviews": {"type": "array", "items": node_review},
            "qualityFindings": {"type": "array", "items": quality_finding},
        },
        "required": ["outcome", "citations", "reasons", "missingMechanisms",
                     "nodeReviews", "qualityFindings"],
    }


def prerequisite_prompt(packet, sid, sources, prior, start, depth=0, mastery=0):
    pairs = json.dumps([{"path": item["path"], "node": item["node"]}
                        for item in sources], ensure_ascii=False, separators=(",", ":"))
    authority = section_quality_authority(start, prior, depth, mastery)
    example = json.dumps({
        "outcome": "FAIL",
        "citations": [{"path": "tomes/example/sections/s01/lessons/l01.toml",
                       "node": "s01.l01"}],
        "reasons": ["A concise evidence-based reason."],
        "missingMechanisms": [{
            "id": "example-mechanism", "label": "Example mechanism",
            "kind": "syntax-form", "owner": "s01.l01", "detect": ["example("],
            "demands": ["s01.l01", "s01.working"],
            "closestExisting": ["nearest-sealed-mechanism"],
            "semanticDelta": "The new responsibility changes state in a way the nearest owner does not cover.",
        }],
        "nodeReviews": [{
            "path": "tomes/example/sections/s01/lessons/l01.toml",
            "node": "s01.l01", "judgment": "FAIL", "evidenceLines": [12, 38],
            "evidence": "The example is present, but its only exercise reproduces the shown answer.",
        }],
        "qualityFindings": [{
            "path": "tomes/example/sections/s01/lessons/l01.toml",
            "node": "s01.l01", "category": "practice-quality",
            "evidenceLines": [31, 38],
            "evidence": "The learner can copy the complete worked example without making a choice.",
            "requiredRepair": "Replace it with a new-context construction or debugging task and a non-revealing hint.",
        }],
    }, separators=(",", ":"))
    return f"""Audit teaching quality, learner independence, and first-use prerequisite
completeness for one course section. This is a language-, runtime-, tool-, and project-neutral
reference-tome quality gate. Inspect every citable source in full.

{NO_TOME_MEMORY_POLICY}

{authority}

Apply the shared authority above to every valid source/node pair in the bounded evidence.

State an explicit PASS or FAIL and give substantive reasons. Any clear readable prose or structure
is accepted; field names, wrappers, punctuation, Markdown, JSON, and ordering do not determine
whether the report is usable. PASS still requires concrete evidence
for every provided valid source/node pair and must report no missing mechanisms or quality defects.
Keep each reason, evidence statement, and requiredRepair to one precise sentence; do not restate
the packet. The complete response must fit the fixed 2,500-output-token validator budget.
When convenient, use the following preferred JSON fields so the harness can apply structured
mechanism amendments automatically:
- outcome: PASS or FAIL.
- citations: source path and node pairs.
- reasons: a non-empty array of strings.
- missingMechanisms: objects identifying id, label, kind, owner, detect,
  demands, closestExisting, and semanticDelta. id, label, kind, owner, and semanticDelta are
  strings. demands is ALWAYS a JSON ARRAY of one or more exact node-ID strings, even when there is
  only one demand. closestExisting is an array of one to three exact ids from the sealed mechanism
  ledger. semanticDelta states the distinct responsibility those nearest owners cannot cover.
  detect is an array of the literal spellings a learner types for this mechanism, exactly as they
  appear in code and with significant whitespace kept ("print(", "import ", "#"); give it the empty
  array only for a mechanism with no fixed spelling. Every spelling you supply here is scanned
  mechanically from then on, so this finding never has to be rediscovered by reading code again.
  Never put a prose description or a bare string in any of these arrays.
- nodeReviews: one review for every VALID SOURCE/NODE PAIR, preferably in the given order, identifying
  path, node, judgment, evidenceLines, and evidence. evidenceLines is a
  two-integer inclusive [first,last] line range inside that source. evidence names concrete
  teaching/practice/Working proof found on those lines; generic claims such as "looks complete"
  are invalid. A PASS outcome requires every node judgment to be PASS.
- qualityFindings: actionable defects identifying path, node, category,
  evidenceLines, evidence, and requiredRepair. category is exactly one of teaching-depth,
  technical-correctness, practice-quality, hint-leakage, learner-independence, working-quality,
  continuity, source-quality, or template-or-filler. Use the exact source path/node and an inclusive
  in-file line range. requiredRepair states the smallest content change needed; do not prescribe a
  broad rewrite. PASS requires this array to be empty.
Here is the preferred compact shape; equivalent readable wording is also valid:
{example}
Use missingMechanisms only for genuinely absent sealed mechanisms; owner must be a lesson in this
section and every demands array item must be an exact node ID for that lesson or this section's
Working. First name the closest sealed mechanism ids and explain the non-spelling semantic delta.
If no such delta exists, the demand belongs to an existing mechanism. If teaching evidence for an
already sealed mechanism or one of its equivalent variants is incomplete, FAIL with reasons but do
not duplicate it as missing. Any omission, ambiguity, or absence of required evidence is FAIL with
the smallest actionable repair.

{DYNAMIC_MARKER}
SECTION: {sid}
VALID SOURCE/NODE PAIRS: {pairs}

{packet}"""
