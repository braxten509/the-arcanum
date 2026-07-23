"""One language-neutral teaching contract shared by section authors and validators."""
from __future__ import annotations

import json
import os

from .workflow.prompts import START_PACING


SECTION_QUALITY_CONTRACT_VERSION = 3

SECTION_QUALITY_CONTRACT = """===== BINDING SHARED SECTION QUALITY CONTRACT v3 =====
This exact contract governs both the Phase 3 author and the section Validator AI. If a looser or
more general instruction conflicts with it, this contract controls.

QUALITY BAR
- Meet the pedagogical standard of the shipped reference tome, The Liber Veritatis, without
  copying its topic, phrasing, section count, or exercise grid. Numerical density, valid TOML, and
  a clean runtime are necessary but never sufficient.
- Inspect every learner-visible demand: exercises, Working brief and rubrics, proof command,
  assessment, hidden reference, and any exceptional artifact step. Do not flag an optional
  implementation choice when the specification permits a completely taught route.

SEALED AUTHORITY AND DENSITY
- The sealed section promise, mechanism owners, ordered `introduces` lists, and Working mechanism
  list are authoritative. For density review, mechanisms co-owned by the same sealed lesson are
  the Phase 2 concept-family allocation. Do not reclassify them as separate families, ask the
  section author to move or defer them, or fail merely because that lesson owns multiple concrete
  mechanisms. Audit whether the authored lesson teaches that sealed family coherently and gives
  each owned mechanism complete evidence. Authored material outside the sealed allocation remains
  reviewable for excess density.
- A section author cannot edit the sealed map. A validator repair must be achievable within the
  current section files while preserving every sealed owner and mechanism id.
- A future-owned mechanism is unavailable. Remove or replace an incidental authored route that
  uses it; never pull it forward or invent a near-duplicate owner.
- The sealed section promise and project milestone define curriculum scope. Authored lesson,
  Working, rubric, diagnostic, recovery, replay, and hidden-reference details are repairable
  evidence, not authority to expand that scope. When an unnecessarily mechanism-heavy authored
  route creates a first-use problem, simplify or replace the route instead of expanding the map.
- Propose a missing mechanism only when it is unavoidable for the sealed milestone. Incomplete
  teaching for an existing mechanism is a content repair, never grounds for a duplicate owner.

FIRST-USE TEACHING
- Before first required use, explain each unfamiliar syntax form, API, tool action, data-format
  rule, and technical term through purpose and mental model, stepwise anatomy or procedure, a
  minimal worked demonstration with an observable result and why it follows, one realistic failure
  with diagnosis or recovery, and guided practice before independent use.
- At high lesson depth, cover relevant limits, tradeoffs, and non-happy paths without filler.
  Linked readings supplement this teaching and never replace it.
- Audit transitive prerequisites through the smallest meaningful example or procedure. Every
  syntax form, API, tool action, data-format rule, and technical term that example requires needs
  an owner no later than first use. A dependent mechanism cannot teach its own prerequisite, and
  copyable unexplained material is still missing teaching.

PRACTICE AND FEEDBACK
- Guided practice must be followed by a materially different recall, trace, explain, diagnose,
  debug, modify, test-design, or construction action appropriate to the mechanism. A response
  copied verbatim from nearby prose or code is not independent evidence. Retyping and recognition
  may build fluency but cannot be the only proof of understanding.
- Required tool-operation practice must make the learner perform, vary, diagnose, or explain the
  operation and its observable result when the selected external tool path can execute it; a
  hypothetical multiple-choice question alone is insufficient.
- Feedback must diagnose the submitted choice or artifact. Hints may unlock reasoning gradually
  but must not reveal the final response, exact code, or exact action sequence.
- Do not require an artificial exercise-type quota or fixed lesson length. Judge the actual
  learning work, observable evidence, and selected depth instead of surface density.

WORKING AND HIDDEN REFERENCE
- Every required Working operation must be taught before use; the brief, requirements, rubric,
  proof, assessment, and hidden reference must agree with the sealed milestone.
- The hidden reference is one private replay solution, not learner-facing starter material. Every
  operation it performs must use currently available mechanisms, affect an observable result, and
  be represented honestly in its mechanism declarations. It may not bypass, contradict, or silently
  replace learner-owned work.
- The learner-facing Working must require substantive construction, adaptation, diagnosis, or
  justification and retain meaningful implementation choices. Its rubric grades observable
  behavior, the promised capability, and at least one exercised learner choice where the task
  permits one; copying a lesson example, lightly renaming supplied material, transcribing a
  starter, following a hidden assumption, or matching one leaked output is insufficient.
- The hidden reference must exercise every mechanism it declares. Every operation it performs
  must affect the artifact's observable result; computing, storing, or listing something that the
  completed step discards is not meaningful evidence.
- If no honest route can satisfy a sealed mechanism in this section, state the unmet demand
  plainly. Treating a real contract conflict as unmet is preferable to a satisfied-in-form hidden
  reference and is never deception.

MECHANISM IDENTITY AND CLOSURE
- A mechanism is one transferable semantic responsibility, not one surface spelling. Compare
  learner intent, preconditions, state transition or resource-lifecycle responsibility,
  observable result, and failure interpretation before declaring anything missing.
- Platform commands, executable aliases, flags, paths, activation spellings, UI routes,
  configuration syntaxes, and language/runtime/tool variants belong to an existing mechanism when
  those semantic properties match.
  They do not get separate owners merely because their tokens differ. Split only for a genuinely
  different transition, lifecycle duty, observable contract, or reusable reasoning responsibility.
- A later owner is unavailable now. If a demand matches a future mechanism, remove the incidental
  early demand or report the late owner; never invent a duplicate.
- Apply observable-interaction closure to the brief, rubric, proof, replay, acceptance path, and
  controls. Concrete operations needed to obtain and inspect input, produce output, advance time,
  make a nondeterministic choice, persist state, release a resource, or respond to an observed
  result require an owner by first use. Acquiring a stream, event, handle, or resource does not
  own the operations that interpret or act on it.
- Trace every tool and data/configuration artifact through creation, editing, saving, invocation,
  observation, diagnosis, and cleanup as applicable. Treat every word in a capability id as
  binding semantic scope; every claimed component family must have teaching evidence in that
  capability's owner lesson or an earlier lesson.

TECHNICAL AND PEDAGOGICAL QUALITY
- Reject factual contradictions, impossible commands, examples whose claimed result does not
  follow, repeated template prose, filler, and duplicated practice hidden behind new labels.
- Linked sources anchor or extend instruction but cannot replace required teaching. Current or
  compatibility-sensitive technical claims must agree with the section's sealed research and
  executable route.
- At Mastery 3 or above, require transferable language reasoning: retrieval of earlier
  capabilities, implementation choices, failure interpretation, and the language's verification
  loop where relevant. At lower mastery, the smaller graduate boundary still requires genuine
  independent construction inside its declared scope.
- Preserve cumulative learner-owned work. Later steps may retrieve, extend, and debug it but may
  not silently replace, contradict, or bypass it.

COMPLETE-PASS DISCIPLINE
- After all section files exist and before handoff, the author must reread every lesson plus the
  Working, assessment, proof, and hidden reference and apply this complete contract once as a
  whole-section coverage sweep. The validator performs the same sweep and reports every current
  defect together. Neither role may stop at the first defect, sample only selected nodes, or treat
  a clean mechanical gate as semantic evidence.
- For every learner-visible demand and every hidden-reference operation, verify all five facts:
  (1) each required syntax, API, tool action, data/configuration rule, and term has an available
  owner that teaches it before use; (2) the exact command or procedure can produce the claimed
  observation on the stated route; (3) required practice makes the learner perform a materially
  varied action and submit or interpret observable evidence rather than copy a nearby answer;
  (4) every operation performed by proof or replay is declared under the mechanisms it actually
  exercises; and (5) the public brief, rubric, assessment, proof, replay, sealed mechanism route,
  and cumulative artifact state do not contradict one another.
- When the sweep finds an incidental future-owned or undeclared prerequisite, first simplify the
  authored route. Report a missing mechanism only when the sealed milestone cannot honestly avoid
  that distinct responsibility. Repair all other sweep findings before marking the section
  validating.
===== END SHARED SECTION QUALITY CONTRACT ====="""


def pacing_contract(start):
    return START_PACING.get(start, (
        "PRIOR-KNOWLEDGE CALIBRATED",
        "Omit fundamentals covered by the selected Starting Level and any concrete optional "
        "prior-knowledge details, but never expand those details to nearby skills. Teach every "
        "course-specific, uncommon, or non-obvious mechanism completely before use. Do not "
        "dilute advanced material with remedial repetition or compress unrelated new ideas.",
    ))


def section_quality_settings(build_dir, build_id):
    """Return the one calibration record consumed by both section roles."""
    try:
        with open(os.path.join(build_dir, f"{build_id}.launch.json"), encoding="utf-8") as handle:
            launch = json.load(handle)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        launch = {}
    gate = launch.get("gate") if isinstance(launch, dict) else {}
    gate = gate if isinstance(gate, dict) else {}

    def number(key):
        try:
            return int(gate.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    return {
        "start": number("prior_level"),
        "prior": str(gate.get("prior_knowledge") or ""),
        "depth": number("depth"),
        "mastery": number("mastery"),
    }


def section_quality_authority(start=0, prior="", depth=0, mastery=0):
    """Render the exact semantic authority inserted into both role prompts."""
    pacing_title, pacing_summary = pacing_contract(start)
    depth_label = f"{depth}/10" if depth else "not recorded (apply the ordinary full standard)"
    mastery_label = (f"{mastery}/5" if mastery else
                     "not recorded (still require an independently achievable Working)")
    return f"""{SECTION_QUALITY_CONTRACT}

===== BINDING SHARED SECTION CALIBRATION =====
OPTIONAL PRIOR-KNOWLEDGE DETAILS: {prior!r}
START LEVEL: {start}/10 ({pacing_title})
LESSON DEPTH: {depth_label}
LANGUAGE MASTERY: {mastery_label}
BINDING LESSON-DENSITY RULE: {pacing_summary}
The selected Start is {start}/10 ({pacing_title}).
Starting level controls cognitive-load packaging, step size, repetition, and pace.
Lesson Depth controls explanatory thoroughness and never overrides the density rule. Mastery
controls the independence and transfer evidence required at the exit; it never excuses missing
first-use teaching.
===== END SHARED SECTION CALIBRATION ====="""


def section_quality_contract_packet(start=0, prior="", depth=0, mastery=0):
    settings = {"start": int(start or 0), "prior": str(prior or ""),
                "depth": int(depth or 0), "mastery": int(mastery or 0)}
    return {"version": SECTION_QUALITY_CONTRACT_VERSION,
            "text": SECTION_QUALITY_CONTRACT,
            "settings": settings,
            "authorityText": section_quality_authority(**settings)}
