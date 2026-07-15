"""Content-depth checks: taught-before-used APIs, verbatim + padded prose reuse,
economy totals, the static pre-solved tell, identifier-spelling drift, and
self-answering questions. The --run execution checks live in execute.py."""
import difflib
import re

from . import err, lang_config, norm_lines, warn
from .attacks import load_intrusion_tiers

# An "API-shaped" identifier segment: a camelCase hump (getMinecraft, setAccessible,
# SideOnly) or an underscore (field_110143_a, snake_case). This is the language-neutral
# tell that a token is *code the course teaches*, not an English prose word — plain and
# single-capitalized words (Item, Field, the) are deliberately excluded to keep noise down.
_API_SHAPE = re.compile(r"[a-z][A-Z]|_")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _unescape(s):
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _api_tokens(text):
    """API-shaped identifier segments in a blob of text (dotted names split on '.').
    Excludes anything carrying a ___+ run: the lone ____ fill-blank placeholder is not
    an identifier, and neither is one glued to real letters (val_ptr____)."""
    return {t for t in _IDENT.findall(_unescape(str(text or "")))
            if _API_SHAPE.search(t) and "___" not in t}


def _all_idents(text):
    """Every identifier in a blob (lenient — used as the 'was this mentioned anywhere' set)."""
    return {t for t in _IDENT.findall(_unescape(str(text or ""))) if set(t) != {"_"}}


def _code_span_text(html):
    """Just the <code>/<pre> contents of a lesson body — where taught code vocabulary lives."""
    s = str(html or "")
    chunks = re.findall(r"<code>(.*?)</code>", s, re.S) + re.findall(r"<pre>(.*?)</pre>", s, re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", c) for c in chunks)


def _exercise_api_tokens(ex):
    """API-shaped tokens a single exercise USES (its code/answer surface, not its prose)."""
    if not isinstance(ex, dict):
        return set()
    toks = set()
    toks |= _api_tokens(_code_span_text(ex.get("prompt")))         # API names cited in the prompt's <code>
    for ch in ex.get("choices", []) or []:                          # mc choices are short/code-heavy
        toks |= _api_tokens(ch)
    for k in ("code", "starter", "answer", "expect"):               # fill/type code, write starter, answers
        if ex.get(k):
            toks |= _api_tokens(ex[k])
    for alt in ex.get("accept", []) or []:
        toks |= _api_tokens(alt)
    return toks


# A dotted METHOD CALL: Receiver.member( … ). The trailing '(' is load-bearing — it keeps
# filenames (Program.cs), URLs (nist.gov), and enum/property access (SpecialFolder.Desktop)
# out, leaving actual API invocations. mc CHOICES are never scanned: a distractor is a
# wrong-by-design fake API, so flagging it as 'untaught' is exactly backwards.
_DOTTED_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def check_taught_before_used(sections_data):
    """#7 invented-API detector + #8 interleaving, off one cumulative-vocabulary pass.

    #7 targets the §3 coverage rule ('no exercise may depend on a concept no lesson taught')
    but only where it can be mechanically sure: a `Receiver.member(` call presented in a
    PROMPT's or freestyle brief's <code> — the given/correct surface, never a distractor
    choice — where both the receiver and the member are absent from every lesson body up to
    AND INCLUDING this section. That narrowness is hard-won: camelCase locals, filenames,
    URLs, enum access, and wrong-by-design mc distractors all masquerade as 'untaught APIs',
    so anything looser drowns a known-good tome in false positives. A never-mentioned method
    call in a question's own given code is the one shape that reliably means we quiz an API
    no lesson taught.

    #8 (interleaving): a section from the 3rd on whose exercises share NO API-shaped token
    with any earlier section is only testing its own lessons — the most common AI-author habit
    (§3 'don't only test the concept a lesson just taught')."""
    taught_idents = set()   # every identifier mentioned in any body up to the PREVIOUS section
    first_api = {}          # API-shaped token -> earliest section index mentioning it
    for i, sd in enumerate(sections_data):
        sid = sd.get("id") or f"section {i + 1}"
        lessons = [l for l in (sd.get("lessons") or []) if isinstance(l, dict)]
        body_all = " ".join(re.sub(r"<[^>]+>", " ", str(les.get("body") or "")) for les in lessons)
        body_all += " " + re.sub(r"<[^>]+>", " ", str(sd.get("brief") or ""))
        for tok in _api_tokens(body_all):
            first_api.setdefault(tok, i)
        taught_incl = taught_idents | _all_idents(body_all)  # this section counts as taught too

        # #7: method calls in the given/correct surface (prompt code + freestyle brief code)
        given = []
        used_api = set()
        for les in lessons:
            for ex in les.get("exercises", []) or []:
                if not isinstance(ex, dict):
                    continue
                used_api |= _exercise_api_tokens(ex)
                given.append(_code_span_text(ex.get("prompt")))
        fs = sd.get("freestyle")
        if isinstance(fs, dict):
            freestyle_given = " ".join([_code_span_text(fs.get("brief")),
                                          _code_span_text(fs.get("xray"))] +
                                         [_code_span_text(row.get("desc"))
                                          for row in (fs.get("rubric") or [])
                                          if isinstance(row, dict)])
            given.append(freestyle_given)
            used_api |= _api_tokens(_code_span_text(fs.get("brief")))
        invented = []
        for recv, member in _DOTTED_CALL.findall(_unescape(" ".join(given))):
            if recv not in taught_incl and member not in taught_incl and f"{recv}.{member}" not in invented:
                invented.append(f"{recv}.{member}")
        if invented:
            shown = ", ".join(invented[:5]) + (f" (+{len(invented) - 5} more)" if len(invented) > 5 else "")
            warn("content", f"{sid}: prompt/brief code calls API(s) no lesson mentions: "
                 f"{shown} — §3: use only what a lesson taught. (Teach it, or fix the name.)",
                 phase=3)
        if isinstance(fs, dict):
            untaught_methods = sorted({f"{recv}.{member}"
                                       for recv, member in _DOTTED_CALL.findall(_unescape(freestyle_given))
                                       if member not in taught_incl})
            if untaught_methods:
                shown = ", ".join(untaught_methods[:5]) + (
                    f" (+{len(untaught_methods) - 5} more)" if len(untaught_methods) > 5 else "")
                warn("coverage", f"{sid}: freestyle calls method(s) no lesson body up to this "
                     f"section mentions: {shown} — a capstone may not invent the final API; teach "
                     "the method and its implementation first", phase=3)

        # #8: does this section's API vocabulary reach back to an earlier section?
        if i >= 2 and used_api:
            if not any(first_api.get(t, i) < i for t in used_api):
                sid = sd.get("id") or f"section {i + 1}"
                earlier = sorted(((origin, token) for token, origin in first_api.items()
                                  if origin < i), reverse=True)[:12]
                candidates = ", ".join(
                    f"{token} ({sections_data[origin].get('id') or f'section {origin + 1}'})"
                    for origin, token in earlier) or "none detected in earlier lesson bodies"
                warn("anti-template", f"{sid}: no exercise reaches back to an earlier section's "
                     "material — it only tests its own lessons. §3 wants interleaving: fold an "
                     "earlier concept into a later section. Reuse one recognized underscore/camelCase "
                     "identifier in an exercise code/answer surface; a kebab-case capability slug in "
                     f"prose does not count. Earlier recognized candidates: {candidates}.",
                     phase=3)

        taught_idents = taught_incl


# Code spans inside freestyle text: markdown backticks or HTML <code>. The brief is
# HTML but authors backtick signatures inside it too, so both forms count.
_TICK_OR_CODE = re.compile(r"`([^`]+)`|<code>(.*?)</code>", re.S)


def check_freestyle_scope(m, sections_data):
    """§3b/§3 coverage: a freestyle must be completable from lessons alone — no outside
    content. The mechanical slice: any LANGUAGE keyword/type (the runtime's own [syntax]
    lists, so this is language-neutral) named in a freestyle's code spans (backticks or
    <code> in brief/xray/rubric) must appear somewhere in a lesson up to AND INCLUDING
    that section — body, prompt, code, starter, or solution. Unlike the dotted-call
    check above, the vocabulary is closed (only tokens the runtime declares), so a hit
    reliably means 'the capstone demands a construct nobody taught' and this is an
    ERROR, not a WARN. Student-invented names (parse_severity, SEV) are never in the
    vocabulary and can't false-positive."""
    rt = m.get("runtime", {}) or {}
    syn = {**lang_config(rt.get("name") or "custom"), **rt}.get("syntax") or {}
    vocab = set(syn.get("keywords") or []) | set(syn.get("types") or [])
    if not vocab:
        return
    taught = set()
    for sd in sections_data:
        sid = sd.get("id") or "?"
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            taught |= set(_IDENT.findall(_unescape(str(les.get("body") or ""))))
            for ex in (les.get("exercises") or []):
                if isinstance(ex, dict):
                    for k in ("prompt", "code", "starter", "solution"):
                        taught |= set(_IDENT.findall(_unescape(str(ex.get(k) or ""))))
        fs = sd.get("freestyle")
        if not isinstance(fs, dict):
            continue
        blobs = [fs.get("brief"), fs.get("xray")] + \
                [r.get("desc") for r in (fs.get("rubric") or []) if isinstance(r, dict)]
        spans = " ".join(g1 or g2 for blob in blobs
                         for g1, g2 in _TICK_OR_CODE.findall(_unescape(str(blob or ""))))
        untaught = sorted(t for t in set(_IDENT.findall(spans)) if t in vocab and t not in taught)
        if untaught:
            err("content", f"{sid}: freestyle code names {', '.join(untaught)} but no lesson up "
                f"to {sid} has taught it — a freestyle must be completable from lessons alone "
                "(§3b). Teach it in a lesson body first, or cut it from the brief/xray/rubric.")


def check_verbatim_prose(sections_data):
    """#9: §3 forbids a sentence appearing verbatim in more than one lesson body. Catch it with
    14-word shingles over visible prose — long enough that a collision is a copied sentence,
    not a stock phrase. Exclude <pre> blocks: cumulative courses intentionally repeat canonical
    source while extending it, and code reuse is not copied teaching prose. Skips shingles that
    are mostly UPPER-CASE, which are shared appendix headers (FIELD NOTES // …) by design."""
    W = 14
    seen = {}   # shingle -> first lesson id that had it
    dupes = []  # (lid_a, lid_b, snippet)
    for sd in sections_data:
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            lid = les.get("id") or "?"
            body = str(les.get("body") or "")
            body = re.sub(r"<pre\b[^>]*>.*?</pre\s*>", " ", body, flags=re.I | re.S)
            words = re.sub(r"<[^>]+>", " ", body).split()
            local = set()  # don't flag a shingle repeated within ONE lesson
            for j in range(len(words) - W + 1):
                win = words[j:j + W]
                caps = sum(1 for w in win if w.isupper())
                if caps >= W // 2:      # a header/label run, not teaching prose
                    continue
                sh = " ".join(win).lower()
                if sh in local:
                    continue
                local.add(sh)
                if sh in seen and seen[sh] != lid:
                    dupes.append((seen[sh], lid, " ".join(win)))
                else:
                    seen.setdefault(sh, lid)
    if dupes:
        a, b, snip = dupes[0]
        warn("anti-template", f"{len(dupes)} passage(s) of ≥{W} words repeat verbatim across "
             f"lessons — §3: write every lesson body fresh. First: {a} & {b} both contain "
             f"{snip[:70]!r}…", phase=3)


# Function words: the connective tissue an author does not choose. A synonym-swapper
# rewrites the content words around them and leaves this skeleton untouched.
_GLUE = frozenset(
    "a an the of to in for on with by from as at is are was be been being not no and or but "
    "that this these those it its you your we our they their all any each every when while "
    "if then than so such which who what how why more most much many few less other same "
    "very can will just do does did have has had would should could may might must into "
    "over under out up down off again once here there both only too yours".split())
_PARA_SPLIT = re.compile(r"</p>|</div>")
_WORDS = re.compile(r"[a-z']+")
_MIN_PARA = 60      # words; the floor a padding paragraph must clear to be worth writing
_SIM = 0.78         # skeleton similarity. Five shipped tomes peak at 0.70 cross-lesson;
                    # a synonym-swapped clone of one template runs 0.84-0.86.


def _skeleton(html):
    """A paragraph reduced to its function words, content words blanked. Two paragraphs
    with the same skeleton were built from the same sentence frames."""
    text = re.sub(r"<[^>]+>", " ", html)
    return [w if w in _GLUE else "*" for w in _WORDS.findall(text.lower())]


def check_padded_prose(sections_data):
    """#11: lesson bodies padded from one template. §3 forbids a sentence repeating across
    lessons, and a word floor rewards long bodies — together they invite an author to write
    ONE filler paragraph, run it through a synonym randomizer, and staple a unique-looking
    copy onto every lesson. check_verbatim_prose cannot see it (no two copies share words);
    the density floor rewards it. But the randomizer only swaps content words, so the
    function-word skeleton stays identical — that is what this measures. Prose written
    fresh per lesson never approaches the threshold, even on the same subject."""
    paras = []
    for sd in sections_data:
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            lid = les.get("id") or "?"
            body = re.sub(r"<pre><code>.*?</code></pre>", " ", str(les.get("body") or ""), flags=re.S)
            for chunk in _PARA_SPLIT.split(body):
                sk = _skeleton(chunk)
                # _GLUE is English function words; prose in another language blanks to
                # all-'*' skeletons that would cross-match near 100%. A skeleton must
                # carry real glue to be comparable — below that, skip, don't guess.
                if len(sk) >= _MIN_PARA and sum(1 for w in sk if w != "*") >= 0.2 * len(sk):
                    paras.append((lid, sk))
    flagged, worst = set(), (0.0, None, None)
    for i, (lid_a, sa) in enumerate(paras):
        for lid_b, sb in paras[i + 1:]:
            if lid_a == lid_b:
                continue
            sm = difflib.SequenceMatcher(None, sa, sb)
            if sm.real_quick_ratio() < _SIM or sm.quick_ratio() < _SIM:
                continue
            r = sm.ratio()
            if r >= _SIM:
                flagged.update((lid_a, lid_b))
                if r > worst[0]:
                    worst = (r, lid_a, lid_b)
    if flagged:
        r, a, b = worst
        warn("anti-template", f"{len(flagged)} lesson(s) carry a paragraph built from the same "
             f"sentence frames as another lesson's — filler stamped from one template (the giveaway "
             f"is identical function-word structure under swapped vocabulary). Worst: {a} & {b} at "
             f"{r:.0%} skeleton match. §3: write every lesson body fresh; a 400-word lesson that "
             "teaches beats a 700-word one that pads. Lessons: " + ", ".join(sorted(flagged)[:8])
             + (" …" if len(flagged) > 8 else ""), phase=3)


def check_economy_totals(tome_path, m, sections_data):
    """#10: recompute fixed face-value credit from disk and check the top rank tracks it.

    Fixed face value = Σ exercise points + Σ freestyle rewards. Hex-defense bounties
    are deliberately reported but excluded: the scheduler can award the same tier bounty
    repeatedly, or award none at all, so summing each tier once invents a finite payout the
    runtime does not have. Combos, S ranks, and repeatable hex wins make a top rank modestly
    above fixed face value reachable; a much higher or much lower threshold is the smell.
    """
    econ = m.get("economy", {}) or {}
    ranks = econ.get("ranks")
    if not isinstance(ranks, list) or not ranks:
        return
    ex_pts = sum(ex.get("points", 0) or 0
                 for sd in sections_data
                 for les in (sd.get("lessons") or []) if isinstance(les, dict)
                 for ex in (les.get("exercises") or []) if isinstance(ex, dict))
    fs_reward = sum((sd.get("freestyle") or {}).get("reward", 0) or 0
                    for sd in sections_data if isinstance(sd.get("freestyle"), dict))
    tiers, _, e = load_intrusion_tiers(tome_path, m)
    bounties = []
    if not e and isinstance(tiers, list):
        bounties = [t.get("bounty") for t in tiers if isinstance(t, dict)
                    and isinstance(t.get("bounty"), (int, float))
                    and not isinstance(t.get("bounty"), bool)]
    bounty = sum(bounties)
    base = ex_pts + fs_reward
    if base <= 0:
        return
    try:
        top = max(r[0] for r in ranks if isinstance(r, list) and r and isinstance(r[0], (int, float)))
    except ValueError:
        return
    hex_detail = (f"; repeatable hex-defense bounties pay {min(bounties)}–{max(bounties)} "
                  f"per win (tier schedule sum {bounty}, excluded from the finite base)"
                  if bounty else "; no hex-defense bonus income")
    detail = f"(exercises {ex_pts} + freestyles {fs_reward}{hex_detail})"
    if top > base * 1.15:
        warn("content", f"[economy] top rank threshold {top} exceeds fixed face-value "
             f"earnings {base} by more than 15% {detail} — that title depends too heavily "
             "on combo/S-rank luck or repeatable bonus play; land it near the fixed course "
             "rewards (§2)", phase=5)
    elif top < base * 0.85:
        warn("content", f"[economy] top rank threshold {top} is far below fixed face-value "
             f"earnings {base} by more than 15% "
             f"{detail} — the top title is reached with most of the course still ahead; spread "
             "ranks so the last title lands near the fixed course rewards (§2)", phase=5)




def check_presolved_static(m, sections_data):
    """#4/#6 (always on, no execution): the static tell of a pre-solved / hardcodable write
    lab — the target `expect` string appears verbatim as a literal inside the starter, so the
    student can ship it untouched (or by copying). Catches the common case without needing the
    toolchain; --run catches the computed cases this misses. The quote characters come from
    the runtime's own `stringDelims` (unioned with the common three), not a hardcoded set —
    the same source check_literal_newlines reads."""
    rt = m.get("runtime", {}) or {}
    delims = {**lang_config(rt.get("name") or "custom"), **rt}.get("stringDelims") or []
    quotes = set(delims) | {'"', "'", "`"}
    for sd in sections_data:
        sid = sd.get("id") or "?"
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            for ex in (les.get("exercises") or []):
                if not isinstance(ex, dict) or ex.get("type") != "write":
                    continue
                starter, expect = str(ex.get("starter", "")), ex.get("expect")
                if not starter.strip() or not (isinstance(expect, str) and expect.strip()):
                    continue
                exp_lines = norm_lines(expect)
                # Every expected line appears as a QUOTED STRING LITERAL in the starter — the
                # print-the-answer signature. Quoted-literal (not bare substring) matching is
                # what keeps input data out: expect "stone" won't match `"minecraft:stone"`.
                if exp_lines and all(any(f'{q}{el}{q}' in starter for q in quotes)
                                     for el in exp_lines):
                    warn("anti-template", f"{sid}: write {ex.get('id')!r} looks pre-solved — every "
                         "target output line is a string literal already in the starter, so it can "
                         "ship untouched. Set up the data in the starter and leave the printing to "
                         "the student (§3).", phase=3)


def check_name_drift(sections_data):
    """One name, one spelling (§3): the same identifier drifting between spellings across
    a tome — PushOp in the s08 lessons, Push_Op in that section's freestyle and every
    later section — breaks the cumulative build: the student's saved code stops matching
    what the prompts name. Compare API-shaped tokens case/underscore-insensitively across
    every code surface, but flag only UPPER-INITIAL (type-name) collisions: Push_Op vs
    PushOp is drift, while push_op vs pushOp is as often two legitimate naming domains
    as a defect (verisearch's max_sources is a config-file key, maxSources the C# local
    reading it), and Push_Op (a type) vs push_op (a variable) is idiom in half the
    languages, as is EVENT_BUS (a constant) vs EventBus (its class). Lower-initial and
    cross-convention drift are the accepted ceiling of this check."""
    spellings = {}   # normalized key -> {spelling: [locations, first few]}
    for sd in sections_data:
        sid = sd.get("id") or "?"
        surfaces = []
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            parts = [_code_span_text(les.get("body"))]
            for ex in (les.get("exercises") or []):
                if not isinstance(ex, dict):
                    continue
                parts.append(_code_span_text(ex.get("prompt")))
                parts += [str(ex.get(k) or "")
                          for k in ("code", "starter", "solution", "answer", "expect")]
            surfaces.append((les.get("id") or "?", " ".join(parts)))
        fs = sd.get("freestyle")
        if isinstance(fs, dict):
            surfaces.append((f"{sid} freestyle", _code_span_text(fs.get("brief"))))
        for loc, text in surfaces:
            for tok in _api_tokens(text):
                locs = spellings.setdefault(tok.lower().replace("_", ""), {}).setdefault(tok, [])
                if loc not in locs:
                    locs.append(loc)
    for group in spellings.values():
        names = sorted(s for s in group if s[0].isupper() and not s.isupper())
        if len(names) < 2:
            continue
        shown = "; ".join(
            f"{s!r} ({', '.join(group[s][:3])}{'…' if len(group[s]) > 3 else ''})"
            for s in names)
        warn("content", f"identifier drift — one name, {len(names)} spellings: {shown}. "
             "Pick one spelling and use it in every lesson, starter, solution, and "
             "freestyle (§3); the cumulative build breaks when prompts rename things.", phase=3)


# [^\W\d] = any unicode letter or underscore — a non-English tome's answers
# (Übung, переменная) get the same treatment as ASCII ones.
_WORDISH_ANSWER = re.compile(r"[^\W\d][\w.]*\Z")


def check_self_answering(sections_data):
    """A text/fill exercise whose answer sits verbatim in its own prompt PROSE is a
    giveaway, not a question ('…stored as a byte offset. What is this value called?' —
    answer 'offset'). Only identifier-shaped answers of ≥3 characters are compared, on
    word boundaries, so symbol answers (':=') stay out. Code is never scanned — neither
    the `code` field nor the prompt's own <code> spans — because a trace/lookup question
    ('what does `$_ = "wax"; say;` print?') shows its answer by design. An answer with
    an uppercase letter is matched case-sensitively: the directive FROM leaking is a
    giveaway, the English word 'from' is not."""
    for sd in sections_data:
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            for ex in (les.get("exercises") or []):
                if not isinstance(ex, dict) or ex.get("type") not in ("text", "fill"):
                    continue
                prose = re.sub(r"<code>.*?</code>", " ", str(ex.get("prompt") or ""), flags=re.S)
                prose = re.sub(r"<[^>]+>", " ", _unescape(prose))
                for ans in [ex.get("answer")] + list(ex.get("accept") or []):
                    a = str(ans or "").strip()
                    if len(a) < 3 or not _WORDISH_ANSWER.fullmatch(a):
                        continue
                    if re.search(rf"(?<!\w){re.escape(a)}(?!\w)", prose,
                                 0 if a != a.lower() else re.I):
                        warn("content", f"{les.get('id')}: {ex.get('type')} {ex.get('id')!r}: "
                             f"the answer {a!r} appears verbatim in its own prompt — the "
                             "question answers itself; reword the prompt or ask for something "
                             "it doesn't already say (§3).", phase=3)
                        break
