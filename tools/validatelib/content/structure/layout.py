"""The file-layout contract: every file in a tome folder must be accounted for."""
import os
import re

from ... import err, rel


def check_layout(tome_path, m):
    """Every file in the tome folder must be accounted for by the layout contract
    (tome_layout.py's docstring). This is the gate the true-sight build proved missing:
    a botched rename left an entire pre-rename tome NESTED inside the new one, plus it
    catches scratch files, backups, and section folders the manifest no longer lists —
    all invisible to checks that only read manifest-declared files. Returns the
    legitimate .toml paths so the placeholder sweep reads exactly the shipped files."""
    content = m.get("content", {}) if isinstance(m.get("content"), dict) else {}
    sections = {str(s) for s in (content.get("sections") or [])}
    attacks_name = str(content.get("attacks") or "generated/attacks.toml").replace(os.sep, "/")
    evidence = ((m.get("mastery") or {}).get("evidenceVersion") == 1
                if isinstance(m.get("mastery"), dict) else False)
    fixed = {"tome.toml", "themes.toml", "shop.toml", "badges.toml", "intrusions.toml",
             "attacks_src.toml", "attacks.toml", attacks_name,
             "generated/README.md"}  # the tooling's DO-NOT-EDIT marker for generated/
    if evidence:
        fixed.add("generated/mastery-evidence.json")

    def legit(p):
        if p in fixed:
            return True
        flat = re.fullmatch(r"sections/([A-Za-z0-9_-]+)\.toml", p)
        if flat:
            return flat.group(1) in sections
        deep = re.fullmatch(r"sections/([A-Za-z0-9_-]+)/(?:(?:section|freestyle)\.toml|lessons/[^/]+\.toml)", p)
        if deep:
            return deep.group(1) in sections
        if evidence:
            hidden = re.fullmatch(
                r"sections/([A-Za-z0-9_-]+)/(?:assessment\.toml|assessment/[^/]+(?:/[^/]+)*|"
                r"mastery-labs/[A-Za-z0-9_.-]+(?:\.toml|/[^/]+(?:/[^/]+)*))", p)
            generated = re.fullmatch(r"generated/mastery-labs/[^/]+/[^/]+/[^/]+(?:/[^/]+)*", p)
            return (bool(hidden) and hidden.group(1) in sections) or bool(generated)
        return False

    legit_tomls, stray = [], []
    for dirpath, dirs, files in os.walk(tome_path):
        rd = os.path.relpath(dirpath, tome_path).replace(os.sep, "/")
        if rd == ".":
            rd = ""
        # save/ is the engine's runtime state (student saves + workspace) — never validated
        dirs[:] = [d for d in dirs if not (rd == "" and d == "save")]
        if rd and "tome.toml" in files:
            err(rel(tome_path), f"an entire tome is nested at {rd!r} (it carries its own tome.toml) "
                                "— the debris of a botched rename (`mv old-dir existing-dir` moves "
                                "INTO it); delete the embedded copy")
            dirs[:] = []  # one finding for the subtree, not fifty
            continue
        for name in sorted(files):
            p = f"{rd}/{name}" if rd else name
            if legit(p):
                if p.endswith(".toml"):
                    legit_tomls.append(os.path.join(dirpath, name))
            else:
                stray.append(p)
    if stray:
        shown = ", ".join(stray[:8]) + (f" (+{len(stray) - 8} more)" if len(stray) > 8 else "")
        err(rel(tome_path), f"unexpected file(s) outside the tome layout: {shown} — a tome ships "
                            "only the layout-contract files (tome_layout.py); scratch files, "
                            "backups, and sections missing from [content].sections must go")
    return legit_tomls
