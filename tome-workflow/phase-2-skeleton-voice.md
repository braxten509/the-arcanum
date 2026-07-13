# Phase 2 — Skeleton & voice

Read **§2**. Fill the existing scaffold in Arc order: `[meta]`, `[runtime]`, `[content]`,
`[narrative]`, and `[defaults]`. Write the narrative voice before flavor text. Expand
the voice-bearing scaffold fields needed by those tables; Phase 6 still owns the finished
themes, shop, and badge banks.

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

Keep `[content].capabilityLedger = true`. Leave each skeleton lesson and freestyle with a
valid placeholder `teaches`/`requires` id for Phase 3 to replace; do not disable the
coverage contract.

Every tome names a reusable runtime file. If `global-configs/runtimes/<name>.toml` is
missing or incomplete, this phase may create or repair it. Read **§5**, copy an existing
runtime's TOML shape, use a toolchain installed on this host, and include the language's
run/check/scaffold, diagnostics, starter, syntax, and completion configuration. Keep
tome-specific overrides in the tome's `[runtime]` table.

Give the placeholder lesson in each section a distinct fiction-facing title so numbered
references cannot be ambiguous, but leave its body as an explicit Phase 3 placeholder.
The `--phase-2-skeleton` check deliberately ignores Phase 3 density, readings, prose,
exercise-variety, and TODO-clearance warnings; never try to satisfy those here. Produce
the complete green skeleton and, only when needed, its reusable runtime configuration.
Do not rename the tome folder; the harness does so after this phase.
