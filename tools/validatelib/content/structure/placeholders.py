"""Scaffolding sweep: authored fields carry no TODO/FIXME/lorem strings."""
import os

from ... import PLACEHOLDER_RE, load_toml, rel, warn


def check_placeholders(toml_files):
    """Findings are owned by the phase that authors their file, while deliberate student
    starter TODOs are exempt.  Future scaffold banks therefore remain legal without
    deferring completed-section debt to Phase 7.
    """
    for path in toml_files:
        data, e = load_toml(path)
        if e:
            continue  # unparseable files are reported by their own checks
        hits = []

        def scan(v, at):
            if isinstance(v, str):
                if PLACEHOLDER_RE.search(v):
                    hits.append(at or "(top level)")
            elif isinstance(v, dict):
                for k, x in v.items():
                    # A starter is the student's deliberately incomplete input.  TODO
                    # markers there are instructions, not authoring scaffolding.
                    if k == "starter":
                        continue
                    scan(x, f"{at}.{k}" if at else k)
            elif isinstance(v, list):
                for i, x in enumerate(v):
                    scan(x, f"{at}[{i}]")

        scan(data, "")
        if hits:
            normalized = rel(path).replace(os.sep, "/")
            if "/sections/" in f"/{normalized}":
                owner_phase = 3
            elif normalized.endswith(("intrusions.toml", "attacks_src.toml", "attacks.toml")):
                owner_phase = 4
            elif normalized.endswith(("themes.toml", "shop.toml", "badges.toml")):
                owner_phase = 6
            else:
                owner_phase = 7
            warn("content", f"{rel(path)}: {len(hits)} string(s) still carry TODO/FIXME/placeholder "
                            f"text (first at {hits[0]}) — clear every bit of scaffolding before "
                            "calling the tome done", phase=owner_phase)
