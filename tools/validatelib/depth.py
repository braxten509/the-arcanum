"""Content-depth checks: taught-before-used APIs, verbatim prose reuse, economy
totals, and the opt-in --run starter execution."""
import os
import re
import subprocess
import tempfile

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
    Excludes all-underscore runs (the ____ fill-blank placeholder is not an identifier)."""
    return {t for t in _IDENT.findall(_unescape(str(text or "")))
            if _API_SHAPE.search(t) and set(t) != {"_"}}


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
            given.append(_code_span_text(fs.get("brief")))
            used_api |= _api_tokens(_code_span_text(fs.get("brief")))
        invented = []
        for recv, member in _DOTTED_CALL.findall(_unescape(" ".join(given))):
            if recv not in taught_incl and member not in taught_incl and f"{recv}.{member}" not in invented:
                invented.append(f"{recv}.{member}")
        if invented:
            sid = sd.get("id") or f"section {i + 1}"
            shown = ", ".join(invented[:5]) + (f" (+{len(invented) - 5} more)" if len(invented) > 5 else "")
            warn("content", f"{sid}: prompt/brief code calls API(s) no lesson mentions: "
                 f"{shown} — §3: use only what a lesson taught. (Teach it, or fix the name.)")

        # #8: does this section's API vocabulary reach back to an earlier section?
        if i >= 2 and used_api:
            if not any(first_api.get(t, i) < i for t in used_api):
                sid = sd.get("id") or f"section {i + 1}"
                warn("anti-template", f"{sid}: no exercise reaches back to an earlier section's "
                     "material — it only tests its own lessons. §3 wants interleaving: fold an "
                     "earlier concept into a later section (a callback mc, a lab reusing prior data).")

        taught_idents = taught_incl


def check_verbatim_prose(sections_data):
    """#9: §3 forbids a sentence appearing verbatim in more than one lesson body. Catch it with
    14-word shingles over visible (tag-stripped) prose — long enough that a collision is a
    copied sentence, not a stock phrase. Skips shingles that are mostly UPPER-CASE, which are
    the shared appendix headers (FIELD NOTES // …, MARGINALIA // …) tomes repeat by design."""
    W = 14
    seen = {}   # shingle -> first lesson id that had it
    dupes = []  # (lid_a, lid_b, snippet)
    for sd in sections_data:
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            lid = les.get("id") or "?"
            words = re.sub(r"<[^>]+>", " ", str(les.get("body") or "")).split()
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
             f"{snip[:70]!r}…")


def check_economy_totals(tome_path, m, sections_data):
    """#10: recompute earnable credit from disk and check the top rank tracks it. §2: 'make
    the top title ≈ total earnable coin'. Base earnable = Σ exercise points + Σ freestyle
    rewards + Σ intrusion bounties (duel coin is a late trickle, excluded per §2). Combos and
    the S multiplier push the real ceiling higher, so the top rank landing a bit UNDER base is
    fine; far under (unreachable ranks) or above (a title no one can earn) is the smell."""
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
    bounty = 0
    if not e and isinstance(tiers, list):
        bounty = sum(t.get("bounty", 0) or 0 for t in tiers if isinstance(t, dict))
    base = ex_pts + fs_reward + bounty
    if base <= 0:
        return
    try:
        top = max(r[0] for r in ranks if isinstance(r, list) and r and isinstance(r[0], (int, float)))
    except ValueError:
        return
    detail = f"(exercises {ex_pts} + freestyles {fs_reward} + bounties {bounty})"
    if top > base * 1.05:
        warn("content", f"[economy] top rank threshold {top} exceeds base earnable {base} "
             f"{detail} — that title is unreachable without heavy combo/S-rank luck; land the "
             "top rank at roughly total earnable (§2)")
    elif top < base * 0.6:
        warn("content", f"[economy] top rank threshold {top} is far below base earnable {base} "
             f"{detail} — the top title is reached with most of the course still ahead; spread "
             "ranks so the last title lands near total earnable (§2)")


def _resolve_run_command(m):
    """The argv that runs ONE file for this tome, plus (entryFile, timeout). Mirrors the
    engine merge: language-TOML defaults ∪ the tome's [runtime], the tome winning."""
    rt = m.get("runtime", {}) or {}
    merged = {**lang_config(rt.get("name") or "custom"), **rt}
    cmd = merged.get("command")
    if not isinstance(cmd, list) or not cmd:
        return None, None, None
    entry = merged.get("entryFile") or "Main.txt"
    timeout = merged.get("runTimeout") or 30
    return cmd, entry, timeout


def _run_one_file(cmd, entry, timeout, source, stdin=None):
    """Run `source` as a single file through the tome's runtime in a temp dir. Returns
    (ok, combined_output) — ok is False on a non-zero exit, timeout, or missing toolchain."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, entry)
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
        argv = [a.replace("{file}", path) for a in cmd]
        if "{file}" not in " ".join(cmd):
            argv = argv + [path]
        try:
            p = subprocess.run(argv, cwd=d, input=stdin, text=True,
                               capture_output=True, timeout=timeout)
        except FileNotFoundError:
            return False, "__NO_TOOLCHAIN__"
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout}s"
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")


def check_starters_run(tome_path, m, sections_data):
    """#4/#5 (opt-in --run): actually execute every write-lab and intrusion starter through
    the tome's own runtime. Two failures neither structure nor static analysis can see:
      • the starter does not COMPILE/RUN as given — a student under the timer repairs logic,
        not a broken scaffold (Phase 8 used to hand-compile these);
      • the starter ALREADY prints the target `expect` — the exercise is pre-solved, so the
        student has nothing to do (this shipped twice in a past build).
    Language-neutral: it uses [runtime].command, so it works for any tome whose toolchain is
    installed. If the toolchain is absent it degrades to a single WARN, never a false ERROR."""
    cmd, entry, timeout = _resolve_run_command(m)
    if not cmd:
        warn("content", "--run: [runtime] resolves no `command` to run a single file — "
             "cannot execute starters (set command in the language TOML or [runtime])")
        return
    labs = []  # (label, id, starter, expect, stdin)
    for sd in sections_data:
        sid = sd.get("id") or "?"
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            for ex in (les.get("exercises") or []):
                if isinstance(ex, dict) and ex.get("type") == "write" and str(ex.get("starter", "")).strip():
                    labs.append((f"{sid}", ex.get("id"), ex["starter"],
                                 ex.get("expect"), ex.get("stdin")))
    tiers, ilabel, e = load_intrusion_tiers(tome_path, m)
    if not e and isinstance(tiers, list):
        for ti, tier in enumerate(tiers):
            for pi, ch in enumerate(tier.get("pool", []) if isinstance(tier, dict) else []):
                if isinstance(ch, dict) and str(ch.get("starter", "")).strip():
                    labs.append((f"intrusion tier {ti + 1} challenge {pi + 1}", None,
                                 ch["starter"], ch.get("expect"), None))
    toolchain_ok = True
    for label, eid, starter, expect, stdin in labs:
        if not toolchain_ok:
            break
        ok, out = _run_one_file(cmd, entry, timeout, starter, stdin)
        name = f"{label}{' ' + repr(eid) if eid else ''}"
        if out == "__NO_TOOLCHAIN__":
            warn("content", f"--run: runtime binary {cmd[0]!r} not installed — skipped "
                 "executing starters (install the toolchain to run this check)")
            toolchain_ok = False
            break
        if not ok:
            err("run", f"{name}: starter does not compile/run as given — a scaffold the student "
                f"can't build on. Runtime said: {out.strip().splitlines()[-1] if out.strip() else '(no output)'}"[:300])
            continue
        # pre-solved: the untouched starter already yields the exact target output
        if expect is not None and str(expect).strip() and norm_lines(out) == norm_lines(expect):
            err("run", f"{name}: starter is PRE-SOLVED — it already prints the exact expect "
                "with no student edits; leave the required logic unwritten (a TODO where the "
                "student codes)")


def check_presolved_static(sections_data):
    """#4/#6 (always on, no execution): the static tell of a pre-solved / hardcodable write
    lab — the target `expect` string appears verbatim as a literal inside the starter, so the
    student can ship it untouched (or by copying). Catches the common case without needing the
    toolchain; --run catches the computed cases this misses."""
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
                if exp_lines and all(any(f'{q}{el}{q}' in starter for q in ('"', "'", "`"))
                                     for el in exp_lines):
                    warn("anti-template", f"{sid}: write {ex.get('id')!r} looks pre-solved — every "
                         "target output line is a string literal already in the starter, so it can "
                         "ship untouched. Set up the data in the starter and leave the printing to "
                         "the student (§3).")
