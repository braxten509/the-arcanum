# Tome workflow — the runbook for generating a tome

**This is the ENTRY POINT.** Interactive builds begin with `single-author.md`: one
resumable AI session follows every phase and its validator without changing hands.
`tome-authoring/` is the full reference; this folder is
the *order* to work in, so you execute the procedure instead of one-shotting a
thousand-line spec and dropping steps. Load each spec section only when its phase
calls for it — do not read the whole reference up front and start emitting TOML.
A phase that says "read **§3**" means `tome-authoring/3-chapters.md`.

Work the phases in order. **Finish and check each phase before starting the next**;
do not batch them. Some phases loop back (the economy can't be summed until the
sections exist) — that's expected and the order accounts for it.

One file per phase. The sole author reads them in order, so the H1 of each file must stay
`# Phase N — Title`.

0. [Gate: six course-shaping questions](phase-0-gate.md) — NEVER skip
1. [Concept & arc](phase-1-concept-arc.md)
2. [Skeleton & voice](phase-2-skeleton-voice.md)
3. [Sections, one at a time](phase-3-sections.md)
4. [Minigames](phase-4-minigames.md)
5. [Economy pass](phase-5-economy.md)
6. [Cosmetics](phase-6-cosmetics.md)
7. [Validate strictly](phase-7-validate.md) — mandatory
8. [Student review & gap-fill](phase-8-student-review.md) — mandatory
