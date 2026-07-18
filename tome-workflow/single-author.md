# Single-author tome workflow

You are the active author for one harness-assigned unit, routed from the configured Phases 1–2,
Phases 3–7, or Phase 8 model choice. Keep the same context while authoring and repairing that
unit, inspect disk before editing, and never delegate it to another AI. Phase 1 and Phase 2 may
share their planning session. From Phase 3 onward, the harness starts a fresh session after every
validated phase or section. The phase guides hold the creative requirements; this file owns
sequencing, progress, and gates.

Across every phase, preserve learner ownership of the promised artifact. The learner creates or
assembles all canonical project structure, source, configuration, data, tests, maps,
documentation, asset selection and placement, packaging, and delivery files. Seed only a blank
editor file or unavoidable behavior-free tool metadata—never project material.
Lessons teach with disposable examples; each section's learner-visible Working owns the ordinary
cumulative project assignment, and complete project solutions exist only in hidden
`referenceSteps`. Omit lesson `artifactSteps` unless a genuinely necessary intermediate
prerequisite must occur before the Working. Beginner support changes the size and clarity of the
Working, never who writes the real project.

Use the stable build id from your opening prompt for every `report_tome_progress.py` call.
After Phase 2, `author_phase_transition.py` may rename the tome; use the printed
`CURRENT_TOME` for all tome paths and validators thereafter. The plan keeps the stable build id.

For each phase, author exactly one harness-assigned unit per turn. A unit is one complete phase,
except in Phase 3 where each section is its own unit:

1. The harness initializes the unit's `working` or `authoring` marker before resuming you.
2. Read `tome-workflow/phase-N-*.md` and only its named references. Reopen the plan and
   relevant authored files. Preserve valid earlier work.
3. Do the phase completely.
4. Run only the exact self-check listed below for the assigned unit. Read its complete report,
   repair only the assigned unit, and rerun that same command until it exits zero. Do not inspect
   validator implementation to predict hidden checks or substitute hand-written schema, replay,
   word-count, or quality scripts for the named command.
5. For a phase, run `python3 tools/workflow/report_tome_progress.py BUILD_ID N validating`. For a
   Phase-3 section, run `python3 tools/workflow/report_section_progress.py BUILD_ID sNN INDEX TOTAL validating`.
   Then **stop your turn**.
6. The harness independently runs the authoritative gate below. It marks a clean unit complete
   and starts the next unit with its configured author. Phase 1→2 may retain the planning session;
   every later clean boundary is fresh even when it reuses the same provider and model. If the
   gate fails, it resumes the current unit session with the complete
   report; repair only the assigned unit, rerun its exact self-check until clean, mark it
   validating again, and stop again.

Run only the validator command assigned to the current unit. Never run a deterministic
phase-transition command or mark a unit complete yourself. Those actions belong to the harness,
which prevents you from starting later work before the current mechanical gate is clean.
There is no validator-attempt limit: the same unit repair session receives every failed report and may
repair and hand off the unit again until the gate passes or the operator stops the session.

The plan is `.tome-build/BUILD_ID.plan.md`. Substitute `CURRENT_TOME`, `BUILD_ID`, and the
Phase-0 `TOOLING` value literally.

- Phase 1: self-check with `python3 tools/validate_tome.py tomes/BUILD_ID --phase-1-plan .tome-build/BUILD_ID.plan.md`;
  the harness repeats it,
  then the deterministic Phase-1 transition after a clean result.
- Phase 2: fill the deterministic skeleton. The harness gate is
  `python3 tools/validate_tome.py tomes/BUILD_ID --phase-2-skeleton --build-phase 2 --no-run --tooling TOOLING --build-plan .tome-build/BUILD_ID.plan.md`.
  Run that exact command as the self-check; the harness repeats it.
  Also complete `.tome-build/BUILD_ID.course-map.proposal.json`; learner-facing section files
  remain Phase-3 placeholders while the proposal names every stable lesson/Working node,
  capability, dependency, learner-owned artifact, obligation, and typed completion packet.
  After a clean result, the harness validates and seals that map, runs the deterministic
  Phase-2 transition, and retains its
  `CURRENT_TOME` output for every later command.
- Phase 3: author one whole section at a time in Arc order. The harness sets its `authoring`
  marker before resuming you. Self-check with
  `python3 tools/validate_section.py tomes/CURRENT_TOME sNN --plan .tome-build/BUILD_ID.plan.md --tooling TOOLING --source-only`.
  This is the only pre-handoff structural/replay check: do not recreate its checks manually.
  After it exits zero, report `validating` and stop. The harness runs the stricter complete gate
  `python3 tools/validate_section.py tomes/CURRENT_TOME sNN --plan .tome-build/BUILD_ID.plan.md --tooling TOOLING`.
  It reports `complete` only when clean, then starts a fresh Phases 3–7 unit session for the next section.
  After the last section, the harness also runs the full Phase-3 gate before advancing.
  After the complete mechanical gate passes, the configured mandatory Validator AI receives one
  read-only bounded packet containing all sealed lessons plus the Working. It audits first-use
  prerequisite completeness, must cite every sealed node to pass, and returns failures to the
  current section's repair session. With an OpenAI key in Settings or `OPENAI_API_KEY`, a Codex GPT
  validator uses no-tools Responses API Structured Output; without it, the installed
  login CLI is the fallback.
  A bounded, evidence-backed Luna FAIL is authoritative even when optional amendment metadata is
  malformed; the harness returns its readable reasons and discards the unusable proposal. A
  malformed PASS is never accepted. Luna escalates to Terra only after an unusable response or an
  explicit UNCERTAIN result. A proposed missing mechanism must identify the
  nearest sealed owner and a genuinely distinct semantic responsibility; platform or syntax
  spellings of the same operation remain teaching evidence under that existing owner. The packet
  is content-digest cached, so an unchanged clean section is not charged twice.
  Every non-PASS AI call and every failed final section gate is also written as its own timestamped
  JSON record under `validator-failures/BUILD_ID/`; this audit history is Git-ignored, excluded from
  the direct-file-count gate, and is not collapsed into the latest section failure.
  Forge also persists the newest 500 mechanical and AI validator lifecycle lines in
  `.tome-build/BUILD_ID.status-log.jsonl`, so restarting or resuming cannot erase them from the
  chronological tool-history view. Older builds recover AI completions from their call ledger.
  Every Phase-3 assignment ends with one regenerated `HARNESS COURSE CONTROL` block. Preserve
  its full spine and active ledger, write only the current handoff-v3 claim, and never edit its
  sealed map, derived state, receipts, prior handoffs, marks, or checkmarks.
- Phases 4–6: self-check with, and then let the harness repeat,
  `python3 tools/validate_tome.py tomes/CURRENT_TOME --build-phase N --phase-only --no-run --tooling TOOLING --build-plan .tome-build/BUILD_ID.plan.md`.
- Phase 7: generate and executable-verify the offline mastery-lab bank first with
  `python3 tools/gen_mastery_labs.py CURRENT_TOME --build-id BUILD_ID`, then self-check with
  `python3 tools/validate_phase3.py tomes/CURRENT_TOME --plan .tome-build/BUILD_ID.plan.md --tooling TOOLING --strict`,
  then `python3 tools/smoke_tome.py CURRENT_TOME`. The harness repeats generation and both gates;
  all runs must exit 0.
- Phase 8: do the semantic first-time-student review and write the exact
  `.tome-build/BUILD_ID.mastery-semantic-review.json` receipt from
  `tome-authoring/10-mastery-evidence.md`. Self-check with
  `python3 tools/validate_mastery_review.py BUILD_ID CURRENT_TOME`, then the Phase-7 strict and
  smoke commands before marking validating. The harness repeats all three checks. A clean
  validator is necessary but does not replace the complete semantic review.

Phase-focused validators may defer later-phase warnings. Do not edit future-phase banks to
silence deferred counts. Never weaken an earlier proof or remove content merely to make a gate
green. Existing proof-v1 files require exact replacement or an all-active rewrite.

The harness records every author, repair, prerequisite-validator, and optional full-review AI
invocation in `.tome-build/BUILD_ID.ai-costs.jsonl`. That detail ledger retains the 500 rows
nearest to the current time. Lifetime accounting is independent of that retention window:
`.tome-build/BUILD_ID.ai-cost-totals.jsonl` always contains one line for each Phase 1–8 total and
one line for every sealed Phase-3 section total. Each line includes normalized token counts,
API-equivalent dollars, direct Responses API dollars, and an explicit incomplete-pricing marker
if a provider/model has no verified rate.
