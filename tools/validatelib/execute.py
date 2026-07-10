"""The --run toolchain checks: compile every whole-program lesson snippet (and, where
the language is calibrated for it, every fragment snippet wrapped in a scratch shell),
and build+run every write-lab, intrusion, and spell-duel starter through the tome's own
runtime. Split from depth.py (the static text/economy checks) on the execution seam."""
import html
import os
import re
import subprocess
import tempfile

from . import err, lang_config, load_toml, norm_lines, warn
from .attacks import load_intrusion_tiers


def _resolve_run_command(m):
    """The argv that BUILDS and the argv that RUNS one file for this tome, plus
    (entryFile, timeout). Mirrors the engine merge: language-TOML defaults ∪ the tome's
    [runtime], the tome winning. Either argv may be None when the language omits it."""
    rt = m.get("runtime", {}) or {}
    merged = {**lang_config(rt.get("name") or "custom"), **rt}

    def argv(key):
        v = merged.get(key)
        return v if isinstance(v, list) and v else None

    entry = merged.get("entryFile") or "Main.txt"
    timeout = merged.get("runTimeout") or 30
    return argv("command"), argv("checkCommand"), entry, timeout


_CODE_BLOCK = re.compile(r"<pre><code[^>]*>(.*?)</code></pre>", re.S)
_TAG = re.compile(r"<[^>]+>")


def _snippet_source(block):
    """The code a student reads, with the highlighter's <span>s removed. Strip the tags
    BEFORE decoding entities: a Perl sample writing s{...}{&lt;/h1&gt;} is code, not markup,
    and decoding first would let the tag-stripper eat the very text under test."""
    return html.unescape(_TAG.sub("", block))


def check_snippets(m, sections_data):
    """Build the lesson bodies' own code samples with the tome's toolchain.

    An AI asked for language X writes the idioms of whatever language it knows best, and a
    wrong sample teaches the wrong thing more loudly than a wrong exercise does. Nothing else
    in this validator reads the samples as code — the prose checks only count words.

    A teaching snippet is usually a fragment: it names things an earlier block declared, and
    imports a sibling module that does not exist beside it. So only blocks matching
    [runtime].snippetEntry — the ones claiming to be a whole program — are built, and
    diagnostics matching [runtime].diagIgnore (the artifacts of judging a snippet alone) are
    dropped. What survives is the sample failing on its own terms.

    Language-neutral by construction: checkCommand builds, diagRegex parses its output, and
    the three snippet keys hold every per-language judgment. To light up a new language, set
    snippetEntry and run this against a tome already known good: each surviving diagnostic is
    either a real bug or an artifact to name in diagIgnore. Until snippetEntry is set the
    check cannot judge, and it says so with an advisory WARN rather than passing silently — Java is the
    standing example, its samples trailing loose statements after a class and extending
    supertypes that live outside the file."""
    rt = m.get("runtime", {}) or {}
    merged = {**lang_config(rt.get("name") or "custom"), **rt}
    chk, pat, rx = merged.get("checkCommand"), merged.get("snippetEntry"), merged.get("diagRegex")
    if not (isinstance(chk, list) and chk and pat and rx):
        # Language not calibrated for snippet checking (or it cannot build a lone file).
        # Say so instead of passing silently: a clean run must never read as "the samples
        # build" when they were never compiled. Advisory, not hard-gate — the fix is a
        # language-TOML calibration (§5), not something a tome author can do per-tome.
        nblocks = sum(len(_CODE_BLOCK.findall(str(les.get("body") or "")))
                      for sd in sections_data
                      for les in (sd.get("lessons") or []) if isinstance(les, dict))
        if nblocks:
            need = "checkCommand + snippetEntry + diagRegex"
            warn("advisory", f"{nblocks} lesson code block(s) were never compile-checked — "
                 f"runtime {merged.get('name') or 'custom'!r} is not calibrated for snippet "
                 f"checking (needs {need} in its language TOML; see §5). A clean run does "
                 "not vouch for these samples.")
        return
    try:
        entry_re = re.compile(pat, re.M)
        diag_re = re.compile(rx, re.M)
        ignore = merged.get("diagIgnore") or []
        ignore_re = re.compile("|".join(ignore), re.I) if ignore else None
    except re.error as e:
        warn("run", f"[runtime] snippetEntry/diagRegex/diagIgnore does not compile: {e}")
        return
    # Fragment checking (optional, per-language): a block that is NOT a whole program but
    # matches snippetFragment gets compiled inside the snippetWrap scratch shell, with
    # snippetHoist lines (imports, package headers) lifted above it. diagIgnore already
    # forgives the artifacts of judging code alone (undeclared names, unused locals), so
    # what survives is the fragment failing on its own terms — wrong builtins, wrong
    # syntax, the "Odin that is really Go" class of lie told in a partial sample.
    wrap, frag_re, hoist_re, frag_ignore_re, skip_re = merged.get("snippetWrap"), None, None, None, None
    if wrap and "{code}" in wrap and merged.get("snippetFragment"):
        try:
            frag_re = re.compile(merged["snippetFragment"], re.M)
            hoist_re = re.compile(merged["snippetHoist"], re.M) if merged.get("snippetHoist") else None
            # Excerpt shapes the wrap cannot make whole (a case list whose switch header
            # lives in the prose above) are skipped outright, not error-forgiven.
            skip_re = re.compile(merged["snippetFragmentSkip"], re.M) \
                if merged.get("snippetFragmentSkip") else None
            # Fragments earn extra forgiveness (snippetFragmentIgnore): the cascades a
            # forgiven undeclared name causes downstream — 'invalid type' fields, ambiguous
            # overloads on unknown arguments — plus excerpt shapes (a mid-switch case list)
            # the wrap cannot make whole. Whole programs never get these passes.
            fi = list(ignore) + list(merged.get("snippetFragmentIgnore") or [])
            frag_ignore_re = re.compile("|".join(fi), re.I) if fi else None
        except re.error as e:
            frag_re = None
            warn("run", f"[runtime] snippetFragment/snippetHoist/snippetFragmentIgnore "
                 f"does not compile: {e}")
    if "msg" not in (diag_re.groupindex or {}):
        return  # no message to judge; the file/line groups alone say nothing about validity

    prelude = merged.get("snippetPrelude") or ""
    head = prelude.strip().splitlines()[0] if prelude.strip() else None
    entry, timeout = merged.get("entryFile") or "Main.txt", merged.get("runTimeout") or 30

    for sd in sections_data:
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            for i, block in enumerate(_CODE_BLOCK.findall(str(les.get("body") or ""))):
                src = _snippet_source(block)
                frag = not entry_re.search(src)
                if frag:
                    if not (frag_re and frag_re.search(src)):
                        continue  # neither program nor code fragment (output, transcript, diagram)
                    if skip_re and skip_re.search(src):
                        continue  # an excerpt shape the wrap cannot make judgeable
                    hoisted, body = [], []
                    for ln in src.splitlines():
                        (hoisted if hoist_re and hoist_re.match(ln) else body).append(ln)
                    src = "\n".join(hoisted + [wrap.replace("{code}", "\n".join(body))])
                if head and not re.search(r"^\s*" + re.escape(head), src, re.M):
                    src = prelude + src
                _, out = _run_one_file(chk, entry, timeout, src)
                if out == "__NO_TOOLCHAIN__":
                    warn("run", f"toolchain binary {chk[0]!r} is not installed — lesson code "
                         "samples were never compiled. Install it and re-validate.")
                    return
                bad = [d.group("msg").strip() for d in diag_re.finditer(out)]
                ir = frag_ignore_re if frag else ignore_re
                bad = [x for x in bad if not (ir and ir.search(x))]
                if not bad:
                    continue
                # One finding per sample: a single wrong line cascades into a dozen
                # diagnostics, and the first one names the cause.
                more = f" (+{len(bad) - 1} more)" if len(bad) > 1 else ""
                if frag:
                    # A fragment is deliberately incomplete, so it gets a WARN (still a
                    # hard gate under --strict) rather than a whole-program's ERROR.
                    warn("content", f"{les.get('id')}: code sample #{i + 1} (a fragment, compiled "
                         f"inside the runtime's snippetWrap shell) is rejected by the toolchain: "
                         f"{bad[0]}{more}"[:300])
                else:
                    err("content", f"{les.get('id')}: code sample #{i + 1} does not compile — the lesson "
                        f"teaches it as correct {merged.get('name') or 'code'}. Toolchain said: "
                        f"{bad[0]}{more}"[:300])


def _diag_re(m):
    """The tome runtime's own compiled diagRegex, or None. Every language file ships one —
    the editor draws its squiggles with it — so it is the language-neutral way to pick the
    diagnostic out of a toolchain's output."""
    rt = m.get("runtime", {}) or {}
    pat = {**lang_config(rt.get("name") or "custom"), **rt}.get("diagRegex")
    try:
        return re.compile(pat, re.M) if pat else None
    except re.error:
        return None


def _error_line(out, diag_re=None):
    """The most informative line of a toolchain's output. Prefer the first line the
    runtime's diagRegex recognises — that is the diagnostic, location and all. Fall back to
    a line naming an error (a toolchain whose diagRegex is narrower than its real output),
    then to the first line. A blind tail is useless: compilers print the caret last."""
    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    if diag_re:
        for ln in lines:
            if diag_re.search(ln):
                return ln
    for ln in lines:
        if "error" in ln.lower():
            return ln
    return lines[0] if lines else "(no output)"


def _run_one_file(cmd, entry, timeout, source, stdin=None):
    """Run `source` as a single file through the tome's runtime in a temp dir. Returns
    (ok, combined_output) — ok is False on a non-zero exit, timeout, or missing toolchain."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, entry)
        os.makedirs(os.path.dirname(path), exist_ok=True)
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


def _project_build_result(data, entry):
    """Turn a project runtime's diagnostics payload into the build gate result.

    Compiler warnings are useful editor feedback, but they do not mean the starter is
    unbuildable.  Only error-severity diagnostics fail this shipping check.
    """
    if not data.get("ok"):
        return False, "project scaffold/build diagnostics failed"
    errors = [d for d in (data.get("diags") or [])
              if str(d.get("sev") or "error").lower() == "error"]
    if not errors:
        return True, ""
    first = errors[0]
    return False, (f"{first.get('file', entry)}({first.get('line', '?')},"
                   f"{first.get('col', '?')}): {first.get('msg', 'build failed')}")


def check_starters_run(tome_path, m, sections_data):
    """#4/#5 (on by default; --no-run skips): put every write-lab, intrusion, and
    spell-duel starter through the tome's own toolchain. Two failures neither structure
    nor static analysis can see:
      • the starter does not BUILD as given — a student under the timer repairs logic, not
        a broken scaffold (Phase 8 used to hand-compile these);
      • the starter ALREADY prints the target `expect` — the exercise is pre-solved, so the
        student has nothing to do (this shipped twice in a past build).

    Building and running are judged separately, and only a BUILD failure is an error. A good
    starter is deliberately incomplete, so it may well crash or exit non-zero when run — a
    nasm starter whose exit syscall is the student's job segfaults by design. Treating that
    as a broken scaffold would condemn every correct low-level starter in the library.
    Language-neutral: [runtime].checkCommand builds, [runtime].command runs. A missing
    toolchain degrades to one WARN, never a false ERROR."""
    cmd, chk, entry, timeout = _resolve_run_command(m)
    diag_re = _diag_re(m)
    project_rt = None
    if not cmd and not chk:
        # Project runtimes (notably dotnet) have no one-file argv, but the engine already
        # knows how to scaffold a temporary project and run snippets inside it. Reuse that
        # exact path instead of returning early and silently skipping every solution.
        try:
            from runtimes import for_config as runtime_for_config
            candidate = runtime_for_config(m.get("runtime", {}))
            can_build = bool(candidate.build_cmd or candidate.check_cmd)
            can_run = bool(candidate.snippet_run_cmd or candidate.run_cmd or candidate.cmd)
            if candidate.available() and can_build and can_run:
                project_rt = candidate
        except Exception:
            project_rt = None
    if cmd and not chk:
        # advisory, not "run": some languages simply cannot build a lone file (dotnet),
        # so a tome author has no per-tome fix — hard-gating this would fail them forever.
        warn("advisory", "[runtime] resolves no `checkCommand` — starters are run but never "
             "build-checked, so one that cannot compile will slip through. Add a "
             "checkCommand to the language TOML (see global-configs/runtimes/odin.toml).")
    labs = []  # (label, id, starter, expect, expectRe, stdin, solution)
    unverified = 0  # graded challenges carrying no `solution` — their expect is unproven
    for sd in sections_data:
        sid = sd.get("id") or "?"
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            for ex in (les.get("exercises") or []):
                if not (isinstance(ex, dict) and ex.get("type") == "write"):
                    continue
                sol = str(ex.get("solution", "")).strip()
                if not sol:
                    unverified += 1
                if str(ex.get("starter", "")).strip() or sol:
                    labs.append((f"{sid}", ex.get("id"), ex.get("starter", ""),
                                 ex.get("expect"), ex.get("expectRe"), ex.get("stdin"), sol))
    tiers, ilabel, e = load_intrusion_tiers(tome_path, m)
    if not e and isinstance(tiers, list):
        for ti, tier in enumerate(tiers):
            for pi, ch in enumerate(tier.get("pool", []) if isinstance(tier, dict) else []):
                if not isinstance(ch, dict):
                    continue
                sol = str(ch.get("solution", "")).strip()
                if not sol:
                    unverified += 1
                if str(ch.get("starter", "")).strip() or sol:
                    labs.append((f"intrusion tier {ti + 1} challenge {pi + 1}", None,
                                 ch.get("starter", ""), ch.get("expect"), None, None, sol))
    if unverified:
        # A runnable single-file runtime gives the author everything needed to prove the
        # target. Keep this a hard shipping warning there; only project-only runtimes that
        # cannot execute a reference solution get the advisory exemption.
        label = "run" if (cmd or project_rt) else "advisory"
        warn(label, f"{unverified} write lab(s)/intrusion(s) carry no `solution` — their "
             "expect was never machine-verified as achievable (a wrong expect is an unwinnable "
             "exercise, the one defect no other check can see). Author a `solution` per §3.")
    # SPELL-DUEL starters obey the same contract (§4: the student computes each stage's
    # output from the starter as given), so they get the same sweep: must build, and must
    # not already print stage 1's expect. This replaces brace-counting as the real teeth —
    # the toolchain judges the starter in its own language, no syntax assumptions.
    attacks_name = ((m.get("content", {}) or {}).get("attacks")) or "generated/attacks.toml"
    adata, ae = load_toml(os.path.join(tome_path, str(attacks_name)))
    if adata and not ae:
        for ti, tier in enumerate(adata.get("tiers", []) or []):
            for pi, ch in enumerate(tier.get("pool", []) if isinstance(tier, dict) else []):
                if isinstance(ch, dict) and str(ch.get("starter", "")).strip():
                    stages = [s for s in (ch.get("stages") or []) if isinstance(s, dict)]
                    labs.append((f"attack tier {ti + 1} challenge {pi + 1}", None,
                                 ch["starter"], stages[0].get("expect") if stages else None,
                                 None, None, ""))  # duel expects are verified by gen_attacks.py
    if not cmd and not chk and not project_rt:
        warn("advisory", "[runtime] has neither a one-file command nor a usable project "
             "scaffold/build/run path — starters and solutions could not be exercised")
        return

    project_tmp = tempfile.TemporaryDirectory() if project_rt else None
    project_scratch = project_tmp.name if project_tmp else None

    def run_source(source, stdin_text):
        if cmd:
            return _run_one_file(cmd, entry, timeout, source, stdin_text)
        data = project_rt.run_snippet(project_scratch, source, stdin_text)
        return bool(data.get("ok")), str(data.get("output") or "")

    def build_source(source):
        if chk:
            return _run_one_file(chk, entry, timeout, source)
        return _project_build_result(project_rt.snippet_diagnostics(project_scratch, source),
                                     entry)

    missing = None  # the binary that isn't installed; stops the sweep after one WARN
    try:
        for label, eid, starter, expect, exre, stdin, solution in labs:
            if missing:
                break
            name = f"{label}{' ' + repr(eid) if eid else ''}"

            # `solution` is the author's reference answer: it must run cleanly and its output
            # must be one the grader accepts — the only proof the expect is ACHIEVABLE.
            if solution and (cmd or project_rt):
                ok, out = run_source(solution, stdin)
                if out == "__NO_TOOLCHAIN__":
                    missing = cmd[0]
                    break
                accepted = (expect is not None and str(expect).strip()
                            and norm_lines(out) == norm_lines(expect))
                if not accepted and isinstance(exre, str) and exre.strip():
                    try:
                        accepted = bool(re.search(re.sub(r"\(\?<(?=[A-Za-z])", "(?P<", exre), out, re.M))
                    except re.error:
                        accepted = True
                if not ok:
                    err("run", f"{name}: solution does not run cleanly — "
                        f"{_error_line(out, diag_re)}"[:300])
                elif not accepted:
                    err("run", f"{name}: solution's output does not satisfy expect — the exercise "
                        f"is unwinnable as written; fix expect or the solution. Solution printed: "
                        f"{_error_line(out) if out.strip() else '(no output)'}"[:300])

            if not str(starter).strip():
                continue
            ok, out = build_source(starter)
            if out == "__NO_TOOLCHAIN__":
                missing = (chk or cmd)[0]
                break
            if not ok:
                err("run", f"{name}: starter does not BUILD as given — a scaffold the student "
                    f"can't build on. Toolchain said: {_error_line(out, diag_re)}"[:300])
                continue

            ok, out = run_source(starter, stdin)
            if out == "__NO_TOOLCHAIN__":
                missing = cmd[0]
                break
            if not ok:
                continue
            presolved = (expect is not None and str(expect).strip()
                         and norm_lines(out) == norm_lines(expect))
            if not presolved and isinstance(exre, str) and exre.strip():
                try:
                    presolved = bool(re.search(re.sub(r"\(\?<(?=[A-Za-z])", "(?P<", exre), out, re.M))
                except re.error:
                    pass
            if presolved:
                err("run", f"{name}: starter is PRE-SOLVED — it already prints output the grader "
                    "accepts with no student edits; leave the required logic unwritten (a TODO "
                    "where the student codes)")
    finally:
        if project_tmp:
            project_tmp.cleanup()
    if missing:
        warn("run", f"toolchain binary {missing!r} is not installed — skipped exercising starters. "
             "Install it and re-validate before shipping; this is the only check that sees a "
             "starter that cannot compile.")
