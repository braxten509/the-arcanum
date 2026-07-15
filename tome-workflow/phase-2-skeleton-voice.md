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
Copy Arc scenario order into `[acceptance]`; choose `package` for promised delivery,
otherwise `runtime`. Package runtimes need delivery argv.

Every tome names a reusable runtime file. If `global-configs/runtimes/<name>.toml` is
missing or incomplete, this phase may create or repair it. Read **§5**, copy an existing
runtime's TOML shape, use a toolchain installed on this host, and include the language's
run/check/scaffold, diagnostics, starter, syntax, and completion configuration. Keep
tome-specific overrides in the tome's `[runtime]` table.

The runtime must scaffold, truthfully build/check, and accept safe proof arguments on its real
run command. Never bypass it with a tome-controlled shell command.

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
Do not rename the tome folder yourself; run the Phase-2 transition command from
`single-author.md`, which renames it safely and prints the new current id.
