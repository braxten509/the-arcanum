"""SPELL-DUEL attack bank checks (+ attacks_src sync) and the HEX-DEFENSE
intrusion bank."""
import os

from . import err, load_toml, norm_lines, rel, warn


def check_attacks(path, m, label, attackstages):
    data, e = load_toml(path)
    if e:
        err(rel(path), e)
        return
    tiers = data.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        err(rel(path), "attacks file has no [[tiers]]")
        return
    want = len(attackstages) if isinstance(attackstages, list) and attackstages else 3
    thin = []
    for ti, tier in enumerate(tiers):
        pool = tier.get("pool", []) if isinstance(tier, dict) else []
        if len(pool) < 5:
            thin.append(ti + 1)
        for pi, chal in enumerate(pool):
            where = f"tier {ti + 1} challenge {pi + 1}"
            starter = chal.get("starter") if isinstance(chal, dict) else None
            if isinstance(starter, str) and starter.count("{") != starter.count("}"):
                err(rel(path), f"{where}: starter has unbalanced braces ({starter.count('{')} open, "
                               f"{starter.count('}')} close) — it must run as given; a student "
                               "under the duel timer repairs logic, not scaffolding")
            stages = chal.get("stages", []) if isinstance(chal, dict) else []
            if len(stages) != want:
                err(rel(path), f"{where}: has {len(stages)} stages; expected exactly {want} "
                               "(one per [progression].attackStages entry)")
            prev = None
            for si, st in enumerate(stages):
                exp = st.get("expect") if isinstance(st, dict) else None
                if exp is None or not str(exp).strip():
                    err(rel(path), f"{where} stage {si + 1}: expect is empty")
                    prev = None
                    continue
                cur = norm_lines(exp)
                if prev is not None and cur[:len(prev)] != prev:
                    err(rel(path), f"{where} stage {si + 1}: breaks the append invariant "
                                   "(each stage's expect must begin with the previous stage's expect)")
                prev = cur
    if thin:
        warn(rel(path), f"{len(thin)} attack tier(s) have <5 challenges (tiers {thin}) — "
                        "spec wants 5+ per tier (one is picked at random) so repeat duels "
                        "at the same tier don't feel identical", phase=4)
    # tier N unlocks after N sections passed (the engine caps depth at #tiers), so a bank
    # far shorter than the course stops scaling — the back half unlocks no new duels.
    sections = (m.get("content", {}) or {}).get("sections")
    nsec = len(sections) if isinstance(sections, list) else 0
    if nsec and len(tiers) < (nsec + 1) // 2:
        warn(rel(path), f"only {len(tiers)} attack tier(s) for a {nsec}-section course — tiers "
                        "should span the course (§4); the later sections unlock no new duels",
             phase=4)


def check_attacks_sync(tome_path, apath):
    """attacks_src.toml is the authored source; generated/attacks.toml is machine-sliced
    from it by tools/gen_attacks.py. A phase that edits one and not the other ships a
    bank that silently disagrees with its source. Titles, starters, and briefs are
    copied verbatim by the generator, so they must match exactly.
    # ponytail: metadata sync only — re-deriving `expect` needs the live server and the
    # tome's toolchain; add a --run deep check if a desync ever slips past this."""
    spath = os.path.join(tome_path, "attacks_src.toml")
    if not os.path.isfile(spath):
        return
    src, e = load_toml(spath)
    if e:
        err(rel(spath), e)
        return
    gen, e = load_toml(apath)
    if e:
        return  # the unreadable generated file is already reported by check_attacks

    def sig(title, starter, briefs):
        return (str(title or "").strip(), str(starter or "").strip(),
                tuple(str(b or "").strip() for b in briefs))

    by_tier = {}
    for ch in src.get("challenge", []) or []:
        if isinstance(ch, dict):
            by_tier.setdefault(ch.get("tier", 0), []).append(
                sig(ch.get("title"), ch.get("starter"), ch.get("briefs") or []))
    ssig = [by_tier[t] for t in sorted(by_tier)]
    gsig = [[sig(c.get("t"), c.get("starter"),
                 [s.get("brief") for s in (c.get("stages") or []) if isinstance(s, dict)])
             for c in (t.get("pool") or []) if isinstance(c, dict)]
            for t in gen.get("tiers", []) if isinstance(t, dict)]
    if ssig == gsig:
        return
    where = f"{len(ssig)} source tier(s) vs {len(gsig)} generated"
    if len(ssig) == len(gsig):
        for ti, (st, gt) in enumerate(zip(ssig, gsig)):
            if st != gt:
                bad = next((ci for ci, pair in enumerate(zip(st, gt)) if pair[0] != pair[1]),
                           min(len(st), len(gt)))
                where = f"tier {ti + 1} challenge {bad + 1}"
                break
    err(rel(apath), "out of sync with attacks_src.toml — someone edited one file without the "
                    f"other (first difference: {where}); regenerate via tools/gen_attacks.py")


def load_intrusion_tiers(tome_path, m):
    """The HEX-DEFENSE bank as (tiers, label, error). Reads intrusions.toml's `tiers`
    key, else inline `[[progression.intrusionTiers]]`. Shared by check_intrusions and
    the economy recompute so bounties are summed from the same source the engine gates on."""
    ipath = os.path.join(tome_path, "intrusions.toml")
    if os.path.isfile(ipath):
        data, e = load_toml(ipath)
        if e:
            return None, rel(ipath), e
        if "tiers" not in data:
            others = [k for k, v in data.items() if isinstance(v, list)] or list(data)
            return None, rel(ipath), ("no [[tiers]] — the engine reads only the 'tiers' key, so "
                f"hex-defense loads as EMPTY and never fires. Found instead: {others}. Use "
                "[[tiers]] with a [[tiers.pool]] of stdout challenges (see §2).")
        return data["tiers"], rel(ipath), None
    tiers = (m.get("progression", {}) or {}).get("intrusionTiers")
    return tiers, rel(os.path.join(tome_path, "tome.toml")), None


def check_intrusions(tome_path, m, label):
    """HEX-DEFENSE bank. The engine gates each tier by `t.min <= sectionsPassed` and picks
    one challenge from `t.pool`, scoring it by exact stdout `expect`. The common AI failure
    is inventing a flat `[[intrusions]]` schema with exercise fields (type/code/answer) and
    a string `min` — which loads as ZERO tiers, silently killing the minigame. None of that
    is caught elsewhere, so it's an ERROR here. Intrusions are optional; when present they
    must be shaped right."""
    tiers, ilabel, e = load_intrusion_tiers(tome_path, m)
    if e:
        err(ilabel, e)
        return
    if tiers is None:
        return  # no intrusion bank at all — optional
    if not isinstance(tiers, list) or not tiers:
        err(ilabel, "intrusions define no tiers")
        return
    # #12: a tier gated at min >= section count can only fire AFTER the course is finished,
    # so its hexes never appear during play. min is 0-based sections-passed; with N sections
    # the last playable gate is N-1 (fires while studying the final section).
    nsec = len((m.get("content", {}) or {}).get("sections") or [])
    for ti, tier in enumerate(tiers):
        if isinstance(tier, dict) and isinstance(tier.get("min"), int) and not isinstance(tier.get("min"), bool):
            if nsec and tier["min"] >= nsec:
                warn(ilabel, f"intrusion tier {ti + 1}: min = {tier['min']} but the course has "
                     f"{nsec} section(s) — this tier only unlocks after the whole course is "
                     f"complete, so its hexes never fire during play (last playable gate is {nsec - 1})",
                     phase=4)
    for ti, tier in enumerate(tiers):
        where = f"intrusion tier {ti + 1}"
        if not isinstance(tier, dict):
            err(ilabel, f"{where}: must be a table")
            continue
        mn = tier.get("min")
        if not isinstance(mn, int) or isinstance(mn, bool):
            err(ilabel, f"{where}: min must be an integer (sections passed before it can "
                        f"fire), got {mn!r} — a string like \"s02\" breaks `t.min <= passed` gating")
        # the engine uses both raw: Date.now() + tier.time * 1000 and addCredits(tier.bounty),
        # so a missing/bad one is a NaN countdown or a NaN purse — a silently dead minigame.
        for key, what in (("time", "seconds to solve"), ("bounty", "coin for shattering it")):
            v = tier.get(key)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
                err(ilabel, f"{where}: {key} must be a positive number ({what}) — the engine "
                            f"consumes it raw, and {v!r} breaks the tier with NaN")
        pool = tier.get("pool")
        if not isinstance(pool, list) or not pool:
            err(ilabel, f"{where}: needs a non-empty [[tiers.pool]] of challenges "
                        "(the flat exercise-style [[intrusions]] shape is not read)")
            continue
        if len(pool) < 5:
            warn(ilabel, f"{where}: only {len(pool)} challenge(s); spec wants 5+ per tier "
                         "so repeat hexes at the same tier don't feel identical", phase=4)
        for pi, ch in enumerate(pool):
            exp = ch.get("expect") if isinstance(ch, dict) else None
            if not (isinstance(exp, str) and exp.strip()):
                err(ilabel, f"{where} challenge {pi + 1}: needs a non-empty expect "
                            "(the exact required stdout)")
