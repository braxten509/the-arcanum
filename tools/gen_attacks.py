#!/usr/bin/env python3
"""Generate a tome's attacks.toml (the SPELL DUEL bank) from its reference solutions.

Language-neutral: reads tomes/<id>/attacks_src.toml, runs each `solution` through THAT
tome's runtime via /api/runsnippet (so C#, Python, Java, … all work the same way),
then slices the verified stdout into the cumulative per-stage `expect` blocks and
writes tomes/<id>/generated/attacks.toml. No language is special — a tome brings its
own solutions in its own tongue; this script only runs and slices them.

  attacks_src.toml (authored, per tome):
    [[challenge]]
    tier    = 1                      # difficulty tier (>=1); tiers are written in order
    title   = "THE NAME-FORGING"     # shown to the player
    starter = '''...'''              # the code the player starts from
    briefs  = ["stage 1 …", "…", "…"]  # one per stage
    solution= '''...'''              # full reference code; its stdout is the answer key
    cuts    = [3, 5, 8]              # cumulative stdout line count at the end of each stage
                                     #   (len(cuts) == len(briefs); last == total lines)

Usage: python3 tools/gen_attacks.py <tome_id>   (server must be running)"""
import json
import os
import sys
import tomllib
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = os.environ.get("ARCANUM_PORT", "8777")


def run(tome, code):
    api = f"http://localhost:{PORT}/api/runsnippet?tome={tome}"
    req = urllib.request.Request(api, json.dumps({"code": code, "stdin": "", "tome": tome}).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


def toml_str(s):
    """Emit a TOML string: multiline literal when it holds newlines, else a basic string."""
    if "\n" in s and "'''" not in s and not s.endswith("'"):
        return "'''\n" + s + "'''"
    return json.dumps(s, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python3 tools/gen_attacks.py <tome_id>   (server must be running)")
    tome = sys.argv[1]
    tome_dir = os.path.join(REPO, "tomes", tome)
    src_path = os.path.join(tome_dir, "attacks_src.toml")
    if not os.path.isfile(src_path):
        sys.exit(f"no {os.path.relpath(src_path, REPO)} — this tome has no duel bank to generate")
    with open(src_path, "rb") as f:
        challenges = tomllib.load(f).get("challenge", [])
    if not challenges:
        sys.exit(f"{os.path.relpath(src_path, REPO)} has no [[challenge]] entries")

    tiers = {}  # tier number -> list of built challenges, in source order
    fails = 0
    for ch in challenges:
        tier, title = ch["tier"], ch["title"]
        briefs, cuts, solution, starter = ch["briefs"], ch["cuts"], ch["solution"], ch["starter"]
        if len(cuts) != len(briefs):
            sys.exit(f"{title}: cuts has {len(cuts)} entries but briefs has {len(briefs)} — they must match")
        r = run(tome, solution)
        if not r.get("ok"):
            print(f"FAIL {title}:\n{r.get('output', '')[:1500]}\n", flush=True)
            fails += 1
            continue
        lines = r["output"].split("\n")
        assert all(line.strip() for line in lines), f"{title}: blank line in output"
        assert len(lines) == cuts[-1], f"{title}: expected {cuts[-1]} lines, got {len(lines)}: {lines}"
        stages = [{"brief": briefs[i], "expect": "\n".join(lines[:cuts[i]])} for i in range(len(briefs))]
        tiers.setdefault(tier, []).append({"t": title, "starter": starter, "stages": stages})
        print(f"ok  D{tier} {title} ({cuts[-1]} lines)", flush=True)

    if fails:
        sys.exit(f"{fails} challenge(s) failed — attacks.toml NOT written")

    out = [
        "# SPELL DUEL challenge bank. Difficulty = tier order (1..N).",
        "# Each stage's `expect` is the COMPLETE required stdout at that stage; demands strictly",
        "# append lines — stages[n].expect == stages[n-1].expect + new lines, never edits.",
        "# Machine-generated from attacks_src.toml by tools/gen_attacks.py — regenerate, don't hand-edit.",
        "",
    ]
    for tier in sorted(tiers):
        out.append(f"# ---- difficulty {tier}")
        out.append("[[tiers]]")
        for ch in tiers[tier]:
            out.append("")
            out.append("[[tiers.pool]]")
            out.append(f"t = {toml_str(ch['t'])}")
            out.append(f"starter = {toml_str(ch['starter'])}")
            for st in ch["stages"]:
                out.append("")
                out.append("[[tiers.pool.stages]]")
                out.append(f"brief = {toml_str(st['brief'])}")
                out.append(f"expect = {toml_str(st['expect'])}")
        out.append("")

    out_path = os.path.join(tome_dir, "generated", "attacks.toml")  # machine-written; authors edit attacks_src.toml
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(out) + "\n")
    print(f"\nwrote {os.path.relpath(out_path, REPO)} ({len(challenges)} challenges, {len(tiers)} tiers)")


if __name__ == "__main__":
    main()
