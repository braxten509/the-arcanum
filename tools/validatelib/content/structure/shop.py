"""The [[shop]] table: the five required power-ups, cross-tome name reuse, theme items."""
import os
import re

from ... import CONSUMABLE_IDS, MULTI_CHARGE, REPO, REQUIRED_CONSUMABLES, err, load_toml, warn


def _bare_shop_name(value):
    return re.sub(r"\s*\(.*?\)\s*$", "", str(value or "")).strip().upper()


def _duplicate_consumable_names():
    """(mechanic id, normalized display name) -> sorted tome ids using it."""
    owners = {}
    tomes_dir = os.path.join(REPO, "tomes")
    try:
        tids = sorted(os.listdir(tomes_dir))
    except OSError:
        return {}
    for tid in tids:
        manifest, e = load_toml(os.path.join(tomes_dir, tid, "tome.toml"))
        if e or not isinstance(manifest, dict):
            continue
        shop_path = os.path.join(tomes_dir, tid, "shop.toml")
        shop_data, se = load_toml(shop_path) if os.path.isfile(shop_path) else (manifest, None)
        if se or not isinstance(shop_data, dict):
            continue
        for item in shop_data.get("shop", []) or []:
            if not isinstance(item, dict) or item.get("kind") != "consumable":
                continue
            key = (item.get("id"), _bare_shop_name(item.get("name")))
            if key[0] and key[1]:
                owners.setdefault(key, set()).add(tid)
    return {key: sorted(tids) for key, tids in owners.items() if len(tids) > 1}


def check_shop(m, theme_ids, earned_granted, label):
    # every tome stocks the five engine power-ups, each reflavored and filled out — the
    # engine supplies generic defaults so mechanics never break, but a SHIPPED tome must
    # carry its own so nothing ever renders in another course's (or placeholder) voice.
    consumables = {i.get("id"): i for i in m.get("shop", [])
                   if isinstance(i, dict) and i.get("kind") == "consumable"}
    missing = REQUIRED_CONSUMABLES - set(consumables)
    if missing:
        err(label, f"[[shop]] is missing required power-up(s): {sorted(missing)} — every tome stocks "
                   "the five engine consumables (firewall/x2/skip/vpn/xray), each reflavored to its "
                   "world (oracle is an optional 6th)")
    duplicate_names = _duplicate_consumable_names()
    current_tid = str((m.get("meta", {}) or {}).get("id") or "?")
    for cid in sorted(REQUIRED_CONSUMABLES & set(consumables)):
        it = consumables[cid]
        for field in ("name", "desc"):
            if not str(it.get(field, "")).strip():
                err(label, f"[[shop]] power-up {cid!r}: {field} is required — reflavor it to this tome's world")
        if not str(it.get("ico", "")).strip():
            err(label, f"[[shop]] power-up {cid!r}: ico is required — pick an icon id for the shop tile")
        if cid == "x2" and "charges" in it:
            warn(label, "[[shop]] power-up 'x2': drop the charges key — the count is engine-fixed at 20",
                 phase=6)
        if cid in MULTI_CHARGE:
            ch = it.get("charges")
            if not isinstance(ch, int) or isinstance(ch, bool) or ch < 2:
                warn(label, f"[[shop]] power-up {cid!r}: set charges to 2+ — a one-charge ward barely "
                            "helps (reference tomes run firewall=5, vpn=3)", phase=6)
        bare = _bare_shop_name(it.get("name"))
        owners = duplicate_names.get((cid, bare))
        if owners:
            others = [tid for tid in owners if tid != current_tid]
            warn(label, f"[[shop]] power-up {cid!r} reuses the name {bare!r} across tomes "
                        f"{owners} — the mechanic repeats, but each course needs its own in-world "
                        f"name. Reflavor it here or in {others}.", phase=6)
    for item in m.get("shop", []):
        if not isinstance(item, dict):
            err(label, "[[shop]] entries must be tables")
            continue
        iid = item.get("id")
        kind = item.get("kind")
        if not iid:
            err(label, "[[shop]] item is missing id")
        cost = item.get("cost")
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost <= 0:
            err(label, f"[[shop]] {iid!r}: cost must be a positive number — the engine's "
                       "spend() subtracts it raw, and a missing cost corrupts the purse to NaN")
        if kind not in ("consumable", "theme"):
            warn(label, f"[[shop]] {iid!r}: kind should be \"consumable\" or \"theme\"",
                 phase=6)
        if kind == "consumable" and iid not in CONSUMABLE_IDS:
            warn(label, f"[[shop]] consumable {iid!r} is not one of the six engine "
                        "mechanics (firewall/x2/skip/vpn/xray/oracle) — it renders but does nothing",
                 phase=6)
        if kind == "theme":
            ref = item.get("theme")
            if not ref:
                err(label, f"[[shop]] theme item {iid!r} is missing its theme = <[[themes]] id>")
            elif ref not in theme_ids:
                err(label, f"[[shop]] theme item {iid!r} references theme {ref!r}, "
                           "which is not a [[themes]] id in this tome")
            elif earned_granted and ref == earned_granted:
                err(label, f"[[shop]] theme item {iid!r} sells the earned theme "
                           f"{earned_granted!r} — [progression.earnedTheme] is a trophy, "
                           "never merchandise")
