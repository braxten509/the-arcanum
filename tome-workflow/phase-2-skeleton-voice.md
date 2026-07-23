# Phase 2 — Skeleton & voice

Read **§2**. Fill `[meta]`, `[runtime]`, `[content]`, `[narrative]`, and `[defaults]` in
Arc order. Phase 2 owns the narrative: write 8–12 `bootLines`, 6–8 `gradingLines`, and
an in-world `completeText`. Phase 6 still owns finished themes, shop, and badges.

Write `[meta].description` as concise, positive shelf copy: name the finished artifact
and the meaningful capabilities the learner builds. Do not advertise exclusions with
phrases such as "does not cover," "stops short of," or "not included." Scope cuts belong
in the plan's Graduate ledger, not in the tome catalog.

The harness has already parsed the approved Arc and deterministically created every
`[content].sections` entry and `sections/<sid>/` directory. Each section contains exactly
ONE placeholder lesson with unique ids and the starter exercise shapes. Preserve that
tree. Do not add lessons, exercises, readings, or authored teaching prose; do not clear
the TODO marker from the lesson body or freestyle brief. Phase 3 alone authors the
3–8 real lessons per section and their content.

Keep `[content].capabilityLedger = true` and `[content].proofVersion = 1`. Leave each
skeleton section's proof, concept-evidence, artifact-step, and reference-step placeholders
for Phase 3 to replace; never downgrade the proof contract. Leave each lesson/freestyle with a
valid placeholder `teaches`/`requires` id for Phase 3 to replace; do not disable the
coverage contract.
Preserve `[mastery].evidenceVersion = 1` and its Phase-0 `level` exactly. The central policy owns
progression and grading thresholds; a tome cannot override them.

Begin with `python3 tools/workflow/context/render_phase2_context.py BUILD_ID`. It prints the sealed lesson
spine and the small author-spec files for this build. Edit only those compact files, the research
ledger, tome skeleton, and any required reusable runtime; do not hand-maintain or repeatedly read
the generated `course-map.proposal.json`. Run the exact assigned preview materializer and mechanical
validator whenever useful and always after the unit is complete; repair and rerun until both exit
0. After handoff, the harness independently repeats those same checks, publishes the protected
proposal from the sealed seed and author spec, and then starts the Validator AI.
In the compact `course.json`, `languageMastery` contains only the seeded performance IDs and
their Phase-2-owned `capabilityIds`; every other language-mastery field remains sealed in the seed.

The manifest `[acceptance]` table describes executable proof; it does not repeat the sealed
delivery record. Its `mode` is `run` or `guided`, and its `artifact` is the discriminator `runtime`
or `package`. A package-delivery course therefore uses `mode = "run"` and
`artifact = "package"`. Keep the exact delivery artifact and requirements paths in the sealed
`artifactContract.delivery` record and the final section's package proof. Never put
`mode = "package"`, a file path, `requirements`, or a nested `sealedDelivery` table under
`[acceptance]`.

The bounded packet also names `audit.json`. This language-neutral sidecar is mandatory author
work, not prose documentation. New runs use version 2 and give it exactly `version`,
`mechanisms`, `capabilityCoverage`, `continuityCoverage`, `failurePaths`, and
`artifactProduction`. Version 1 remains
readable only so an already-running Phase 2 is not invalidated underneath its author:

- `mechanisms` contains exactly one row for every mechanism in `mechanisms.json`, using
  `{"id":"...","family":"...","dependsOn":["..."],"productionDependsOn":["..."]}`.
  `family` groups only one coherent
  pedagogical concept or operation family at the lesson level; it is not a one-row-per-verb or
  one-row-per-state-transition category. Concrete mechanisms may share a family when they form one
  teach-practice-observe loop—for example a decision and its displayed result, an action and its
  verification, a deliberately triggered failure and observation of that failure path, or a guided
  change and its evidence. Do not merge independently teachable foundations merely to meet a
  density limit. `dependsOn` names every concrete prerequisite
  mechanism needed by the smallest meaningful example. A same-lesson dependency is valid only
  within that one family and only when the prerequisite occurs first in the lesson's ordered
  `introduces` list; a cross-family prerequisite needs an earlier lesson. Working demand lists
  must be transitively closed over those edges. `productionDependsOn` is the narrower subset of
  those prerequisites whose concrete operations are required to create an artifact containing or
  implementing this mechanism. It must never invent an edge outside `dependsOn` closure.
- `capabilityCoverage` contains exactly one row per taught capability, using
  `{"capability":"...","mechanisms":["..."]}`. Name every concrete semantic component of that
  capability. The gate rejects a capability claimed before any named component mechanism's lesson
  owner, including an umbrella capability whose final component is introduced in the same lesson
  after its prerequisites.
- `continuityCoverage` contains exactly one row per planned obligation, using
  `{"obligation":"...","mechanisms":["..."]}`. Name the concrete operations that the target
  Working must retain for that obligation. The gate rejects a target Working that drops any named
  mechanism, so a final delivery cannot silently lose an earlier diagnostic, cleanup, integration,
  verification, or other sealed continuity contract.
- `failurePaths` uses
  `{"id":"...","status":["..."],"branches":["..."],"diagnostics":["..."],"cleanup":["..."]}`
  for each planned failure route. A branch must depend on the observed status and must not depend
  on its later diagnostic or cleanup. Diagnostics depend on a status observation. When the route
  owns resources, cleanup depends on the failure branch; `cleanup` may be empty only when no
  cleanup operation is truthfully required. These roles are language-neutral lifecycle
  responsibilities.
- `artifactProduction` contains exactly one row for every sealed artifact, using
  `{"artifact":"...","ownerWorking":"sNN.working","mode":"authored|generated|copied|packaged","inputs":["..."],"mechanisms":["..."]}`.
  `authored` begins without artifact inputs. `generated` may have zero artifact inputs when a tool
  truthfully creates the artifact from parameters or a non-artifact template. `copied` and
  `packaged` each name at least one earlier or same-Working artifact input. Every mode's mechanism
  list must name the concrete operations that actually create that artifact, not a nearby broad
  capability, and must be transitively closed over those mechanisms' `productionDependsOn` edges.

When tooling is external or both, the first section must teach `tool-install` and the observable
`tool-diagnose` verification before the first lesson that teaches `tool-edit-save`. The gate checks
this from the language-neutral capability owners rather than recognizing a compiler, framework,
package manager, or file extension.

This is language agnostic: families describe responsibilities such as a source layout, build
pipeline, resource lifecycle, deterministic control, or delivery transition. They never assume a
particular keyword, compiler, package manager, framework, or file extension. The Validator AI
checks semantic honesty, while the materializer mechanically rejects missing rows, unknown edges,
cycles, late prerequisites, non-closed Working demands, false artifact ownership, and lesson-family
density beyond the selected Starting level.

For external tooling, research only facts that affect current installation, commands, APIs,
compatibility, or delivery. Record at most six official or primary sources in the bounded research
ledger printed by the context command. Phase 3 receives that ledger in every section packet and
must reuse it before repeating web research.

Expand the compact author spec into the complete Phase-3 skeleton while the learner-facing tome
files remain placeholders. Preserve every seeded Phase-1 field and planned obligation. Materialize
exactly each sealed `lessonCount`; do not add, remove, or regroup lessons in Phase 2. For every
section, assign stable kebab-case capability IDs, earlier dependencies, the project milestone, and
every planned lesson plus exactly one Working:

Before assigning nodes, perform a cold-start dependency walk in section order. For every Working,
inventory the unavoidable language mechanisms, library or runtime APIs, tool actions,
configuration or data-format rules, and technical terms demanded by its milestone, artifacts,
rubric, proof, validation, and hidden replay—not only by its short learner-facing brief. Resolve the
order from foundational language mechanisms to dependent runtime, library, tool, configuration,
and integration work, and place every owner before first required use. An early setup step is valid
only when it is behavior-free, mechanically followable, and requires no learner-authored source,
configuration, entrypoint, or integration that relies on untaught mechanisms. If the sealed Arc
cannot support this order within the allowed lesson capacity, fail the proposal instead of hiding
the conflict in broad labels.

Make a second pass over executable command demands before sealing. Copy every literal command from
each section milestone, Working, acceptance route, proof, and package argument list into the owner
audit. A distinct subcommand, task-runner rule, or Make target is a distinct mechanism: demanding
`make run`, `make package`, and `make release` requires concrete owners for all three before those
commands appear, not one broad "Makefile" capability. Put each owned mechanism in the demanding
Working's `mechanisms` list. The Phase-2 gate infers Make target semantics from a `Makefile` or a
direct Make runtime; a runtime with another first-positional target tool declares it through
`commandTargetTools = ["tool"]`.

For `externalWorkspace = true`, broad `tool-install` and `tool-deliver` capabilities are not enough.
Their section Workings must include concrete, already-owned `tool-action` mechanisms that actually
set up/provision the workspace and package/copy/stage the deliverable. Name the real learner action,
not a synonym for the capability.

Compute transitive prerequisite closure, not only the visible demand list. For each mechanism, ask
what its smallest meaningful example must contain or invoke. Every unlisted syntax form, API, tool
action, data-format rule, or technical term in that example needs an earlier owner. At Start 1–3,
a same-lesson prerequisite counts only when it shares the lesson's coherent family and comes first
in the ordered `introduces` list; a cross-family prerequisite needs an earlier lesson. A dependent
construct cannot be used as the vehicle that supposedly teaches its own prerequisite. For an API, trace how its inputs
and resources are created, obtained, and released. Apply observable-interaction closure to every
section promise, Working, acceptance path, and control: list the concrete operations needed to
obtain and inspect input, produce output, advance time, make nondeterministic choices, persist
state, release resources, and respond to the observed result. Acquiring a stream, event, handle,
or resource does not by itself own the operations that interpret or act on its contents. Add these
rows to the private owner audit even when they are project/runtime mechanisms rather than language
capabilities. For a tool or data/configuration file, trace the create, edit, save, and invocation
actions. Do not invent a library- or project-specific mechanism label for general language syntax
and then introduce the real syntax later.

- lesson nodes use sequential `sNN.lNN` IDs, name what they teach, and carry a non-empty typed
  `doneWhen.checks` packet. `doneWhen` is always a JSON object, never a bare array. Use exactly
  `"doneWhen": {"checks": ["learner-construction", "lesson-source"]}` for lessons and
  `"doneWhen": {"checks": ["learner-construction", "working-replay"]}` for Workings; mastery
  labs use the exact object shown below. Except for `s01.l01`, every lesson names prerequisite evidence;
  each later lesson in a section depends on the immediately previous lesson, and each later
  section starts from an earlier Working;
- lesson-node granularity obeys the plan's exact `Lesson pacing` line. Start 1 assigns one
  foundational concept family per lesson; Start 2 assigns one major family plus only tightly
  related support; Start 3 may group multiple closely related families after prerequisites are
  secure. Do not hide density by giving one mechanism id to several independently teachable
  syntax forms, APIs, tool actions, or technical terms; split them into honest mechanism owners.
  The Phase-1 count is authority: fit the dependency walk honestly into those named lesson slots.
  If no compliant Phase-2 repair can satisfy mutually incompatible sealed requirements, the
  Validator AI must report `# CONTRACT CONFLICT`; the harness pauses without returning that
  impossible repair to the Phase-2 author;
- the Working uses `sNN.working`, requires only capabilities taught in this or an earlier section,
  depends on its section's final lesson, repeats the section milestone, lists every learner-owned
  artifact, and includes
  `working-replay` and `learner-construction` checks;
- preserve the seeded `artifactContract` exactly. Every Working artifact must exist in its
  exhaustive Phase-1 inventory, every declared owner Working must introduce its artifact,
  no earlier Working may contain it, retired artifacts disappear at and after their retirement
  section, and every shipped artifact remains listed in the final Working. The runtime entrypoint,
  every non-placeholder proof `expectedFiles` path, and package
  `requirementsFile`/`artifactPath` must all be declared `ships` artifacts;
- preserve `artifactContract.delivery` exactly. `[acceptance].artifact` must equal its mode. For
  runtime delivery, `[runtime].entryFile` must equal its artifact path. For package delivery, the
  final proof must remain `mode = "package"` and its `artifactPath` and `requirementsFile` must
  equal the Phase-1 paths; source-only acceptance is not an allowed downgrade;
- section capabilities exactly equal the capabilities owned by its lessons, and section
  `doneWhen.checks` retains `section-source`, `section-replay`, and `continuity`;
- preserve the seeded `languageMastery.language`, level, capability spine, foundation-role
  mapping, and structured performances. Include every `language-*` capability in
  `graduateCapabilities` and give it one
  real lesson teaching owner. Treat every word in a capability id as binding semantic scope. Its
  owner is the cumulative boundary: component families may have explicit owners in earlier
  prerequisite lessons, but every claimed component must be taught no later than the capability
  owner. If a component would be taught afterward, move the umbrella owner later or fail because
  Phase 1 should have split families with materially different first-use points. Coverage-profile
  token groups are satisfied across the full spine and never require unrelated families to share
  one capability id. Before submission, make a private capability-owner audit table with one row
  per language capability, every semantic family named by its id, and each family's exact mechanism
  owner; the capability owner must be at or after the latest row entry. Fill each performance's
  `capabilityIds`, but never change its seeded
  Working, kind, rationale requirement, or description;
- at Finish 3–5, distribute every declared language capability—including the seven foundation
  roles data, control, decomposition, structured abstraction, modularity, failure, and
  verification—across the late graded performances. Map each performance only to capabilities its
  seeded novel task materially exercises; make the performances different and complementary, and
  let their combined union cover the spine. Never attach the complete spine to every performance
  or invent unrelated task requirements to force coverage. Practice every language capability in
  at least two Workings, and make the final Working require the complete language spine as a
  cumulative graduation boundary; its performance mapping remains the subset exercised by its
  novel task. A framework-only extension cannot satisfy language mastery;
- preserve every section's non-empty seeded `languagePractice` minimum from Phase 1. Add truthful
  later retrieval when useful, but never remove or replace a seeded capability. Each section's
  Working must require and materially exercise every listed capability through real language work;
  tooling, framework, build, packaging, or story activity alone does not qualify. If a seeded
  minimum cannot be implemented honestly without changing its sealed milestone or ownership,
  report a contract conflict rather than manufacturing a Phase-2 owner;
- at Finish 3–5, preserve the sealed foundation and verification cadence in actual owners, not
  merely promise wording. Every mapped foundation capability owner must be no later than the Arc
  midpoint, and the learner-authored verification owner must be no later than the section after
  decomposition first becomes usable. Retrieve verification across representative later Workings;
  hidden replay does not satisfy this learner-owned cadence;
- every Working has `masteryPerformances = []` unless a seeded performance targets it. For a
  targeted Working, use the exact ordered union of its IDs: seeded `languageMastery` performance
  IDs first, followed by any non-lab `masteryEvidence` performance IDs, with duplicates removed.
  Phase 3 will repeat that complete list in `[freestyle].masteryPerformances` and attach rubric rows
  that explicitly grade the mapped capabilities and rationale;
- preserve the seeded `masteryEvidence` object exactly. For every declared `sNN.labNN`, add a
  `mastery-lab` node at the corresponding point in that section. Its keys are `id`, `kind`,
  `title`, `performanceKind`, `capabilityIds`, `cognitiveTasks`, `contextRelation`, `aidPolicy`,
  `variantFamilyId`, `rationaleRequired`, `dependsOn`, `validationDependencies`, and `doneWhen`.
  Copy the performance fields exactly, use all central cognitive tasks materially exercised by
  that lab, depend on prior evidence rather than future nodes, and set
  `doneWhen.checks = ["learner-evidence", "variant-proof"]`. A lab is standalone: it must not
  modify or copy the cumulative project unless its sealed performance is explicitly a final-
  project change request;
- every planned obligation has a real later target and typed evidence locations, capability IDs,
  proof IDs, acceptance IDs, and an observable result. Its `location` is an existing file relative
  to the origin section (for example `section.toml` or `lessons/l02.toml`); every
  `doneWhen.evidenceLocations` entry is an existing file relative to the target section, with an
  optional `#anchor`. Never use repository-global `sections/sNN/...` paths—the Phase-2 gate proves
  these references resolve before sealing.

For course-map version 6, preserve and complete the language-neutral `mechanismContract`.
Capabilities state broad outcomes; mechanisms name the concrete required keyword, syntax form,
operator, API, tool action, or technical term. Give each mechanism a stable kebab-case `id`, a
plain `label`, a language-neutral kebab-case `kind` (for example `syntax-form`, `api`, or
`tool-action`), and exactly one lesson `owner`. Every lesson node includes `introduces = []` and
lists exactly the mechanisms it first teaches. Every Working node includes `mechanisms = []` and
lists every mechanism its eventual learner-visible brief, rubric, proof, or hidden replay will
unavoidably require. An owner must occur no later than any use. The Phase-3 author repeats these
sealed declarations at each demand site; undeclared first use is a blocking prerequisite failure,
not an invitation to infer that a nearby capability covered it. Every introduced mechanism must
also materially support its own section's Working or an unavoidable immediate prerequisite for
that Working. Do not introduce the next catalog item without a milestone need, teach a prerequisite
after its dependent use, or create a near-duplicate label for the same mechanism later.

Use this shape (with course-specific values):
`"mechanismContract":{"version":1,"coverageStart":"s01","mechanisms":[{"id":"...","label":"...","kind":"syntax-form","owner":"s01.l01"}]}`.
Lesson nodes carry `"introduces":["..."]`; Working nodes carry
`"mechanisms":["..."]`. Empty arrays are explicit.

For course-map version 6, every lesson, Working, and mastery-lab node must also include
`validationDependencies = []`. Put the exact package spec in that array on every node whose
authored examples, exercises, hidden replay, checks, or promised capability require a third-party
package. The union of node packages must exactly equal `[runtime].validationDependencies` in
`tome.toml`. This declaration is Phase 2's responsibility because Phase 3 section workers cannot
edit the manifest. A node that teaches or relies on a third-party verification library must place
that library's exact package specification on its nodes and in the manifest even when an earlier
section already uses a different package.

Apply the **dependency installability rule** before choosing any exact package spec. Resolve the
selected runtime's actual interpreter or toolchain version and target platform, then verify every
declared spec is currently available and installable through that runtime's declared isolated
package command. Never guess a remembered version or select a stale pin merely because its API is
familiar. Phase 2 is not complete until the exact union can provision in the validation
environment; an unavailable or runtime-incompatible release must be replaced with a verified
compatible spec without changing the learning contract.

Do not invent a completion/checkmark field. Do not change seeded section IDs, titles, promises,
acceptance order, or continuity requirements. The Phase-2 gate rejects unknown keys, gaps,
duplicates, cycles, missing owners, graded use before teaching, and incomplete proof packets;
the transition alone seals the normalized map. It also rejects a project-complete skeleton whose
language capabilities have no owner, cumulative Working practice, or structured late assessment;
a mislabeled verification capability, flat lesson graph, or artifact-lifecycle mismatch also
blocks the seal. These are deterministic local checks. After they pass, the harness separately
sends the sealed Phase-1 plan, generated proposal, compact author files, audit, research ledger,
manifest, selected runtime profile, and the shared Phase-2 authority block to the mandatory
read-only Validator AI; repair only its cited Phase-2 findings. That review is ordinary Markdown
whose suggested layout is optional and no response field names are required. The author receives
ordinary reports unchanged; a durable repeated-evidence marker or explicit contract conflict stays
at the harness without an author turn. Phase 3 cannot begin until both gates pass and the transition
seals the map.

The learner-facing runtime scaffold contains only a blank editor file or unavoidable
behavior-free tool metadata. Do not seed project structure, implementation, reusable subsystems,
filled data/configuration, tests, maps, documentation, assets, packaging, or delivery files.
Keep the tome runtime overrides `starterCode = ""` and `scaffoldCommand = []`; hidden replay
steps may reconstruct the proof project, but the learner's initial workspace remains theirs.
Where the platform permits, make the learner create even the entry file and project shell. Phase
3 lessons teach with disposable examples and each Working makes the learner create or assemble
the corresponding canonical artifacts; hidden referenceSteps alone reconstruct the complete
replayable non-media solution for the harness. Media remains learner-sourced and unbundled.
Copy Arc scenario order into `[acceptance]`; choose `package` for promised delivery,
otherwise `runtime`. Package runtimes need delivery argv.

Every tome names a reusable runtime file. If `global-configs/runtimes/<name>.toml` is
missing or incomplete, this phase may create or repair it. Read **§5**, copy an existing
runtime's TOML shape, use a toolchain installed on this host, and include the language's
run/check/scaffold, diagnostics, starter, syntax, and completion configuration. Keep
tome-specific overrides in the tome's `[runtime]` table.

The runtime must scaffold, truthfully build/check, and accept safe proof arguments on its real
run command. Never bypass it with a tome-controlled shell command.

For package delivery, read `runtimes/delivery.py` as well as §5 and trace the exact argv lifecycle.
Every delivery command runs with cwd set to the learner project. `{env}` is a fresh dependency or
staging directory; it does not contain the learner's Makefile or source tree. `{requirements}` and
`{artifact}` are absolute paths inside the learner project, and final `packageArgs` are appended to
`deliveryBuildCommand`. Therefore never `cd` to `{env}` and try to build unstaged project sources.
Build from project cwd. If this runtime itself promises to copy the built artifact to a clean
location, declare the sealed paths as the paired `deliveryArtifact` and `deliveryRequirements`
values and make `deliveryBuildCommand` consume both `{artifact}` and `{env}` while staging it.

If any authored solution, starter, or executable sample imports a third-party package,
declare every such package in the tome as `validationDependencies = ["package", ...]`.
Never embed a host-specific path, temporary install directory, shell-time package install,
or package workaround in `command`/`checkCommand`. The reusable runtime owns the generic
isolated installer: environment-scoped ecosystems use `validationCreateCommand`,
`validationPackageCommand`, and `validationEnv`; project-scoped ecosystems use
`validationProjectPackageCommand` (or their existing `packageCommand`). The harness provisions
the former once and the validator provisions the latter inside each scratch project.

Give the placeholder lesson in each section a distinct fiction-facing title so numbered
references cannot be ambiguous, but leave its body as an explicit Phase 3 placeholder.
The `--phase-2-skeleton` check deliberately ignores Phase 3 density, readings, prose,
exercise-variety, and TODO-clearance warnings; never try to satisfy those here. Produce
the complete green skeleton and, only when needed, its reusable runtime configuration.
Do not rename the tome folder or run the Phase-2 transition yourself. The harness does so only
after the mechanical and Validator AI gates pass, then prints the new current id.
