"""The badge bank must define every engine-granted badge id."""
import glob
import os
import re

from ... import REPO, err, rel, warn


def engine_badge_ids():
    """The badge ids the engine hard-grants — the literal grantBadge(\"...\") calls in
    the web engine's JS (streaks, defenses, duel wins, completion). Scraped live so the
    contract can't drift; variable-id calls (freestyle badges) don't match and don't
    belong here. Scans web/js/*.js (the split engine) plus web/app.js if it exists."""
    js = ""
    paths = sorted(glob.glob(os.path.join(REPO, "web", "js", "*.js")))
    paths.append(os.path.join(REPO, "web", "app.js"))
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                js += f.read()
        except OSError:
            continue
    if not js:
        return set()  # validator run without the web app checked out — skip the contract
    # the literal must be the WHOLE first argument — grantBadge("rank-" + …) builds a
    # dynamic id and carries its own name/desc, so it never needs a bank entry
    return set(re.findall(r'grantBadge\(\s*"([A-Za-z0-9_-]+)"\s*[,)]', js))


def check_badges(m, tome_path):
    """The badge bank must define every engine-granted id: grantBadge falls back to the
    RAW ID as the badge's name, so a missing entry toasts \"SIGIL PRESSED // combo-10\"
    at the student — working mechanics, dead flavor. The true-sight build shipped 1 of 6."""
    engine = engine_badge_ids()
    if not engine:
        return
    bpath = os.path.join(tome_path, "badges.toml")
    blabel = rel(bpath if os.path.isfile(bpath) else os.path.join(tome_path, "tome.toml"))
    bank = {b.get("id") for b in (m.get("badges") or []) if isinstance(b, dict)}
    missing = engine - bank
    if missing:
        err(blabel, f"badge bank is missing engine-granted id(s): {sorted(missing)} — the engine "
                    "grants these by id and an undefined one toasts as a raw id with no name "
                    "or story; define all of them, in this tome's voice")
    extra = bank - engine
    if extra:
        warn(blabel, f"badge id(s) {sorted(extra)} are never granted by the engine — dead sigils "
                     "(section badges belong in each section's [freestyle.badge], not the bank)",
             phase=6)
