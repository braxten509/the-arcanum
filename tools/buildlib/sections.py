"""Split-mode Phase 3: author each section in its OWN fresh worker, plus the
sections-done resume bookkeeping."""
import json
import os
import shutil
import tomllib

from . import BUILD_DIR, REPO, retries_for
from .continuity import (continuity_prompt, prepare_handoff, reset_handoffs,
                         validate_handoff)
from .liveness import preflight_runners, run_agent
from .measure import validate
from .prompts import build_prompt, read_tooling
from .runners import _implicit_fallback, request_runner
from .agent_runtime import section_runner_command
from .workflow import support_prompt


def section_ids(tid):
    """Ordered section ids from tome.toml [content].sections — the validator's source of truth,
    and (once Phase 2 scaffolds it) the list a split Phase 3 authors one worker at a time."""
    try:
        with open(os.path.join(REPO, "tomes", tid, "tome.toml"), "rb") as f:
            d = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(s) for s in ((d.get("content") or {}).get("sections") or [])]


def wipe_sections(tid):
    """A resume that re-runs Phase 2 or earlier rebuilds the skeleton — sections on disk are
    the OLD run's output (possibly authored against no arc at all). Remove them, plus the
    split-mode resume manifest, so nothing downstream resumes on trash. Returns how many
    section dirs were removed."""
    sec = os.path.join(REPO, "tomes", tid, "sections")
    n = len([d for d in (os.listdir(sec) if os.path.isdir(sec) else [])
             if os.path.isdir(os.path.join(sec, d))])
    if os.path.isdir(sec):
        shutil.rmtree(sec)
    try:
        os.remove(_sections_done_path(tid))
    except OSError:
        pass
    reset_handoffs(tid)
    return n


def _author_section(chain, ri, prompt, sid, num, cfg, overrides,
                    ping, dead, cap, ask_on_death, interactive, tome_id, section_dir,
                    handoff, preflighted):
    """Run ONE section's worker with liveness + death recovery (fallback → human ask → implicit
    default), switching runners as needed. Returns (ri, ok) — ri may have grown as the chain did,
    ok is True only if a runner finished cleanly. Mirrors the main loop's death handling but scoped
    to a single section, so split Phase 3 stays isolated from the normal phase loop."""
    while True:
        name, cmd, im = chain[ri]
        worker_env = os.environ.copy()
        worker_env["ARCANUM_REPO_ROOT"] = REPO
        worker_env["ARCANUM_SECTION_ROOT"] = section_dir
        # Avoid harmless __pycache__ write attempts when a worker executes trusted Python
        # elsewhere in the read-only repository.
        worker_env["PYTHONDONTWRITEBYTECODE"] = "1"
        scoped = section_runner_command(name, cmd, section_dir, REPO,
                                        writable_sidecars=[handoff])
        # A runner selected after a death (human choice or implicit default) was not present
        # during the build's initial census. Never let it start authoring without Phase 0.
        if tuple(cmd) not in preflighted:
            preflight_runners([(name, scoped, im)])
            preflighted.add(tuple(cmd))
        rc = run_agent(scoped, im, prompt, ping, dead, cap,
                       cwd=section_dir, env=worker_env)
        if rc == 0:
            return ri, True
        reason = "hung/timeout" if rc == 124 else f"exit {rc}"
        print(f"  ! section {sid}: runner {name} exited {rc}" + (" (hung/timeout)" if rc == 124 else ""))
        nxt = chain[ri + 1] if ri + 1 < len(chain) else None
        if nxt is None and (ask_on_death or interactive):
            nxt, _ = request_runner(tome_id, num, name, reason, interactive)
            if nxt is not None:
                chain.append(nxt)
        elif nxt is None:
            imp = _implicit_fallback(cfg, overrides, chain[ri])
            if imp and imp[0][1] not in [c[1] for c in chain]:
                chain.append(imp[0])
                nxt = imp[0]
        if nxt is None:
            return ri, False  # out of options — the post-split whole-tome validation catches the gap
        ri += 1
        print(f"  ⇒ continuing section {sid} on {chain[ri][0]}")


# Which sections Phase 3 has finished, persisted so a resume skips them without re-running a
# worker. Recorded per section on a clean exit; the id is the FINAL tome id, since Phase 3 runs
# after the Phase-2 rename. This is the reliable completion signal — file content can't be trusted
# (authored exercises legitimately contain `# TODO:` fill-in markers, so a placeholder sweep gives
# false "stub" hits). Lesson-level continuation inside the one interrupted section is delegated to
# the worker: it reads what's on disk, keeps the finished lessons, and authors the rest.
def _sections_done_path(tid):
    return os.path.join(BUILD_DIR, f"{tid}.sections-done")


def _load_sections_done(tid):
    try:
        with open(_sections_done_path(tid), encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def _mark_section_done(tid, sid):
    done = _load_sections_done(tid)
    done.add(sid)
    try:
        with open(_sections_done_path(tid), "w", encoding="utf-8") as f:
            json.dump(sorted(done), f)
    except OSError:
        pass


def author_sections_split(tid, num, title, chain, refs, cfg, overrides,
                          ping, dead, cap, ask_on_death, interactive, tome_id, resume=False,
                          preflighted=None):
    """Phase 3, split mode: author each section in its OWN fresh worker, so the context (and the
    cache-read tokens that dominated GLM's bill) never accumulate across the whole tome — which
    makes ANY model affordable here. On resume, sections recorded done are skipped and the one that
    was interrupted is finished IN PLACE — its worker keeps the lessons already correct on disk and
    authors only the rest. The workflow's end-of-phase cross-tome reconcile then runs in the caller's
    normal loop. Returns ri after the last section."""
    plan_rel, verdict_rel, findings_rel = refs
    plan_path = os.path.join(REPO, plan_rel)
    worker_body = support_prompt("section-author")
    preflighted = preflighted if preflighted is not None else set()
    ids = section_ids(tid)
    done = _load_sections_done(tid) if resume else set()
    print(f"  · split-sections: {len(ids)} sections, one worker each — {', '.join(ids)}"
          + (f"  (resume: {len(done)} already done)" if resume and done else ""))
    ri = 0
    for i, sid in enumerate(ids):
        handoff = prepare_handoff(tid, sid, reset=not resume)
        handoff_clean, handoff_report = validate_handoff(tid, sid, ids, plan_path)
        if sid in done and handoff_clean:
            print(f"    · section {sid} [{i + 1}/{len(ids)}] already authored — skipping (resume)")
            continue
        if sid in done:
            print(f"    · section {sid} [{i + 1}/{len(ids)}] content is checkpointed, but its "
                  "continuity handoff is missing/invalid — rebuilding the handoff")
        prev = (f"Section {ids[i - 1]} is finished on disk — read it so concepts stay strictly "
                f"cumulative and callbacks reach back into it. Also SEARCH all earlier sections "
                f"for every class, API, capability id, asset, or workflow step this section reuses, "
                f"then read each canonical owner before writing. The immediately previous section "
                f"alone is not enough when an older type returns later. Read the plan's Artifact "
                f"lifecycle too: if this section retires a prompt, fixture, demo call, placeholder, "
                f"or temporary API, teach that exact removal/replacement instead of blindly saying "
                f"to preserve every earlier line." if i else
                "This is the FIRST section — it opens the course.")
        continuity = continuity_prompt(tid, sid, ids, plan_path)
        if resume:  # interrupted (or never-started) section: finish it, keeping what's already correct
            focus = (f"\n\n===== SPLIT RUN — RESUME section {sid} ({i + 1} of {len(ids)}) =====\n"
                     f"A previous run was interrupted mid-build. Open tomes/{tid}/sections/{sid}/ and "
                     f"FINISH section {sid}: KEEP every lesson already fully and correctly authored (do "
                     f"not rewrite, reword, or reorder them — a scaffold-placeholder file counts as NOT "
                     f"authored), and author only what is missing or still a stub — the remaining lessons "
                     f"and their exercises, the section brief, and the freestyle — so the section is "
                     f"complete and coherent. If nothing here has been authored yet, author the whole "
                     f"section. Do NOT create, author, edit, or delete any OTHER section this run. {prev} "
                     f"The [narrative] voice and the Phase 1 arc for this op live in the plan — follow "
                     f"them exactly so {sid} reads as one book with the rest.")
            print(f"    · resuming {sid} [{i + 1}/{len(ids)}] — keep finished lessons, author the rest — on {chain[ri][0]}")
        else:
            focus = (f"\n\n===== SPLIT RUN — author ONLY section {sid} ({i + 1} of {len(ids)}) =====\n"
                     f"Author the COMPLETE section {sid} — its brief, its lessons and their exercises, and "
                     f"its freestyle — into tomes/{tid}/sections/{sid}/. Do NOT create, author, edit, or "
                     f"delete any OTHER section this run. {prev} The [narrative] voice and the Phase 1 arc "
                     f"line for this op live in the plan — follow them exactly so {sid} reads as one book "
                     f"with the rest.")
            print(f"    · authoring {sid} [{i + 1}/{len(ids)}] on {chain[ri][0]}")
        section_dir = os.path.join(REPO, "tomes", tid, "sections", sid)
        os.makedirs(section_dir, exist_ok=True)
        boundary = (f"\n\n===== SECTION WORKER SECURITY BOUNDARY =====\n"
                    f"The repository root is {REPO}. Your process cwd and ONLY writable project "
                    f"directory is {section_dir}; the only other writable path is the exact "
                    f"continuity sidecar {handoff}. You may READ any file under the repository, "
                    "execute trusted Python files from the repository, and use WebSearch/WebFetch "
                    "for current documentation and research. Do not edit the build plan or another "
                    "section. Resolve repo-relative paths against the repository root.")
        p = build_prompt(tid, num, title, worker_body, plan_rel, verdict_rel, findings_rel,
                         validation_flags="--no-run") + focus + continuity + boundary
        attempts = 0
        while True:
            ri, ok = _author_section(chain, ri, p, sid, num, cfg, overrides,
                                     ping, dead, cap, ask_on_death, interactive, tome_id,
                                     section_dir, handoff, preflighted)
            if not ok:
                break
            # This checkpoint is a fast schema/content pass. The whole Phase-3 gate
            # immediately after the split executes every starter and solution once;
            # doing that after each section would re-run the growing tome O(n^2).
            clean, report = validate(tid, tooling=read_tooling(os.path.join(REPO, plan_rel)),
                                     run=False)
            handoff_clean, handoff_report = validate_handoff(tid, sid, ids, plan_path)
            if clean and handoff_clean:
                _mark_section_done(tid, sid)  # a future resume skips only validator-clean work
                break
            attempts += 1
            if attempts > retries_for(chain[ri][0]):
                print(f"    ! section {sid}: worker exited cleanly but validator still fails; "
                      "leaving it uncheckpointed for the whole-tome repair pass")
                break
            print(f"    x section {sid}: validator errors -> re-running its worker "
                  f"(attempt {attempts + 1})")
            p = (build_prompt(tid, num, title, worker_body, plan_rel, verdict_rel, findings_rel,
                              validation_flags="--no-run")
                 + focus
                 + continuity
                 + boundary
                 + "\n\n===== THIS SECTION STILL FAILS VALIDATION =====\n"
                 + "Fix the errors below in this section or its handoff. Do not edit another "
                   "section or an earlier handoff.\n"
                 + "\n".join(part for part in (report, handoff_report) if part))
    return ri
