"""Structural checks: the file-layout contract, placeholder sweep, badge bank,
and the meta/runtime/narrative/economy/shop tables."""
import glob
import os
import re
import shutil

from . import (CONSUMABLE_IDS, ID_RE, META_REQUIRED, MULTI_CHARGE, PLACEHOLDER_RE,
               REPO, REQUIRED_CONSUMABLES, RUNTIMES_DIR, err, load_toml, rel,
               runtime_resolves, warn)


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
    fixed = {"tome.toml", "themes.toml", "shop.toml", "badges.toml", "intrusions.toml",
             "attacks_src.toml", "attacks.toml", attacks_name,
             "generated/README.md"}  # the tooling's DO-NOT-EDIT marker for generated/

    def legit(p):
        if p in fixed:
            return True
        flat = re.fullmatch(r"sections/([A-Za-z0-9_-]+)\.toml", p)
        if flat:
            return flat.group(1) in sections
        deep = re.fullmatch(r"sections/([A-Za-z0-9_-]+)/(?:(?:section|freestyle)\.toml|lessons/[^/]+\.toml)", p)
        return bool(deep) and deep.group(1) in sections

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


def check_placeholders(toml_files):
    """Scaffolding sweep: a finished tome carries no TODO/FIXME/lorem strings. WARN
    class 'content' so it hard-gates at Phase 7 (--strict) without blocking the
    scaffold phases, which legitimately leave TODOs for later phases to fill."""
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
                    scan(x, f"{at}.{k}" if at else k)
            elif isinstance(v, list):
                for i, x in enumerate(v):
                    scan(x, f"{at}[{i}]")

        scan(data, "")
        if hits:
            warn("content", f"{rel(path)}: {len(hits)} string(s) still carry TODO/FIXME/placeholder "
                            f"text (first at {hits[0]}) — clear every bit of scaffolding before "
                            "calling the tome done")


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
                     "(section badges belong in each section's [freestyle.badge], not the bank)")


def check_meta(m, label):
    meta = m.get("meta")
    if not isinstance(meta, dict):
        err(label, "[meta] table is missing")
        return None
    for key in META_REQUIRED:
        if not str(meta.get(key, "")).strip():
            err(label, f"[meta] {key} is required and must be non-empty")
    description = str(meta.get("description", ""))
    negative_scope = re.compile(
        r"\b(?:does not|doesn't|do not|don't)\s+(?:cover|include|teach)\b|"
        r"\b(?:deliberately\s+)?stops?\s+short\b|"
        r"\b(?:the\s+)?course\s+(?:deliberately\s+)?stops?\s+at\b|"
        r"\bnot\s+(?:covered|included|taught)\b|"
        r"\bscope\s+cuts?\b",
        re.IGNORECASE,
    )
    if negative_scope.search(description):
        warn(label, "[meta] description is public shelf copy: summarize the artifact and "
                    "capabilities positively; keep exclusions in the plan's Graduate ledger")
    return meta


def check_runtime(m, tome_id, label):
    rt = m.get("runtime")
    if not isinstance(rt, dict):
        err(label, "[runtime] table is missing")
        return
    name = rt.get("name") or "custom"  # matches the engine's default (generic.py NAME) when name is omitted
    runtime_name = str(name)
    if not ID_RE.fullmatch(runtime_name):
        err(label, f"[runtime] name {name!r} must match [A-Za-z0-9_-]+")
    runtime_path = os.path.join(RUNTIMES_DIR, runtime_name + ".toml")
    runtime_data = {}
    if not runtime_resolves(runtime_name):
        err(label, f"[runtime] name {name!r} has no global-configs/runtimes/{name}.toml — "
                   "every tome ships on a NAMED runtime file, so the language is reusable "
                   "and reviewable. CREATE that file now (zero code — command, checkCommand, "
                   "diagRegex, starterCode…; read tome-authoring/5-runtimes.md and copy the "
                   "shape of any existing global-configs/runtimes/*.toml), keeping only "
                   "tome-specific tweaks in this table")
    else:
        runtime_data, runtime_error = load_toml(runtime_path)
        if runtime_error:
            err(rel(runtime_path), runtime_error)
            runtime_data = {}
    merged = {**(runtime_data or {}), **rt}

    def source_label(key):
        return label if key in rt else rel(runtime_path)

    # Phase 2 and Phase 8 may author this shared config. Validate the generic runtime's
    # executable schema here, before a malformed value reaches list(), re.compile(), or
    # os.path.join() inside the live engine.
    command_keys = ("command", "runCommand", "buildCommand", "checkCommand",
                    "scaffoldCommand", "packageCommand", "snippetRunCommand",
                    "validationCreateCommand", "validationPackageCommand",
                    "validationProjectPackageCommand")
    for key in command_keys:
        if key not in merged:
            continue
        value = merged[key]
        if (not isinstance(value, list)
                or any(not isinstance(arg, str) or not arg for arg in value)):
            err(source_label(key), f"[runtime] {key} must be an array of non-empty argv strings")
    for key in ("codeExt", "excludeDirs", "diagIgnore", "snippetFragmentIgnore"):
        if key not in merged:
            continue
        value = merged[key]
        if (not isinstance(value, list)
                or any(not isinstance(item, str) or not item for item in value)):
            err(source_label(key), f"[runtime] {key} must be an array of non-empty strings")
    dependencies = merged.get("validationDependencies")
    if dependencies is not None:
        if (not isinstance(dependencies, list)
                or any(not isinstance(item, str) or not item.strip()
                       or item.lstrip().startswith("-")
                       or any(ord(ch) < 32 for ch in item) for item in dependencies)):
            err(source_label("validationDependencies"),
                "[runtime] validationDependencies must be an array of non-empty package strings")
        elif len(set(dependencies)) != len(dependencies):
            err(source_label("validationDependencies"),
                "[runtime] validationDependencies contains duplicate packages")
        elif dependencies and not (merged.get("validationPackageCommand")
                                   or merged.get("validationProjectPackageCommand")
                                   or merged.get("packageCommand")):
            err(label, "[runtime] validationDependencies are declared, but the named runtime "
                       "has no validationPackageCommand or scratch-project packageCommand")
    validation_env = merged.get("validationEnv")
    if (validation_env is not None
            and (not isinstance(validation_env, dict)
                 or any(not isinstance(key, str) or not key
                        or not isinstance(value, str)
                        for key, value in validation_env.items()))):
        err(source_label("validationEnv"),
            "[runtime] validationEnv must be a table of non-empty environment names to strings")
    for key in ("validationPackageCommand", "validationProjectPackageCommand"):
        value = merged.get(key)
        if (isinstance(value, list) and value and not any("{package}" in arg for arg in value)):
            err(source_label(key), f"[runtime] {key} must contain a {{package}} placeholder")
    for key in ("entryFile", "projectFile"):
        value = merged.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            err(source_label(key), f"[runtime] {key} must be a non-empty relative path")
            continue
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            err(source_label(key), f"[runtime] {key} must stay inside the learner project; "
                                   f"got {value!r}")
    regex_keys = ("diagRegex", "snippetEntry", "snippetFragment", "snippetHoist",
                  "snippetFragmentSkip")
    for key in regex_keys:
        value = merged.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            err(source_label(key), f"[runtime] {key} must be a regex string")
            continue
        try:
            re.compile(value, re.M)
        except re.error as exc:
            err(source_label(key), f"[runtime] {key} is not a valid Python regex: {exc}")
    for key in ("diagIgnore", "snippetFragmentIgnore"):
        value = merged.get(key)
        if not isinstance(value, list):
            continue  # the list-shape error above is already specific
        for index, pattern in enumerate(value):
            if not isinstance(pattern, str):
                continue
            try:
                re.compile(pattern, re.M)
            except re.error as exc:
                err(source_label(key), f"[runtime] {key}[{index}] is not a valid Python "
                                       f"regex: {exc}")
    for key in ("buildTimeout", "runTimeout"):
        value = merged.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                                  or value <= 0):
            err(source_label(key), f"[runtime] {key} must be a positive integer number of seconds")

    if not (merged.get("command") or merged.get("runCommand")):
        err(label, f"[runtime] {name!r} sets neither command nor runCommand — nothing can run")
    # The named toolchain must exist on THIS host: a runtime whose binary isn't installed
    # validates green and then every lab run dies in front of the student.
    extra = os.pathsep.join(os.path.expanduser(p) for p in
                            ("~/.local/bin", "~/.cargo/bin", "/usr/local/bin", "/usr/bin"))
    seen = set()
    for key in ("command", "runCommand", "buildCommand", "checkCommand", "scaffoldCommand",
                "validationCreateCommand", "validationPackageCommand",
                "validationProjectPackageCommand"):
        v = merged.get(key)
        exe = v[0] if isinstance(v, list) and v and isinstance(v[0], str) else None
        if not exe or exe in seen or "{" in exe:
            continue
        seen.add(exe)
        if not shutil.which(exe, path=os.environ.get("PATH", "") + os.pathsep + extra):
            err(label, f"[runtime] {key} runs {exe!r} but it is not installed on this host — "
                       "install the toolchain or point the runtime file at one that exists")
    if "workspaceDir" in rt:
        warn(label, "[runtime] workspaceDir is removed — a tome never hardwires the "
                    "project location. Use externalWorkspace = true to REQUIRE external "
                    "mode; the student always chooses the folder")
    xw = rt.get("externalWorkspace")
    if xw is not None and not isinstance(xw, bool):
        err(label, "[runtime] externalWorkspace must be a boolean (true to require external mode)")


def check_narrative(m, label):
    nar = m.get("narrative", {})
    if not isinstance(nar, dict) or not str(nar.get("objective", "")).strip():
        err(label, "[narrative] objective is required and must be non-empty — "
                   "the server refuses to load a tome without it")


def check_economy(m, label):
    econ = m.get("economy", {})
    if not isinstance(econ, dict):
        return
    ranks = econ.get("ranks")
    if ranks is None:
        return
    if not isinstance(ranks, list) or not ranks:
        warn(label, "[economy] ranks should be a non-empty array of [threshold, title] pairs")
        return
    ok = True
    for r in ranks:
        if (not isinstance(r, list) or len(r) != 2
                or not isinstance(r[0], (int, float)) or not isinstance(r[1], str)):
            ok = False
    if not ok:
        warn(label, "[economy] ranks entries should each be [threshold(number), title(string)]")
    elif ranks[0][0] != 0:
        warn(label, "[economy] ranks: the first title should start at threshold 0")


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
            warn(label, "[[shop]] power-up 'x2': drop the charges key — the count is engine-fixed at 20")
        if cid in MULTI_CHARGE:
            ch = it.get("charges")
            if not isinstance(ch, int) or isinstance(ch, bool) or ch < 2:
                warn(label, f"[[shop]] power-up {cid!r}: set charges to 2+ — a one-charge ward barely "
                            "helps (reference tomes run firewall=5, vpn=3)")
        bare = _bare_shop_name(it.get("name"))
        owners = duplicate_names.get((cid, bare))
        if owners:
            others = [tid for tid in owners if tid != current_tid]
            warn(label, f"[[shop]] power-up {cid!r} reuses the name {bare!r} across tomes "
                        f"{owners} — the mechanic repeats, but each course needs its own in-world "
                        f"name. Reflavor it here or in {others}.")
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
            warn(label, f"[[shop]] {iid!r}: kind should be \"consumable\" or \"theme\"")
        if kind == "consumable" and iid not in CONSUMABLE_IDS:
            warn(label, f"[[shop]] consumable {iid!r} is not one of the six engine "
                        "mechanics (firewall/x2/skip/vpn/xray/oracle) — it renders but does nothing")
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
