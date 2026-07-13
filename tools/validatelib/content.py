"""Section/lesson/exercise checks, the anti-template tells, density floors, and
the content-quality gates."""
import re
from collections import Counter

from . import EXERCISE_TYPES, err, lang_config, warn
from .phase2 import check_tooling_contract


def is_shouting_title(value):
    """True for a multi-word ALL-CAPS display title, but not a short acronym like JSON."""
    letters = [c for c in str(value) if c.isalpha()]
    return len(letters) > 5 and all(c.isupper() for c in letters)


def check_exercise(ex, label, seen_ex):
    if not isinstance(ex, dict):
        err(label, "[[lessons.exercises]] entries must be tables")
        return
    eid = ex.get("id")
    if not eid:
        err(label, "an exercise is missing its id")
    elif eid in seen_ex:
        err(label, f"exercise id {eid!r} is duplicated — ids key saved progress and must be unique per tome")
    else:
        seen_ex.add(eid)
    t = ex.get("type")
    if t not in EXERCISE_TYPES:
        err(label, f"exercise {eid!r}: type {t!r} is not one of mc/text/fill/type/write")
        return
    if not str(ex.get("prompt", "")).strip():
        err(label, f"exercise {eid!r}: prompt is required — the client renders it as the "
                   "student's entire instruction for this trial")
    pts = ex.get("points")
    if not isinstance(pts, (int, float)) or isinstance(pts, bool) or pts <= 0:
        err(label, f"exercise {eid!r}: points must be a positive number — the engine pays "
                   "e.points raw, so a missing one credits NaN and corrupts the purse")
    if t == "mc":
        choices = ex.get("choices")
        ans = ex.get("answer")
        if not isinstance(choices, list) or len(choices) < 2:
            err(label, f"mc {eid!r}: choices must be an array with at least two options")
        elif any(not isinstance(choice, str) or not choice.strip() for choice in choices):
            err(label, f"mc {eid!r}: every choice must be a non-empty string")
        elif len({choice.strip().casefold() for choice in choices}) != len(choices):
            err(label, f"mc {eid!r}: choices must be distinct — duplicate options make the "
                       "question ambiguous or reveal the answer")
        if not isinstance(ans, int) or isinstance(ans, bool):
            err(label, f"mc {eid!r}: answer must be a 0-based integer index")
        elif isinstance(choices, list) and not (0 <= ans < len(choices)):
            err(label, f"mc {eid!r}: answer index {ans} is out of range for {len(choices)} choices")
        if not str(ex.get("whyWrong", "")).strip():
            err(label, f"mc {eid!r}: whyWrong is required — every mc must name the misconception "
                       "its wrong answers betray (§3, the highest-value feedback channel)")
    elif t in ("text", "fill"):
        if not str(ex.get("answer", "")).strip():
            err(label, f"{t} {eid!r}: answer is required")
        if t == "fill" and "____" not in str(ex.get("code", "")):
            err(label, f"fill {eid!r}: code must contain the ____ blank the answer fills — "
                       "without it the client renders a fill exercise with nothing to complete")
    elif t == "type":
        if not str(ex.get("code", "")).strip():
            err(label, f"type drill {eid!r}: code (the text to retype) is required")
        reps = ex.get("reps")
        if reps is not None and (not isinstance(reps, int) or isinstance(reps, bool) or reps < 1):
            err(label, f"type drill {eid!r}: reps must be a positive integer when present")
    elif t == "write":
        has_re = bool(str(ex.get("expectRe", "")).strip())
        if has_re:
            # The engine grades with `new RegExp(expectRe, "m")` — an invalid pattern
            # throws at grade time and the lab is unwinnable. Python re is the proxy;
            # JS named groups (?<n>…) are rewritten to Python's (?P<n>…) first so the
            # one syntax that legitimately differs doesn't false-error.
            try:
                re.compile(re.sub(r"\(\?<(?=[A-Za-z])", "(?P<", str(ex["expectRe"])))
            except re.error as rex:
                err(label, f"write {eid!r}: expectRe does not compile ({rex}) — the engine "
                           "builds new RegExp(expectRe, \"m\") at grade time, so this lab is unwinnable")
        if "expect" in ex:
            if not str(ex["expect"]).strip():
                err(label, f"write {eid!r}: expect is empty — unwinnable (empty stdout reads as \"(no output)\")")
        elif not has_re:
            err(label, f"write {eid!r}: needs a non-empty expect or an expectRe")
    if t != "type" and not str(ex.get("hint", "")).strip():
        warn(label, f"exercise {eid!r}: no hint (every exercise should have an exercise-specific one)")


def check_freestyle(fs, slabel):
    if not isinstance(fs, dict):
        err(slabel, "[freestyle] is required in every section and must be a table")
        return
    for key in ("title", "brief"):
        if not str(fs.get(key, "")).strip():
            err(slabel, f"[freestyle] {key} is required")
    rw = fs.get("reward")
    if not isinstance(rw, (int, float)) or isinstance(rw, bool) or rw <= 0:
        err(slabel, "[freestyle] reward must be a positive number — the engine pays "
                    "freestyle.reward raw, so a missing one credits NaN")
    if not str(fs.get("xray", "")).strip():
        warn(slabel, "[freestyle] xray is missing — the scrying-lens consumable would reveal nothing")
    badge = fs.get("badge")
    if isinstance(badge, dict) and not str(badge.get("id", "")).strip():
        err(slabel, "[freestyle.badge] present but missing id")
    rubric = fs.get("rubric")
    if not isinstance(rubric, list) or not rubric:
        err(slabel, "[[freestyle.rubric]] is required — at least one weighted criterion")
        return
    total = 0
    for row in rubric:
        if not isinstance(row, dict):
            err(slabel, "[[freestyle.rubric]] rows must be tables")
            continue
        if not str(row.get("criterion", "")).strip():
            err(slabel, "[[freestyle.rubric]] row is missing criterion")
        w = row.get("weight")
        if not isinstance(w, (int, float)):
            err(slabel, "[[freestyle.rubric]] row is missing a numeric weight")
        else:
            total += w
    if round(total, 6) != 100:
        err(slabel, f"[[freestyle.rubric]] weights must sum to exactly 100 (got {total})")


def check_section(sdata, sid, slabel, seen_ex, seen_les):
    if sdata.get("id") != sid:
        err(slabel, f"top-level id is {sdata.get('id')!r} but the section is listed as {sid!r}")
    for key in ("id", "codename", "title", "build", "brief"):
        if not str(sdata.get(key, "")).strip():
            err(slabel, f"section is missing required key {key!r}")
    # Chapter names are Title Case — one capital per word, acronyms excepted. The
    # mechanical tell is a title whose every letter is a capital (an acronym-length
    # one is allowed: a chapter named "JSON" is fine, "THE FIRST CUT" is not).
    # `codename` is the deliberate all-caps channel; `title` never shouts.
    title = str(sdata.get("title", ""))
    if is_shouting_title(title):
        warn("content", f"{slabel}: section title {title!r} is ALL CAPS — chapter names are "
             "Title Case (one capital per word, acronyms excepted); all-caps styling belongs "
             "to the codename, not the title")
    check_freestyle(sdata.get("freestyle"), slabel)
    lessons = sdata.get("lessons", [])
    if not isinstance(lessons, list) or not lessons:
        warn(slabel, "section has no [[lessons]]")
    for les in lessons:
        if not isinstance(les, dict):
            err(slabel, "[[lessons]] entries must be tables")
            continue
        lid = les.get("id")
        if not lid:
            err(slabel, "a lesson is missing its id")
        elif lid in seen_les:
            err(slabel, f"lesson id {lid!r} is duplicated — lesson ids must be unique per tome")
        else:
            seen_les.add(lid)
        # title/body must sit directly on the [[lessons]] entry — a common breakage is
        # nesting them in a stray [lesson] sub-table or using `desc`, which parses fine
        # but renders a titleless, textless lesson the engine shows blank.
        if not str(les.get("title", "")).strip():
            err(slabel, f"lesson {lid!r}: missing title (must be a key on [[lessons]], not a "
                        "nested [lesson] table)")
        lesson_title = str(les.get("title", ""))
        if is_shouting_title(lesson_title):
            warn("content", f"{slabel}: lesson {lid!r} title {lesson_title!r} is ALL CAPS — lesson "
                 "names follow the same Title Case convention as chapter names (acronyms excepted)")
        if not str(les.get("body", "")).strip():
            hint = " — found `desc`; the engine reads `body`" if str(les.get("desc", "")).strip() else ""
            err(slabel, f"lesson {lid!r}: missing body (the lesson's HTML teaching text){hint}")
        for ex in les.get("exercises", []):
            check_exercise(ex, slabel, seen_ex)
        for rd in les.get("readings", []) or []:
            if not isinstance(rd, dict):
                err(slabel, f"lesson {lid!r}: [[lessons.readings]] entries must be tables")
                continue
            u = str(rd.get("url", "")).strip()
            if not re.match(r"https?://", u):
                err(slabel, f"lesson {lid!r}: reading {str(rd.get('label', '?'))[:40]!r} needs an "
                            f"http(s) url (got {u!r}) — a reading the student cannot open is dead content")


def check_anti_template(sections_data):
    """Tome-wide WARNs for the two §3 anti-template rules structure checks miss:
    the machine-generated grid (every section the same shape) and mc answers
    stuck on one index. WARN, never ERROR — both are judgement calls, but they're
    the failures AI authors ship most, so name them mechanically."""
    mc_answers = []
    shapes = []  # (lesson_count, tuple(exercise_counts)) per section
    lesson_types = []  # sorted type-tuple per lesson — catches "one of each type, every lesson"
    fields = {"hint": [], "prompt": [], "whyWrong": [], "explain": []}  # near-unique per §3
    for sdata in sections_data:
        lessons = sdata.get("lessons", []) or []
        ex_counts = []
        for les in lessons:
            if not isinstance(les, dict):
                continue
            exs = les.get("exercises", []) or []
            ex_counts.append(len(exs))
            lesson_types.append(tuple(sorted(e.get("type") for e in exs if isinstance(e, dict))))
            for ex in exs:
                if not isinstance(ex, dict):
                    continue
                if ex.get("type") == "mc" and isinstance(ex.get("answer"), int):
                    ch = ex.get("choices")
                    mc_answers.append((ex["answer"], len(ch) if isinstance(ch, list) else 0))
                for k, bucket in fields.items():
                    v = ex.get(k)
                    if isinstance(v, str) and v.strip():
                        bucket.append(v.strip())
        shapes.append((len(lessons), tuple(ex_counts)))
    # §3: hints/prompts/whyWrong/explain are exercise-specific — "180 exercises,
    # ~180 distinct hints". One canned string stamped across many exercises is the
    # content-level version of the uniform grid, and the shape checks miss it.
    for k, vals in fields.items():
        if len(vals) < 8:
            continue
        top, n = Counter(vals).most_common(1)[0]
        if n > 3:
            warn("anti-template", f"{k}: one string is reused {n}× of {len(vals)} "
                 f"({len(set(vals))} distinct) — {k} must be exercise-specific (§3), not a "
                 f"canned per-type sentence. Offender: {top[:60]!r}")
    # mc answer spread across 0–3. Catch three flavors, most-specific first: all one
    # index; a 4-choice bank that never lands on some index (the "only 1 & 2" case);
    # any bank clustered on <3 distinct indices.
    idxs = [a for a, _ in mc_answers]
    four = [a for a, n in mc_answers if n >= 4]
    if len(idxs) >= 4 and len(set(idxs)) == 1:
        warn("anti-template", f"all {len(idxs)} mc answers are index {idxs[0]} — spread "
             "correct answers across positions 0–3 (§3); a fixed index is guessable "
             "and reads as machine-authored")
    elif len(four) >= 8 and (set(range(4)) - set(four)):
        miss = sorted(set(range(4)) - set(four))
        warn("anti-template", f"mc answers never land on index {miss} across {len(four)} "
             f"four-choice questions (they cluster on {sorted(set(four))}) — spread correct "
             "answers evenly across 0–3 (§3), don't over-correct to the middle")
    elif len(idxs) >= 8 and len(set(idxs)) < 3:
        warn("anti-template", f"mc answers cluster on only {sorted(set(idxs))} — spread "
             "correct answers across positions 0–3 (§3)")
    # every index used, but not comparably: a bank where one position carries <10%
    # of the answers is still guessable-by-elimination and reads machine-authored
    # (§3 says 0-3 must each be used "a comparable number of times").
    elif len(four) >= 20:
        counts = Counter(four)
        starved = [i for i in range(4) if counts[i] / len(four) < 0.10]
        if starved:
            share = {i: counts[i] for i in range(4)}
            warn("anti-template", f"mc answer index(es) {starved} carry under 10% of {len(four)} "
                 f"four-choice answers (spread: {share}) — rebalance so 0–3 are each used a "
                 "comparable number of times (§3)")
    if len(shapes) >= 3 and len(set(shapes)) == 1:
        lc, ec = shapes[0]
        warn("anti-template", f"every section has the same shape ({lc} lessons, exercise counts "
             f"{list(ec)}) — vary lesson counts (3–8) and exercise counts (4–6) by material (§3); "
             "a uniform grid reads as machine-generated")
    # even when section shapes differ, every lesson carrying the identical type mix
    # (e.g. exactly one of each of mc/text/fill/type/write) is a machine tell the
    # section-level shape check misses.
    if len(lesson_types) >= 4 and len(set(lesson_types)) == 1:
        warn("anti-template", f"all {len(lesson_types)} lessons have the identical exercise-type "
             f"mix {list(lesson_types[0])} — vary the mix and order per lesson (§3), not one of "
             "each type every time")


def _visible_words(html):
    """Word count of a lesson body as a reader sees it — HTML tags stripped. §3 wants
    300–600 words; the shipped reference (verisearch) runs 205–390. The floor below
    sits under that range so only genuinely thin prose trips it."""
    return len(re.sub(r"<[^>]+>", " ", str(html or "")).split())


def _code_string_re(delims):
    """Matches one string literal written in the code sample's own language, so a \\n
    inside it can be recognised as real source. The delimiters come from the runtime's
    `stringDelims`; most languages quote with " and ', but nasm also takes a backtick
    (and only a backtick string interprets \\n), which is why this is not hardcoded."""
    alts = []
    for d in delims:
        e = re.escape(d)
        alts.append(rf"{e}(?:\\.|[^{e}\\])*{e}")
    return re.compile("|".join(alts))


def check_literal_newlines(m, sections_data):
    """A TOML literal string ('…') does NOT interpret \\n. Author a multi-line code
    sample as code = 'a\\nb' instead of code = '''…''' and the escape survives verbatim:
    the student is shown one long line with \\n punched through it, and a `type` drill
    asks them to retype that. It parses, so every structural check passes — but the
    exercise is corrupt. Flag any code/starter whose \\n sits OUTSIDE a string literal
    (i.e. was meant as a line break) while the value carries no real newline at all."""
    rt = m.get("runtime", {}) or {}
    delims = {**lang_config(rt.get("name") or "custom"), **rt}.get("stringDelims") or ['"', "'"]
    code_string = _code_string_re(delims)
    for sd in sections_data:
        sid = sd.get("id") or "?"
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            for ex in (les.get("exercises") or []):
                if not isinstance(ex, dict):
                    continue
                for field, level in (("code", err), ("starter", err),
                                     ("expect", warn), ("stdin", warn)):
                    v = ex.get(field)
                    if not isinstance(v, str) or "\n" in v or "\\n" not in v:
                        continue
                    if "\\n" not in code_string.sub('""', v):
                        continue  # every \n is inside a string literal — real source
                    level("content", f"{sid}: {ex.get('id')!r} {field} contains a literal \\n and no "
                          "real line break — a TOML '…' literal does not expand escapes. Use a "
                          "'''…''' block so the sample renders as multiple lines.")


def check_density(sections_data):
    """Anti-hollowness floors. A stub course — 1-exercise lessons, two-sentence bodies,
    one rubric cloned across every section — parses clean but teaches nothing; that is
    the failure a validator was assumed unable to catch, but thinness is mechanical.
    The floors sit far below a real tome (verisearch runs 4-6 lessons/section, 4+
    exercises and 205+ word bodies per lesson, every rubric distinct), so only a
    genuinely thin tome trips them. While the tome still carries TODO scaffolding these
    are WARNs (work in progress); once the TODOs are gone — the author calls it done —
    they become ERRORs. Simulated-but-dense labs and handed-over addresses are NOT
    caught here (that stays a judgement call for the Phase 8 student review)."""
    MIN_LESSONS, MIN_EXERCISES, MIN_BODY_WORDS = 3, 4, 180  # §3: 3-8 lessons, 4-6 exercises, 300-600 words
    wip = any("TODO" in str(les.get("body", ""))
              for sd in sections_data
              for les in (sd.get("lessons") or []) if isinstance(les, dict))
    report = warn if wip else err
    tag = "density (WIP → ERROR once TODOs cleared)" if wip else "density"
    rubric_sigs = []
    for sd in sections_data:
        sid = sd.get("id") or "?"
        lessons = [l for l in (sd.get("lessons") or []) if isinstance(l, dict)]
        if len(lessons) < MIN_LESSONS:
            report(tag, f"{sid}: only {len(lessons)} lesson(s) — need ≥{MIN_LESSONS} "
                   f"(§3: vary 3-8 by material); a thin section is the hollow-tome tell")
        for les in lessons:
            lid = les.get("id") or "?"
            nex = len([e for e in (les.get("exercises") or []) if isinstance(e, dict)])
            if nex < MIN_EXERCISES:
                report(tag, f"{sid}: lesson {lid!r} has {nex} exercise(s) — need ≥"
                       f"{MIN_EXERCISES} (§3: vary 4-6); too few is the hollow-tome tell")
            n = _visible_words(les.get("body"))
            if n < MIN_BODY_WORDS:
                report(tag, f"{sid}: lesson {lid!r} body is {n} visible words — under "
                       f"{MIN_BODY_WORDS} is a stub, not a taught lesson (§3 wants 300–600)")
        fs = sd.get("freestyle")
        if isinstance(fs, dict) and isinstance(fs.get("rubric"), list):
            rubric_sigs.append(tuple((r.get("criterion"), str(r.get("desc", "")).strip())
                                     for r in fs["rubric"] if isinstance(r, dict)))
    if len(rubric_sigs) >= 3 and len(set(rubric_sigs)) == 1:
        report(tag, f"all {len(rubric_sigs)} freestyle rubrics are identical — grade THAT "
               "section's build (§3), not one canned rubric cloned across the tome")


def check_content(m, sections_data, label, tooling=None):
    """Content-quality gates the structural checks miss. These are the floors a
    harness run erodes first, because until now nothing failed for them: prose
    depth, field-notes, narrative line counts, toolchain setup, naming drift.
    Language-neutral proxies only — no keyword matching, so non-English tomes
    aren't penalized. WARNs here are hard gates per tome-workflow phase 7."""
    nar = m.get("narrative", {}) or {}
    nboot = len(nar.get("bootLines", []) or [])
    ngrade = len(nar.get("gradingLines", []) or [])
    if not 8 <= nboot <= 12:
        warn("content", f"[narrative] bootLines has {nboot} line(s) — spec wants 8–12 "
             "(establish the fiction, the mentor, and the commission)")
    if not 6 <= ngrade <= 8:
        warn("content", f"[narrative] gradingLines has {ngrade} line(s) — spec wants 6–8 in-character lines")
    if not str(nar.get("completeText", "")).strip():
        warn("content", "[narrative] completeText is missing — the course-complete screen falls "
             "back to generic engine text instead of this tome's voice at its biggest moment")

    lessons = [les for sd in sections_data
               for les in (sd.get("lessons") or []) if isinstance(les, dict)]
    if lessons:
        # §3: field-notes appendix "strongly recommended on every lesson"; the
        # reference tome carries 52/52. Near-zero coverage is the hollow-content tell.
        fn = sum(1 for les in lessons if "field-notes" in str(les.get("body", "")))
        if fn / len(lessons) < 0.5:
            warn("content", f"only {fn} of {len(lessons)} lessons carry a FIELD NOTES appendix — "
                 "§3 strongly recommends one on every lesson (the deeper-cut channel)")
        words = sorted(_visible_words(les.get("body")) for les in lessons)
        median = words[len(words) // 2]
        if median < 300:
            warn("content", f"median lesson body is {median} words — §3 wants 300–600 per "
                 "lesson; the per-lesson floor only catches stubs, this catches systematic thinness")

        # Readings are otherwise optional (quality/count is a judgement call), but a
        # lesson with ZERO is a student left with no anchor doc — this tends to
        # collapse in the later, denser chapters, exactly where it's needed most.
        no_reading = [les.get("id", "?") for les in lessons
                      if not any(str(r.get("url", "")).strip()
                                 for r in (les.get("readings") or []) if isinstance(r, dict))]
        if no_reading:
            warn("content", f"{len(no_reading)} of {len(lessons)} lesson(s) have zero "
                 f"[[lessons.readings]]: {no_reading[:12]}{'…' if len(no_reading) > 12 else ''} "
                 "— every lesson should link at least one reading, even if just one; "
                 "check the later/denser sections aren't where coverage thins out")

        # essential = true means "the course itself cannot fully teach this concept" —
        # rare by definition. A high ratio is quota-filling (a past Binder run flagged
        # one per lesson to give every lesson an essential reading), not curation.
        ess = sum(1 for les in lessons
                  if any(r.get("essential") is True
                         for r in (les.get("readings") or []) if isinstance(r, dict)))
        if ess > 2 and ess / len(lessons) > 0.15:
            warn("anti-template", f"{ess} of {len(lessons)} lessons flag an essential reading — "
                 "essential means the course itself cannot fully teach that concept, so it is "
                 "rare; flagging one per lesson is quota-filling. Unflag all but the few readings "
                 "a student genuinely must study externally to proceed")

    # §5 + the Phase-0 gate's Tooling choice. Kept in its own helper so the Phase-2
    # skeleton mode can enforce it without running Phase-3 prose/density checks.
    check_tooling_contract(m, sections_data, label, tooling)
    rt = m.get("runtime", {}) or {}
    if rt.get("externalWorkspace") is True and not str(rt.get("projectFile", "")).strip():
        warn("content", "[runtime] externalWorkspace = true but no projectFile — the workbench's "
             "required-files panel falls back to the language default (e.g. a lone Main.java), "
             "misdescribing the real project; name its true build file (e.g. \"build.gradle\")")

    # §6 step 1, "one name, one spelling": the machine id is the kebab-case of the
    # project name — a word boundary (camelCase or a space) becomes a hyphen, so
    # ManaWeaver → mana-weaver. (meta.name is the tome-card title and may legitimately
    # differ — verisearch's card reads "The Liber Veritatis" — runtime.project anchors.)
    project = str(rt.get("project", "")).strip()
    tome_id = str((m.get("meta", {}) or {}).get("id", ""))
    if project:
        kebab = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", project)
        norm = re.sub(r"[^a-z0-9]+", "-", kebab.lower()).strip("-")
        if norm and norm != tome_id:
            warn("content", f"tome id {tome_id!r} is not the kebab-case of the project name "
                 f"{project!r} (→ {norm!r}) — §6: one name, one spelling, and never the "
                 "requester's phrasing; every derived form (id, caps branding, packages) "
                 "uses the same letters")
