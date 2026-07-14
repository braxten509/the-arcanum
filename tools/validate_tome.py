#!/usr/bin/env python3
"""validate_tome.py — hold a tome up to the candlelight before you ship it.

Machine-checks one tome folder against the rules in tome-authoring/: does the
TOML parse, do the ids line up, does every palette carry all 22 inks, do the
rubric weights sum true. One finding per line; a tome with any ERROR is not done.

    python3 tools/validate_tome.py tomes/<id>

Exit 0 = clean (WARNs allowed). Exit 1 = at least one ERROR. Stdlib only.
The checks live in tools/validatelib/ (see its __init__ for the module map);
this file is the CLI + the orchestrator."""
import argparse
import os
import sys

from validatelib import ID_RE, _findings, err, load_toml, rel, set_build_phase, warn
from validatelib.attacks import check_attacks, check_attacks_sync, check_intrusions
from validatelib.content import (check_anti_template, check_content, check_density,
                                 check_literal_newlines, check_section)
from validatelib.coverage import check_capability_ledger, check_canonical_type_regressions
from validatelib.depth import (check_economy_totals, check_freestyle_scope, check_name_drift,
                               check_padded_prose, check_presolved_static,
                               check_self_answering, check_taught_before_used,
                               check_verbatim_prose)
from validatelib.execute import check_snippets, check_starters_run
from validatelib.phase2 import check_phase2_skeleton, check_tooling_contract
from validatelib.proof import check_future_tome_proof
from validatelib.structure import (check_badges, check_economy, check_layout, check_meta,
                                   check_narrative, check_placeholders, check_runtime,
                                   check_shop)
from validatelib.themes import (check_sigil_palette_uniqueness, check_theme_distinctness,
                                check_themes)
from buildlib.validation_env import (ValidationEnvironmentError,
                                     ready_validation_environment)

import tome_layout  # noqa: E402 — validatelib put REPO on sys.path; in lockstep with server


def validate(tome_path, run=False, tooling=None, phase2_skeleton=False, run_section=None,
             require_proof_v1=False, build_plan=None):
    tome_path = os.path.abspath(tome_path.rstrip(os.sep))
    tome_id = os.path.basename(tome_path)
    manifest = os.path.join(tome_path, "tome.toml")
    label = rel(manifest)

    if not os.path.isdir(tome_path):
        err(rel(tome_path), "not a directory")
        return
    m, e = load_toml(manifest)
    if e:
        err(label, e)
        return
    if run:
        try:
            # Harness launches already carry this environment. Activating it here as
            # well makes a direct validate_tome.py invocation use the identical cache.
            os.environ.update(ready_validation_environment(tome_id))
        except ValidationEnvironmentError as ex:
            err(label, f"validation dependencies are not ready — run/resume the tome harness "
                       f"to provision them: {ex}")
            run = False
    try:
        tome_layout.merge_banks(m, tome_path)  # fold in themes/shop/badges/intrusions siblings, if split out
    except Exception as ex:  # a malformed sibling bank file
        err(label, f"failed to read a split bank file: {ex}")

    meta = check_meta(m, label)
    if meta is not None and meta.get("id") != tome_id:
        err(label, f"[meta] id is {meta.get('id')!r} but the folder is named {tome_id!r} — they must match")
    if not ID_RE.fullmatch(tome_id):
        err(rel(tome_path), f"folder name {tome_id!r} must match [A-Za-z0-9_-]+")

    layout_files = check_layout(tome_path, m)
    if not phase2_skeleton:
        placeholder_files = layout_files
        declared = ((m.get("content") or {}).get("sections")
                    if isinstance(m.get("content"), dict) else []) or []
        if run_section and str(run_section) in [str(sid) for sid in declared]:
            through = [str(sid) for sid in declared]
            prefix_ids = set(through[:through.index(str(run_section)) + 1])

            def in_authored_prefix(path):
                local = os.path.relpath(path, tome_path).replace(os.sep, "/")
                if not local.startswith("sections/"):
                    return True
                owner = local.split("/", 2)[1]
                if owner.endswith(".toml"):
                    owner = owner[:-5]
                return owner in prefix_ids

            placeholder_files = [path for path in layout_files if in_authored_prefix(path)]
        check_placeholders(placeholder_files)
    check_runtime(m, tome_id, label)
    check_narrative(m, label)
    if not phase2_skeleton:
        # These banks are authored in Phases 4–6. Phase 2 preserves their valid base
        # scaffold and should not receive cosmetic/economy warnings as fake work.
        check_badges(m, tome_path)
        check_economy(m, label)
        theme_ids, earned_granted = check_themes(m, label)
        check_theme_distinctness(m, label)
        check_sigil_palette_uniqueness(m, tome_path, label)
        check_shop(m, theme_ids, earned_granted, label)

    content = m.get("content", {})
    if require_proof_v1 and (not isinstance(content, dict)
                             or content.get("proofVersion") != 1):
        err(label, "harness-built tomes must preserve [content] proofVersion = 1")
    sections = content.get("sections") if isinstance(content, dict) else None
    if not isinstance(sections, list) or not sections:
        err(label, "[content] sections must be a non-empty array of section ids")
        sections = []

    seen_ex, seen_les, seen_sid = set(), set(), set()
    sections_data = []
    prefix_ids = None
    if run_section and str(run_section) in [str(sid) for sid in sections]:
        ordered_ids = [str(sid) for sid in sections]
        prefix_ids = set(ordered_ids[:ordered_ids.index(str(run_section)) + 1])
    for sid in sections:
        if sid in seen_sid:
            err(label, f"[content] section id {sid!r} is listed more than once")
        seen_sid.add(sid)
        folder = os.path.join(tome_path, "sections", str(sid))
        slabel = rel(folder if os.path.isdir(folder) else folder + ".toml")
        try:
            sdata = tome_layout.load_section(tome_path, sid)  # folder or flat
        except Exception as se:
            err(slabel, str(se))
            continue
        if prefix_ids is None or str(sid) in prefix_ids:
            check_section(sdata, sid, slabel, seen_ex, seen_les)
        sections_data.append(sdata)
    if phase2_skeleton:
        check_phase2_skeleton(sections_data)
        check_tooling_contract(m, sections_data, label, tooling)
        check_future_tome_proof(tome_path, m, sections_data, run=False,
                                plan_path=build_plan)
    else:
        quality_sections = (sections_data if prefix_ids is None else
                            [section for section in sections_data
                             if str(section.get("id")) in prefix_ids])
        check_anti_template(quality_sections)
        check_density(quality_sections)
        check_content(m, quality_sections, label, tooling)
        check_literal_newlines(m, quality_sections)
        check_taught_before_used(quality_sections)
        check_freestyle_scope(m, quality_sections)
        check_capability_ledger(
            m, quality_sections,
            course_complete=(prefix_ids is None or str(run_section) == str(sections[-1])))
        check_canonical_type_regressions(m, quality_sections)
        check_verbatim_prose(quality_sections)
        check_padded_prose(quality_sections)
        check_economy_totals(tome_path, m, quality_sections)
        check_presolved_static(m, quality_sections)
        check_name_drift(quality_sections)
        check_self_answering(quality_sections)
    if not phase2_skeleton:
        check_intrusions(tome_path, m, label)
        check_future_tome_proof(tome_path, m, sections_data, run=run,
                                run_section=run_section, plan_path=build_plan)
    if run:
        execution_sections = sections_data
        if run_section:
            execution_sections = [section for section in sections_data
                                  if str(section.get("id")) == str(run_section)]
            if not execution_sections:
                err("run", f"--run-section {run_section!r} is not a loaded section id")
        check_snippets(m, execution_sections)
        check_starters_run(
            tome_path, m, execution_sections, include_banks=not bool(run_section))

    # attacks is optional and machine-generated; default to generated/attacks.toml,
    # and only validate it when the file is actually present.
    attacks_name = (content.get("attacks") if isinstance(content, dict) else None) or "generated/attacks.toml"
    apath = os.path.join(tome_path, str(attacks_name))
    if not phase2_skeleton and os.path.isfile(apath):
        stages = (m.get("progression", {}) or {}).get("attackStages")
        check_attacks(apath, m, label, stages)
        check_attacks_sync(tome_path, apath)

    # Exercise the same final assembly path the HTTP /api/tome route uses. The
    # structural checks above are intentionally detailed, but only the real loader can
    # prove its merged runtime/banks/sections payload can actually be constructed.
    installed_root = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "tomes"))
    if os.path.realpath(os.path.dirname(tome_path)) == installed_root:
        try:
            from arcanum.tomes import assemble_tome
            payload = assemble_tome(tome_id)
            if len(payload.get("sections", [])) != len(sections_data):
                err("loader", f"assembled payload has {len(payload.get('sections', []))} section(s), "
                    f"validator loaded {len(sections_data)}")
        except Exception as ex:
            err("loader", f"the server's assemble_tome() path failed: {type(ex).__name__}: {ex}")
    else:
        warn("advisory", "server assembly was skipped because this tome is outside the repo's "
             "tomes/ directory; install it there to exercise the /api/tome loader path")


def main():
    ap = argparse.ArgumentParser(
        description="Validate one ARCANUM tome folder against tome-authoring/.",
        epilog="Fix every ERROR. With --build-phase, current/earlier owned warnings are "
               "promoted to errors; --strict also gates all non-advisory warnings.")
    ap.add_argument("tome", help="path to the tome folder, e.g. tomes/verisearch")
    ap.add_argument("--strict", action="store_true",
                    help="also exit 1 on every WARN except 'advisory' ones (language-calibration "
                         "limits no tome can fix) — the tome-workflow phase 7 bar: a finished tome "
                         "carries zero warnings; the harness uses this from Phase 7 on")
    ap.add_argument("--build-phase", type=int, choices=range(2, 9), default=None,
                    metavar="N", help="promote warnings owned by Phase N or earlier to ERROR; "
                         "the harness supplies this so unfinished work cannot leak forward")
    ap.add_argument("--run", action=argparse.BooleanOptionalAction, default=True,
                    help="EXECUTE every write-lab and intrusion starter through the tome's runtime: "
                         "flags starters that don't compile/run and ones already pre-solved. On by "
                         "default (it is the only check that can see a broken scaffold); degrades to "
                         "a WARN when the toolchain is absent. --no-run skips it.")
    ap.add_argument("--run-section", metavar="SID", default=None,
                    help="execute lesson snippets/write labs only for SID (the warm Phase-3 "
                         "checkpoint); proof-v1 checks cover the authored prefix through SID, "
                         "while whole-tome scaffold checks still run and global intrusion/duel "
                         "banks wait for the final gate")
    ap.add_argument("--tooling", choices=("internal", "external", "both"), default=None,
                    help="enforce the build's gate Tooling choice: internal forbids "
                         "externalWorkspace; external/both require external tools taught in section 1")
    ap.add_argument("--phase-1-plan", metavar="PATH", default=None,
                    help="Phase 1 warm-context mode: validate the build plan's Arc instead of "
                         "the intentionally unfinished tome")
    ap.add_argument("--phase-2-skeleton", action="store_true",
                    help="Phase 2 warm-context mode: validate the complete one-placeholder-lesson "
                         "skeleton without Phase 3 density/prose checks or TODO warnings")
    ap.add_argument("--require-proof-v1", action="store_true",
                    help="harness-owned future-tome gate: proofVersion = 1 cannot be removed")
    ap.add_argument("--build-plan", metavar="PATH", default=None,
                    help="Phase-1 plan whose machine-readable acceptance scenarios must match")
    args = ap.parse_args()

    if args.phase_1_plan and args.phase_2_skeleton:
        ap.error("--phase-1-plan and --phase-2-skeleton are mutually exclusive")

    if args.phase_1_plan:
        from buildlib.checkpoints import arc_written
        plan = os.path.abspath(args.phase_1_plan)
        clean, report = arc_written(plan, rel(plan))
        if not clean:
            print(f"ERROR plan: {report}")
        print(f"-- {os.path.basename(plan)}: {'clean' if clean else '1 error(s)'} [Phase 1 Arc]")
        sys.exit(0 if clean else 1)

    set_build_phase(args.build_phase)
    validate(args.tome, run=args.run, tooling=args.tooling,
             phase2_skeleton=args.phase_2_skeleton, run_section=args.run_section,
             require_proof_v1=args.require_proof_v1, build_plan=args.build_plan)

    errors = sum(1 for f in _findings if f[0] == "ERROR")
    warns = len(_findings) - errors
    hard = sum(1 for lv, lbl, _ in _findings if lv == "WARN" and lbl != "advisory")
    for level, lbl, msg in _findings:
        print(f"{level} {lbl}: {msg}")
    strict_note = f", {hard} hard-gate warn(s) [--strict]" if args.strict and hard else ""
    mode_note = (" [Phase 2 skeleton]" if args.phase_2_skeleton else
                 f" [executed section {args.run_section}]" if args.run_section else "")
    if args.build_phase is not None:
        mode_note += f" [Phase {args.build_phase} owned-warning gate]"
    print(f"-- {os.path.basename(os.path.abspath(args.tome.rstrip(os.sep)))}: "
          f"{errors} error(s), {warns} warning(s){strict_note}{mode_note}")
    sys.exit(1 if errors or (args.strict and hard) else 0)


if __name__ == "__main__":
    main()
