"""Provider-neutral prompts for the mandatory prerequisite audit."""
from __future__ import annotations

import json

from ..workflow.prompts import START_PACING


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
            "demands": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["id", "label", "kind", "owner", "demands"],
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "outcome": {"type": "string", "enum": ["PASS", "FAIL", "UNCERTAIN"]},
            "citations": {"type": "array", "items": citation},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "missingMechanisms": {"type": "array", "items": finding},
        },
        "required": ["outcome", "citations", "reasons", "missingMechanisms"],
    }


def prerequisite_prompt(packet, sid, sources, prior, start):
    pairs = json.dumps(sources, ensure_ascii=False, separators=(",", ":"))
    pacing_title, pacing_summary = START_PACING[start]
    example = json.dumps({
        "outcome": "FAIL",
        "citations": [{"path": "tomes/example/sections/s01/lessons/l01.toml",
                       "node": "s01.l01"}],
        "reasons": ["A concise evidence-based reason."],
        "missingMechanisms": [{
            "id": "example-mechanism", "label": "Example mechanism",
            "kind": "syntax-form", "owner": "s01.l01",
            "demands": ["s01.l01", "s01.working"],
        }],
    }, separators=(",", ":"))
    return f"""Audit first-use prerequisite completeness for one beginner course section. This is
a language-agnostic audit, not a broad quality review. Inspect every learner-visible demand:
lesson exercises, artifact steps, Working brief, rubrics, proof command, and the hidden reference
solution as evidence of what the Working actually requires. For every required keyword, syntax
form, operator, API, tool action, or technical term outside the provided whitelist, verify that its
sealed mechanism has an owner no later than first use and that the owner's lesson explains purpose,
stepwise anatomy, a minimal worked example with observable output, one likely failure, and guided
practice before independent use. Do not flag an optional implementation choice when the
specification permits a taught route.

Audit transitive prerequisites too. For each mechanism, inspect the smallest meaningful example
or procedure that teaches it. Every unlisted syntax form, API, tool action, data-format rule, or
technical term required by that example needs an earlier owner; a dependent mechanism cannot count
as teaching its own prerequisite, and copyable unexplained material is still missing teaching.
Trace how each API input or resource is created, obtained, and released. Apply observable-interaction
closure to the learner-visible brief, rubric, proof, replay, acceptance path, and
controls: every concrete operation needed to obtain and inspect input, produce output, advance
time, make a nondeterministic choice, persist state, release a resource, or respond to the observed
result needs an earlier owner. Acquiring a stream, event, handle, or resource does not own the
operations that interpret or act on its contents. Trace how each tool or data/configuration file is
created, edited, saved, and invoked. Treat every word in a capability id as binding semantic scope:
its owner is the cumulative boundary, so every claimed component family
must have explicit teaching evidence in that lesson or an earlier one, never a later one.

Return only one JSON object, with no Markdown fence or surrounding prose. PASS requires every
provided valid source/node pair to be cited and missingMechanisms to be empty.
The result has exactly four keys and these exact JSON types:
- outcome: one string, exactly "PASS", "FAIL", or "UNCERTAIN".
- citations: an array of objects; each object has exactly the string keys path and node.
- reasons: a non-empty array of strings.
- missingMechanisms: an array of objects; each object has exactly id, label, kind, owner, and
  demands. id, label, kind, and owner are strings. demands is ALWAYS a JSON ARRAY of one or more
  exact node-ID strings, even when there is only one demand. Never put a prose description or a
  bare string in demands.
Use this shape and replace the example values with audit evidence:
{example}
Use missingMechanisms only for genuinely absent sealed mechanisms; owner must be a lesson in this
section and every demands array item must be an exact node ID for that lesson or this section's
Working. If teaching evidence for an already sealed mechanism is incomplete, FAIL with reasons but
do not duplicate it as missing. Missing evidence is UNCERTAIN, never PASS.

{DYNAMIC_MARKER}
SECTION: {sid}
EXHAUSTIVE PRIOR-KNOWLEDGE WHITELIST: {prior!r}
START: {start}/3 ({pacing_title})
The selected Start is {start}/3 ({pacing_title}).
BINDING LESSON-DENSITY RULE: {pacing_summary}
Starting level controls cognitive-load packaging, step size, repetition, and pace;
Lesson Depth controls explanatory thoroughness and never overrides this density rule.
VALID SOURCE/NODE PAIRS: {pairs}

{packet}"""


def format_repair_prompt(prompt, raw):
    previous = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    return f"""{prompt}

===== FORMAT CORRECTION RETRY =====
Your previous answer below had the required audit intent but violated the mechanically enforced
JSON contract. Preserve its substantive PASS, FAIL, or UNCERTAIN judgment and evidence. Return the
entire corrected result again as only one JSON object with exactly outcome, citations, reasons, and
missingMechanisms. In particular, every missingMechanisms item must contain exactly id, label,
kind, owner, and demands; demands must be a non-empty JSON array of exact current node-ID strings,
never a prose string. Do not add Markdown or commentary.

PREVIOUS ANSWER TO REFORMAT:
{previous[-20_000:]}"""
