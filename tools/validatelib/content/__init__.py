"""Section/lesson/exercise checks, the anti-template tells, density floors, and
the content-quality gates."""
import re
from collections import Counter

from .. import err, lang_config, warn
from ..phase2 import check_tooling_contract
from ..phase3 import MIN_BODY_WORDS, MIN_EXERCISES, MIN_LESSONS
from .anti_template import check_anti_template  # noqa: F401  (re-exported)
from .exercises import check_exercise


def is_shouting_title(value):
    """True for a multi-word ALL-CAPS display title, but not a short acronym like JSON."""
    letters = [c for c in str(value) if c.isalpha()]
    return len(letters) > 5 and all(c.isupper() for c in letters)


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
        warn(slabel, "[freestyle] xray is missing — the scrying-lens consumable would reveal nothing",
             phase=3)
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
        essential = row.get("essential")
        if essential is not None and not isinstance(essential, bool):
            err(slabel, "[[freestyle.rubric]] essential must be a boolean")
        minimum = row.get("minimumScore")
        if minimum is not None:
            if essential is not True:
                err(slabel, "[[freestyle.rubric]] minimumScore requires essential = true")
            if (not isinstance(minimum, (int, float)) or isinstance(minimum, bool)
                    or not 0 <= minimum <= 10):
                err(slabel, "[[freestyle.rubric]] minimumScore must be between 0 and 10")
    if round(total, 6) != 100:
        err(slabel, f"[[freestyle.rubric]] weights must sum to exactly 100 (got {total})")
    verification = fs.get("verification")
    if verification is not None:
        if not isinstance(verification, list):
            err(slabel, "[[freestyle.verification]] must be an array of tables")
        else:
            ids = set()
            allowed = {"id", "command", "label", "required", "args", "stdin",
                       "timeout", "expect"}
            for index, row in enumerate(verification):
                where = f"{slabel} [[freestyle.verification]] row {index + 1}"
                if not isinstance(row, dict):
                    err(where, "verification row must be a table")
                    continue
                unknown = set(row) - allowed
                if unknown:
                    err(where, "unknown keys: " + ", ".join(sorted(unknown)))
                vid = str(row.get("id") or row.get("command") or "")
                command = str(row.get("command") or "")
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", vid):
                    err(where, "id must be a stable identifier")
                elif vid in ids:
                    err(where, f"verification id {vid!r} is duplicated")
                ids.add(vid)
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", command):
                    err(where, "command must name a registered runtime assessment command")
                if "required" in row and not isinstance(row["required"], bool):
                    err(where, "required must be boolean")
                if ("args" in row and
                        (not isinstance(row["args"], list)
                         or any(not isinstance(arg, str) for arg in row["args"]))):
                    err(where, "args must be a string array")
                timeout = row.get("timeout")
                if (timeout is not None and
                        (not isinstance(timeout, int) or isinstance(timeout, bool)
                         or not 1 <= timeout <= 300)):
                    err(where, "timeout must be 1 through 300")
                expect = row.get("expect")
                if expect is not None and not isinstance(expect, dict):
                    err(where, "expect must be a table")
                elif isinstance(expect, dict):
                    allowed_expect = {
                        "exitCode", "exact", "raw", "regex", "json", "path",
                        "fileRegex",
                    }
                    unknown_expect = set(expect) - allowed_expect
                    if unknown_expect:
                        err(where, "expect has unknown keys: "
                            + ", ".join(sorted(unknown_expect)))
                    if ("exitCode" in expect
                            and (not isinstance(expect["exitCode"], int)
                                 or isinstance(expect["exitCode"], bool))):
                        err(where, "expect.exitCode must be an integer")
                    for pattern_key in ("regex", "fileRegex"):
                        if pattern_key in expect:
                            try:
                                re.compile(str(expect[pattern_key]))
                            except re.error as exc:
                                err(where, f"expect.{pattern_key} is invalid: {exc}")
                    if "fileRegex" in expect and "path" not in expect:
                        err(where, "expect.fileRegex requires expect.path")


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
             "to the codename, not the title", phase=3)
    check_freestyle(sdata.get("freestyle"), slabel)
    lessons = sdata.get("lessons", [])
    if not isinstance(lessons, list) or not lessons:
        warn(slabel, "section has no [[lessons]]", phase=3)
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
                 "names follow the same Title Case convention as chapter names (acronyms excepted)",
                 phase=3)
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
    wip = any("TODO" in str(les.get("body", ""))
              for sd in sections_data
              for les in (sd.get("lessons") or []) if isinstance(les, dict))
    def report(label, message):
        if wip:
            warn(label, message, phase=3)
        else:
            err(label, message)
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
    # Two sections sharing a rubric verbatim IS the defect; demanding that every one of
    # them match let twelve-of-thirteen through untouched — the same averaging that hid
    # the per-section answer clustering above. Both shipped tomes are wholly distinct,
    # so nothing that was ever correct starts failing here.
    if len(rubric_sigs) >= 2:
        clone, n = Counter(rubric_sigs).most_common(1)[0]
        if n >= 2:
            report(tag, f"{n} of {len(rubric_sigs)} freestyle rubrics are identical — grade "
                   "THAT section's build (§3), not one canned rubric cloned across the tome"
                   + (f"; the repeated criteria are {[c for c, _ in clone][:4]}" if clone else ""))


def check_content(m, sections_data, label, tooling=None, include_manifest=True):
    """Content-quality gates the structural checks miss. These are the floors a
    harness run erodes first, because until now nothing failed for them: prose
    depth, field-notes, narrative line counts, toolchain setup, naming drift.
    Language-neutral proxies only — no keyword matching, so non-English tomes
    aren't penalized. These warnings are owned and hard-gated by Phase 3."""
    runtime = {**lang_config((m.get("runtime") or {}).get("name") or "custom"),
               **(m.get("runtime") or {})}
    registered = set((runtime.get("assessmentCommands") or {}).keys())
    if runtime.get("buildCommand") or "build" in registered:
        registered.add("build")
    if runtime.get("runCommand") or runtime.get("command"):
        registered.add("run")
    for section in sections_data:
        sid = section.get("id") or "?"
        freestyle = section.get("freestyle") or {}
        for row in freestyle.get("verification") or []:
            if not isinstance(row, dict):
                continue
            command = str(row.get("command") or "")
            if command and command not in registered:
                err(label, f"{sid}: Working verification command {command!r} is not registered "
                    "by the named runtime's build/run/assessmentCommands")
    lesson_records = [(sd.get("id") or "?", les) for sd in sections_data
                      for les in (sd.get("lessons") or []) if isinstance(les, dict)]
    lessons = [lesson for _, lesson in lesson_records]
    if lessons:
        # §3: field-notes appendix "strongly recommended on every lesson"; the
        # reference tome carries 52/52. Near-zero coverage is the hollow-content tell.
        fn = sum(1 for les in lessons if "field-notes" in str(les.get("body", "")))
        if fn / len(lessons) < 0.5:
            warn("content", f"only {fn} of {len(lessons)} lessons carry a FIELD NOTES appendix — "
                 "§3 strongly recommends one on every lesson (the deeper-cut channel)", phase=3)
        word_rows = sorted((_visible_words(lesson.get("body")), sid,
                            lesson.get("id") or "?")
                           for sid, lesson in lesson_records)
        words = [row[0] for row in word_rows]
        median = words[len(words) // 2]
        if median < 300:
            below = [row for row in word_rows if row[0] < 300]
            must_raise = max(1, len(below) - len(words) // 2)
            closest = sorted(below, reverse=True)[:12]
            candidates = ", ".join(f"{sid}/{lid}={count}"
                                   for count, sid, lid in closest)
            warn("content", f"median lesson body is {median} visible words — canonical math "
                 f"strips HTML tags, then splits the remaining text on whitespace. {len(below)} "
                 f"of {len(words)} lessons are below 300; raise at least {must_raise} of them "
                 f"to ≥300 to clear this exact prefix (aim for 340–500 meaningful words, not "
                 f"filler, so the next batch has margin). Closest repair candidates: {candidates}",
                 phase=3)

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
                 "check the later/denser sections aren't where coverage thins out", phase=3)

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
                 "a student genuinely must study externally to proceed", phase=3)

    # §5 + the Phase-0 gate's Tooling choice. Kept in its own helper so the Phase-2
    # skeleton mode can enforce it without running Phase-3 prose/density checks.
    if not include_manifest:
        return
    check_tooling_contract(m, sections_data, label, tooling)

    # The harness deterministically renames the folder and meta.id from runtime.project
    # between Phases 2 and 3.  Check the resulting invariant once that rename has occurred.
    rt = m.get("runtime", {}) or {}
    project = str(rt.get("project", "")).strip()
    tome_id = str((m.get("meta", {}) or {}).get("id", ""))
    if project:
        kebab = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", project)
        norm = re.sub(r"[^a-z0-9]+", "-", kebab.lower()).strip("-")
        if norm and norm != tome_id:
            warn("content", f"tome id {tome_id!r} is not the kebab-case of the project name "
                 f"{project!r} (→ {norm!r}) — §6: one name, one spelling, and never the "
                 "requester's phrasing; every derived form (id, caps branding, packages) "
                 "uses the same letters", phase=3)
