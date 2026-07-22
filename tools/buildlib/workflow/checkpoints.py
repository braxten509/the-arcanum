"""Between-phase checks on the plan and tome folder: Arc gate and deterministic rename."""
import os
import re
import tomllib

from .. import REPO
from ..course.limits import mastery_section_count_error
from ..language_mastery.foundations import (block_field as arc_block_field,
                                            contract_version as foundation_contract_version,
                                            coverage as foundation_coverage,
                                            required_by_plan as foundations_required)
from ..language_mastery import (performance_specs, phase1_contract_problems, required_by_plan,
                                seed_contract as seed_language_mastery)
from ..mastery_evidence import (required_by_plan as mastery_evidence_required,
                                seed_contract as seed_mastery_evidence)
from ..skeleton.integrity import phase1_problems as skeleton_integrity_problems
from ..skeleton.integrity import contract_version as skeleton_integrity_version
from ..skeleton.integrity import required_by_plan as skeleton_integrity_required
from ..skeleton import parse_section_list
from ..course_map.plan import lesson_counts
from .arc_contract import (ARC_CONTRACT, ARC_HEADING, ARC_MIN_CHARS, ARC_PARTS,  # re-exported
                           DAILY_DRIVERS)


ACCEPTANCE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def acceptance_scenarios(plan_path):
    """Parse the Phase-1 machine-owned acceptance journey, or return ``[]``."""
    try:
        text = open(plan_path, encoding="utf-8").read()
    except OSError:
        return []
    match = re.search(r"(?im)^\*\*Acceptance scenarios:\*\*\s*(\S.*)$", text)
    if not match:
        return []
    items = [item.strip() for item in match.group(1).split(" -> ")]
    if (len(items) < 2 or len(set(items)) != len(items)
            or any(not ACCEPTANCE_ID.fullmatch(item) for item in items)):
        return []
    return items


def preflight_arc_transition(plan_path, build_id=None):
    """Run every plan-derived Phase-1 transition invariant without writing files."""
    try:
        with open(plan_path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise ValueError(f"could not read plan {plan_path}: {exc}") from exc
    # The real transition removes this authoring schema before seeding the map.
    # Preview the identical logical plan so instructions cannot classify as promises
    # and the preview hash/schema exactly match the eventual transition input.
    finalized = text.replace(ARC_CONTRACT, "", 1)
    from ..course_map import build_id_from_plan, preview_course_map
    resolved = build_id or build_id_from_plan(plan_path) or "phase-1-preflight"
    return preview_course_map(resolved, finalized)


_TOOL_SETUP = re.compile(
    r"\b(?:install(?:ation|ed|ing)?|set\s*up|setup|provision(?:ed|ing)?|"
    r"configure(?:d|s|ing)?|acquire(?:d|s|ing)?|bootstrap(?:ped|s|ping)?)\b", re.I)
_TOOL_VERIFICATION = re.compile(
    r"\b(?:verif(?:y|ies|ied|ication)|version(?:s|ed|ing)?|check(?:s|ed|ing)?|"
    r"diagnos(?:e|es|ed|is|tic|tics)|probe(?:d|s|ing)?)\b|--version\b", re.I)
_REPRODUCIBLE_DELIVERY = re.compile(
    r"\b(?:reproducible|byte[- ]identical)\b[^\n.;]{0,80}"
    r"\b(?:archive|package|bundle|artifact)\b|"
    r"\b(?:archive|package|bundle|artifact)\b[^\n.;]{0,80}"
    r"\b(?:reproducible|byte[- ]identical)\b|"
    r"\bdeterministic(?:ally)?\s+(?:source\s+)?"
    r"(?:archive|package|bundle|artifact)\b|"
    r"\b(?:archive|package|bundle|artifact)\b\s+(?:is\s+)?deterministic\b", re.I)
_REPEAT_PROOF = re.compile(
    r"\b(?:twice|repeat(?:ed|s|ing)?|two\s+(?:clean\s+)?"
    r"(?:builds?|packages?|archives?|bundles?|artifacts?))\b", re.I)
_DIGEST_PROOF = re.compile(
    r"\b(?:sha(?:-?\d+)?|hash(?:es|ed|ing)?|checksum(?:s)?|digest(?:s)?|"
    r"byte[- ]identical|identical\s+bytes?)\b", re.I)
_NORMALIZATION_PROOF = re.compile(
    r"\b(?:normaliz(?:e|es|ed|ing|ation)|sorted\s+(?:file|path)|fixed\s+timestamp|"
    r"source[_-]date[_-]epoch|deterministic\s+metadata)\b", re.I)
_EXACT_BOUND = re.compile(
    r"\b(?:exactly|only)\s+(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b",
    re.I)
_BOUND_CONTEXT = re.compile(
    r"\b(?:accept(?:s|ed|ing)?|reject(?:s|ed|ing)?|valid(?:ate|ates|ated|ation)?|"
    r"target|limit|range|threshold|count|score|rule|bound|maximum|minimum)\b", re.I)


def _first_promise_position(capability, specs):
    pattern = re.compile(
        rf"(?<![a-z0-9-]){re.escape(str(capability or '').casefold())}(?![a-z0-9-])")
    for ordinal, spec in enumerate(specs, 1):
        match = pattern.search(spec.promise.casefold())
        if match:
            return ordinal, match.start()
    return None


def _repeats_exact_bound(text, value):
    return bool(re.search(
        rf"\b(?:exactly|only)\s+{re.escape(value)}\b", str(text or ""), re.I))


def phase1_operational_problems(text, body, specs):
    """Mechanically reject recurring Arc defects that do not need an AI judgment."""
    problems = []
    tooling_match = re.search(
        r"(?im)^- \*\*Tooling:\*\*\s*(internal|external|both)\s*$", text)
    tooling = tooling_match.group(1).casefold() if tooling_match else ""
    acceptance = arc_block_field(body, "Acceptance proof")
    finished = arc_block_field(body, "Finished tool")
    mastery_proof = arc_block_field(body, "Mastery proof")

    if tooling in ("external", "both") and specs:
        first = specs[0].promise
        if not (_TOOL_SETUP.search(first) and _TOOL_VERIFICATION.search(first)):
            problems.append(
                f"external tooling requires {specs[0].sid}'s Section-list promise to own "
                "both real-tool installation/setup and an observable version, check, or "
                "diagnostic verification before project source is demanded")
        if not (_TOOL_SETUP.search(acceptance) and _TOOL_VERIFICATION.search(acceptance)):
            problems.append(
                "external tooling requires **Acceptance proof:** to start from real-tool "
                "installation/setup and verify the resulting environment before the build")

    # A declared failure path depends on control flow and decomposition. When their first
    # owner is the same section, the Section-list promise is itself an ordered contract.
    if foundations_required(text) and specs:
        mastery = re.search(r"(?im)^- \*\*Mastery \(1-5\):\*\*\s*([1-5])\s*$", text)
        mapped, mapping_problems = foundation_coverage(
            body, version=foundation_contract_version(text),
            level=int(mastery.group(1)) if mastery else 0)
        if not mapping_problems:
            failure = _first_promise_position(mapped.get("failure"), specs)
            for role in ("control", "decomposition"):
                prerequisite = _first_promise_position(mapped.get(role), specs)
                if failure and prerequisite and prerequisite > failure:
                    problems.append(
                        f"the mapped {role} foundation {mapped[role]} must be owned before "
                        f"the mapped failure foundation {mapped['failure']} in the ordered "
                        "Section list")

    # If the Arc promises byte reproducibility, the clean-start proof must actually vary
    # the build invocation and compare normalized output bytes. A single green package is
    # delivery proof, not reproducibility proof.
    final_promise = specs[-1].promise if specs else ""
    if _REPRODUCIBLE_DELIVERY.search(finished + "\n" + final_promise):
        missing = []
        if not _REPEAT_PROOF.search(acceptance):
            missing.append("produce the clean package/archive at least twice")
        if not _NORMALIZATION_PROOF.search(acceptance):
            missing.append("normalize ordering and volatile archive metadata")
        if not _DIGEST_PROOF.search(acceptance):
            missing.append("compare hashes, checksums, digests, or identical bytes")
        if missing:
            problems.append(
                "the promised reproducible delivery needs **Acceptance proof:** to "
                + ", ".join(missing))

    # A guided bounded modification is safer when its exact invariant is repeated at the
    # three authority boundaries that later phases consume. This prevents a vague range
    # change in the Section list from silently replacing an exact graded requirement.
    performances, performance_problems = performance_specs(body)
    if not performance_problems:
        by_sid = {spec.sid: spec.promise for spec in specs}
        for performance in performances:
            if performance.get("kind") != "guided-modification":
                continue
            description = performance["description"]
            bounds = {
                match.group(1).casefold()
                for match in _EXACT_BOUND.finditer(description)
                if _BOUND_CONTEXT.search(
                    description[max(0, match.start() - 80):match.end() + 80])
            }
            sid = performance["workingId"].split(".", 1)[0]
            for bound in sorted(bounds):
                if not _repeats_exact_bound(by_sid.get(sid, ""), bound):
                    problems.append(
                        f"{performance['workingId']} grades the exact bound {bound!r}; "
                        f"the {sid} Section-list promise must repeat it as `exactly {bound}` "
                        f"or `only {bound}`")
                if not _repeats_exact_bound(mastery_proof, bound):
                    problems.append(
                        f"{performance['workingId']} grades the exact bound {bound!r}; "
                        "**Mastery proof:** must repeat the same invariant")

    start_match = re.search(
        r"(?im)^- \*\*Starting level \(1-10\):\*\*\s*(10|[1-9])\s*$", text)
    if specs and start_match and int(start_match.group(1)) <= 2:
        for spec in specs:
            steps = spec.promise.count("->") + 1
            if "lesson" not in spec.promise.casefold() or steps < 4:
                continue
            if steps > 8:
                problems.append(
                    f"{spec.sid}'s explicit lesson route has {steps} steps; Start 1-2 "
                    "Section-list routes may name at most eight before the milestone must be "
                    "narrowed or honestly split within the section budget")
            if ("practice" not in spec.promise.casefold()
                    or "working" not in spec.promise.casefold()):
                problems.append(
                    f"{spec.sid}'s explicit Start 1-2 lesson route must promise guided "
                    "practice before the mechanisms are combined in its Working")
    return problems


def arc_written(plan_path, plan_rel):
    """Phase 1's whole deliverable is the plan's '## Arc' section — gate on that artifact,
    not the runner's exit code. A runner that answers conversationally (agy has repeatedly
    greeted a CLI flag instead of reading the prompt) exits 0 having written nothing, which
    used to send an arc-less build into ~30k tokens of authoring. Checks every ARC_PARTS
    label is present and the content clears ARC_MIN_CHARS."""
    try:
        text = open(plan_path, encoding="utf-8").read()
    except OSError:
        text = ""
    _, sep, arc = text.partition("## Arc")
    contract = set(ARC_CONTRACT.splitlines())
    body = "\n".join(l for l in arc.splitlines()[1:]
                     if l.strip() and l not in contract) if sep else ""
    if not body:
        return False, (f"The '## Arc' section of {plan_rel} is still EMPTY — the previous run "
                       f"did no work (it likely answered conversationally instead of executing "
                       f"the phase). Do the phase now: EDIT {plan_rel} and write the full arc "
                       f"under '## Arc'. Printing it to the terminal does not count; later "
                       f"phases read only the file on disk.")
    low = body.lower()
    # Plans created before the mastery-evidence contract remain readable. New plans carry
    # its numbered marker and must provide the corresponding Phase-1 proof explicitly.
    required_parts = list(ARC_PARTS if re.search(
        r"(?im)^- \*\*Mastery evidence [1-5]/5:\*\*", text)
        else tuple(part for part in ARC_PARTS if part != "Mastery proof"))
    if required_by_plan(text):
        required_parts += ["Language mastery", "Language capability spine", "Language performances"]
    if foundations_required(text):
        required_parts += ["Language foundation coverage"]
    if mastery_evidence_required(text):
        required_parts += ["Mastery cognitive tasks", "Mastery evidence performances",
                           "Mastery retention"]
    if skeleton_integrity_required(text):
        required_parts += ["Artifact ownership"]
    if skeleton_integrity_version(text) >= 3:
        required_parts += ["Delivery contract"]
    missing = [p for p in required_parts if f"**{p.lower()}:**" not in low]
    probs = []
    gate_tooling = re.search(r"(?im)^- \*\*Tooling:\*\*\s*(internal|external|both)\s*$", text)
    fit = re.search(
        r"(?im)^\*\*Tooling fit:\*\*\s*(internal|external|both)\s*[—-]\s*"
        r"COMPATIBLE\s*:\s*(\S.+)$", body)
    if not gate_tooling:
        probs.append("the immutable Phase-0 **Tooling:** answer is missing or invalid")
    elif not fit:
        probs.append("**Tooling fit:** must prove the immutable Phase-0 choice with exactly "
                     "`<mode> — COMPATIBLE: evidence`; construction cannot request a human change")
    elif fit.group(1).lower() != gate_tooling.group(1).lower():
        probs.append("**Tooling fit:** must repeat the Phase-0 Tooling answer exactly; "
                     f"gate={gate_tooling.group(1).lower()}, fit={fit.group(1).lower()}")
    if (os.environ.get("ARCANUM_REQUIRE_PROOF_V1") == "1"
            and not re.search(r"(?im)^- \*\*Proof contract:\*\*\s*1\s*$", text)):
        probs.append("the harness-owned **Proof contract:** 1 marker was removed from the plan")
    if missing:
        probs.append("these parts are missing and must be written EXACTLY as their own "
                     "`**Label:** value` line: " + "; ".join(f"**{p}:**" for p in missing))
    unassigned = [d for d in DAILY_DRIVERS
                  if not re.search(rf"{re.escape(d)}\s*=\s*CAN(NOT)?\b", body, re.I)]
    if unassigned:
        probs.append("the **Daily drivers:** line must assign every item EXACTLY as "
                     "`item = CAN` or `item = CANNOT`; unassigned: " + "; ".join(unassigned))
    if not acceptance_scenarios(plan_path):
        probs.append("**Acceptance scenarios:** must be one physical line with at least two "
                     "unique kebab-case ids separated exactly by ` -> `")
    specs = []
    try:
        specs = parse_section_list(body)
    except ValueError as exc:
        probs.append(f"the **Section list:** is not machine-scaffoldable: {exc}")
    if specs:
        probs.extend(phase1_operational_problems(text, body, specs))
        try:
            lesson_counts(body, [spec.sid for spec in specs])
        except ValueError as exc:
            probs.append(str(exc))
    mastery_match = re.search(
        r"(?im)^- \*\*Mastery \(1-5\):\*\*\s*([1-5])\s*$", text)
    scope_match = re.search(
        r"(?im)^- \*\*Project scope \(1-5\):\*\*\s*([1-5])\s*$", text)
    if specs and mastery_match and scope_match:
        budget_error = mastery_section_count_error(
            len(specs), int(mastery_match.group(1)), int(scope_match.group(1)))
        if budget_error:
            probs.append(budget_error)
    if skeleton_integrity_required(text):
        probs.extend(skeleton_integrity_problems(text, body, [spec.sid for spec in specs]))
    promises = [spec.promise for spec in specs]
    if specs and (any(len(promise) < 20 for promise in promises)
                  or len(set(promise.casefold() for promise in promises)) != len(promises)):
        probs.append("every Section-list entry needs a distinct necessary capability or "
                     "integration-milestone promise of at least 20 characters")
    probs += phase1_contract_problems(
        text, body, [spec.sid for spec in specs], [spec.promise for spec in specs])
    if mastery_evidence_required(text) and specs:
        try:
            language_contract = seed_language_mastery(text, [spec.sid for spec in specs])
            seed_sections = [
                {"id": spec.sid, "ordinal": ordinal, "nodes": []}
                for ordinal, spec in enumerate(specs, 1)
            ]
            seed_mastery_evidence(text, seed_sections, language_contract)
        except ValueError as exc:
            probs.append(str(exc))
    continuity_match = re.search(r"(?i)\*\*Continuity map:\*\*", body)
    continuity_tail = body[continuity_match.end():] if continuity_match else ""
    continuity = re.split(r"(?m)^\*\*[^\n]+:\*\*", continuity_tail, maxsplit=1)[0]
    # Accept the current physical-line contract and legacy semicolon-separated arcs,
    # but validate every clause independently so one greedy match cannot hide a
    # malformed, backward, or nonexistent later edge.
    edge_lines = [line.strip() for line in re.split(r"\s*(?:;|\n)\s*", continuity)
                  if line.strip()]
    edge_pattern = re.compile(r"(?:[-*]\s*)?s(\d{2})\s*->\s*s(\d{2})\s*:\s*\S.+", re.I)
    if not edge_lines or not any(edge_pattern.fullmatch(line) for line in edge_lines):
        probs.append("the **Continuity map:** needs at least one explicit `sNN -> sMM:` "
                     "dependency edge")
    else:
        malformed = [line for line in edge_lines if not edge_pattern.fullmatch(line)]
        ids = {spec.sid for spec in specs}
        nonexistent = [line for line in edge_lines
                       if edge_pattern.fullmatch(line)
                       and ({"s" + edge_pattern.fullmatch(line).group(1),
                             "s" + edge_pattern.fullmatch(line).group(2)} - ids)]
        backwards = [line for line in edge_lines
                     if edge_pattern.fullmatch(line)
                     and int(edge_pattern.fullmatch(line).group(1))
                     >= int(edge_pattern.fullmatch(line).group(2))]
        if malformed:
            probs.append("every **Continuity map:** entry must be one complete physical "
                         "`sNN -> sMM: promise` line; malformed: " + "; ".join(malformed))
        if backwards:
            probs.append("Continuity-map edges must point forward to a later section: "
                         + "; ".join(backwards))
        if nonexistent:
            probs.append("Continuity-map edges must name real Section-list ids: "
                         + "; ".join(nonexistent))
    if len(body) < ARC_MIN_CHARS:
        probs.append(f"the arc is only {len(body)} chars — a real arc is far longer "
                     f"(minimum {ARC_MIN_CHARS})")
    if not probs:
        try:
            preflight_arc_transition(plan_path)
        except ValueError as exc:
            probs.append(f"Phase-1 transition preflight failed: {exc}")
    if not probs:
        return True, ""
    return False, (f"The '## Arc' section of {plan_rel} is incomplete — "
                   + "; and ".join(probs) + f". EDIT {plan_rel} and complete it.")


def reset_arc(plan_path):
    """Re-running Phase 1 must be judged on THIS run's output: blank the plan's Arc section
    so arc_written can't pass on a previous run's arc. Anything after the Arc (rename notes,
    ground-truth appendix) is the old run's too and goes with it."""
    try:
        text = open(plan_path, encoding="utf-8").read()
    except OSError:
        return
    head, sep, _ = text.partition("## Arc")
    if sep:
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write(head + ARC_HEADING + ARC_CONTRACT)


def finalize_arc(plan_path):
    """Drop the Phase-1-only schema once the arc passes, so every later worker reads
    decisions rather than the instructions that produced them."""
    try:
        text = open(plan_path, encoding="utf-8").read()
    except OSError:
        return False
    if ARC_CONTRACT not in text:
        return False
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write(text.replace(ARC_CONTRACT, "", 1))
    return True


KEBAB_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")  # camel boundary -> hyphen (§6 one-name rule)


def maybe_rename(tid, plan_path):
    """Filesystem surgery is the harness's job, not an agent's: when [runtime] project
    implies a different kebab-case id (§6: ManaWeaver -> mana-weaver, never the
    requester's phrasing), rename the folder and patch meta.id deterministically. The
    agent-driven version of this move nested an entire tome inside itself once; never again.
    Returns the (possibly new) tome id."""
    manifest = os.path.join(REPO, "tomes", tid, "tome.toml")
    if not os.path.isfile(manifest):
        return tid
    try:
        with open(manifest, "rb") as f:
            m = tomllib.load(f)
    except Exception:
        return tid  # unparseable manifest — the validator will say so
    project = str((m.get("runtime") or {}).get("project") or "").strip()
    new = re.sub(r"[^a-z0-9]+", "-", KEBAB_SPLIT.sub("-", project).lower()).strip("-")
    if not new or new == tid:
        return tid
    target = os.path.join(REPO, "tomes", new)
    if os.path.exists(target):
        print(f"  ! naming: id should be {new!r} but tomes/{new} already exists — keeping {tid!r}")
        return tid
    os.rename(os.path.join(REPO, "tomes", tid), target)
    tpath = os.path.join(target, "tome.toml")
    txt = open(tpath, encoding="utf-8").read()
    with open(tpath, "w", encoding="utf-8") as f:  # [meta] id is the first id = "…" line
        f.write(re.sub(r'(?m)^(id\s*=\s*)"[^"]*"', rf'\g<1>"{new}"', txt, count=1))
    with open(plan_path, "a", encoding="utf-8") as f:
        f.write(f"\n- **Tome id renamed by the harness:** `{tid}` → `{new}` "
                f"(kebab-case of project {project!r}); all later phases use tomes/{new}/\n")
    print(f"  · renamed tomes/{tid} -> tomes/{new} (kebab-case of project {project!r}); meta.id patched")
    return new
