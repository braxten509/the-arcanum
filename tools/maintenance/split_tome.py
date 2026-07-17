#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[2]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""Migrate one tome from the flat layout to the split-folder layout, by TEXT slicing
(never parse-and-reserialize) so every byte, comment, and quirk of formatting is
preserved. Idempotent-ish: refuses if split files already exist.

  themes/shop/badges banks  -> themes.toml / shop.toml / badges.toml
  [[progression.intrusionTiers]] (+ .pool) -> intrusions.toml as [[tiers]] (+ .pool)
  each sections/<id>.toml  -> sections/<id>/section.toml + freestyle.toml + lessons/lNN.toml
  attacks.toml (generated) -> generated/attacks.toml   (attacks_src.toml stays put — you author it)

Usage: python3 tools/maintenance/split_tome.py <tome_dir>
After running, confirm with:  python3 tools/validate_tome.py <tome_dir>
The engine (server.py) and validate_tome.py both load either layout via tome_layout.py,
so a split tome and a flat one behave identically.
"""
import os
import sys

QUIET = False  # set True when imported (e.g. by new_tome.py) to silence per-file prints


def _log(message):
    if not QUIET:
        print(message)


def _header_line_indexes(lines):
    """Indexes of lines that open a top-level TOML table: they start with '[' at col 0
    AND are not sitting inside a triple-quoted multiline string. Tracking the string
    state is essential — content fields hold lines like '[0] intro' and '[142, 143]'
    inside '''...''' that are NOT headers."""
    out, in_multiline = [], None  # in_multiline is None, "'''" or '\"\"\"'
    for i, line in enumerate(lines):
        if in_multiline is None and line.startswith("["):
            out.append(i)
        # toggle multiline state across this line's triple-quote delimiters
        pos = 0
        while pos < len(line):
            if in_multiline is None:
                nxt3 = min((line.find(q, pos) for q in ("'''", '"""') if line.find(q, pos) != -1), default=-1)
                if nxt3 == -1:
                    break
                in_multiline = line[nxt3:nxt3 + 3]
                pos = nxt3 + 3
            else:
                close = line.find(in_multiline, pos)
                if close == -1:
                    break
                in_multiline = None
                pos = close + 3
    return out


def split_top_level(lines):
    """Yield (header_line_or_None, block_lines) for the file, where each block runs
    from a top-level header line up to (not including) the next top-level header.
    The preamble before the first header comes back with header=None."""
    idxs = _header_line_indexes(lines)
    if not idxs:
        yield None, lines
        return
    if idxs[0] > 0:
        yield None, lines[:idxs[0]]
    for k, start in enumerate(idxs):
        end = idxs[k + 1] if k + 1 < len(idxs) else len(lines)
        yield lines[start], lines[start:end]


def header_name(header_line):
    """'[[shop]]' -> 'shop'; '[progression.earnedTheme]' -> 'progression.earnedTheme'."""
    return header_line.strip().strip("[]").strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        sys.exit(f"REFUSING: {path} already exists")
    with open(path, "w") as f:
        f.write(text)
    _log(f"  wrote {os.path.relpath(path)}")


def migrate_manifest(tome_dir):
    """Pull the [[themes]]/[[shop]]/[[badges]] banks and the intrusion tiers out of
    tome.toml into sibling files; rewrite tome.toml with them removed."""
    path = os.path.join(tome_dir, "tome.toml")
    with open(path) as f:
        lines = f.read().splitlines(keepends=True)

    banks = {"themes": [], "shop": [], "badges": []}
    intrusion_blocks = []
    kept = []  # blocks that stay in tome.toml

    for header, block in split_top_level(lines):
        if header is None:
            kept.append(block)
            continue
        name = header_name(header)
        top = name.split(".")[0].strip()
        # [[themes]] and its [themes.vars] child both belong to the themes bank
        if top == "themes":
            banks["themes"].append(block)
        elif top == "shop":
            banks["shop"].append(block)
        elif top == "badges":
            banks["badges"].append(block)
        elif name.startswith("progression.intrusionTiers"):
            intrusion_blocks.append((name, block))
        else:
            kept.append(block)

    # --- sibling bank files: same blocks, verbatim ---
    for name in ("themes", "shop", "badges"):
        if banks[name]:
            body = "".join("".join(b) for b in banks[name])
            write(os.path.join(tome_dir, name + ".toml"),
                  f"# {name} bank for this tome — moved out of tome.toml, loaded back in by the engine.\n\n"
                  + body.lstrip("\n"))

    # --- intrusions.toml: rename the header prefix progression.intrusionTiers -> tiers.
    # Only the header line changes ('progression.intrusionTiers' -> 'tiers'), inside
    # whatever brackets it already has; every other byte of the block is preserved. ---
    if intrusion_blocks:
        out = ["# Hex-defense intrusion bank — was [[progression.intrusionTiers]] in tome.toml.\n",
               "# Same shape; the engine reads [[tiers]] here and restores it as progression.intrusionTiers.\n\n"]
        for _name, block in intrusion_blocks:
            block = list(block)
            block[0] = block[0].replace("progression.intrusionTiers", "tiers", 1)
            out.append("".join(block))
        write(os.path.join(tome_dir, "intrusions.toml"), "".join(out))

    # --- rewrite tome.toml with the extracted blocks gone ---
    new_manifest = "".join("".join(b) for b in kept).rstrip("\n") + "\n"
    with open(path, "w") as f:
        f.write(new_manifest)
    _log(f"  rewrote {os.path.relpath(path)} ({len(kept)} blocks kept)")


def migrate_section(tome_dir, sid):
    """sections/<sid>.toml -> sections/<sid>/section.toml + freestyle.toml + lessons/lNN.toml."""
    src = os.path.join(tome_dir, "sections", sid + ".toml")
    with open(src) as f:
        lines = f.read().splitlines(keepends=True)

    preamble = []       # section-level keys before the first table (id/codename/…)
    freestyle_blocks = []
    lesson_groups = []  # list of list-of-blocks; a new group starts at each [[lessons]]
    section_tail = []   # any stray top-level block that isn't freestyle/lessons (defensive)

    for header, block in split_top_level(lines):
        if header is None:
            preamble.append(block)
            continue
        name = header_name(header)
        top = name.split(".")[0].strip()
        if top == "freestyle":
            freestyle_blocks.append(block)
        elif name == "lessons":            # [[lessons]] opens a new lesson
            lesson_groups.append([block])
        elif top == "lessons":             # [[lessons.readings]] / [[lessons.exercises]] — child of the current lesson
            lesson_groups[-1].append(block)
        else:
            section_tail.append(block)

    folder = os.path.join(tome_dir, "sections", sid)

    # section.toml — the preamble keys, plus any defensive tail block
    section_text = "".join("".join(b) for b in preamble)
    for b in section_tail:
        section_text += "".join(b)
    write(os.path.join(folder, "section.toml"), section_text.rstrip("\n") + "\n")

    # freestyle.toml
    if freestyle_blocks:
        write(os.path.join(folder, "freestyle.toml"),
              "".join("".join(b) for b in freestyle_blocks).rstrip("\n") + "\n")

    # lessons/lNN.toml — one file per [[lessons]] group, numbered by order
    for i, group in enumerate(lesson_groups, 1):
        text = "".join("".join(b) for b in group).rstrip("\n") + "\n"
        write(os.path.join(folder, "lessons", f"l{i:02d}.toml"), text)

    os.remove(src)
    _log(f"  removed flat {os.path.relpath(src)} ({len(lesson_groups)} lessons)")


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: migrate_tome.py <tome_dir>")
    tome_dir = sys.argv[1].rstrip("/")
    print(f"== migrating {tome_dir} ==")
    # read section ids from [content] sections before we rewrite the manifest
    import tomllib
    with open(os.path.join(tome_dir, "tome.toml"), "rb") as f:
        sids = tomllib.load(f).get("content", {}).get("sections", [])
    migrate_manifest(tome_dir)
    for sid in sids:
        migrate_section(tome_dir, sid)
    # a generated attacks.toml at the tome root belongs under generated/ now
    root_attacks = os.path.join(tome_dir, "attacks.toml")
    if os.path.isfile(root_attacks):
        dest = os.path.join(tome_dir, "generated", "attacks.toml")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.replace(root_attacks, dest)
        _log(f"  moved attacks.toml -> {os.path.relpath(dest, tome_dir)}")
        # keep any explicit [content].attacks pointer in step with the move
        manifest_path = os.path.join(tome_dir, "tome.toml")
        text = open(manifest_path).read()
        if 'attacks = "attacks.toml"' in text:
            with open(manifest_path, "w") as f:
                f.write(text.replace('attacks = "attacks.toml"', 'attacks = "generated/attacks.toml"'))
    print("== done ==")


if __name__ == "__main__":
    main()
