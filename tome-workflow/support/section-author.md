# Section author contract

Author the assigned section as one coherent addition to the single evolving project.
Read the plan's gate answers and Arc, `tome.toml` runtime/narrative, this section's
scaffold, and the earlier files that own anything this section reuses. Consult
`tome-authoring/3-chapters.md` only when you need exact TOML field or pedagogy details.

Before drafting prose, replace placeholder capability ids. Each lesson's `teaches` names
concrete abilities or API contracts in stable kebab-case; the freestyle's cumulative
`requires` lists exactly what its checklist and rubric exercise. A matching id is not
enough: every requirement must be completely taught in this or an earlier lesson.

Preserve cumulative artifact truth:

- Give every file/type one canonical owner. A later change is either a complete replacement
  retaining all required imports, members, behavior, and wiring, or an explicitly located
  member-only patch that says where it goes and not to create a duplicate file/type.
- At every transition, explicitly remove, replace, isolate, or intentionally ship temporary
  prompts, fixtures, demo mutations, debug output, mock data, and placeholder assets recorded
  in the Arc or earlier handoffs.
- Trace the actual program from its first executable step after the freestyle. A learner must
  not need to infer a deletion, insertion point, asset, value, working directory, or API.

Teach before testing. Use complete worked examples before faded `fill` and independent
`write` work when a mechanism is new. Keep starters runnable but unsolved. Make every prompt,
hint, distractor, `whyWrong`, and explanation specific to its exercise and consistent with the
final canonical code. MC distractors must be plausible learner misconceptions and `whyWrong`
must diagnose them. Use recall exercises for domain/tool concepts a one-file lab cannot execute.
Vary lesson and exercise shape; do not stamp a fixed template through the section. The validator
owns numeric floors and schema details and will report them precisely.

For `externalWorkspace`, section 1 must genuinely teach install, create/open, navigation,
edit/save, run/test, diagnostics, and first recovery; the last section must teach delivery and
end-to-end verification. Required unsupplied assets or inputs need a legal taught placeholder
path or must be optional.

Finish the exact continuity handoff supplied by the harness. Record current artifact state,
public contracts, named future obligations, temporary-artifact retirement targets, and evidence
for obligations due here. Open every cited file: the handoff is a navigation map, never proof.

Produce only the assigned section and its handoff. Do not edit the shared plan or another
section, and do not spawn subagents; the harness owns section parallelism.
