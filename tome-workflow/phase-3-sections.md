# Phase 3 — Sections (the course)

Read `tome-workflow/support/section-author.md`, `tome-authoring/9-proof-and-assets.md`, and
`tome-authoring/10-mastery-evidence.md`,
then author in Arc order, one complete section at a time: brief, lessons/exercises, and
cumulative freestyle. Each section adds its promised capability to the evolving project.
Never test material that this or an earlier lesson has not taught.

Draw the teaching from this tome alone. Never take lesson shape, exercise mix, concept ordering,
pacing, Working phrasing, or prose from another tome under `tomes/`, from another build's state
under `.tome-build/`, or from an archived attempt at this section; a finished section elsewhere is
not a template and its choices prove nothing about this plan. Reusing them produces the stamped
material the quality audit rejects as `template-or-filler`. For TOML format, use this section's
scaffold, `tome-authoring/3-chapters.md`, `10-mastery-evidence.md`, and the validator's own
precise schema findings — never a neighboring tome.

Establish current external truth before writing any prose. For each section, use `websearch` to
locate authoritative sources for every API, library, version, command, flag, and error message the
section teaches, and `webfetch` to read the primary documentation rather than trusting a search
snippet or your own recall. Prefer official documentation, release notes, and changelogs over blog
posts and tutorials. Confirm that every version number, function signature, and default you state
matches the current published source, and that anything presented as current behavior has not been
deprecated or renamed. Where sources disagree or a detail cannot be confirmed, teach the
conservative version and say so plainly instead of inventing a specific. Research is a
precondition for drafting, not a repair step: complete it before the first lesson body, not after
the validator or reviewer objects.

The learner authors every part of that evolving project. Lesson bodies and exercises may use
small disposable worked examples, but they may not provide canonical source, configuration,
data, tests, maps, documentation, delivery files, production-ready stubs, ready-to-paste
patches, or rename-equivalent solutions. The section's learner-visible Working owns the ordinary
cumulative project assignment: give it a concrete outcome, requirements, constraints, commands,
diagnostics, observable acceptance, and meaningful implementation choices. Do not repeat that
assignment beneath every lesson. Omit lesson `artifactSteps` normally; use one only for a genuinely
necessary intermediate prerequisite that must occur before the Working, with `mode = "author"` and
no answer content. Put one complete implementation of the Working only in the section's hidden
`referenceSteps`. Apply this in every section, including s01; scaffold fading changes task size and
hint detail, never who writes the real artifact.

For an evidence-version tome, copy every exercise's sealed capability/cognitive/scaffold/context/
aid obligation into its TOML, author exact structured public Working requirements and rubric rows,
and put deterministic scenarios in the section's private `assessment.toml`. A scenario may test
only a public requirement and must call a registered generic runtime command. Author each sealed
mastery-lab family, its public/hidden directories, and its full blueprint pool in the assigned
section. Do not place a hidden check, reference answer, mutation, or blueprint in learner-visible
TOML or public files.

The harness gives each section a fresh author session after the preceding section validates.
Stay in that session for the assigned section and all of its repair turns; do not begin the next
section yourself. The first turn researches and authors every sealed lesson in one batch, then
stops before the Working. The same session returns for one Working/assessment/handoff batch.
Begin with the assignment's `render_section_context.py` command instead of a
series of one-file discovery calls. Batch independent reads/searches and apply related edits in
one coherent edit pass using small valid patch operations. Gate each section before advancing and reopen its files from
disk. Repairs target only failures and never wipe the
tree. Phase-focused gates hide later-phase warning
details. A deferred count is informational: do not edit badges, shop, themes, economy,
attacks, or other later banks to clear it.

Treat the final `HARNESS COURSE CONTROL` block in every assignment as the current machine-owned
navigation contract. It is regenerated from the sealed map and evidence after initial assignment,
repair, resume, compaction, or model switch. Read the complete spine, expand only the assigned
section, follow each required prior owner, and preserve every `DUE NOW` or `LATER` obligation.
Never edit the sealed map, derived state, receipts, prior handoffs, status words, or checkmarks.
If the projection reports a deterministic size-budget failure, stop on that exact gate instead
of omitting an item.

A real post-seal plan discovery is an operator action, never an author edit. The operator supplies
a complete candidate map and runs
`python3 tools/workflow/amend_course_map.py BUILD_ID CANDIDATE.json --reason "specific audited reason"`.
That command validates the whole graph, records old and new values, bumps the revision and digest,
and invalidates the earliest affected section plus every downstream receipt before work resumes.

Write the preseeded handoff-v3 proposal for the assigned section. The harness projects sealed
planned obligations automatically; never copy them into the handoff. Add only genuine discovered
future requirements or temporary retirements under `discoveries`, with a
real later target and typed `doneWhen`; and give due fulfillments exact current-section evidence
locations plus real capability, proof, and acceptance IDs. Do not add `complete`, `completed`, or
`verified` fields. The final section may create no future obligation and must leave the active
ledger empty. After authoring the assigned section and handoff, run the assignment's exact complete
mechanical section gate. Repair and rerun it without a one-run limit until it exits 0, then mark the
section `validating` and stop. The harness independently repeats the TOML, pedagogy, replay,
proof-source, continuity, and complete section gate.
For the final section, the assignment additionally lists the whole-Phase-3 command. Run it after
the section command; the harness repeats both mechanical gates before the Validator AI.
It returns one aggregate repair packet to this same session when findings remain. Do not inspect
validator source to guess at extra checks or replace it with hand-written parsing, replay,
word-count, exercise-distribution, or schema scripts.

Use the plan's calibration and `[narrative]` voice. Before changing a recurring type, file,
API, asset, or workflow, search all earlier sections. Preserve canonical contracts, retire
temporary scaffolding on schedule, and align feedback with final code. Use the active-contract
state in the bounded packet; the harness runs its report after handoff. `write` creates only;
otherwise use exact replacement or an
all-active rewrite. The gate reruns active proofs. Repair later regressions without weakening
earlier proofs. Acceptance controls input/time/seed/frame limit but drives real behavior.

Produce the complete `sections/<sid>/` tree. Do not append a phase narrative or audit log
to the build plan.
