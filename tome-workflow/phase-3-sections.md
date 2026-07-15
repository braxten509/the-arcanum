# Phase 3 — Sections (the course)

Read `tome-workflow/support/section-author.md` and `tome-authoring/9-proof-and-assets.md`,
then author in Arc order, one complete section at a time: brief, lessons/exercises, and
cumulative freestyle. Each section adds its promised capability to the evolving project.
Never test material that this or an earlier lesson has not taught.

Stay in this author session for the entire section sequence. Gate each section before
advancing and reopen its files from disk. Repairs target only failures and never wipe the
tree. Phase-focused gates hide later-phase warning
details. A deferred count is informational: do not edit badges, shop, themes, economy,
attacks, or other later banks to clear it.

After authoring the assigned section and its continuity handoff, run exactly:
`python3 tools/validate_section.py tomes/CURRENT_TOME sNN --plan .tome-build/BUILD_ID.plan.md --tooling TOOLING --source-only`.
Read the complete report, repair only its findings, and rerun until it exits zero. This command
owns the pre-handoff TOML, pedagogy, replay, proof-source, and continuity checks. Do not inspect
validator source to guess at extra checks or replace it with hand-written parsing, replay,
word-count, exercise-distribution, or schema scripts. Then mark the section `validating` and
stop; the harness independently repeats the complete gate without `--source-only`.

Use the plan's calibration and `[narrative]` voice. Before changing a recurring type, file,
API, asset, or workflow, search all earlier sections. Preserve canonical contracts, retire
temporary scaffolding on schedule, and align feedback with final code. Run the active-contract
report before each section. `write` creates only; otherwise use exact replacement or an
all-active rewrite. The gate reruns active proofs. Repair later regressions without weakening
earlier proofs. Acceptance controls input/time/seed/frame limit but drives real behavior.

Produce the complete `sections/<sid>/` tree. Do not append a phase narrative or audit log
to the build plan.
