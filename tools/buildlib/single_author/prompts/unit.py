"""Render the complete prompt for one authoring unit."""
import os


def render_unit_prompt(build_id, unit, dependencies):
    REPO = dependencies["REPO"]
    LEARNER_CONSTRUCTION_INSTRUCTION = dependencies["LEARNER_CONSTRUCTION_INSTRUCTION"]
    LESSON_BATCH_INSTRUCTION = dependencies["LESSON_BATCH_INSTRUCTION"]
    append_course_control = dependencies["append_course_control"]
    context = dependencies["context"]
    continuity_prompt = dependencies["continuity_prompt"]
    label = dependencies["label"]
    load_course_map = dependencies["load_course_map"]
    map_path = dependencies["map_path"]
    mechanical_validation_prompt = dependencies["mechanical_validation_prompt"]
    prepare_handoff = dependencies["prepare_handoff"]
    unit_semantic_authority = dependencies["unit_semantic_authority"]

    marker = ((f"python3 tools/workflow/report_section_progress.py {build_id} {unit['section']} "
               f"{unit['index']} {unit['total']} validating")
              if unit["kind"] == "section" else
              f"python3 tools/workflow/report_tome_progress.py {build_id} {unit['phase']} validating")
    construction = (f" {LEARNER_CONSTRUCTION_INSTRUCTION}" if unit["kind"] == "section" else "")
    rhythm = (f" {LESSON_BATCH_INSTRUCTION}" if unit["kind"] == "section" else "")
    prompt = (f"Continue with {label(unit)}. Read its phase guide, then complete exactly this unit."
              f"{construction}{rhythm} "
              f"{mechanical_validation_prompt(build_id, unit)} Then run exactly `{marker}` and stop so the harness "
              "can validate it.")
    authority = unit_semantic_authority(build_id, unit)
    if authority:
        prompt += "\n\n" + authority
    if unit["kind"] != "section":
        phase = int(unit.get("phase") or 0)
        if phase == 2:
            prompt += (
                f" Begin with exactly `python3 tools/workflow/context/render_phase2_context.py {build_id}`. "
                "That bounded packet replaces broad repository discovery. Edit only the compact "
                "Phase-2 sources and other repairable paths it names. Its authority block controls "
                "family meaning, same-lesson prerequisite order, artifact-production modes, source "
                "budget, and repair ownership. Complete audit.json v2 with one exact family, "
                "teaching-prerequisite list, and production-prerequisite list per mechanism; one "
                "component-mechanism row per taught capability; one preserved-mechanism row per "
                "planned continuity obligation; every failure-path role; and one "
                "production row per sealed artifact. External installation and verification must "
                "precede project source editing. This "
                "is mechanically checked author work, not an optional prose checklist. The harness "
                "deterministically materializes the full "
                "proposal after handoff. Complete every section plan in one coherent batch. If external "
                "tooling is selected, use web search only for facts that affect installation, current "
                "commands, APIs, compatibility, or delivery; cite no more than six official or primary "
                "sources in the research ledger. Later authors reuse that ledger. Target no more than "
                "$2 API-equivalent for initial Phase 2 planning; avoid rereading generated proposal JSON."
            )
        return prompt
    prompt += (
        f" Begin with exactly `python3 tools/workflow/context/render_section_context.py {build_id} "
        f"{unit['section']}`; that bounded packet replaces scattered initial discovery reads. "
        "Its `sectionQualityContract` is the exact binding policy used by the Validator AI; apply "
        "it before drafting lessons or the Working. "
        "After it, batch independent file reads and searches into one tool call and group related "
        "file edits into one coherent edit pass using small valid patch operations. Do not inspect one "
        "known file per tool round trip. The operating target for the Phase 3 author plus its "
        "mandatory Validator AI is $1–2 API-equivalent per section for Codex authors; Claude "
        "authors may use up to $4. Meet the complete quality "
        "contract within that target by using this bounded packet once and avoiding redundant "
        "discovery or speculative rewrites."
    )
    if not os.path.isfile(map_path(build_id)):
        return prompt  # direct legacy/test helper; ensure_unit blocks real Phase 3 entry
    ctx = context(build_id)
    course = load_course_map(build_id)
    ids = [section["id"] for section in course["sections"]]
    prepare_handoff(ctx["tid"], unit["section"], ids=ids,
                    plan_path=os.path.join(REPO, ctx["plan"]))
    prompt += continuity_prompt(ctx["tid"], unit["section"], ids,
                                os.path.join(REPO, ctx["plan"]))
    return append_course_control(prompt, build_id, unit["section"])
