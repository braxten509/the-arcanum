# course-configuration-guide.md — the knob map for small course changes

You are making a **small, surgical change** to an existing course (a "tome") on
request — a typo, a wrong color, a price, a missing sentence. This file tells you
exactly where each knob lives so you touch one file, change one value, and stop.
For authoring whole courses, that's `tome-authoring/` / `tome-workflow/` — not
this file, and not your job here.

## Ground rules (read first)

0. **A question is not an edit request.** If the request only asks for information,
   an explanation, or advice — rather than instructing a change — answer it and make
   no edits. Don't touch a file just to have something to show for the run.
1. **Smallest possible edit.** Never rewrite a file to change a line. Never
   restructure, rename, or "improve" things the user didn't ask about.
2. **Never change ids.** Exercise/lesson/section/theme/badge ids key the player's
   saved progress (`tomes/<id>/save/`). Renaming an id silently wipes progress on it.
   Same for the tome folder name and `meta.id`.
3. **Keep every `[[array]]` its length.** Don't drop or add entries unless that IS
   the request.
4. **Don't touch engine code** — `web/`, `server.py`, `tools/`, `runtimes/`,
   `global-configs/`, `sounds/`, `skins/` (platform skins are never a course
   deliverable). A course change lives in `tomes/<id>/` only. Never edit another tome.
5. **Don't touch `tomes/<id>/save/`** (player progress) or
   `tomes/<id>/generated/attacks.toml` by hand (machine-generated — see Duels below).
6. **Validate when done** (mandatory):
   `python3 tools/validate_tome.py tomes/<id>` — 0 errors required; don't introduce
   new WARNs.
7. Bodies are **HTML strings inside TOML** `'''…'''` literals. Mind the TOML: no
   `'''` inside a literal block.
8. The course speaks in a fictional voice (`[narrative]` in `tome.toml` — mentor
   persona, currency, student term). Any text you add must match that voice.

## Where each knob lives (`tomes/<id>/…`)

| You want to change… | File | Field(s) |
|---|---|---|
| Course title / description / tab icon | `tome.toml` | `[meta]` `name`, `description`, `favicon` |
| Mentor persona, boot text, currency name, HUD logo | `tome.toml` | `[narrative]` `graderPersona`, `bootLines`, `gradingLines`, `currency`, `logo`, `objective`, `completeText` |
| Starting look of the course | `tome.toml` | `[defaults]` `theme` — a `[[themes]]` id, or a skin id under `skins/` |
| Rank names / thresholds, hint & oracle costs, scoring multipliers | `tome.toml` | `[economy]` `ranks`, `hintCost`, `oracleCost`, `attemptMultipliers`, … |
| Default AI models (oracle/grader) | `tome.toml` | `[defaults.ai]` |
| Language/runtime, starter code, entry file | `tome.toml` | `[runtime]` |
| Chapter title / brief text | `sections/<sid>/section.toml` | `title`, `codename`, `brief` (HTML) |
| Lesson prose (missing text goes here) | `sections/<sid>/lessons/<lNN>.toml` | `[[lessons]]` `title`, `body` (HTML, 300–600 words + a `field-notes` div) |
| An exercise: question, choices, right answer, hint, explanation | same lesson file | `[[lessons.exercises]]` — `prompt`, `choices`, `answer` (0-based index for `mc`), `whyWrong` (mandatory on `mc`), `hint`, `explain`, `points`; `write` labs also have `starter`, `expect`/`expectRe` |
| End-of-chapter project brief / grading rubric | `sections/<sid>/freestyle.toml` | `brief` (HTML), `[[rubric]]` (weights MUST sum to 100), `reward`, `[badge]` |
| A theme color | `themes.toml` | the 22 `[themes.vars]` keys (see below) |
| Shop item name / price / flavor | `shop.toml` | `[[shop]]` `name`, `cost`, `desc`, `ico` — never change `id` or `kind` (they bind the engine mechanic) |
| Badge names / art | `badges.toml` | `[[badges]]` `name`, `desc` — ids are engine-granted, don't change them. No `ico` field: the engine always renders a fixed seal icon for badges regardless of TOML content, so don't add one |
| Hex-defense minigame challenges | `intrusions.toml` | `[[tiers]]` (integer `min` gate) → `[[tiers.pool]]` |
| Duel minigame challenges | `attacks_src.toml`, then regenerate: `python3 tools/gen_attacks.py <id>` (server must be running) — never hand-edit `generated/attacks.toml` |

## The 22 theme vars (a `[[themes]]` palette)

`bg0` table wood · `bg1` parchment/page (also editor bg) · `bg2` panels ·
`bg3` raised elements · `line`/`line-hi` hairlines · `tx`/`tx-dim`/`tx-faint` inks ·
`ac`/`ac-dim`/`ac-bg` accent · `warn` · `bad` · `info` · `slab`/`slab-tx` code slabs ·
`candle` — the candlelight glow · `sigil-1`–`sigil-4` — the four casting inks
carried visibly along each lightning stroke and scattered through its released motes.

Color rules the validator enforces:
- **`candle` is a bare `r, g, b` triple** (e.g. `"255, 172, 66"`) — a hex value
  renders NO candlelight at all.
- **`bg1` must still read as paper**: warm hue (10–95°) or near-neutral; a cool hue
  over ~10% chroma is "dyed paper" and fails. Put bold color in `bg0`, panels, and
  accents — not the page.
- **No palette may sit close to the global Sepia Vellum palette or another of this
  tome's palettes** — the validator measures the color distance and fails near-copies,
  so a recolor must actually move the values.
- All 22 keys present in every palette; hex like `#rrggbb` everywhere except
  `candle` and `ac-bg` (an `rgba(...)` wash).
- The four `sigil-1`–`sigil-4` colors must form a set not used by any other
  authored tome theme. Sharing up to three colors is fine, but changing only their
  slot order is not. Global skin themes under `skins/` are exempt.

A palette may also pick the coin icon's face with a top-level `coin = "<name>"`
on its `[[themes]]` entry (next to `id`/`name`, NOT inside `[themes.vars]`):
`star` (default) · `rune` · `gem` · `holed` · `serpent` · `sun` · `bolt` · `eye`.
Unknown names are a validator ERROR. Pick the face that matches the tome's
`currency` fiction (e.g. `gem` for "shards", `serpent` for a snake-cult "scale").

## Content rules that bite small edits

- Changing an `mc` exercise's `choices` order? Update `answer` (0-based) and make
  sure `whyWrong` still names the actual distractors' misconceptions.
- Changing a `write` lab's `starter` or `prompt`? The `expect` string must still be
  the program's EXACT stdout, the starter must still compile as given, and must NOT
  already print the answer.
- Rubric weights in any `freestyle.toml` must sum to exactly **100**.
- `expect` values compare against normalized output (blank lines dropped,
  whitespace runs collapsed) — but keep them exact anyway.
- No `TODO`/`FIXME`/lorem text may remain anywhere (validator hard-gates it).

## After the edit

```
python3 tools/validate_tome.py tomes/<id>
```

Fix anything it reports that your edit caused. Then state, in one short paragraph,
exactly which file(s) and field(s) you changed and why — nothing else.
