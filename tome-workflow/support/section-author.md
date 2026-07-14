# Section author contract

Author each section as one addition to the evolving project.
Read the plan and Arc, `tome.toml` runtime/narrative, this section's scaffold, and earlier
files that own anything reused. Read
`tome-authoring/9-proof-and-assets.md`; consult `tome-authoring/3-chapters.md` when you need
the remaining TOML field or pedagogy details.

Before drafting prose, replace placeholder capability ids. Each lesson's `teaches` names
concrete abilities or API contracts in stable kebab-case; the freestyle's cumulative
`requires` lists exactly what its checklist and rubric exercise. A matching id is not
enough: every requirement must be completely taught in this or an earlier lesson.

Preserve cumulative artifact truth and make it machine-replayable:

- Give every file/type one canonical owner. `write` creates only an absent path. Later edits use
  exact `replace`, or rare `rewrite` with `preserves = "all-active"`; never duplicate ownership.
- At every transition, explicitly remove, replace, isolate, or intentionally ship temporary
  prompts, fixtures, demo mutations, debug output, mock data, and placeholder assets recorded
  in the Arc or earlier handoffs.
- Give lessons visible `artifactSteps`, Workings hidden `referenceSteps`, and sections `[proof]`.
  Run the active-contract report: the harness replays from the real scaffold and reruns every
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

For Start 1–3, the prior-knowledge answer is the complete assumption boundary. At the first
required use of every unlisted keyword, syntax form, operator, API, tool action, or technical
term, explain its purpose in plain language, read its parts or steps in order, show a minimal
worked example with an observable result, name one likely failure, and give guided practice
before independent work. A term followed by unexplained sample code, a reading link, or a
capstone demand does not count as an introduction. Start 2 may move through this sequence
faster than Start 1, but it may not omit a fundamental.

For `externalWorkspace`, section 1 must genuinely teach install, create/open, navigation,
edit/save, run/test, diagnostics, and first recovery; the last section must teach delivery and
end-to-end verification. Never make media assets. For each required sprite, sound, music track,
image, font, animation, or video, add an `[[assets]]` guide that teaches the human where to find
a licensed asset, how to evaluate it, and exactly where to place it. The deterministic proof
path must work without those human-supplied files.
Acceptance may control input, clock, seed, and frame limit, but must call real behavior—not assign
the target state or print a fake win.

Finish every exact continuity handoff supplied by the harness. Record current artifact state,
public contracts, named future obligations, temporary-artifact retirement targets, and evidence
for obligations due here. Open every cited file: the handoff is a navigation map, never proof.

Produce only the Phase-3 scope assigned by the harness: either the complete Arc in one warm
worker or one bounded section batch. Work in Arc order, run and repair each section's
warm-context gate before moving forward, and reopen the preceding section's files rather than
relying on memory alone. In complete-Arc mode, also run every supplied periodic quality window;
in batch mode, do not edit a section outside the assigned batch. Never edit the shared plan or
spawn subagents; the harness owns process boundaries.
