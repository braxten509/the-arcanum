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

For each phase, author exactly one harness-assigned unit at a time. A unit is one complete phase,
except in Phase 3 where each section is its own unit and uses two normal author turns: all sealed
lessons in one batch, then the Working/assessment/handoff in one batch:

1. The harness initializes the unit's `working` or `authoring` marker before resuming you.
2. Read `tome-workflow/phase-N-*.md` and only its named references. Reopen the plan and
   relevant authored files. Preserve valid earlier work.
3. Do the phase completely.
4. Run only the exact mechanical commands in the assignment whenever useful and always after the
   unit is complete. Repair their authored findings and rerun without a one-run limit until every
   exact command exits 0. Never run or imitate the Validator AI, a transition, or hand-written
   substitutes.
5. For a phase, run `python3 tools/workflow/report_tome_progress.py BUILD_ID N validating`. For a
   Phase-3 section, run `python3 tools/workflow/report_section_progress.py BUILD_ID sNN INDEX TOTAL validating`.
   Then **stop your turn**.
6. The harness independently reruns the same complete mechanical gate, then starts the Validator AI
   when the unit has one. It marks a fully clean unit complete
   and starts the next unit with its configured author. Phase 1→2 may retain the planning session;
   every later clean boundary is fresh even when it reuses the same provider and model. If the
   gate fails, it resumes the current unit session with the complete
   report; repair all cited findings as one coherent batch, mark it validating again, and stop.

Never run a Validator AI, an unassigned check, a deterministic phase-transition command, or mark a
unit complete yourself. Exact assigned validators, materializers, generators, and smoke commands
are transparent author self-checks and may be rerun until clean; only the harness classifies the
authoritative repeat and advances.
For Phase 1, Phase 2, and every Phase-3 section, the unit assignment embeds the exact binding
semantic-authority block used in the Validator AI prompt. The author and validator may receive
different role, evidence, and output-format instructions, but never different quality, scope,
density, delivery, prerequisite, or repair rules. The Phase-2 and section context renderers also
carry the same generated authority values so dynamic calibration cannot drift.
For a Phase-3 section, the harness pauses before another paid repair after two failed authoritative
gates or once the recorded AI API-equivalent total reaches $2.00 for a Codex author or $4.00 for a
Claude author. An explicit resume authorizes
one more bounded repair; switching the section author starts that repair in a fresh session.

The plan is `.tome-build/BUILD_ID.plan.md`. Substitute `CURRENT_TOME`, `BUILD_ID`, and the
Phase-0 `TOOLING` value literally.

- Phase 1: the author runs the exact Phase-1 mechanical gate until clean and marks the phase
  `validating`. The harness repeats it, then sends the complete plan plus operator calibration to the configured mandatory read-only
  Validator AI. Its bounded, line-cited audit must pass concept alignment, learner calibration,
  scope feasibility, arc sequencing, learner ownership, and proof/delivery coherence before the
  deterministic Phase-1 transition can run. Helpful findings return to the same planning repair
  session; the AI never edits files or expands the requested scope.
- Phase 2: fill the deterministic skeleton. The assignment gives an exact preview materializer plus
  `validate_tome.py` command. Run both until clean. The preview lives inside the writable compact
  source root; it never replaces the protected proposal. After handoff, the harness reruns those
  same commands and only then publishes the deterministic protected proposal.
  Complete only the compact files under `.tome-build/BUILD_ID.course-map-author/`, including
  `audit.json`, plus the bounded Phase-2 research ledger and permitted manifest, skeleton, and
  reusable-runtime fields.
  The harness materializes `.tome-build/BUILD_ID.course-map.proposal.json` from those authored
  sources and the sealed seed; the proposal is generated, read-only evidence. Learner-facing
  section files remain Phase-3 TODO scaffolds while the compact sources name every stable
  lesson/Working node, capability, dependency, learner-owned artifact, obligation, and typed
  completion packet.
  After the mechanical result is clean, the mandatory read-only Validator AI receives the sealed
  Phase-1 plan as authority plus the complete proposal, manifest, and selected runtime profile. It
  audits arc fidelity,
  prerequisite order, pacing, capability coverage, cumulative project continuity, planned Working
  independence, runtime/delivery feasibility, and voice/skeleton coherence. Only an AI PASS lets
  the harness validate and seal that map, run the deterministic Phase-2 transition, and retain its
  `CURRENT_TOME` output for every later command.
  Planning Validator AI calls request ordinary Markdown explanation and evidence, not JSON or a
  response schema. A PASS/FAIL heading and short criterion sections are recommended only;
  no heading, field name, order, punctuation, or citation spelling is required. The harness infers
  ordinary prose when necessary and returns the original Markdown unchanged to the author. A useful
  unlabeled report therefore never buys a formatting retry: an ambiguous substantive report keeps
  the gate closed so the author can read it. The selected Validator AI is never automatically
  replaced by a different model. Any readable response is accepted without a formatting or schema
  retry; ambiguous evidence is an ordinary FAIL and returns to the author with a concrete repair.
  The sole exception is an explicit `# CONTRACT CONFLICT`: when the validator proves that only a
  sealed Phase-1 change could resolve the defect, the harness pauses the same validation gate
  without an author or alternate-model retry.
  Section reviews retain optional structured details for automatic mechanism-ledger
  amendments, but harmless representation drift does not cause another model call. Usable verdicts
  are content-and-model fingerprint cached. A genuinely new evidence fingerprint forces a fresh
  call; returning to any prior failed fingerprint is a durable planning-contract cycle, so the
  harness pauses without another validator or author turn even after a worker restart.
- Phase 3: author one whole section at a time in Arc order. The harness sets its `authoring`
  marker before resuming you. After authoring, run the complete gate
  `python3 tools/validate_section.py tomes/CURRENT_TOME sNN --plan .tome-build/BUILD_ID.plan.md --tooling TOOLING`.
  Repair and rerun it until clean, mark the section `validating`, and stop. The harness repeats that
  command and reports `complete` only when clean, then starts a fresh Phases 3–7 unit session for the next section.
  The final-section assignment also includes the full Phase-3 command; the author runs it after the
  section command, and the harness repeats both before starting the section Validator AI.
  After the complete mechanical gate passes, the configured mandatory Validator AI receives one
  read-only bounded packet containing all sealed lessons plus the Working. It audits teaching
  quality, learner independence, and first-use prerequisite completeness. A PASS must cite every
  sealed node and provide one concrete, in-file line-bounded review for every lesson and the
  Working; helpful quality defects return only their cited repairs to the current section's repair
  session. This same compact call runs at every Start level and stays capped at 2,500 output tokens;
  it does not add a second reviewer pass. Tome authors and reviewers may use only Claude CLI or
  Codex CLI. The validator may also use the distinct Codex API choice, which requires an OpenAI key
  in Settings or `OPENAI_API_KEY` and uses a no-tools, plain-text Responses API call. CLI selections
  always remain CLI selections; there is no implicit billable API fallback. Each section stays on
  the configured Validator AI for every pass and is never escalated to another model.
  The shared readable-verdict policy above governs every section call. A proposed missing mechanism
  must identify the
  nearest sealed owner and a genuinely distinct semantic responsibility; platform or syntax
  spellings of the same operation remain teaching evidence under that existing owner. Once Phase 2
  passes, the harness mechanically expands each untouched section scaffold to the exact sealed
  lesson count, ids, titles, capabilities, mechanisms, validation dependencies, and Working
  contract before Phase 3 begins. The packet
  is content-digest cached, so an unchanged clean section is not charged twice.
  Every non-PASS AI call and every failed final section gate is also written under
  `validator-failures/BUILD_ID/`; Phase-1/2 planning reviews are timestamped Markdown files containing
  the original report, while structured Phase-3 section/final-gate records remain JSON. This audit
  history is Git-ignored, excluded from the direct-file-count gate, and is not collapsed into the
  latest section failure.
  The operating target for the Phase-3 author plus this Validator AI is $1–2 API-equivalent per
  section for Codex authors; Claude authors may use up to $4. Initial author prompts require one bounded context render, one all-lessons batch, and
  one Working/assessment/handoff batch; a
  failed gate returns one compact repair packet without rerendering the initial section context or
  adding a second review pass. Lifetime section totals include both roles.
  Forge also persists the newest 500 mechanical and AI validator lifecycle lines in
  `.tome-build/BUILD_ID.status-log.jsonl`, so restarting or resuming cannot erase them from the
  chronological tool-history view. Older builds recover AI completions from their call ledger.
  Every Phase-3 assignment ends with one regenerated `HARNESS COURSE CONTROL` block. Preserve
  its full spine and active ledger, write only the current handoff-v3 claim, and never edit its
  sealed map, derived state, receipts, prior handoffs, marks, or checkmarks.
- Phases 4–6: the author runs, and after handoff the harness independently repeats,
  `python3 tools/validate_tome.py tomes/CURRENT_TOME --build-phase N --phase-only --no-run --tooling TOOLING --build-plan .tome-build/BUILD_ID.plan.md`.
- Phase 7: the author runs the assigned generation, strict Phase-3, and live-smoke commands until
  clean. After handoff, the harness independently repeats all three.
- Phase 8: do the semantic first-time-student review and write the exact
  `.tome-build/BUILD_ID.mastery-semantic-review.json` receipt from
  `tome-authoring/10-mastery-evidence.md`, then run the assigned mastery-review, strict, and smoke
  commands until clean and mark the phase `validating`. The harness independently repeats them. A clean
  validator is necessary but does not replace the complete semantic review.

Phase-focused validators may defer later-phase warnings. Do not edit future-phase banks to
silence deferred counts. Never weaken an earlier proof or remove content merely to make a gate
green. Existing proof-v1 files require exact replacement or an all-active rewrite.

The harness records every author, repair, planning-validator, prerequisite-validator, and optional
full-review AI
invocation in `.tome-build/BUILD_ID.ai-costs.jsonl`. That detail ledger retains the 500 rows
nearest to the current time. Lifetime accounting is independent of that retention window:
`.tome-build/BUILD_ID.ai-cost-totals.jsonl` always contains one line for each Phase 1–8 total and
one line for every sealed Phase-3 section total. Each line includes normalized token counts,
API-equivalent dollars, direct Responses API dollars, and an explicit incomplete-pricing marker
if a provider/model has no verified rate. At every clean phase boundary, and after every clean
Phase-3 section, the Forge trace prints an **AI API-equivalent cost** when at least one priced
Claude or GPT model participated. Claude cache reads, 5-minute cache writes, fresh input, and output
use the verified Anthropic API-equivalent rate for the selected model; GPT turns use the verified
OpenAI rate. Unknown models or missing usage stay visibly partial. The Phase-3 completion amount is calculated as the sum of the displayed section
amounts, so it must equal those section lines exactly. Totals survive harness resumes and accumulate
model changes; cumulative CLI usage is differenced by provider session before each turn is priced
at the model that actually produced that delta. The optional full-tome reviewer is included in
Phase 8 when it uses a priced Claude or GPT model. An ordinary resume preserves these totals. A destructive
restart from Phase N transactionally removes AI turns, totals, and visible cost-completion events
owned by Phase N and every later phase while preserving earlier-phase totals. Provider cumulative
counter baselines may remain as non-billable internal metadata solely to prevent discarded usage
from reappearing after a same-session resume or model change; restarting from Phase 1 therefore
displays only new post-restart cost.
