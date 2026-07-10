#!/usr/bin/env python3
"""validate_tome.py — hold a tome up to the candlelight before you ship it.

Machine-checks one tome folder against the rules in tome-authoring/: does the
TOML parse, do the ids line up, does every palette carry all 18 inks, do the
rubric weights sum true. One finding per line; a tome with any ERROR is not done.

    python3 tools/validate_tome.py tomes/<id>

Exit 0 = clean (WARNs allowed). Exit 1 = at least one ERROR. Stdlib only.
The checks live in tools/validatelib/ (see its __init__ for the module map);
this file is the CLI + the orchestrator."""
import argparse
import os
import sys

from validatelib import ID_RE, _findings, err, load_toml, rel
from validatelib.attacks import check_attacks, check_attacks_sync, check_intrusions
from validatelib.content import (check_anti_template, check_content, check_density,
                                 check_literal_newlines, check_section)
from validatelib.depth import (check_economy_totals, check_freestyle_scope, check_name_drift,
                               check_padded_prose, check_presolved_static,
                               check_self_answering, check_taught_before_used,
                               check_verbatim_prose)
from validatelib.execute import check_snippets, check_starters_run
from validatelib.structure import (check_badges, check_economy, check_layout, check_meta,
                                   check_narrative, check_placeholders, check_runtime,
                                   check_shop)
from validatelib.themes import check_theme_distinctness, check_themes

import tome_layout  # noqa: E402 — validatelib put REPO on sys.path; in lockstep with server


def validate(tome_path, run=False, tooling=None):
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
    try:
        tome_layout.merge_banks(m, tome_path)  # fold in themes/shop/badges/intrusions siblings, if split out
    except Exception as ex:  # a malformed sibling bank file
        err(label, f"failed to read a split bank file: {ex}")

    meta = check_meta(m, label)
    if meta is not None and meta.get("id") != tome_id:
        err(label, f"[meta] id is {meta.get('id')!r} but the folder is named {tome_id!r} — they must match")
    if not ID_RE.fullmatch(tome_id):
        err(rel(tome_path), f"folder name {tome_id!r} must match [A-Za-z0-9_-]+")

    check_placeholders(check_layout(tome_path, m))
    check_badges(m, tome_path)
    check_runtime(m, tome_id, label)
    check_narrative(m, label)
    check_economy(m, label)
    theme_ids, earned_granted = check_themes(m, label)
    check_theme_distinctness(m, label)
    check_shop(m, theme_ids, earned_granted, label)

    content = m.get("content", {})
    sections = content.get("sections") if isinstance(content, dict) else None
    if not isinstance(sections, list) or not sections:
        err(label, "[content] sections must be a non-empty array of section ids")
        sections = []

    seen_ex, seen_les, seen_sid = set(), set(), set()
    sections_data = []
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
        check_section(sdata, sid, slabel, seen_ex, seen_les)
        sections_data.append(sdata)
    check_anti_template(sections_data)
    check_density(sections_data)
    check_content(m, sections_data, label, tooling)
    check_literal_newlines(m, sections_data)
    check_taught_before_used(sections_data)
    check_freestyle_scope(m, sections_data)
    check_verbatim_prose(sections_data)
    check_padded_prose(sections_data)
    check_economy_totals(tome_path, m, sections_data)
    check_presolved_static(m, sections_data)
    check_name_drift(sections_data)
    check_self_answering(sections_data)
    check_intrusions(tome_path, m, label)
    if run:
        check_snippets(m, sections_data)
        check_starters_run(tome_path, m, sections_data)

    # attacks is optional and machine-generated; default to generated/attacks.toml,
    # and only validate it when the file is actually present.
    attacks_name = (content.get("attacks") if isinstance(content, dict) else None) or "generated/attacks.toml"
    apath = os.path.join(tome_path, str(attacks_name))
    if os.path.isfile(apath):
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
        epilog="Fix every ERROR before shipping. WARNs are advisory; a tome that "
               "still emits an ERROR is not done.")
    ap.add_argument("tome", help="path to the tome folder, e.g. tomes/verisearch")
    ap.add_argument("--strict", action="store_true",
                    help="also exit 1 on every WARN except 'advisory' ones (language-calibration "
                         "limits no tome can fix) — the tome-workflow phase 7 bar: a finished tome "
                         "carries zero warnings; the harness uses this from Phase 7 on")
    ap.add_argument("--run", action=argparse.BooleanOptionalAction, default=True,
                    help="EXECUTE every write-lab and intrusion starter through the tome's runtime: "
                         "flags starters that don't compile/run and ones already pre-solved. On by "
                         "default (it is the only check that can see a broken scaffold); degrades to "
                         "a WARN when the toolchain is absent. --no-run skips it.")
    ap.add_argument("--tooling", choices=("internal", "external", "both"), default=None,
                    help="enforce the build's gate Tooling choice: internal forbids "
                         "externalWorkspace; external/both require external tools taught in section 1")
    args = ap.parse_args()

    validate(args.tome, run=args.run, tooling=args.tooling)

    errors = sum(1 for f in _findings if f[0] == "ERROR")
    warns = len(_findings) - errors
    hard = sum(1 for lv, lbl, _ in _findings if lv == "WARN" and lbl != "advisory")
    for level, lbl, msg in _findings:
        print(f"{level} {lbl}: {msg}")
    strict_note = f", {hard} hard-gate warn(s) [--strict]" if args.strict and hard else ""
    print(f"-- {os.path.basename(os.path.abspath(args.tome.rstrip(os.sep)))}: "
          f"{errors} error(s), {warns} warning(s){strict_note}")
    sys.exit(1 if errors or (args.strict and hard) else 0)


if __name__ == "__main__":
    main()
