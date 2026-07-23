"""Phase-0 answers and the calibrated build plan given to the sole author."""
import json
import re
import sys

from .checkpoints import ARC_CONTRACT, ARC_HEADING
from ..course.limits import mastery_section_cap
from ..mastery_evidence import load_policy


GATE_QS = [
    ("Prior knowledge", "What can the student already do? (optional; leave blank to use Starting level only)"),
    ("Starting level (1-10)", "How much does the student know about this subject?"),
    ("Project scope (1-5)", "How large and complete should the finished project be?"),
    ("Lesson depth (1-10)", "How deeply should each included mechanism be taught?"),
    ("Mastery (1-5)", "How independently must the student use the course's declared language after the last chapter? Levels 1–2 remain project-first; levels 3–5 make language mastery primary."),
    ("Tooling", "internal, external, or both?"),
]

PRIOR_KNOWLEDGE_UNSPECIFIED = "Not specified; use Starting level as the sole entry baseline."

PROJECT_SCOPE_LEVELS = {
    1: ("MINIMAL PROOF", "A barely functional proof project: one complete workflow and only "
        "the pieces needed to demonstrate the course skills."),
    2: ("SMALL SLICE", "A compact prototype with a few connected features and a clear "
        "end-to-end workflow."),
    3: ("COMPLETE SMALL PROJECT", "A coherent small project with several integrated "
        "features, persistent state where relevant, and a clear completion condition."),
    4: ("SUBSTANTIAL PROJECT", "A substantial project with deeper functionality, robust "
        "behavior, testing, polish, and complete delivery."),
    5: ("FULL-FLEDGED PROJECT", "The broadest feasible finished project: multiple "
        "developed subsystems, broad coverage, polished behavior, testing, and packaged "
        "delivery where the platform supports it."),
}

# Lesson depth may add detail, but it cannot undercut the selected language finish.
MASTERY_DEPTH_FLOORS = {1: 3, 2: 5, 3: 7, 4: 8, 5: 9}

MASTERY_LEVELS = {
    1: ("MINIMUM BUILD PATH", "Learns only the language and tooling required to build the requested project from scratch, with guided explanation and modification rather than broad fluency."),
    2: ("FUNCTIONAL", "Can use the language for familiar small tasks and repair simple faults without step-by-step help."),
    3: ("CAPABLE", "Can transfer language concepts to novel real problems, integrate and debug the result, and justify language-level choices independently."),
    4: ("ADVANCED", "Can use the language across unfamiliar variations, important tradeoffs, internals, and power tools with minimal scaffolding."),
    5: ("EXPERT", "Can architect a substantial solution in the language from goals and constraints, validate it, and defend consequential language and design tradeoffs."),
}

MASTERY_EVIDENCE = {
    1: ("The final Working may remain guided, but it must grade explanation and safe modification "
        "of the declared language's taught mechanisms. Project completion alone is not evidence."),
    2: ("At least one later Working must remove step-by-step language implementation and grade a "
        "complete familiar language task or simple language-level fault repair from requirements "
        "and observable results."),
    3: ("Use at least two graded late language-transfer performances, including the final Working. "
        "State project behavior, constraints, and observable checks, but not the language "
        "implementation. Each must require a novel extension, integration, or diagnosis that "
        "cannot be completed by mechanically copying or renaming a worked example, and at least "
        "one must grade a recorded rationale for a taught language choice."),
    4: ("Use repeated late language performances with unfamiliar variations, incomplete-but-fair "
        "requirements, edge cases, tool-driven diagnosis, and competing language tradeoffs. "
        "Supply contracts and evidence, not solution structure."),
    5: ("Make the culminating work a substantial language architecture problem: the learner "
        "defines boundaries and tests, adapts to a new constraint, validates the delivered "
        "result, and defends language and design tradeoffs without implementation scaffolding."),
}

PRIOR_LEVELS = {
    1: ("FROM ZERO", "Assume no subject knowledge; teach setup, first run, and every required construct from first principles at a deliberately low-density pace."),
    2: ("NEAR ZERO", "Cover level-1 fundamentals at a moderate pace with less repetition, never fewer concepts."),
    3: ("BEGINNER", "Teach the subject from the ground up; dense lessons are allowed after their prerequisites are secure."),
    4: ("TRANSFER LEARNER", "Compress general transferable concepts; use optional prior-knowledge details to tailor the bridge."),
    5: ("GENERALIST", "Assume general practice, not subject expertise; teach focused foundations."),
    6: ("ADJACENT", "Bridge typical neighboring-domain experience to this subject; use optional details to tailor the bridge."),
    7: ("PRACTITIONER", "Assume routine fundamentals; introduce course-specific APIs and constraints."),
    8: ("FLUENT", "Focus on integration, tradeoffs, and failure modes; teach uncommon material."),
    9: ("ADVANCED", "Focus on internals, architecture, edge cases, and difficult tradeoffs."),
    10: ("EXPERT", "Treat the learner as a peer and teach only relevant non-obvious material."),
}

START_PACING = {
    1: ("LOW DENSITY", "Introduce one foundational concept family per lesson. Keep independently "
        "teachable language, API, and tool families in separate lessons, and provide repeated "
        "guided practice before combining them."),
    2: ("MODERATE DENSITY", "Introduce one major concept family per lesson, with only tightly "
        "related supporting syntax, APIs, terms, or tool actions. Split independently teachable "
        "foundations and use less repetition than Start 1."),
    3: ("DENSE READY", "Lessons may introduce multiple closely related concept families once their "
        "prerequisites are secure and each receives complete first-use teaching and guided practice. "
        "Do not combine unrelated foundations merely to shorten the course."),
}

TOOLING_POLICY = {
    "internal": ("INTERNAL (in-browser only)", "Use the browser workbench only; do not require downloads or externalWorkspace."),
    "external": ("EXTERNAL (teach the real tools)", "Teach the real toolchain from install through diagnostics and delivery."),
    "both": ("BOTH (internal + external available)", "Support the browser workbench and the complete real-tool path."),
}


LEARNER_CONSTRUCTION_INSTRUCTION = (
    "Every canonical project artifact must be created or assembled by the learner: project "
    "structure, source, configuration, data, tests, maps, documentation, asset selection and "
    "placement, packaging, and delivery. Seed only a blank editor file or unavoidable behavior-free "
    "tool metadata—never project material. Do not give them any starter implementation, "
    "production-ready stub, ready-to-paste file or patch, filled record, answer-bearing test, or "
    "decisive integration. Make each section's learner-visible Working the canonical project "
    "assignment: state its outcome, flexible implementation choices, constraints, commands, "
    "diagnostics, and observable acceptance there. Lessons teach with small disposable examples "
    "that use different identifiers, values, and problem shapes; do not repeat the chapter Working "
    "beneath every lesson. Omit lesson artifactSteps normally. Use one only for a genuinely necessary "
    "intermediate prerequisite that must happen before the Working, and keep it a work order rather "
    "than answer delivery. Complete replayable non-media solutions belong only in hidden "
    "referenceSteps, while media remains learner-sourced rather than bundled."
)


def learner_construction_contract():
    """Language-agnostic ownership boundary for the artifact the course promises."""
    return (
        "- **Learner-construction rule:** The learner creates or assembles every canonical project "
        "structure, source, configuration, data, test, map, documentation, asset selection and "
        "placement, package, and delivery artifact. Seed only a blank editor file or unavoidable "
        "behavior-free tool metadata; never provide project material, a starter implementation, "
        "production-ready stub, ready-to-paste file/patch, filled record, answer-bearing test, or "
        "decisive integration.",
        "- **Worked-example boundary:** Teach unfamiliar material with small, complete, disposable "
        "examples whose identifiers, values, and problem shape differ from the canonical project. "
        "Examples explain a mechanism; they are not pieces the learner can copy or lightly rename "
        "into the promised artifact.",
        "- **Working-project boundary:** Each section's learner-visible Working is the ordinary "
        "cumulative project assignment. It states the outcome, required behavior, constraints, "
        "commands, diagnostics, observable acceptance, and a meaningful surface for learner design "
        "choices. Put the complete replayable non-media answer only in hidden referenceSteps; media "
        "remains learner-sourced rather than bundled.",
        "- **Exceptional-step boundary:** Omit lesson artifactSteps normally; lessons teach and "
        "practice with disposable examples instead of repeatedly assigning the chapter project. Add "
        "an artifactStep only when a genuinely necessary intermediate prerequisite must occur before "
        "the Working. It may state a path and observable checks but never reveal canonical project "
        "content or duplicate the Working.",
    )


def mastery_contract(mastery):
    """Language-agnostic exit evidence written into every build plan."""
    title, outcome = MASTERY_LEVELS[mastery]
    evidence = load_policy()
    evidence_level = evidence.for_level(mastery)
    if mastery == 1:
        mastery_target = (
            "The requested project is primary. Teach the bare minimum of the declared language "
            "needed to complete it, while still requiring the learner—not supplied project "
            "code—to write or assemble every canonical implementation.")
    elif mastery == 2:
        mastery_target = (
            "The requested project is primary, but the course must deliberately teach useful "
            "general areas of the declared language beyond the narrowest project path. The "
            "learner authors every canonical implementation.")
    else:
        mastery_target = (
            "Language mastery is the primary product. The requested project is the cumulative "
            "practice, integration, and proof vehicle; completing project behavior cannot "
            "substitute for language fluency.")
    foundation_rule = (
        "Map the declared language's idiomatic mechanisms to five universal roles—data, control, "
        "decomposition, failure handling, and verification. These are language outcomes, never "
        "framework features."
        if mastery < 3 else
        "Map the declared language's idiomatic mechanisms to seven universal roles—data, control, "
        "decomposition, structured abstraction, modularity, failure handling, and verification. "
        "Structured abstraction must name a concrete idiom the language actually provides for "
        "organizing related state and behavior or representing variants and contracts; modularity "
        "must name its real module, package, namespace, or boundary mechanism. These are language "
        "outcomes, never framework features. Any matching profile in "
        "global-configs/language-mastery.toml further names essential idioms that cannot be "
        "substituted. When no profile exists, derive idiomatic capability names from verified "
        "semantics of the declared language instead of borrowing another language's taxonomy. "
        "Routine failure handling and verification must be graduate abilities, and late graded "
        "evidence must exercise every declared language capability."
    )
    return (
        f"- **Finish {mastery}/5 — {title}:** {outcome}",
        "- **Language mastery contract:** 1",
        "- **Language practice contract:** 1",
        f"- **Mastery evidence contract:** {evidence.version}",
        "- **Evidence progression:** Resolve 100% of required lesson work and every blocking "
        "due review before a Working unlocks. A Working passes only at 80/B or better with "
        "every essential check green. Supported work resolves learning work but never counts "
        "as independent mastery evidence; retries remain unlimited.",
        f"- **Evidence profile {mastery}/5:** at least {evidence_level.late_performances} late "
        f"performance(s), {evidence_level.standalone_labs} standalone mastery lab(s), "
        f"{evidence_level.rationales} rationale/defense item(s), and "
        f"{evidence_level.minimum_verified_variants} verified variants across at least "
        f"{evidence_level.minimum_variation_axes} material axes per required lab family. "
        f"Required cognitive tasks: {' -> '.join(evidence_level.cognitive_tasks)}.",
        "- **Language coverage profile:** 1",
        "- **Language foundation contract:** 2",
        "- **Skeleton integrity contract:** 3",
        f"- **Mastery target:** {mastery_target}",
        "- **Entry/exit separation:** Starting level controls the opening explanation and "
        "practice; mastery controls what the learner can do in the language after that support "
        "fades. A low "
        "start never lowers the required finish.",
        f"- **Mastery depth floor:** Finish {mastery}/5 requires effective lesson depth of at "
        f"least {MASTERY_DEPTH_FLOORS[mastery]}/10. A lower depth preference cannot narrow, "
        "skip, or compress required language coverage.",
        "- **Mastery proof boundary:** A sophisticated finished project artifact, hidden reference "
        "solution, or green replay proves course solvability—not learner independence. The "
        "selected language finish must be demonstrated in learner-visible, graded language work.",
        *learner_construction_contract(),
        "- **Language-through-project rule:** Every section Working must deliberately practice "
        "declared language capabilities while advancing the project. Teach mechanisms through "
        "disposable examples, then make the project use them; do not teach disconnected snippets "
        "or treat framework behavior as language mastery.",
        f"- **Language-foundation rule:** {foundation_rule}",
        "- **Language-coverage rule:** Language Mastery—not Project Scope—selects the generic "
        "minimum capability count and every cumulative area in the matching versioned language "
        "profile. Phase 1 must read global-configs/language-mastery.toml and name stable "
        "language capability ids satisfying every required token group; it may add useful areas "
        "but cannot omit or substitute required ones.",
        "- **Transfer distribution rule:** Map each graded language performance only to the "
        "capabilities its stated task materially exercises. When the selected Finish requires "
        "multiple performances, make them genuinely different and complementary; their combined "
        "coverage must satisfy the required language spine. Never attach the whole spine to every "
        "performance or invent unrelated subrequirements to make a checklist look complete. The "
        "final Working may require the complete spine as a cumulative graduation boundary while "
        "its performance rubric maps only the capabilities exercised by its novel task.",
        "- **Artifact-ownership rule:** Declare one exhaustive, language-neutral Artifact "
        "ownership line. Every learner-owned path or stable artifact identifier names the "
        "Working that first owns it and either `ships` or `retires@sNN`; the sealed map must "
        "match that inventory and retain shipped artifacts through the final Working. In the "
        "Artifact lifecycle field, wrap every inventory artifact—and no other token—in backticks "
        "so the harness can prove the prose and inventory are identical.",
        "- **Delivery-lock rule:** Phase 1 must choose exactly one language-neutral Delivery "
        "contract line: `mode = runtime|package; artifact = path; requirements = path|none`. "
        "Every path is a normalized project-relative POSIX identifier with no leading, trailing, "
        "or doubled slash and no `.` or `..` segment. "
        "Runtime is source-workspace delivery: its artifact is the source entrypoint and its "
        "requirements value is always `none`. The requirements slot is never a generic source "
        "inventory or build entrypoint; put other shipped source, configuration, build, test, and "
        "documentation paths in Artifact ownership/lifecycle and prove their clean-start use in "
        "Acceptance proof. "
        "A packaged, standalone, installable, or distributable promise requires package mode. "
        "The harness seals this choice and its exact paths; Phase 2 cannot downgrade package "
        "acceptance to source execution or substitute a different output.",
        "- **Scaffold-fading rule:** Fade explanation, hint detail, task size, and practice support—"
        "never learner ownership of the canonical artifact. Early Workings may use smaller work "
        "orders and more observable checks; later Workings use broader specifications. At every "
        "stage the learner writes the real project implementation.",
        f"- **Mastery evidence {mastery}/5:** {MASTERY_EVIDENCE[mastery]}",
    )


def gate_errors(answers):
    values = {label: str(value or "").strip() for label, value in answers}
    errors = []
    for label, maximum in (("Starting level (1-10)", 10), ("Project scope (1-5)", 5),
                           ("Lesson depth (1-10)", 10), ("Mastery (1-5)", 5)):
        raw = values.get(label, "")
        try:
            number = int(raw)
        except ValueError:
            number = 0
        if str(number) != raw or not 1 <= number <= maximum:
            errors.append(f"{label} must be a whole number from 1 to {maximum}")
    if values.get("Tooling", "").lower() not in TOOLING_POLICY:
        errors.append("Tooling must be exactly internal, external, or both")
    try:
        depth = int(values.get("Lesson depth (1-10)", "0"))
        mastery = int(values.get("Mastery (1-5)", "0"))
    except ValueError:
        depth = mastery = 0
    if mastery in MASTERY_DEPTH_FLOORS and depth < MASTERY_DEPTH_FLOORS[mastery]:
        errors.append(
            f"Lesson depth must be at least {MASTERY_DEPTH_FLOORS[mastery]} for Mastery {mastery}; "
            "language mastery owns the minimum depth floor")
    return errors


def read_tooling(plan_path):
    try:
        text = open(plan_path, encoding="utf-8").read()
    except OSError:
        return None
    match = re.search(r"(?im)^- \*\*Tooling:\*\*\s*(\w+)", text)
    value = match.group(1).lower() if match else None
    return value if value in TOOLING_POLICY else None


def calibration_contract(answers):
    """Render machine-owned calibration so Phase-1 resets can refresh stale snapshots."""
    values = {key: str(value).strip() for key, value in answers}
    start = int(values["Starting level (1-10)"])
    mastery = int(values["Mastery (1-5)"])
    project_scope = int(values["Project scope (1-5)"])
    tooling = values["Tooling"].lower()
    scope_title, scope_summary = PROJECT_SCOPE_LEVELS[project_scope]
    lines = [
        f"- **Start {start}/10 — {PRIOR_LEVELS[start][0]}:** {PRIOR_LEVELS[start][1]}",
        "- **Assumption boundary:** Starting level is the complete entry baseline. Prior "
        "knowledge is optional; when supplied, treat it as an exhaustive list of additional "
        "concrete skills, not evidence that nearby skills are safe to assume. When omitted, "
        "make no specific experience assumptions beyond the selected Start definition.",
        "- **Prerequisite topology rule:** Before sealing the Arc or course map, perform a "
        "cold-start dependency walk from the entry baseline through every Working and "
        "the final acceptance journey. Inventory every unavoidable language mechanism, library or "
        "runtime API, tool action, configuration or data-format rule, and technical term demanded "
        "by the milestone, learner-owned artifacts, rubric, proof, validation, or hidden replay. "
        "Give each demand a teaching owner before first required use, with foundational language "
        "mechanisms before work that depends on them. Operational setup may come first only when "
        "it is behavior-free, mechanically followable, and requires no learner-authored source, "
        "configuration, entrypoint, or integration that uses untaught mechanisms.",
        "- **Transitive prerequisite closure rule:** Teaching a dependent mechanism never "
        "implicitly teaches the mechanisms that make its smallest meaningful example possible. "
        "For every planned owner, expand each mechanism through that transitive prerequisite "
        "closure. Every prerequisite outside the entry baseline needs a teaching owner. At Start "
        "1–3, a prerequisite may share its dependent's lesson only when both serve that lesson's "
        "one coherent pedagogical family and the prerequisite comes first in the Phase-2 ordered "
        "introduction list; a cross-family prerequisite requires an earlier lesson. "
        "If the smallest example contains an unlisted syntax form, API, tool action, data-format "
        "rule, or term, that item is a prerequisite even when the learner could copy it blindly. "
        "For an API, trace how its inputs and resources are created, obtained, and released. For "
        "a tool or data/configuration file, "
        "trace the create, edit, save, and invocation actions. "
        "Never invent a library- or project-specific alias for a general language prerequisite "
        "and then introduce the real mechanism later.",
        "- **Mechanism identity rule:** A mechanism owns one transferable semantic "
        "responsibility, not one spelling. Platform commands, executable aliases, flags, paths, "
        "activation forms, UI routes, configuration syntaxes, and language/runtime/tool variants "
        "share an owner when learner intent, preconditions, state transition or resource-lifecycle "
        "duty, observable result, and failure interpretation are the same. Split only when a "
        "demand adds a genuinely different state transition, lifecycle duty, observable contract, "
        "or reusable reasoning responsibility. This decides mechanism identity, not lesson-family "
        "count: distinct mechanisms may share one pedagogical family when they form one coherent "
        "teach-practice-observe loop. Apply this without assuming any particular "
        "language, runtime, tool, operating system, or project.",
        "- **Observable-interaction closure rule:** Apply closure to every promise, Working, "
        "acceptance path, and control. Decompose obtaining input, producing output, advancing "
        "time, choosing nondeterministically, persisting state, releasing resources, and responding "
        "to observations into the concrete operations that make the behavior real. Acquiring a "
        "stream, event, handle, or resource does not by itself own the operations that inspect, "
        "interpret, select, transform, or act on its contents.",
        "- **Capability honesty rule:** A capability owner is the cumulative boundary after all "
        "semantic component families claimed by its id have explicit mechanism owners. Components "
        "may be taught in earlier prerequisite lessons, but none may be postponed until after the "
        "capability owner. Coverage-profile token groups are satisfied across the complete spine, "
        "so split independent families when their prerequisite chains, milestone needs, or first-"
        "use points differ materially. Never place an umbrella owner early merely to contain "
        "profile keywords or claim material taught only later.",
        "- **Milestone coherence rule:** Every capability or mechanism first taught in a section "
        "must materially enable that section's Working or be an unavoidable immediate prerequisite "
        "for it. Never introduce material merely because it is next in a language catalog, assign "
        "a later owner to a demand already present, or invent a near-duplicate mechanism to disguise "
        "use before teaching.",
    ]
    if tooling in ("external", "both"):
        lines.append(
            "- **External clean-start rule:** The first Section-list milestone must own the "
            "real toolchain's installation or setup and an observable version, check, or "
            "diagnostic verification before it demands project source. Repeat that clean-start "
            "setup and verification in Acceptance proof; a machine where the tools happen to "
            "already exist is not the declared zero-entry journey.")
    lines.extend((
        "- **Failure-path prerequisite rule:** Own the mapped control-flow and decomposition "
        "foundations before the mapped failure-handling foundation, including literal lesson "
        "order when they share a section. A library cleanup branch cannot be the learner's "
        "first unexplained comparison, jump, call, or return path.",
        "- **Bounded-modification consistency rule:** When a graded guided modification names "
        "an exact numeric bound, repeat that same exact invariant in its Section-list promise "
        "and Mastery proof. Do not let a vague range change replace the graded contract.",
        "- **Reproducible-delivery proof rule:** If Finished tool or the final milestone promises "
        "a reproducible, deterministic, or byte-identical package/archive, Acceptance proof "
        "must create it at least twice from clean input, normalize ordering and volatile archive "
        "metadata, and compare hashes, checksums, digests, or bytes.",
    ))
    if mastery >= 3:
        lines.append(
            "- **Foundation cadence rule:** At Mastery 3–5, place every mapped language "
            "foundation role at an explicit Section-list owner boundary by the Arc midpoint and "
            "before dependent framework, runtime, or integration work. Mention every declared "
            "language capability in a Section-list promise so Phase 1's ownership order is "
            "auditable before Phase 2.")
        lines.append(
            "- **Verification cadence rule:** At Mastery 3–5, establish the language's "
            "learner-authored, idiomatic verification loop no later than the first nontrivial "
            "decomposed behavior that later integrations depend on, then retrieve it across "
            "representative later Workings. Hidden harness replay and end-loaded release checks "
            "do not substitute for learner-owned verification. If basic checking/testing and "
            "tool-driven diagnosis mature at materially different points, declare separate "
            "capability ids rather than back-loading both under one umbrella.")
    if mastery == 1:
        section_cap = mastery_section_cap(mastery, project_scope)
        lines.append(
            f"- **Mastery-1 minimum-path budget:** Use the fewest honest project milestones and "
            f"no more than {section_cap} sections for Project Scope {project_scope}/5. Teach only "
            "language, API, tooling, diagnosis, and delivery mechanisms that the requested "
            "artifact or its acceptance proof actually requires. Combine adjacent prerequisites "
            "as ordered lessons inside the first project milestone that uses them; do not create "
            "standalone language-survey sections. Starting Level may increase explanation, "
            "practice, and lesson count, but never increases this section budget."
        )
    if start <= 3:
        pacing_title, pacing_summary = START_PACING[start]
        lines.append(
            f"- **Lesson pacing {start}/3 — {pacing_title}:** {pacing_summary}")
        lines.append(
            "- **Pacing/depth separation:** Starting level controls cognitive-load packaging, "
            "step size, repetition, and pace. Lesson Depth controls explanatory thoroughness, "
            "debugging, and edge cases; it does not authorize denser concept packaging.")
        lines.append(
            "- **First-use rule for Start 1–3:** Before required use, every unlisted keyword, "
            "syntax form, operator, API, tool action, or term needs a plain-language purpose, "
            "stepwise anatomy, a minimal worked example with observable output, one likely "
            "failure, and guided practice.")
        lines.append(
            "- **Enforcement:** Phase 2 seals a language-neutral mechanism owner ledger; Phase 3 "
            "declares mechanisms on every learner demand. Deterministic ordering checks run "
            "before one compact, content-digest-cached teaching-quality, learner-independence, "
            "and prerequisite-completeness audit. PASS requires line-bounded evidence for every "
            "lesson and Working; typed defects return only the cited repairs to the same section.")
        lines.append(
            "- **Curriculum capacity rule:** Derive lesson and section counts from the dependency "
            "walk and calibrated concept-family load. Three lessons is a schema minimum, not a "
            "planning default. Use the available lesson capacity, and at Start 1–2 split material "
            "into honest ordered lessons when independent foundations would otherwise be compressed. "
            "Starting Level alone never creates another project section. If one section would need "
            "more than eight lessons, split it only within the selected Mastery section budget; at "
            "Mastery 1, first remove nonessential language breadth and consolidate lessons around "
            "the project milestone they immediately enable. Never hide overflow inside broad labels "
            "or lower the promised project contract.")
    lines.extend([
        f"- **Project scope {project_scope}/5 — {scope_title}:** {scope_summary}",
        "- **Scope/mastery separation:** Project scope controls the size, content, systems, and "
        "delivery ambition of the finished artifact. It never reduces the language topics, "
        "transfer evidence, or lesson-depth floor required by the selected Mastery.",
        f"- **Depth {values['Lesson depth (1-10)']}/10:** controls how far each mechanism is "
        "explained, debugged, and qualified.",
        "- **Section-bound rule:** Derive the section count backward from the graduate contract, "
        "capability graph, project milestones, and acceptance proof. It must be from 2 through "
        "40 inclusive. Every section owns a necessary capability or integration milestone; "
        "removing any section must break a stated graduate or acceptance requirement. If honest "
        "coverage cannot fit, fail Phase 1 instead of exceeding the bound or lowering the contract.",
        *mastery_contract(mastery),
        f"- **Tooling — {TOOLING_POLICY[tooling][0]}:** {TOOLING_POLICY[tooling][1]}",
        "- These answers override casual scope adjectives. Phase 1 converts them into the "
        "language capability spine, language graduate boundary, language mastery proof, project "
        "lifecycle, acceptance proof, and section arc.",
    ])
    return "\n".join(lines) + "\n"


def write_plan(plan_path, tid, answers, concept=None):
    answers = [
        (key, PRIOR_KNOWLEDGE_UNSPECIFIED if key == "Prior knowledge" and not str(value or "").strip()
         else str(value or "").strip())
        for key, value in answers
    ]
    with open(plan_path, "w", encoding="utf-8") as handle:
        handle.write(f"# BUILD PLAN — {tid}\n\n")
        if concept:
            handle.write("## Concept\n" + concept.strip() + "\n\n")
        handle.write("## Build contract\n- **Proof contract:** 1\n\n## Gate answers (Phase 0)\n")
        for key, value in answers:
            handle.write(f"- **{key}:** {value}\n")
        handle.write("\n## Calibration contract\n")
        handle.write(calibration_contract(answers))
        handle.write("\n" + ARC_HEADING + ARC_CONTRACT)


def do_gate(plan_path, tid, concept=None):
    while True:
        answers = [(label, input(f"{question}\n> ").strip()) for label, question in GATE_QS]
        errors = gate_errors(answers)
        if not errors:
            break
        print("\n".join(f"- {error}" for error in errors))
    write_plan(plan_path, tid, answers, concept)


def do_gate_json(plan_path, tid, gate_json, concept=None):
    try:
        values = json.loads(gate_json)
    except json.JSONDecodeError as exc:
        sys.exit(f"--gate-json is not valid JSON: {exc}")
    if not isinstance(values, dict):
        sys.exit("--gate-json must be an object")
    if not values.get("project_scope") and values.get("breadth"):
        try:
            # Read old launch payloads without preserving the ambiguous axis: 1–2=>1, ... 9–10=>5.
            values["project_scope"] = str(max(1, min(5, (int(values["breadth"]) + 1) // 2)))
        except (TypeError, ValueError):
            pass
    keys = ("prior_knowledge", "prior_level", "project_scope", "depth", "mastery", "tooling")
    answers = [(label, str(values.get(key, "")).strip())
               for (label, _), key in zip(GATE_QS, keys)]
    errors = gate_errors(answers)
    if errors:
        sys.exit("--gate-json is invalid:\n- " + "\n- ".join(errors))
    write_plan(plan_path, tid, answers, concept)
    print(f"Phase 0 setup recorded in {plan_path}")
