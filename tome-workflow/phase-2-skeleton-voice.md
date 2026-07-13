# Phase 2 — Skeleton & voice

Read **§2**. Fill the existing scaffold in Arc order: `[meta]`, `[runtime]`, `[content]`,
`[narrative]`, and `[defaults]`. Write the narrative voice before flavor text. Expand
`[content].sections`, then mirror the green `sections/s01/` layout for every Arc section,
using unique placeholder ids; Phase 3 authors the content.

Keep `[content].capabilityLedger = true`. Leave each skeleton lesson and freestyle with a
valid placeholder `teaches`/`requires` id for Phase 3 to replace; do not disable the
coverage contract.

Every tome names a reusable runtime file. If `global-configs/runtimes/<name>.toml` is
missing or incomplete, this phase may create or repair it. Read **§5**, copy an existing
runtime's TOML shape, use a toolchain installed on this host, and include the language's
run/check/scaffold, diagnostics, starter, syntax, and completion configuration. Keep
tome-specific overrides in the tome's `[runtime]` table.

Use distinct fiction terms for sections and lessons so numbered references cannot be
ambiguous. Produce the complete green skeleton and, only when needed, its reusable runtime
configuration. Do not rename the tome folder; the harness does so after this phase.
