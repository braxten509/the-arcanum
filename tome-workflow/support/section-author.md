# Section author contract

Author each section as one addition to the evolving project.
Read the plan and Arc, `tome.toml`, this section's scaffold, and earlier owners of reused
work. Read `tome-authoring/9-proof-and-assets.md`; consult
`tome-authoring/3-chapters.md` for TOML or pedagogy details.

Before drafting prose, replace placeholder capability ids. Each lesson's `teaches` names
concrete abilities or API contracts in stable kebab-case; the freestyle's cumulative
`requires` lists exactly what its checklist and rubric exercise. Every requirement must
be completely taught by this or an earlier lesson.

Preserve cumulative artifact truth and make it machine-replayable:

- Give every file/type one canonical owner. `write` creates only an absent path. Later edits use
  exact `replace`, or rare `rewrite` with `preserves = "all-active"`; never duplicate ownership.
- At every transition, explicitly remove, replace, isolate, or intentionally ship temporary
  prompts, fixtures, demo mutations, debug output, mock data, and placeholder assets recorded
  in the Arc or earlier handoffs.
- Give lessons visible `artifactSteps`, Workings hidden `referenceSteps`, and sections `[proof]`.
  Run the active-contract report: validation replays from the real scaffold and reruns every
  active proof. Prose proves nothing. Proofs ship by default; `supersedes` requires a genuine
  migration and `protects` covering inherited capabilities.
- Trace the actual program from its first executable step after the freestyle. A learner must
  not need to infer a deletion, insertion point, asset, value, working directory, or API.

Teach before testing. Use complete worked examples before faded `fill` and independent
`write` work when a mechanism is new. Keep starters runnable but unsolved. Make every prompt,
hint, distractor, `whyWrong`, and explanation specific to its exercise and consistent with the
final canonical code. MC distractors must be plausible learner misconceptions and `whyWrong`
must diagnose them. Use recall exercises for domain/tool concepts a one-file lab cannot execute.
Vary lesson and exercise shape; do not stamp a fixed template through the section. The validator
owns numeric floors and schema details and will report them precisely.

Phase-3 validation defers later-phase warnings. Ignore the informational count; never edit
badges, shop, themes, economy, attacks, or other out-of-scope banks to clear it.

Target 340–500 meaningful visible words per lesson, leaving margin above the cumulative 300 median.
The canonical count strips HTML tags then splits on whitespace; never substitute a custom tally or
filler. From the third section onward, make an exercise reuse an earlier code identifier. Mechanical
proof recognizes underscore/camelCase names in code/answer surfaces, not kebab-case capability prose.

For Start 1–3, the prior-knowledge answer is the complete assumption boundary. At the first
required use of every unlisted keyword, syntax form, operator, API, tool action, or technical
term, explain its purpose in plain language, read its parts or steps in order, show a minimal
worked example with an observable result, name one likely failure, and give guided practice
before independent work. A term followed by unexplained sample code, a reading link, or a
capstone demand does not count as an introduction. Start 2 may move through this sequence
faster than Start 1, but it may not omit a fundamental.

For `externalWorkspace`, section 1 teaches install, create/open, navigation, edit/save, run/test,
diagnostics, and recovery; the last teaches delivery and end-to-end verification. Never make media.
For every required asset, add an `[[assets]]` guide covering licensed sourcing, evaluation, and exact
placement. Deterministic proof must work without it. Acceptance may control input, clock, seed, and
frame limit, but must call real behavior—not assign the target state or print a fake win.

Maintain continuity directly in the same author context: record current artifact state, public
contracts, named future obligations, temporary-artifact retirement targets, and evidence for
obligations due here. Verify every claim against files; context is a navigation aid, never proof.

Work in Arc order, repair each section gate before advancing, and reopen disk instead of trusting
memory. Never edit the plan during Phase 3 or spawn another author.
