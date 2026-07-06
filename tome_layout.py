"""Shared tome-folder layout — the single source of truth for how a split tome
reassembles into the one manifest shape the client and the validator expect, so the
runtime loader (server.py) and validate_tome.py can never drift.

A tome may keep everything in one big tome.toml + flat sections/<id>.toml (the old
flat layout), OR split the big banks into sibling files and each section into a
folder (the split layout). Both load to the identical result:

  tomes/<id>/
    tome.toml          core config: [meta] [runtime] [content] [defaults] [economy] [narrative] [progression]
    themes.toml        [[themes]]            (else inline in tome.toml)
    shop.toml          [[shop]]              (else inline)
    badges.toml        [[badges]]            (else inline)
    intrusions.toml    [[tiers]] hex-defense (else [[progression.intrusionTiers]] inline)
    attacks.toml       [[tiers]] spell-duel  (unchanged, single file)
    sections/<sid>/    section.toml + freestyle.toml + lessons/*.toml  (else flat sections/<sid>.toml)
"""
import os
import glob
import tomllib


def _read(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def merge_banks(manifest, tome_dir):
    """Fold any split-out sibling bank files into the manifest dict, in place.
    A missing sibling leaves whatever tome.toml already had inline, so flat tomes are
    untouched. Returns the manifest for convenience."""
    for name in ("themes", "shop", "badges"):
        path = os.path.join(tome_dir, name + ".toml")
        if os.path.isfile(path):
            manifest[name] = _read(path).get(name, [])
    intrusions_path = os.path.join(tome_dir, "intrusions.toml")
    if os.path.isfile(intrusions_path):
        progression = dict(manifest.get("progression", {}))  # copy — never mutate a cached table
        progression["intrusionTiers"] = _read(intrusions_path).get("tiers", [])
        manifest["progression"] = progression
    return manifest


def load_section(tome_dir, section_id):
    """One section as a single dict, from either a folder (section.toml + freestyle.toml
    + lessons/*.toml, lessons ordered by filename) or a flat sections/<id>.toml."""
    folder = os.path.join(tome_dir, "sections", str(section_id))
    if os.path.isdir(folder):
        section = _read(os.path.join(folder, "section.toml"))
        freestyle_path = os.path.join(folder, "freestyle.toml")
        if os.path.isfile(freestyle_path):
            freestyle = _read(freestyle_path)
            if "freestyle" in freestyle:
                section["freestyle"] = freestyle["freestyle"]
        lessons = []
        for lesson_path in sorted(glob.glob(os.path.join(folder, "lessons", "*.toml"))):
            lessons += _read(lesson_path).get("lessons", [])
        section["lessons"] = lessons
        return section
    return _read(os.path.join(tome_dir, "sections", str(section_id) + ".toml"))
