# Section author contract

Author each section as one addition to the evolving project.
Use two coherent authoring batches in the same section session: research first, then author every
sealed lesson together and stop; on return, author the Working, assessment, and handoff together.
If an interrupted first batch left lessons incomplete, finish all remaining lessons together and
stop once more before the Working. Never split a healthy section into one lesson per turn.
Run the assignment's bounded `render_section_context.py` command first. Treat that packet as the
initial read of the plan, named guides, sealed section, handoffs, tome metadata, and current
section sources; do not reread each item in a separate tool turn. Batch later independent reads
and searches, and group related artifact edits in one coherent edit pass using small valid patch
operations.
The packet's `sectionQualityContract` is the exact versioned policy also sent to the section
Validator AI. Treat it as binding. In particular, Phase 2's sealed co-ownership is the authoritative
concept-family allocation for lesson density: teach every co-owned mechanism completely and
coherently, but do not split, defer, or move a sealed owner in response to an independent density
reinterpretation.
Read the plan and Arc, `tome.toml`, this section's scaffold, and earlier owners of reused
work. Read `tome-authoring/9-proof-and-assets.md` and, for evidence-version tomes,
`tome-authoring/10-mastery-evidence.md`; consult
`tome-authoring/3-chapters.md` for TOML or pedagogy details.

Author the teaching from this tome alone. Never take lesson shape, exercise mix, concept ordering,
pacing, Working phrasing, or any prose from another tome under `tomes/`, from another build's state
under `.tome-build/`, or from an archived attempt at this section. Another tome's finished section
is not a template and its choices are not evidence about this plan; reusing them is how sections
come out stamped from a mold, which the quality audit records as `template-or-filler`. Your sources
for what to teach are the bounded packet, the sealed map, the plan, this tome's own earlier
sections, and this section's scaffold.

The TOML format is the exception, and the scaffold already carries it. Its fields, tables, and
required keys are this section's format reference; `tome-authoring/3-chapters.md` and
`10-mastery-evidence.md` document the rest, and `validate_section.py` reports schema faults
precisely. Read those rather than another tome. If a format question survives all of them, run the
finish the authoring pass and let the harness gate name the fault after handoff.

Before drafting prose, research this section's external subject matter online. Use `websearch` to
locate authoritative sources and `webfetch` to read the primary documentation for every API,
library, version, command, flag, and error message this section teaches; prefer official
documentation and release notes over tutorials and over your own recall. Verify each version
number, signature, and default against the published source, and prefer a conservative claim to an
invented specific when a detail cannot be confirmed. Do this before the first lesson body.
If `[mastery].sourceEvidenceVersion = 1`, complete this section's `research.toml` before drafting:
each source is a primary HTTPS source with a concrete checked claim, every lesson names source IDs
through `researchSources`, and lesson readings are citations from that same receipt set. This is an
audit trail for technical truth, not learner-facing filler.

The Phase-2 transition has already expanded untouched scaffolds to the exact sealed lesson count,
ids, titles, capabilities, mechanisms, and validation dependencies. Preserve those generated
contract fields while replacing TODO content. Each lesson's `teaches` names
concrete abilities or API contracts in stable kebab-case; the freestyle's cumulative
`requires` lists exactly what its checklist and rubric exercise. Every requirement must
be completely taught by this or an earlier lesson.

For an evidence-version tome, treat the sealed evidence fields as the same kind of immutable
obligation as mechanisms. Every exercise declares whether it is required, the capability subset it
actually exercises, its cognitive task, scaffold, context family, and aid policy. Every Working
uses stable structured public requirements, deterministic/qualitative rubric rows totaling 100,
and a private `assessment.toml` whose scenarios map only to those public IDs. Essential behavior
must be executable. If this section owns a mastery-lab node, author the aligned family TOML and
blueprints here; generation and verification occur at the Phase 7 harness boundary.
For the hardened source-evidence contract, each essential requirement needs at least two distinct
non-build scenarios and deterministic-rubric linkage for both; include its declared capabilities
in each scenario. Use an ordinary path plus a boundary, failure, or alternate input—not two copies
of the same launch.

Obey the sealed language-neutral mechanism ledger. Copy each lesson node's `introduces` exactly
to its `[[lessons]]` table and the Working node's `mechanisms` exactly to `[freestyle]`. Add
`mechanisms = []`, even when empty, to every exercise, hidden reference step, rubric row, and
`[proof]`, plus any exceptional visible artifact step, and list every concrete mechanism that
demand requires. Give every introduced mechanism its own complete `[[lessons.concepts]]` evidence
and real guided practice. Declarations never substitute for teaching.

Do not audit your own bookkeeping against that ledger. The deterministic gate re-derives it and
reports the exact file and finding: drifted `introduces`/`mechanisms`, unknown ids, use before the
owner lesson, a concept pointing at an exercise that omits the mechanism it claims to practice, a
typing drill standing in as the only guided practice, an introduced mechanism with no guided
exercise or no Working demand, and any sealed spelling — `print(`, `import `, `#` — appearing in
your code, starters, solutions, reference steps, proof, or code spans before the lesson that owns
it. Spend your turn on the teaching those checks cannot see.

A separate cached prerequisite audit reads the actual prose, code, commands, checklist, rubric,
proof, and replay for the omissions no scan can find. If it discovers a real undeclared mechanism,
only the harness may add it through the audited map-amendment path, after which this section must
teach and declare it before validation can pass. The harness refuses to auto-add a near-duplicate
ahead of its closest sealed future owner; simplify an incidental authored route instead of pulling
later curriculum forward under a new name.

Before drafting, walk the Working backward from every checklist item, rubric row, proof action,
validation dependency, artifact change, and hidden replay step to the learner's declared prior
knowledge and earlier lessons. Every unavoidable mechanism must already have an owner or be taught
here before the demand. Every mechanism introduced here must materially support this section's
Working or an unavoidable immediate prerequisite for it. Do not manufacture a disposable project
feature merely to justify an unrelated sealed mechanism, treat a broad capability name as proof of
a prerequisite, or relabel an earlier use as a different later mechanism. Surface a structural map
conflict through the assigned validation path; Phase 3 prose cannot repair a broken section order.

Check transitive prerequisites through the smallest meaningful example of every introduced
mechanism. Any unlisted syntax form, API, tool action, data-format rule, or term that example needs
must already have an owner. A prerequisite may share this lesson only when the Phase-2 audit puts
it in the same coherent family and before its dependent in the ordered `introduces` list; otherwise
an earlier lesson must own it. A dependent mechanism cannot serve as evidence that its own
prerequisite was taught. Trace how every API input or resource is created, obtained, and released.
Apply observable-interaction closure to the section promise, Working, acceptance path, and controls:
every concrete operation needed to obtain and inspect input, produce output, advance time, make a
nondeterministic choice, persist state, release a resource, or respond to the observed result needs
an owner before use. Acquiring a stream, event, handle, or resource does not own the operations that
interpret or act on its contents. Trace how every tool or data/configuration file is created,
edited, saved, and invoked. Also treat the semantic scope of every newly owned capability id as
binding: its owner is a cumulative boundary, so every claimed component family must have explicit
teaching evidence in this or an earlier
lesson, never a later one.

Preserve cumulative artifact truth and make it machine-replayable:

- Give every file/type one canonical owner. `write` creates only an absent path. Later edits use
  exact `replace`, or rare `rewrite` with `preserves = "all-active"`; never duplicate ownership.
- At every transition, explicitly remove, replace, isolate, or intentionally ship temporary
  prompts, fixtures, demo mutations, debug output, mock data, and placeholder assets recorded
  in the Arc or earlier handoffs.
- Give every chapter Working a complete learner-visible brief, complete hidden `referenceSteps`,
  and a section `[proof]`. The Working is the normal project work order: it states the outcome,
  requirements, constraints, commands, diagnostics, observable checks, and which design decisions
  remain the learner's. Do not repeat it beneath every teaching lesson. Omit lesson
  `artifactSteps` normally; use an exceptional `mode = "author"` step only when a real intermediate
  prerequisite must occur before the Working. Such a step names the path and observable check but
  contains no production-ready project content, patch, filled record, answer-bearing test, decisive
  integration, or restatement of the Working. Hidden referenceSteps reconstruct what the learner
  authors in the Working. The harness's active-contract validation replays from the real scaffold
  and reruns every active proof. Prose proves nothing. Proofs ship by default; `supersedes` requires
  a genuine migration and `protects` covering inherited capabilities.
- Trace the actual program from its first executable step after the freestyle. A learner must
  not need to infer a deletion, insertion point, asset, value, working directory, or API.

If a sealed mechanism cannot be demonstrated meaningfully in this Working — the milestone does not
need it, or every honest route to it belongs in a later section — say so and leave it undone rather
than satisfying it in form. A declaration the reference never exercises, arithmetic a later step
discards, a value computed and never read, or a token placed to match a required spelling is worse
than an unmet demand: it clears the mechanical gate and teaches the learner a lie. Report the
conflict through the assigned validation path, naming the mechanism id and why no honest route
exists here, and leave the reference honest. An unmet demand is a repairable finding the harness
can see; a faked one is not.

Teach before testing. Use complete, disposable worked examples before faded `fill` and
independent `write` work when a mechanism is new. A worked example uses different identifiers,
values, and problem shape from the canonical project; it cannot be copied, concatenated, or
lightly renamed into the learner's implementation. Keep exercise starters runnable but unsolved,
and keep the canonical project empty until the learner authors it through the Working. Make every
prompt, hint, distractor, `whyWrong`, and explanation specific to its exercise and consistent
with the final canonical behavior. MC distractors must be plausible learner misconceptions and
`whyWrong` must diagnose them. Use recall exercises for domain/tool concepts a one-file lab
cannot execute. Vary lesson and exercise shape; do not stamp a fixed template through the
section. The validator owns numeric floors and schema details and will report them precisely.

Phase-3 validation defers later-phase warnings. Ignore the informational count; never edit
badges, shop, themes, economy, attacks, or other out-of-scope banks to clear it.

Target 340–500 meaningful visible words per lesson, leaving margin above the cumulative 300 median.
The canonical count strips HTML tags then splits on whitespace; never substitute a custom tally or
filler. From the third section onward, make an exercise reuse an earlier code identifier. Mechanical
proof recognizes underscore/camelCase names in code/answer surfaces, not kebab-case capability prose.

Starting level is the complete entry baseline; optional prior-knowledge details add only the
concrete skills they name. For Start 1–3, at the first
required use of every unlisted keyword, syntax form, operator, API, tool action, or technical
term, explain its purpose in plain language, read its parts or steps in order, show a minimal
worked example with an observable result, name one likely failure, and give guided practice
before independent work. A term followed by unexplained sample code, a reading link, or a
capstone demand does not count as an introduction. Start 2 may move through this sequence
faster than Start 1, but it may not omit a fundamental. Operational setup may precede foundations
only when it is behavior-free, mechanically followable, and asks the learner to author no source,
configuration, entrypoint, or integration using untaught mechanisms.

Apply the plan's exact `Lesson pacing` contract. At Start 1, keep each lesson to one foundational
concept family and repeat guided practice before integration. At Start 2, teach one major concept
family with only tightly related supporting material; split independently teachable foundations
instead of stacking them. At Start 3, dense lessons may combine multiple closely related families
after prerequisites are secure, but every family still needs full first-use evidence and guided
practice. Never use a broad capability or mechanism label to conceal excessive lesson density.

Honor the plan's language exit contract independently of its starting level and preserve its
objective hierarchy: Mastery 1 is project-first/minimum-language, Mastery 2 is project-first with
general-language breadth, and Mastery 3–5 is language-first with the project as practice/proof.
Follow the sealed section's
`languagePractice` list: teach any newly owned `language-*` mechanism through disposable examples,
retrieve earlier language mechanisms, and make the Working require and apply every listed item.
Fade support across the course: complete disposable examples for new language material, then
partial practice, then graded project construction from a behavioral specification and observable
checks. The learner creates
or assembles every canonical project structure, source, configuration, data, test, map,
documentation, asset selection and placement, package, and delivery artifact in the Workings—not
only the two late mastery performances. Do not give starter implementations,
production-ready stubs, interfaces, fixtures, tests, records, or integration code that become
part of the final project. Put every complete solvable project answer only in hidden
`referenceSteps`.

When the sealed Working lists `masteryPerformances`, copy those IDs exactly into
`[freestyle].masteryPerformances`. For every ID, add at least one `[[freestyle.rubric]]` row with
`masteryPerformance = "<id>"` and `languageCapabilities = ["language-...", ...]` covering its
mapped language capabilities. If the map requires a rationale, that rubric row also sets
`rationaleRequired = true` and grades a rationale recorded in the artifact, comments, or a project
note. Project behavior alone cannot satisfy the row.

For Finish 3, the sealed map includes at least two late graded language-transfer performances,
including the final Working. Each asks for a novel extension, integration, or diagnosis using
taught language capabilities, their combined rubric mappings cover every declared language
capability, including structured abstraction and modularity, and at least one rubric criterion
evaluates a rationale. Each individual performance maps only the capabilities materially exercised
by its own novel task; do not repeat the complete spine on every performance or add unrelated
project requirements to manufacture coverage. The final Working's full-spine `requires` remains a
cumulative graduation boundary, not a demand that its novel performance freshly exercise every
mechanism. Do not
defer the promised ordinary user experience to a giant final lesson rewrite and then grade only
a receipt: integrate it incrementally, or leave the decisive integration to the specification-only
Working. Higher finishes remove more solution structure; lower finishes may retain the amount of
guidance stated by their exact `Mastery evidence` line.

The allowed learner-facing material is instruction, not implementation: precise goals, file
paths, public behavior, constraints, tool commands, expected observations, failure diagnostics,
and grading criteria. When more help is appropriate, split one large Working into smaller
learner-authored requirements or add isolated practice; never respond by revealing a canonical
project solution.

For `externalWorkspace`, section 1 teaches install, create/open, navigation, edit/save, run/test,
diagnostics, and recovery; the last teaches delivery and end-to-end verification. Never make media.
For every required asset, add an `[[assets]]` guide covering licensed sourcing, evaluation, and exact
placement. Deterministic proof must work without it. Acceptance may control input, clock, seed, and
frame limit, but must call real behavior—not assign the target state or print a fake win.

Maintain continuity in the preseeded handoff-v3 proposal: describe current artifact state and
public contracts, leave sealed planned obligations to the harness projection, add bounded discovered future
obligations or temporary-artifact retirement targets under `discoveries`, and cite typed evidence for every item due
here. Never author a completion boolean, delete/retarget a planned item, claim an item early, or
edit a prior handoff. Verify every claim against files; context is navigation, never proof. The
harness accepts discoveries only after the origin section passes, closes due items only after all
gates pass, and retains the closure archive after removing them from active context.

The assignment's final `HARNESS COURSE CONTROL` block is authoritative and must remain the final
block when you stop. It lists all sections, expands this section's sealed lesson/Working nodes,
points to required prior owners, and carries every active obligation. Do not award its marks or
rewrite its state. Run the assignment's named mechanical check until it exits 0, report the real
section validating, and stop. The harness repeats the check and returns its complete findings.

Work in Arc order, repair each section gate before advancing, and reopen disk instead of trusting
memory. Never edit the plan during Phase 3 or spawn another author.
