# Phase 7 — Validate (mandatory)

Run `python3 tools/validate_tome.py tomes/<id> --strict` and **fix every ERROR and
every non-`advisory` WARN** — a tome that still emits one is not done. `advisory`
is reserved for limitations the tome author cannot fix, such as a runtime that cannot
compile a one-file sample; every other warning is a shipping failure. In particular,
every `anti-template` and `content` WARN is a hard gate: a uniform shape, a fixed or starved mc index, a
reused hint/prompt/whyWrong/explain string, thin bootLines/gradingLines, missing
field-notes, a sub-300-word body median, or a naming drift between id and project
all mean the tome is machine-generated boilerplate; fix them until those WARNs are
gone. **The validator also hard-fails a *hollow* tome** once its TODOs are cleared:
a section under 3 lessons, a lesson under 4 exercises, a stub body (<180 visible
words; §3 wants 300–600), or one freestyle rubric cloned across sections all ERROR
as `density` — thinness is machine-generated boilerplate too, and these are the
floors of the §3 ranges, not new rules. It also ERRORs an `earned = true` palette
nothing grants, and an `externalWorkspace` tome whose first section links no
install resources (§5's MUST). It further ERRORs every file outside the layout
contract (a nested tome folder, backups, scratch, sections the manifest no longer
lists), a badge bank missing an engine-granted id (`grantBadge` literals in
web/app.js), a shop item selling the earned theme, an attack starter with
unbalanced braces, a `generated/attacks.toml` out of sync with `attacks_src.toml`,
and readings without an http(s) url; TODO/FIXME placeholder text anywhere is a
hard-gate `content` WARN. Then run the
human-judgement checklist in **§7** (voice, anti-template variety, balance,
coverage/no untaught dependencies, learning design). Smoke-test live: drop the folder
in `tomes/`, open `http://localhost:8777/?tome=<id>`, and walk the boot, a lesson, a
code lab, and the freestyle grader.

**Editing discipline (the badge-massacre rule):** fix each finding with the smallest
edit that removes it — NEVER rewrite a whole file to fix one line. After every edit
re-read the file and confirm every `[[array]]` kept its length and every id that
existed still exists; the harness diffs the file tree and content counts around each
phase and re-invokes you on unjustified shrinkage. **Renames:** the machine id is the
kebab-case of `[runtime] project` (§6); the harness derives it and renames the folder
(and `meta.id`) FOR YOU after Phase 2 — never `mv`/`cp` the tome folder yourself, in any
phase. The folder stays `untitled` until then; do not try to fix its name.

→ **Produce:** a tome with zero ERRORs and zero non-`advisory` WARNs, that plays.
