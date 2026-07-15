# 6. Generation procedure — follow in order

0. **Ask the six questions FIRST — mandatory, never skip (see the §0 HARD GATE).**
   Before designing anything, ask the requester the SIX course-shaping questions
   and wait for the answers; the answers reshape every later step. This holds in
   EVERY run mode: even under autonomous/automode, interrupt the run and ask — never
   answer on the user's behalf, assume defaults, or proceed unanswered. The six:
   - Prior knowledge: "What can you already do — which languages/tools do you
     know?" (a Minecraft-mod tome for a Java veteran skips Java fundamentals;
     for a newcomer it must teach them)
   - Starting level (1–10): how much they already know about THIS subject —
     1 = zero, 2 = near zero with full foundations at a faster pace, 3 = beginner,
     4 = transfer learner, 5 = generalist, 6 = adjacent, 7 = practitioner,
     8 = fluent, 9 = advanced, and 10 = peer expert
   - Breadth (1–10): how much of the topic's surface — one tight path to the
     objective, or the whole territory (drives section count)
   - Lesson depth (1–10): how deep each lesson digs — just use it, or internals
     and edge cases (drives lesson density)
   - Mastery (1–5): what the student can do without step-by-step help after the
     last chapter — 1 = explain and modify guided examples; 2 = complete familiar
     small tasks and simple repairs; 3 = transfer concepts to novel real problems,
     integrate/debug them, and justify choices independently; 4 = handle unfamiliar
     variations and tradeoffs with minimal scaffolding; 5 = architect, validate, and
     defend a substantial solution from goals and constraints. Starting level controls
     the entrance; mastery controls how far scaffolding must fade by the exit.
   - Tooling: work inside the engine's own workbench, in the real external
     project/IDE (`externalWorkspace`, §5), or both? — and for externals, which
     exact tool versions
   A seventh (fiction/theme taste) is welcome; skipping the gate is a review
   failure.

1. **Concept & end product.** Pick the finished tool the student will genuinely
   build, the language, the fiction (operation name, mentor persona, student
   term), and a distinctive visual identity (signature accent hue).
   **One name, one spelling.** Fix the project's name here and derive every
   other form from it mechanically: display name `Runebound` → machine id
   `runebound`; a word boundary in the name (camelCase or a space) becomes a
   hyphen, so `ManaWeaver` → `mana-weaver`. Caps branding `RUNEBOUND`, matching
   workspace, package, and artifact names. Never drop or add letters between
   forms — an id that isn't derived from the display name reads as a typo in
   every prompt and path it appears in, and any exercise that computes the id
   by normalizing the display name will expect the wrong string.
   **The id NEVER comes from the requester's phrasing.** A past run shipped a
   tome whose folder was the user's request sentence (`teach-me-how-to-make`)
   instead of the project's name — the id is derived from the name fixed in
   this step, nothing else. Under the harness you never create OR rename the
   folder: it is scaffolded as `untitled` after Phase 0, and the harness renames
   it (folder AND `meta.id`) from `[runtime] project` after Phase 2. Then decide
   the op arc **backwards from the finished tool**: what capability does each op
   add? The number of ops is however many that arc needs (§2 `[content]`) — not a
   fixed target.
2. **`tome.toml` skeleton.** Start from the generated skeleton — `python3
   tools/new_tome.py <id> [--name N] [--language L] [--runtime R] [--sections N]`
   writes every required table valid-by-default with TODO markers. Then fill it in:
   meta → runtime → content (section ids) → narrative (write the voice FIRST;
   everything else quotes it) → defaults.
3. **Sections.** For each op: brief → lessons (vary 3–8 by how much the op
   genuinely teaches, body + field-notes) →
   exercises per lesson (vary 4–6, mix all five types, differing orders; every
   lesson ends with ≥1 `write` lab with concrete named inputs) → the freestyle
   that extends the ONE evolving project (brief with a <ul> checklist, rubric summing to 100,
   xray, badge). Concepts strictly cumulative; obey the anti-template rules in §3.
4. **Minigames.** intrusions bank gated by `min` to match the syllabus; the attacks
   bank via `attacks_src.toml` + `tools/gen_attacks.py` (§4).
5. **Economy pass.** Sum all earnable credits; set ranks, prices, rewards,
   hint/oracle costs so mid-course purchases and late-game trophies both exist.
6. **Cosmetics.** 3–5 `[[themes]]` palettes with genuinely different paper
   tints, accent inks, candle colors, and four sigil inks (22 vars each, one `earned`), shop
   entries wiring themes + the engine consumables **reflavored to this course's
   world** (name/desc/ico). Themes only — never a skin; the global SEPIA VELLUM
   and OPHIDIAN DEN skins join this tome's palette picker automatically. Every
   palette must be measurably distinct from Sepia Vellum AND from this tome's
   other palettes (the validator computes the color distance — the scaffold's
   placeholder vars are vellum's, so keeping them is an instant fail).
7. **Validate** against the checklist below.
