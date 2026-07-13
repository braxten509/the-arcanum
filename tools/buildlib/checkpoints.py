"""Between-phase checkpoints on the plan and the tome folder: the Phase-1 arc gate,
the human arc approval pause, and the deterministic harness-side tome rename."""
import os
import re
import sys
import tomllib

from . import REPO
from .skeleton import parse_section_list


# The arc's REQUIRED parts — the gate checks each appears as a bold `**Label:**` line.
# Difficulty spine + Graduate ledger are plan deliverables Phase 1 has skipped before.
ARC_PARTS = ("Finished tool", "Language", "Project name", "Mentor persona", "Student term",
             "Visual identity", "Difficulty spine", "Graduate ledger", "Daily drivers",
             "Continuity map", "Artifact lifecycle", "Acceptance proof", "Section list")
# The plan's daily-driver kit, machine-checked: each must be assigned CAN or CANNOT in
# the arc (Phase 1 has silently dropped the key-value type twice), and a CANNOT is a
# declared scope cut repeated in the Graduate ledger — never public catalog copy.
DAILY_DRIVERS = ("growable collection", "key-value", "strings", "errors")
ARC_HEADING = "## Arc (Phase 1 fills this in, later phases read it)\n"
# Written into the plan right under the heading, so the contract sits exactly where
# Phase 1 must write. Labels are listed WITHOUT the **…:** shape the gate matches on,
# or the instructions themselves would satisfy the gate.
ARC_CONTRACT = (
    "_Phase 1: write the arc below this line. The harness gates on these parts, each as\n"
    "its own bold `**Label:** value` line, labels spelled exactly: Finished tool;\n"
    "Language; Project name; Mentor persona; Student term; Visual identity; Difficulty\n"
    "spine (the 3-6 concepts practitioners of this language/tool find hard and idiomatic\n"
    "at the target level); Graduate ledger (after the last chapter the student CAN … /\n"
    "still CANNOT …); Daily drivers (this language's daily-driver kit, every item\n"
    "assigned as `item = CAN` or `item = CANNOT`, items spelled exactly: growable\n"
    "collection; key-value; strings; errors — a CANNOT is a deliberate scope cut and\n"
    "must be repeated in the Graduate ledger); Continuity map (one-line `sNN -> sMM:`\n"
    "edges for every non-adjacent API/data/file reuse and every promise a later section\n"
    "must honor — write `single-section course` only when there truly is one section);\n"
    "Artifact lifecycle (the canonical files/\n"
    "entrypoints plus every temporary prompt, fixture, demo call, placeholder, or debug\n"
    "behavior, with the section that retires or deliberately ships it); Acceptance proof\n"
    "(a literal clean-start user journey from launch through the promised final outcome,\n"
    "including delivery outside the authoring surface when applicable); Section list\n"
    "(one physical line per entry, sequential, in the exact form "
    "`1. **s01 — Title:** capability/build promise`; the harness deterministically "
    "scaffolds those entries)._\n")
ARC_MIN_CHARS = 500  # of the striker's own content, contract lines excluded


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
    missing = [p for p in ARC_PARTS if f"**{p.lower()}:**" not in low]
    probs = []
    if missing:
        probs.append("these parts are missing and must be written EXACTLY as their own "
                     "`**Label:** value` line: " + "; ".join(f"**{p}:**" for p in missing))
    unassigned = [d for d in DAILY_DRIVERS
                  if not re.search(rf"{re.escape(d)}\s*=\s*CAN(NOT)?\b", body, re.I)]
    if unassigned:
        probs.append("the **Daily drivers:** line must assign every item EXACTLY as "
                     "`item = CAN` or `item = CANNOT`; unassigned: " + "; ".join(unassigned))
    try:
        parse_section_list(body)
    except ValueError as exc:
        probs.append(f"the **Section list:** is not machine-scaffoldable: {exc}")
    continuity_match = re.search(r"(?i)\*\*Continuity map:\*\*", body)
    continuity_tail = body[continuity_match.end():] if continuity_match else ""
    continuity = re.split(r"(?m)^\*\*[^\n]+:\*\*", continuity_tail, maxsplit=1)[0]
    edge_lines = [line.strip() for line in continuity.splitlines() if line.strip()]
    edge_pattern = re.compile(r"(?:[-*]\s*)?s(\d{2})\s*->\s*s(\d{2})\s*:\s*\S.+", re.I)
    single = len(edge_lines) == 1 and edge_lines[0].lower() == "single-section course"
    if not edge_lines or (not single and not any(edge_pattern.fullmatch(line)
                                                 for line in edge_lines)):
        probs.append("the **Continuity map:** needs at least one explicit `sNN -> sMM:` "
                     "dependency edge (or the exact phrase `single-section course`)")
    elif not single:
        malformed = [line for line in edge_lines if not edge_pattern.fullmatch(line)]
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
    if len(body) < ARC_MIN_CHARS:
        probs.append(f"the arc is only {len(body)} chars — a real arc is far longer "
                     f"(minimum {ARC_MIN_CHARS})")
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


def arc_checkpoint(plan_path, interactive, skip):
    """#21: after Phase 1, let a human approve the arc before ~30k tokens of authoring commit
    to it. Zero model cost. Skipped automatically when non-interactive (web/--gate-json) or --yes."""
    if skip or not interactive:
        print("  · arc checkpoint skipped (non-interactive or --yes) — review the plan's Arc if unsure")
        return
    try:
        arc = open(plan_path, encoding="utf-8").read().split("## Arc", 1)[-1]
    except OSError:
        return
    print("\n" + "-" * 64 + "\n  PHASE 1 ARC — approve before authoring commits to it:\n" + "-" * 64)
    print(arc.strip()[:2000] or "(no arc recorded?)")
    ans = input("\n  Proceed with this arc? [y = go / anything else = stop and edit the plan] > ").strip().lower()
    if ans != "y":
        sys.exit("Stopped at the arc checkpoint. Edit the plan's Arc, then resume with "
                 "--from-phase 2.")


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
