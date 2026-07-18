# Phase 1 — Concept & arc

Read the plan, **§1**, and **§2 `[content]`**. Translate its six answers into the listed Arc
fields as course-specific decisions, not generic instructions.

Begin with the real finished artifact and its acceptance proof. Honor Phase 0 Tooling
exactly: `internal` keeps every required action in-browser and forbids `externalWorkspace`;
`external` requires real external tools; `both` permits a taught mix. Never override it or
simulate the core skill. Write `**Tooling fit:** <answer> — COMPATIBLE: <evidence>` in the
Arc. A `BLOCKED`/`REQUIRED` request is forbidden because construction has no human pause.
Choose and prove an honest compatible realization. If none exists, fail the Arc gate; never
simulate the core skill or ask a human to rescue construction.

Choose one project spelling for Phase 2. Do not move the scaffold; the deterministic Phase-2
transition derives its kebab-case id after `[runtime] project` exists.

Design backward from acceptance; section count follows required capabilities, not a target, and
must be from 2 through 40 inclusive. Every section must own a necessary capability or integration
milestone. Apply the removal test: deleting any section must break a named graduate capability,
project milestone, continuity dependency, or acceptance requirement. If the honest arc cannot fit
inside the bound, fail Phase 1; never exceed it, compress away required teaching, lower the finish,
or defer the missing scope to a later phase.
Respect every gate answer. Record the real difficulty spine, graduate CAN/CANNOT boundary,
and daily drivers. Low starts need fundamentals and toolchain work before domain work.
For Start 1–3, treat the prior-knowledge answer as an exhaustive whitelist and order the
arc so every required keyword, syntax form, operator, API, tool action, and technical term
is introduced before first use. Start 2 changes pace and repetition, not fundamental
coverage; a construct cannot disappear from the teaching sequence merely because the
learner is not at absolute zero.

Before writing the Section list, perform a cold-start dependency walk from that whitelist through
every proposed Working and the final acceptance journey. For each Working, enumerate every
unavoidable language mechanism, library or runtime API, tool action, configuration or data-format
rule, and technical term demanded by its milestone, learner-owned artifacts, rubric, proof,
validation, and hidden replay. Give each demand an earlier teaching owner. Put foundational
language mechanisms before dependent library, runtime, tooling, configuration, and integration
work. Operational setup may appear first only when it is behavior-free, mechanically followable,
and asks the learner to author no source, configuration, entrypoint, or integration that depends on
untaught mechanisms.

Teaching a dependent mechanism does not implicitly teach the mechanisms needed to make its
smallest meaningful example work. Expand every proposed mechanism through its transitive
prerequisite closure. If that smallest example contains an unlisted syntax form, API, tool action,
data-format rule, or technical term, give that prerequisite an earlier owner even when a learner
could copy it without understanding it. At Start 1–3, a prerequisite in the same section counts
only when an earlier lesson owns it. For each API, trace how its inputs and resources are created,
obtained, and released. Apply observable-interaction closure to every promise, acceptance path,
and control: plan distinct owner families for the concrete operations needed to obtain and inspect
input, produce output, advance time, make nondeterministic choices, persist state, release
resources, and respond to the observed result. Merely acquiring a stream, event, handle, or
resource does not own the operations that interpret or act on its contents. For each tool or
data/configuration file, trace the create, edit, save, and invocation actions. Never use a library-
or project-specific alias for a general language prerequisite and then introduce the real
mechanism later.

Keep mechanisms coherent with milestones. Every capability or mechanism first introduced in a
section must materially enable that section's Working or be an unavoidable immediate prerequisite
for it. Do not march through a language catalog independently of the project arc, postpone a
prerequisite until after its first demand, or create a near-duplicate later mechanism to disguise
the same earlier use. Each Section-list promise must survive both the removal test and this
dependency-and-relevance test.

Honor the plan's exact `Lesson pacing` line when sizing the arc. Start 1 is deliberately
low-density: plan one foundational concept family per lesson and separate independently teachable
language, API, and tool families. Start 2 uses moderate density: one major concept family plus only
tightly related supporting material, with less repetition than Start 1. Start 3 may use dense
lessons that combine multiple closely related families once their prerequisites are secure and
each still receives complete first-use teaching and guided practice. Never combine unrelated
foundations merely to reduce the lesson or section count. Derive each section's likely lesson count
from this concept-family load: three lessons is the schema minimum, not a default. Use the available
capacity through eight lessons, and split the Arc into more sections if honest low-start teaching
would exceed it.

Starting level and mastery are separate axes. Starting level controls the support at the
entrance; mastery controls how independently the learner uses the declared language at the exit.
Project scope controls only how large, complete, content-rich, and polished the finished artifact
must be. A small Project Scope can use a compact artifact to exercise a broad Mastery contract;
it never removes required language areas or lowers the mastery-owned lesson-depth floor.
Follow the plan's exact objective hierarchy: Mastery 1 is project-first with the minimum necessary
language taught and learner-authored; Mastery 2 is project-first with deliberate general-language
breadth; Mastery 3–5 is language-first, with the project as integration and proof. At those higher
levels, project behavior is not a substitute for language fluency. Follow the plan's exact
`Entry/exit separation`, `Learner-construction rule`, `Worked-example boundary`,
`Working-project boundary`, `Exceptional-step boundary`, `Language-through-project rule`,
`Scaffold-fading rule`, and numbered
`Mastery evidence` lines.
Every section's Working—not its lessons—owns the real canonical project changes. Plan lessons
that teach mechanisms through disposable examples with different identifiers, values, and
problem shapes; never plan a ready-to-paste project file, patch, filled record, test, map, or
integration. More beginner support means smaller work orders, clearer constraints, more guided
practice, and more observable checks—not giving away any part of the promised artifact.

At Finish 3–5, apply the plan's `Foundation cadence rule`. Mention every declared language
capability in at least one Section-list promise, establish all mapped foundation-role capabilities
by the Arc midpoint, and place them before framework, runtime, or integration work that depends on
them. A late promise cannot retroactively make an earlier dependent milestone beginner-safe.

Write these machine-owned language decisions before the ordinary mastery prose:

- `**Language mastery:** <Language> — Finish N/5: <language exit ability>` repeats the Arc's
  language and the selected Phase-0 level exactly.
- `**Language capability spine:** language-... -> language-...` names at least four stable,
  language-general capabilities. They describe fluency in the language—not project outcomes,
  framework features, or story behavior. Each id is an honest cumulative unit: Phase 2 may teach
  its component families in earlier prerequisite lessons, but the capability owner must occur only
  after every semantic component named by the id has an explicit mechanism owner. Split families
  when their prerequisite chains, milestone needs, or first-use points differ materially. Never
  combine an early family and a late family merely to include required keywords or place an
  umbrella owner before material taught only later.
- `**Language foundation coverage:**` is one physical line mapping the universal roles `data`,
  `control`, `decomposition`, `failure`, and `verification` to five distinct ids from the
  capability spine. Map each role to the declared language's idiomatic mechanism; never use a
  framework feature or unrelated language operation as the mapping. The verification capability
  id must explicitly name verification, testing, checking, assertion, validation, debugging,
  diagnosis, inspection, proof, or quality, and its late performance must describe an observable
  verification action. At Finish 3–5, also map `abstraction` and `modularity` to distinct
  capabilities. Abstraction must name a concrete structured idiom the declared language actually
  provides; modularity must name its real module, package, namespace, or boundary mechanism. At
  Finish 3–5, read `global-configs/language-mastery.toml`; obey the generic minimum capability count
  for the selected Finish and every cumulative coverage area in any matching language profile.
  Name stable capability ids that visibly satisfy every required token group. Token groups are
  checked across the complete spine: separate ids may satisfy separate groups in one area, and an
  individual id does not need to contain every group. Preserve those honest boundaries instead of
  manufacturing compound ids. When a profile area sets `distinctCapabilityGroups = true`, each
  token group must map to a different capability id; one umbrella id cannot satisfy two groups.
  When no profile
  matches, retain the complete generic foundation contract and derive idiomatic mechanisms from
  verified semantics of the declared language rather than borrowing another language's feature
  taxonomy. At Finish 3–5,
  `errors = CAN`, every declared language capability must be practiced in at least two Workings and
  required by the final Working, and the combined late graded performances must exercise all
  capabilities.
- At Finish 3–5, apply the plan's `Verification cadence rule`: establish the language's
  learner-authored idiomatic verification loop no later than the first nontrivial decomposed
  behavior that later integrations depend on, and retrieve it across representative later
  Workings. Hidden replay or end-loaded release checks are not learner verification. If ordinary
  checking/testing and tool-driven diagnosis mature at materially different points, use separate
  capability ids instead of back-loading both inside one umbrella.
- `**Language performances:**` is one physical semicolon-separated line. Each clause is
  `sNN.working = <kind> [+ rationale]: <description>` using `guided-modification`,
  `familiar-independent-task`, `novel-transfer`, `unfamiliar-tradeoff`, or
  `architecture-defense`. The selected Finish contract determines the minimum number, lateness,
  kind, rationale evidence, and final-Working inclusion. Make multiple performances genuinely
  different and complementary. Each description must demand only the language capabilities its
  novel task materially exercises; across the full performance set their union covers the required
  spine. Never make every performance repeat the whole capability checklist or manufacture
  unrelated project work to force coverage. The final Working's complete-spine `requires` is a
  cumulative graduation contract, distinct from the capability subset graded for its novel
  performance.

Then write `**Mastery proof:**` naming those late graded language performances, the novel language
transfer each demands, which exact implementation help is withheld, and where the learner records
or demonstrates a rationale. Explicitly name the declared language.
A finished reference project or successful harness replay proves solvability, not student
independence. For Finish 3, plan at least two late language-transfer performances including the final
Working; they may reuse learner-authored interfaces and checks, but cannot be mechanical copies
of lesson examples.

Keep scope cuts in the internal Graduate ledger; Phase 2 shelf copy stays positive.
The Graduate ledger must separately state what the learner CAN and still CANNOT do in the
declared language. Each Section-list promise should identify how that project milestone advances
or retrieves the language capabilities it materially needs so Phase 2 can keep practice cumulative
without assigning unrelated mechanisms merely to distribute the spine.

Make cross-section state explicit:

- `Continuity map`: one physical `sNN -> sMM: promise` line for every non-adjacent reuse
  of an API, file, data shape, asset, launch path, or learner-visible behavior. Every target
  must be a real later section, and every dependency must have one earlier owner.
- `Artifact lifecycle`: canonical files/entrypoints plus every temporary prompt, fixture,
  demo mutation, mock, placeholder, or debug behavior and the section that retires,
  replaces, isolates, or intentionally ships it. In strict v2+ plans, wrap every inventory
  artifact—and no other token in this field—in backticks; the gate requires exact equality with
  `Artifact ownership`.
- `Artifact ownership`: one physical semicolon-separated, exhaustive inventory of every stable
  learner-owned path or artifact identifier used by a Working. Use
  `path @ sNN.working -> ships` for durable artifacts and
  `path @ sNN.working -> retires@sMM` for temporary ones. The owner is the first Working that
  creates or assumes responsibility for it; no earlier Working may list it, and the retirement
  section must be later. At every section, at least one artifact must already be owned and not
  yet retired, because every Phase-2 Working requires a real learner-owned artifact. Include the
  exact runtime entrypoint, every non-placeholder proof
  `expectedFiles` path, and package `requirementsFile` and `artifactPath` as shipped artifacts.
- `Delivery contract`: one physical line exactly
  `mode = runtime|package; artifact = path; requirements = path|none`. Use `runtime` only when
  the promised final result is the source entrypoint itself, with `requirements = none`. Use
  `package` whenever the Arc promises a packaged, standalone, installable, or distributable
  result; its artifact and requirements paths must be declared `ships`. This selection and its
  exact paths are sealed before Phase 2. Write every artifact, delivery, and requirements path as
  a normalized project-relative POSIX identifier: no leading, trailing, or doubled slash and no
  `.` or `..` segment. A directory artifact is `dist/tool`, never `dist/tool/`.
- `Acceptance proof`: the literal clean-start learner journey through setup, launch,
  meaningful use, persistence/relaunch where relevant, delivery, and end-to-end proof. Name
  the deterministic per-section build/run evidence the proof-v1 harness can execute. If the
  final artifact needs media, name only the licensed human-sourcing and placement journey;
  never plan AI-made assets, and keep the machine proof independent of them.
- `Acceptance scenarios`: one line of unique kebab ids separated by ` -> `, covering meaningful
  behavior, persistence/quit, and promised delivery. Phase 2 and execution preserve it exactly.
- `Section list`: one physical line per section, sequential, exactly
  `1. **s01 — Title:** capability/build promise`. The harness parses these lines to create
  Phase 2's section tree and section-level seed map; prose paragraphs, a different id/order,
  an unnecessary promise, or a count outside the bound does not pass the gate.

Produce only the completed Arc in the plan. Phase 2 turns it into tome files.
