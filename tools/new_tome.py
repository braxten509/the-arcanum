#!/usr/bin/env python3
"""new_tome.py — strike the first match for a new tome.

Scaffolds tomes/<id>/ with every required table filled with valid placeholder
content and TODO markers telling the author-AI exactly what to replace. The
skeleton passes validate_tome.py as-is, so you start from green and only ever
have errors you introduced. It refuses to overwrite an existing tome folder.

    python3 tools/new_tome.py <id> --sections N [--mastery 1-5] [--name N]
                                      [--language L] [--runtime R]

No attacks bank is written — author tomes/<id>/attacks_src.toml later, then run
python3 tools/gen_attacks.py <id> to generate attacks.toml. Stdlib only.
"""
import argparse
import os
import re
import sys

try:
    from buildlib.course.limits import MAX_SECTIONS, MIN_SECTIONS, section_count_error
except ModuleNotFoundError:
    from tools.buildlib.course.limits import MAX_SECTIONS, MIN_SECTIONS, section_count_error
try:
    from scaffold import RESEARCH_TEMPLATE
except ModuleNotFoundError:
    from tools.scaffold import RESEARCH_TEMPLATE

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOMES_DIR = os.path.join(REPO, "tomes")
ID_RE = re.compile(r"[A-Za-z0-9_-]+")
ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
         "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]


def roman(n):
    return ROMAN[n] if 0 <= n < len(ROMAN) else str(n)


# tome.toml — @@TOKENS@@ are replaced; a raw triple-quoted string keeps the TOML
# literal strings (''' ''') and any backslashes intact.
TOME_TEMPLATE = r"""
# ARCANUM tome manifest — scaffolded by tools/new_tome.py.
# Replace every TODO, then run:  python3 tools/validate_tome.py tomes/@@ID@@
# Read tome-authoring/2-tome-toml.md before filling this in — every key here is documented there.

[meta]
id = "@@ID@@"                       # MUST equal the folder name
name = "@@NAME@@"                   # TODO: the title on the tome-switcher card
description = "TODO: 1-2 sentences — what the player builds, over how many chapters."
author = "TODO: your name or house"
version = "0.1.0"
favicon = ">_"                      # TODO: 1-2 character browser-tab glyph

[runtime]
name = "@@RUNTIME@@"                # basename of a TOML under global-configs/runtimes/
project = "@@PROJECT@@"             # TODO: the workspace project/folder name
language = "@@LANGUAGE@@"           # display name, used in grader/oracle prompts
starterCode = ""                   # learner authors the canonical entry file
scaffoldCommand = []               # learner assembles project structure/configuration
# packages = false                 # true only for dotnet/NuGet tomes
# externalWorkspace = true         # ONLY for courses whose real work lives in the player's
                                   # own external tools; the player chooses its location.

[content]
sections = [@@SECTIONS_ARRAY@@]     # ordered section ids; each maps to sections/<id>/
capabilityLedger = true             # keep this: lessons declare `teaches`, capstones
                                    # declare cumulative `requires`; validator proves order
proofVersion = 1                    # future-tome contract: replay learner edits + run milestones
# OPTIONAL duel bank → generated/attacks.toml (the engine default). Do NOT hand-write it:
# author attacks_src.toml, then run  python3 tools/gen_attacks.py @@ID@@

[mastery]
evidenceVersion = 1                # central, language-neutral evidence policy
sourceEvidenceVersion = 1          # Phase-3 source receipts + adversarial Working evidence
level = @@MASTERY@@                 # sealed Phase-0 Finish selection; never lower per tome

[acceptance]
version = 1
mode = "run"                       # run; guided only for inherently unautomatable external work
artifact = "runtime"               # runtime | package
runArgs = ["--arcanum-acceptance"]
scenarios = ["replace-me", "finished-outcome"] # Phase 2 copies the exact Phase-1 journey ids
controls = ["input", "clock", "seed", "frame-limit"]

[defaults]
theme = "signature"                # a [[themes]] id below (this tome's own default look)

[defaults.ai]
oracle = "llama3.1:8b"
grader = "qwen2.5:14b"
graderKind = "claude-cli"
graderModel = "claude-opus-4-8"

[economy]
# TODO: rebalance once your exercise/freestyle points are set (see § [economy]).
ranks = [[0, "NOVICE"], [400, "ADEPT"], [1000, "MASTER"]]
hintCost = 50
oracleCost = 10
attemptMultipliers = [1, 0.6, 0.3]
comboStep = 0.05
comboCap = 0.5
sRankMultiplier = 1.5
attackStakePerDiff = 20
attackWinPerDiff = 15

[narrative]
objective = "TODO: one or two sentences naming the tool the whole tome builds toward. REQUIRED — the server refuses to load a tome with this blank."
title = "ARCANUM // TODO"
logo = "TODO"
opsLabel = "CHAPTERS"
graderPersona = "TODO PERSONA"     # the mentor's codename; role-played by the grader
studentTerm = "apprentice"
currency = "coin"
currencyShort = "gp"
gradeScale = "S|A|B|C|D|F"
bootLines = [
  "TODO: opening line, written by candlelight.",
  "TODO: name the tome — {N} chapters within.",
  "TODO: introduce the mentor and the commission.",
]
gradingLines = [
  "TODO: in-character flavor while the AI grades...",
  "TODO: another one...",
]

# --- the peddler's shop -------------------------------------------------------
# Every tome stocks these FIVE engine power-ups. The mechanic is fixed by `id`;
# reflavor name/desc/cost/ico to this course's world (validator requires all 5,
# each filled). oracle is an optional 6th (needs an [runtime] oracle model).
[[shop]]
id = "firewall"                    # engine mechanic: while charged, a wrong answer costs no credits
kind = "consumable"
name = "TODO WARD OF ABSORPTION"
cost = 450
desc = "TODO: one flavorful sentence that also explains the mechanic."
ico = "shield"
charges = 5

[[shop]]
id = "x2"                          # engine mechanic: next 20 correct answers pay double (count engine-fixed — no charges key)
kind = "consumable"
name = "TODO CATALYST"
cost = 600
desc = "TODO: reflavor."
ico = "zap"

[[shop]]
id = "skip"                        # engine mechanic: solves one trial at full points
kind = "consumable"
name = "TODO SCROLL OF REVELATION"
cost = 700
desc = "TODO: reflavor."
ico = "scroll"

[[shop]]
id = "vpn"                         # engine mechanic: deflects one incoming hex per charge
kind = "consumable"
name = "TODO CLOAK OF UNSEEING"
cost = 800
desc = "TODO: reflavor."
ico = "cloak"
charges = 3

[[shop]]
id = "xray"                        # engine mechanic: reveals the grader's private xray notes
kind = "consumable"
name = "TODO SCRYING LENS"
cost = 500
desc = "TODO: reflavor."
ico = "eye"

[[shop]]
id = "theme-alt"
kind = "theme"
name = "TODO ALTERNATE PALETTE"
cost = 2200
theme = "alt"                      # unlocks the [[themes]] id "alt" below
desc = "TODO: reflavor."

# --- badges (register ONLY engine-granted ids here; per-chapter badges live in sections)
[[badges]]
id = "ghost-protocol"
name = "TODO OPUS"
desc = "TODO: awarded when every chapter's Great Working is passed."

# --- palettes: 22 inks each; recolor freely, keep all keys ---------------------
# Contract: bg0 = table wood · bg1 = parchment · bg2/bg3 = panels · line* = ink
# hairlines · tx* = inks · ac = accent ink · slab/slab-tx = the speaking stone
# (grey mineral, never wood browns) · candle = "r, g, b" of the light.
[[themes]]
id = "signature"
name = "TODO Signature Palette"
light = true                       # light parchment palette; omit for a dark one

[themes.vars]
bg0 = "#241609"
bg1 = "#e7d9b5"
bg2 = "#ddcda4"
bg3 = "#d3c092"
line = "#b9a67c"
line-hi = "#97815a"
tx = "#3d2b17"
tx-dim = "#6b5638"
tx-faint = "#8d7854"
ac = "#275d4d"
ac-dim = "#3e7a67"
ac-bg = "rgba(39, 93, 77, .10)"
warn = "#8a5d14"
bad = "#8e2f23"
info = "#3d4d78"
slab = "#27272b"
slab-tx = "#e3d3ac"
candle = "255, 172, 66"
sigil-1 = "#f7ffff"               # four casting inks, all visible along each bolt
sigil-2 = "#62d9dc"
sigil-3 = "#168db4"
sigil-4 = "#3d4d78"

[[themes]]
id = "alt"
name = "TODO Alternate Palette"

[themes.vars]
bg0 = "#0b0910"
bg1 = "#1e1b2a"
bg2 = "#262238"
bg3 = "#2e2a44"
line = "#3a3552"
line-hi = "#4d4870"
tx = "#d6d2c4"
tx-dim = "#9a95a8"
tx-faint = "#6d687f"
ac = "#7ba88f"
ac-dim = "#547a64"
ac-bg = "rgba(123, 168, 143, .10)"
warn = "#c9a45e"
bad = "#c96a54"
info = "#7a9aca"
slab = "#0e0c14"
slab-tx = "#cfc9b8"
candle = "255, 172, 66"
sigil-1 = "#ffffff"
sigil-2 = "#9beec0"
sigil-3 = "#4fb481"
sigil-4 = "#547a64"
"""


from scaffold.section_templates import ASSESSMENT_TEMPLATE, SECTION_TEMPLATE


def render(template, subs):
    out = template
    for k, v in subs.items():
        out = out.replace("@@" + k + "@@", v)
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Scaffold a new ARCANUM tome that passes validate_tome.py.",
        epilog="Then edit tomes/<id>/, replace every TODO, and re-run the validator.")
    ap.add_argument("id", help="tome id / folder name (letters, digits, - and _ only)")
    ap.add_argument("--name", help="display name (default: derived from the id)")
    ap.add_argument("--language", default="Python", help="display language name (default: Python)")
    ap.add_argument("--runtime", default="python",
                    help="runtime id — a unique TOML basename under global-configs/runtimes/ (default: python)")
    ap.add_argument("--mastery", type=int, default=1, choices=range(1, 6),
                    help="selected evidence finish, from 1 through 5 (default: 1)")
    ap.add_argument("--sections", type=int, required=True,
                    help=f"section count, from {MIN_SECTIONS} through {MAX_SECTIONS} inclusive")
    args = ap.parse_args()

    if not ID_RE.fullmatch(args.id):
        sys.exit(f"error: tome id {args.id!r} must match [A-Za-z0-9_-]+")
    if not MIN_SECTIONS <= args.sections <= MAX_SECTIONS:
        sys.exit("error: " + section_count_error(args.sections))

    tome_path = os.path.join(TOMES_DIR, args.id)
    if os.path.exists(tome_path):
        sys.exit(f"error: {os.path.relpath(tome_path, REPO)} already exists — refusing to overwrite")

    name = args.name or args.id.replace("-", " ").replace("_", " ").title()
    project = "".join(w.capitalize() for w in re.split(r"[-_ ]+", args.id)) or "Project"
    sids = [f"s{n:02d}" for n in range(1, args.sections + 1)]

    os.makedirs(os.path.join(tome_path, "sections"))
    tome_toml = render(TOME_TEMPLATE, {
        "ID": args.id,
        "NAME": name,
        "RUNTIME": args.runtime,
        "LANGUAGE": args.language,
        "PROJECT": project,
        "MASTERY": str(args.mastery),
        "SECTIONS_ARRAY": ", ".join(f'"{s}"' for s in sids),
    })
    with open(os.path.join(tome_path, "tome.toml"), "w", encoding="utf-8") as f:
        f.write(tome_toml.lstrip("\n"))

    for n, sid in enumerate(sids, start=1):
        section = render(SECTION_TEMPLATE, {"SID": sid, "ROMAN": roman(n)})
        with open(os.path.join(tome_path, "sections", sid + ".toml"), "w", encoding="utf-8") as f:
            f.write(section.lstrip("\n"))

    # scaffold flat, then convert to the split-folder layout (banks + per-section folders)
    # by reusing the round-trip-proven splitter — one source of truth for the layout.
    try:
        from maintenance import split_tome
    except ModuleNotFoundError:
        from tools.maintenance import split_tome
    split_tome.QUIET = True  # the new tome was never "flat" to the user; hide the internal churn
    split_tome.migrate_manifest(tome_path)
    for sid in sids:
        split_tome.migrate_section(tome_path, sid)
        with open(os.path.join(tome_path, "sections", sid, "assessment.toml"),
                  "w", encoding="utf-8") as handle:
            handle.write(ASSESSMENT_TEMPLATE.lstrip("\n"))
        with open(os.path.join(tome_path, "sections", sid, "research.toml"),
                  "w", encoding="utf-8") as handle:
            handle.write(RESEARCH_TEMPLATE.lstrip("\n"))

    print(f"scaffolded tomes/{args.id}/ (split layout)")
    print(f"next: fill in the TODOs, then  python3 tools/validate_tome.py tomes/{args.id}")


if __name__ == "__main__":
    main()
