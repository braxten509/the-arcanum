"""Provider-neutral prompts for the mandatory section-quality audit."""
from __future__ import annotations

import json

from ..workflow.prompts import START_PACING


DYNAMIC_MARKER = "===== DYNAMIC AUDIT INPUT ====="


def pacing_contract(start):
    return START_PACING.get(start, (
        "PRIOR-KNOWLEDGE CALIBRATED",
        "Omit fundamentals covered by the selected Starting Level and any concrete optional "
        "prior-knowledge details, but never expand those details to nearby skills. Teach every "
        "course-specific, uncommon, or non-obvious mechanism completely before use. Do not "
        "dilute advanced material with remedial repetition or compress unrelated new ideas.",
    ))


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
            "demands": {"type": "array", "items": {"type": "string"},
                        "minItems": 1},
            "closestExisting": {"type": "array", "items": {"type": "string"},
                                "minItems": 1, "maxItems": 3},
            "semanticDelta": {"type": "string"},
        },
        "required": ["id", "label", "kind", "owner", "demands",
                     "closestExisting", "semanticDelta"],
    }
    node_review = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "path": {"type": "string"}, "node": {"type": "string"},
            "judgment": {"type": "string", "enum": ["PASS", "FAIL", "UNCERTAIN"]},
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
            "outcome": {"type": "string", "enum": ["PASS", "FAIL", "UNCERTAIN"]},
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
    pacing_title, pacing_summary = pacing_contract(start)
    example = json.dumps({
        "outcome": "FAIL",
        "citations": [{"path": "tomes/example/sections/s01/lessons/l01.toml",
                       "node": "s01.l01"}],
        "reasons": ["A concise evidence-based reason."],
        "missingMechanisms": [{
            "id": "example-mechanism", "label": "Example mechanism",
            "kind": "syntax-form", "owner": "s01.l01",
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
    depth_label = f"{depth}/10" if depth else "not recorded (apply the ordinary full standard)"
    mastery_label = (f"{mastery}/5" if mastery else
                     "not recorded (still require an independently achievable Working)")
    return f"""Audit teaching quality, learner independence, and first-use prerequisite
completeness for one course section. This is a language-, runtime-, tool-, and project-neutral
reference-tome quality gate. The target is the pedagogical standard of the shipped reference tome,
The Liber Veritatis, not its topic, phrasing, section count, or exercise grid. Inspect every
citable source in full.
Numerical density, valid TOML, and a clean runtime are necessary but never sufficient for PASS.

Inspect every learner-visible demand:
lesson exercises, the Working brief and rubrics, proof command, hidden reference solution, and any
exceptional lesson artifact step. For every required keyword, syntax
form, operator, API, tool action, or technical term outside the declared entry baseline, verify that its
sealed mechanism has an owner no later than first use and that the owner's lesson explains purpose,
stepwise anatomy, a minimal worked example with observable output, one likely failure, and guided
practice before independent use. Do not flag an optional implementation choice when the
specification permits a taught route.

Audit teaching quality separately from prerequisite ownership. A lesson passes only when its
selected concept family is coherent at the sealed Start pace and the learner-visible path:
- explains purpose and mental model in plain language, then anatomy or procedure step by step;
- contains a minimal worked example or demonstration with an observable result and explains why
  that result follows, rather than presenting unexplained copyable material;
- teaches at least one realistic failure, how the learner recognizes it, and how to diagnose or
  recover from it; at high lesson depth, it also covers relevant limits, tradeoffs, and non-happy
  paths without padding the word count;
- provides guided practice followed by a materially different recall, trace, explain, debug,
  modify, test-design, or construct action appropriate to the topic. A prompt answered verbatim by
  nearby prose or code is not independent practice. Retyping may build fluency but cannot be the
  only proof of understanding;
- gives exercise-specific feedback and a graduated hint that unlocks reasoning without revealing
  the final response, exact code, or exact sequence of actions; and
- uses linked readings as anchors or extensions, never as a substitute for teaching required
  course material.

The section Working passes only when every required operation is taught before use, the brief and
rubric agree, the hidden reference is feasible, and a learner who followed only the visible path
can complete it. Hold the hidden reference to the same standard as a lesson worked example,
because it is what a learner compares their own attempt against. It must exercise every mechanism
it declares rather than merely listing it, and every operation it performs must affect the
artifact's observable result. FAIL a reference that declares a mechanism absent from what it
actually writes, that computes or stores a value the rest of the step discards, or that satisfies a
required demand by its literal form while demonstrating nothing a learner could learn from. When
the author instead states plainly that a sealed mechanism has no honest route in this section, treat
that as an ordinary unmet demand naming the conflict, not as deception; it is the outcome this gate
prefers over a satisfied-in-form reference. The learner must construct, adapt, diagnose, or justify something substantive and
retain meaningful implementation choices. FAIL if success is mainly copying a lesson example,
renaming a supplied solution, transcribing the starter, following a hidden assumption, or matching
one leaked output. The rubric must grade observable behavior and the section's promised capability,
not surface tokens. Check cumulative continuity: later steps may retrieve earlier learning but may
not silently replace, contradict, or bypass learner-owned work.

At Mastery 3 or above, require transferable language reasoning rather than project-only mimicry:
the section must make the learner retrieve earlier capabilities, make implementation choices,
interpret failures, and use the language's verification loop where relevant. At lower Mastery,
the smaller graduate boundary is still real: do not waive independent construction inside the
declared scope. Reject repeated template prose, filler, duplicated practice in new labels, factual
contradictions, impossible commands, and examples whose claimed observable result does not follow.
Do not demand an artificial exercise-type quota or a fixed lesson length; judge the learning work.

The sealed section promise and projectMilestone define required curriculum scope. Authored lesson,
Working, rubric, diagnostic, recovery, and replay details are repairable evidence, not authority to
expand that scope. If an unowned mechanism appears only because the author chose an unnecessarily
mechanism-heavy route and the sealed milestone can be met with existing owners, FAIL with a reason
to simplify or replace that route and leave missingMechanisms empty. Propose a new mechanism only
when it is unavoidable for the sealed milestone itself.

A mechanism is one transferable semantic responsibility, not one surface spelling. Before
proposing anything missing, compare the demand with all sealed mechanisms available by first use
using learner intent, preconditions, state transition or resource-lifecycle responsibility,
observable result, and failure interpretation. Platform-specific commands, executable aliases,
flags, paths, activation spellings, UI routes, configuration syntaxes, and language/runtime/tool
variants are evidence or anatomy under an existing mechanism when those properties are the same.
They do not get separate owners merely because their tokens differ. Split mechanisms only when the
demand adds a genuinely different state transition, lifecycle duty, observable contract, or
reusable reasoning responsibility. This rule is language-, runtime-, tool-, and project-neutral.

Audit transitive prerequisites too. For each mechanism, inspect the smallest meaningful example
or procedure that teaches it. Every unlisted syntax form, API, tool action, data-format rule, or
technical term required by that example needs an earlier owner; a dependent mechanism cannot count
as teaching its own prerequisite, and copyable unexplained material is still missing teaching.
The packet contains the mechanisms available by this section plus a compact sealed future index of
[id, owner] pairs. A future mechanism is not available yet. If a current demand matches one of
those later mechanisms, report the late owner as a FAIL reason and do not propose a duplicate.
Trace how each API input or resource is created, obtained, and released. Apply observable-interaction
closure to the learner-visible brief, rubric, proof, replay, acceptance path, and
controls: every concrete operation needed to obtain and inspect input, produce output, advance
time, make a nondeterministic choice, persist state, release a resource, or respond to the observed
result needs an earlier owner. Acquiring a stream, event, handle, or resource does not own the
operations that interpret or act on its contents. Trace how each tool or data/configuration file is
created, edited, saved, and invoked. Treat every word in a capability id as binding semantic scope:
its owner is the cumulative boundary, so every claimed component family
must have explicit teaching evidence in that lesson or an earlier one, never a later one.

State an explicit PASS, FAIL, or UNCERTAIN and give substantive reasons. Any clear readable structure
is accepted: JSON is preferred for compactness, but field names, wrappers, punctuation, Markdown,
and ordering do not determine whether the report is usable. PASS still requires concrete evidence
for every provided valid source/node pair and must report no missing mechanisms or quality defects.
Keep each reason, evidence statement, and requiredRepair to one precise sentence; do not restate
the packet. The complete response must fit the fixed 2,500-output-token validator budget.
When convenient, use the following preferred JSON fields so the harness can apply structured
mechanism amendments automatically:
- outcome: PASS, FAIL, or UNCERTAIN.
- citations: source path and node pairs.
- reasons: a non-empty array of strings.
- missingMechanisms: objects identifying id, label, kind, owner,
  demands, closestExisting, and semanticDelta. id, label, kind, owner, and semanticDelta are
  strings. demands is ALWAYS a JSON ARRAY of one or more exact node-ID strings, even when there is
  only one demand. closestExisting is an array of one to three exact ids from the sealed mechanism
  ledger. semanticDelta states the distinct responsibility those nearest owners cannot cover.
  Never put a prose description or a bare string in either array.
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
not duplicate it as missing. Use FAIL when the bounded packet shows an actual omission. Use
UNCERTAIN only when a specific ambiguity prevents a defensible PASS or FAIL; absence of required
evidence is a definitive FAIL, not uncertainty.

{DYNAMIC_MARKER}
SECTION: {sid}
OPTIONAL PRIOR-KNOWLEDGE DETAILS: {prior!r}
START LEVEL: {start}/10 ({pacing_title})
LESSON DEPTH: {depth_label}
LANGUAGE MASTERY: {mastery_label}
The selected Start is {start}/10 ({pacing_title}).
BINDING LESSON-DENSITY RULE: {pacing_summary}
Starting level controls cognitive-load packaging, step size, repetition, and pace;
Lesson Depth controls explanatory thoroughness and never overrides this density rule.
VALID SOURCE/NODE PAIRS: {pairs}

{packet}"""


def unusable_response_retry_prompt(prompt, raw, errors=(), known_mechanisms=()):
    previous = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    error_list = json.dumps(list(errors), ensure_ascii=False)
    allowed = json.dumps(sorted(known_mechanisms), ensure_ascii=False)
    return f"""{prompt}

===== UNUSABLE RESPONSE RECOVERY RETRY =====
The previous answer below did not contain a safely recoverable verdict with the required bounded
evidence. This retry is for unusable content, not harmless formatting drift. Return the entire
result with an explicit verdict, source-bounded evidence, and any actionable repairs. JSON using
outcome, citations, reasons, missingMechanisms, nodeReviews, and qualityFindings is preferred but
not required. Cover every source. For an automatic missing-mechanism amendment, identify id, label,
kind, owner, demands, closestExisting, and semanticDelta. demands must be a non-empty JSON array of
exact current node-ID strings; closestExisting must contain one to three exact sealed mechanism
ids; semanticDelta must identify a genuinely distinct responsibility, not a command or syntax
spelling.

UNUSABLE RESPONSE DEFECTS: {error_list}
ALLOWED closestExisting MECHANISM IDS: {allowed}

PREVIOUS UNUSABLE ANSWER:
{previous[-20_000:]}"""
