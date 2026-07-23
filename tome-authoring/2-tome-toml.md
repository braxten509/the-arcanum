# 2. `tome.toml` — complete schema

### `[meta]` (required)
| key | type | notes |
|---|---|---|
| `id` | string | must equal the folder name |
| `name` | string | shown on the tome-switcher card |
| `description` | string | 1–2 sentences on the card: what you build, how many chapters |
| `author` | string | |
| `version` | string | semver-ish |
| `favicon` | string | 1–2 characters; becomes the browser-tab icon glyph (e.g. `">_"`, `"π"`) |

### `[runtime]` — the programming language (required)
| key | type | notes |
|---|---|---|
| `name` | string | runtime id → the uniquely named `<name>.toml` under `global-configs/runtimes/` (category directories are allowed). **No language is built into Python; every one is a TOML.** Shipped: `"dotnet"`, `"python"`, `"java"`, `"odin"`. Any other id works if a matching TOML is shipped, or if you set `command`/`runCommand` directly in this table (§5) |
| `project` | string | workspace project/folder name, e.g. `"Verisearch"` |
| `language` | string | display name; also used in grader/oracle prompts, e.g. `"C#"` |
| `packages` | bool | show the PACKAGES button (dotnet/NuGet only) |
| `editorLang` | string | Monaco mode for highlighting (`"csharp"`, `"python"`, `"go"`, `"odin"`, …). Any id works: one Monaco doesn't ship (e.g. `"odin"`) is auto-registered from the language TOML's `[syntax]` table (§5) |
| `entryFile` | string | file the runtime executes, e.g. `"Program.cs"`, `"main.py"` |
| `newFileExt` | string | default extension for the NEW FILE button |
| `starterCode` | string | contents of the entry file when the workspace is first scaffolded |
| `runLabel` | string | command shown in run/compile flavor text, e.g. `"python3 main.py"` |
| `validationDependencies` | string[] | third-party packages required to execute authored solutions/starters/samples during validation. The harness installs these only in an isolated validation environment or scratch project; it never changes the learner project or system runtime (§5) |

Every key in the matching runtime TOML is a **default** that this
tome's `[runtime]` table overrides key-by-key (`{language TOML} ∪ {your [runtime]}`,
your value winning). A typical tome sets only `name` and `project` and inherits the
rest; override `starterCode` (or any other key) when the default is wrong for this
course. The full key set — including the compile/run/diagnostics keys not listed
above, and the optional `externalWorkspace` (§5) — is documented in §5 and, canonically,
in the module docstring at the top of `runtimes/generic.py`.

Bindery course-map builds must override `starterCode = ""` and
`scaffoldCommand = []`. Their learner starts with an empty editor file and assembles every
canonical project artifact; hidden `referenceSteps` reconstruct the private proof project.

### `[content]` (required)
```toml
[content]
sections = ["s01", "s02", "s03"]   # ordered section ids; each maps to sections/<id>/
                                   # (split) or sections/<id>.toml (flat).
                                   # Order = unlock order (pass s01's freestyle to open s02).
# attacks = "..."                  # OPTIONAL override of the duel-bank path. Omit it: the
                                   # engine defaults to generated/attacks.toml (built by
                                   # gen_attacks.py). No duel bank? Just don't author one.
```
**Derive the section count from the contract, within 2 through 40 inclusive.** Work backward
from graduate capabilities, project milestones, dependencies, and acceptance proof. Every
section owns a necessary capability or integration milestone; removing one must break a stated
requirement. Pad nothing, cut no required teaching, and do not lower the promised mastery to fit.
Bindery-generated IDs are sequential `sNN` values in unlock order.

### `[defaults]` — a fresh save starts with these
```toml
[defaults]
theme = "shedskin"      # a [[themes]] id below — the tome's OWN signature
                        # palette, so opening this tome immediately reads as
                        # this tome. ("vellum", the global skin, is also legal
                        # but wastes the tome's identity.)

[defaults.ai]
oracle = "llama3.1:8b"           # the ORACLE mentor's model (an Ollama tag by default)
# oracleKind = "ollama"          # optional: where the ORACLE dwells — "ollama" (default)
                                 # | "claude-cli" | "antigravity-cli" | "codex-cli"
grader = "qwen2.5:14b"           # local fallback grading model
graderKind = "claude-cli"        # "claude-cli" | "antigravity-cli" | "codex-cli" | "anthropic"
                                 # | "openai" | "ollama" | "other"
graderModel = "claude-opus-4-8"  # model for the main grader
# graderCommand = "codex exec -" # kind="other" only: a shell command; the grading
                                 # prompt is piped to its stdin, JSON read from stdout
```
These are only the *defaults for a fresh save* — the player can change every one
of them later in the study settings. `"claude-cli"` + `"claude-opus-4-8"` is the
standard choice; keep it unless the course has a real reason not to.

### `[economy]` — every tunable, with engine semantics
| key | example | engine behavior |
|---|---|---|
| `ranks` | `[[0,"NOVICE SCRIBE"],[400,"APPRENTICE"],…]` | lifetime-earned coin → title in the HUD. 8–10 titles; make the top title ≈ total earnable coin |
| `hintCost` | `75` | credits to reveal an exercise hint (also marks the exercise as hint-used) |
| `oracleCost` | `10` | credits per ORACLE question |
| `attemptMultipliers` | `[1, 0.6, 0.3]` | points multiplier by attempt number (1st/2nd/3rd+). Typing drills and code labs never decay |
| `comboStep` | `0.05` | bonus multiplier added per consecutive correct answer |
| `comboCap` | `0.5` | max combo bonus (+50%) |
| `sRankMultiplier` | `1.5` | freestyle reward multiplier for an S grade |
| `attackStakePerDiff` | `20` | credits **staked** (lost on failure) per difficulty tier of an attack |
| `attackWinPerDiff` | `15` | duel wins pay NO coin until the `earnedTheme` palette is won; after that, every **2nd** win at the current circle pays `attackWinPerDiff × circle` (a post-theme trickle, not a per-stage payout) |

**Balance math you must do:** fixed face-value earnings = Σ exercise points +
Σ freestyle rewards. Intrusion bounties are repeatable bonus income: a player may
win none or may win the same tier many times, so never add each tier's bounty once to
invent a finite base total. Duel coin is another late-game trickle — see
`attackWinPerDiff` above. A freestyle pays `reward × total/100`
(× `sRankMultiplier` on an S), and re-submissions pay only the improvement over
the previous best — so budget freestyles at roughly their face `reward`. Price the shop so consumables are
affordable mid-course and cosmetic themes are late-game trophies (see the price
ladder in §2's shop). Rank thresholds should spread evenly across the fixed total;
the top title should land within about 15% of it. Sitting modestly above is reachable
because combos, S ranks, and successful defenses provide bonus income; sitting farther
below awards the final title while too much of the course remains.

### `[[shop]]` — one table per item
| key | notes |
|---|---|
| `id` | unique. For consumables, the id selects the **engine mechanic** (see below). For themes, any unique id |
| `kind` | `"consumable"` \| `"theme"` |
| `name` | ALL-CAPS themed label — **reflavor per course** (see below), e.g. `"WARD OF ABSORPTION (5 CHARGES)"` |
| `cost` | credits |
| `desc` | one flavorful sentence that also explains the mechanic, in the course's voice |
| `ico` | icon id, **consumables only** — theme items ignore any `ico` and always render the inkwell automatically, so don't set one. Full set: `save zap star chip eye bulb shield swatch file award upload pkg book x arrow terminal lock quill scroll cloak coin flame bell orb wand seal ink` |
| `charges` | consumables only: how many uses per purchase (omit = 1). **Exception: `x2` is engine-fixed at 20 charges — don't set it (any value is ignored), and balance the economy assuming each `x2` purchase buys 20 double-credit answers** |
| `theme` | kind=theme only: the `[[themes]]` id it unlocks |

**Consumable mechanics are a FIXED vocabulary of six engine abilities — the `id`
picks the mechanic, but you MUST reflavor its `name`/`desc`/`ico`/`cost`/`charges`
to the course's world.** These are deliberately generic (mitigate mistakes, boost
economy, bypass difficulty, reduce minigame risk, get help) so they fit any
subject; a consumable id the engine doesn't recognize renders in the shop but
**does nothing** (never invent new ids expecting an effect).

| `id` | mechanic (fixed) | example reflavors |
|---|---|---|
| `firewall` | absorbs wrong answers — no point decay while charged | `WARD OF ABSORPTION`, `SEGV GUARD` (a systems-language course), `TYPE CHECKER` (a typed-lang course) |
| `x2` | next 20 correct answers pay double credits (count engine-fixed at 20 — don't set `charges`) | `OVERCLOCK x2`, `PIPELINE BURST`, `CACHE HIT` |
| `skip` | instantly solves one trial at full points | `SCROLL OF REVELATION`, `NOP SLED`, `CHEAT SHEET` |
| `vpn` | deflects one incoming hex-defense hit per charge | `CLOAK OF UNSEEING`, `TRAP HANDLER`, `SANDBOX` |
| `xray` | reveals the grader's private `xray` notes for one Great Working | `SCRYING LENS`, `DISASSEMBLY PEEK` |
| `oracle` | grants one ORACLE (AI mentor) question | `ORACLE QUERY`, `MENTOR PING` |

Stock all **five** required power-ups — `firewall`, `x2`, `skip`, `vpn`, `xray` — each
with its own filled-in `name`, `desc`, `cost`, and `ico` (the validator errors on a
missing or blank one). `oracle` is an optional 6th (it needs a `[runtime]` oracle model).

**How to modify a power-up:** the engine ships a generic default for each of the five
(in `web/app.js`'s `DEFAULT_CONSUMABLES` — flavorless English, so mechanics never break
mid-build). You **override** a default by declaring a `[[shop]]` entry with that `id` in
the tome's `shop.toml`: your `name`/`desc`/`cost`/`ico` (and `charges`) replace the
default's, field for field. That per-tome `shop.toml` is the *only* place power-ups are
edited — you never touch the engine defaults, and a finished tome always carries its own
reflavored five rather than leaning on them. `x2`'s charge count is engine-fixed at 20 —
don't set it; give `firewall`/`vpn` a `charges` of 2+.
Reusing the same six names verbatim across every course is a review failure — the
mechanics repeat, the flavor must not. (If a course genuinely needs a *new*
mechanic, that's an engine change, not a TOML one — request it separately.)

Typical price ladder: consumables 400–900, themes 2200–3500.

### `[[badges]]` — the badge registry
`id`, `name`, `desc`. **Load-bearing ids the engine grants automatically:**
`combo-10` (10 correct in a row), `first-defense` (first intrusion-defense win),
`atk-1` / `atk-5` (1st / 5th duel won), `atk-ice` (duel-win count reaches
`blackIceThreshold` — pairs with `[progression.earnedTheme]`), `ghost-protocol`
(every chapter's Great Working passed). Each chapter's `[freestyle.badge]` adds its
own badge on a grade of C (70) or better — don't repeat those here. (The engine
also self-generates rank-title badges and per-chapter `<sid>-s-rank` badges with
their own names — those need no registry entry; register ONLY the six ids above.)

### `[[themes]]` — ink & vellum palettes (the tome's OWN look)

**THEMES, NOT SKINS — the platform policy (hard requirement):**
- A **theme** is palette-only: the 18 CSS vars below, nothing else. It recolors
  the same candlelit study — paper tint, inks, candle light — and that is the
  whole point: opening another tome changes the *coloring and lighting* of the
  desk, never the desk itself. The parchment-and-candlelight staging is the
  platform's constant.
- **Palette-only is necessary but not sufficient — you can abandon the study with
  the 22 vars alone.** Pushing `bg0` to `#000000` and the accents to neon makes a
  neon-on-black terminal: no CSS was added, but the candlelit desk is gone, and
  that restaging is a *skin's* job, forbidden here. Keep the material: `bg0` is
  the table **wood** (a timber/earth tone — dark is fine, pure-black void is not);
  `bg1`–`bg3` are **parchment** (tinted paper still legible as paper, even a deep
  "night vellum" — not a black screen); `candle` is a warm-ish **glow**, never a
  neon replacement. Recolor the study boldly; do not turn it into something else.
  The validator measures this on `bg1`: paper is warm (hue 10–95°) or near-neutral,
  and a *cool* hue may carry at most a whisper of tint (≤10% chroma — the shipped
  night palettes run 6–7%). A saturated purple/blue/green page is dyed paper, not
  parchment; a "Void and Gold" identity belongs in `bg0`, the panels, and the
  accents — never in the page itself.
- Themes are **exclusive to their tome**. They live in this file, ship only
  with this tome, and never appear in another tome's palette picker. Every
  tome MUST bring at least one signature theme of its own.
- A **global** (§8) is the opposite: platform-level (`skins/<id>/`), shared by
  every tome, and shown with an italic tag in the picker — *(theme)* if it is
  palette-only (no `css`), *(skin)* if it carries structural CSS that restages
  the desk. Exactly two ship: **SEPIA VELLUM** *(theme)* — the baseline palette,
  pinned to the top of the picker — and **THE OPHIDIAN DEN** *(skin)*.
  **A tome never adds anything under `skins/`.** Globals are built only on a
  direct, separate request — never as part of tome generation.
- Every tome gets the global skins automatically, so do **not** re-create
  Sepia Vellum (or anything near it) inside a tome — author fresh palettes.
  **This is now measured, not advised:** the scaffold's placeholder palette IS
  Sepia Vellum's values, and a past run shipped it renamed as its "signature"
  — a byte-for-byte replica. The validator computes each palette's color
  distance from the global vellum palette (and from this tome's other
  palettes) and hard-gates a near-copy; replace ALL 22 vars with a palette
  designed for this course.

```toml
[[themes]]
id = "shedskin"
name = "Shed Skin"      # label in the TRIM THE WICK palette picker
light = true            # parchment palettes are light-based (keys Monaco to its vs base)
# earned = true         # optional: unlockable ONLY via the duel minigame (not sold)
coin = "serpent"        # optional: the coin icon's face while this palette is equipped —
                        # star (default) | rune | gem | holed | serpent | sun | bolt | eye
                        # (pick the face that fits the tome's currency fiction; unknown
                        # names are a validator ERROR)

[themes.vars]      # CSS custom properties — ALL 22 required.
                   # (Values annotated with what each var paints; pick your own.)
bg0 = "#241609"    # the table wood (page surround)
bg1 = "#e7d9b5"    # the parchment itself (also the Monaco editor background)
bg2 = "#ddcda4"    # parchment panels
bg3 = "#d3c092"    # raised parchment elements
line = "#b9a67c"   # ink hairlines
line-hi = "#97815a"# highlighted hairlines
tx = "#3d2b17"     # main ink (also Monaco foreground)
tx-dim = "#6b5638" # secondary ink
tx-faint = "#8d7854" # faintest ink (also Monaco comments/line numbers)
ac = "#275d4d"     # the accent ink (also Monaco numbers/types/cursor)
ac-dim = "#3e7a67" # dimmed accent
ac-bg = "rgba(39,93,77,.10)" # accent wash
warn = "#8a5d14"   # warning ink (also Monaco strings)
bad = "#8e2f23"    # errors/danger ink
info = "#3d4d78"   # info ink (also Monaco keywords)
slab = "#27272b"   # the speaking stone (terminal) surface — STONE, not wood: a
                   # grey-led mineral tone (may lean warm or cool with the palette,
                   # but grey must dominate; never reuse bg0's timber browns)
slab-tx = "#e3d3ac"# the speaking stone's glowing script
candle = "255, 172, 66"  # a bare "r, g, b" triple, NOT hex/rgb() — it is used as
                         # rgba(var(--candle), …); "#39ff14" makes rgba(#39ff14, …),
                         # invalid CSS, and the candlelight glow vanishes (validator ERROR)
sigil-1 = "#f7ffff" # first casting ink
sigil-2 = "#62d9dc" # second casting ink
sigil-3 = "#168db4" # third casting ink
sigil-4 = "#3d4d78" # fourth casting ink
```

The four sigil inks are checked as one order-independent color set across every
authored tome. Another tome theme may reuse one, two, or three of them, but not all
four; moving the same colors between `sigil-1`–`sigil-4` does not make a new set.
Platform-wide skin themes under `skins/` are exempt from this uniqueness rule.
At runtime every main lightning stroke traverses all four inks, while its small
branches and release particles pick individual colors from the same set.

Injected as `body[data-theme="<id>"]` and mirrored into the Monaco editor theme —
one source of truth. Provide: 1 signature default palette (the `[defaults].theme`),
2–3 purchasable palettes (matching `kind="theme"` shop items), and optionally 1
`earned = true` palette granted by `[progression.earnedTheme]`.

**Give the course a DISTINCTIVE identity within the study.** The contract is a
candlelit table: `bg0` is the wood, `bg1`–`bg3` the parchment, `candle` the light.
Most palettes are light parchment (`light = true`); a dark palette (night vellum,
pale script) omits `light` and reads as writing after midnight. Vary the paper
tint, the accent ink, and the candle color between palettes — a cold blue-lit
"moonlit" page feels utterly different from an ember-orange one. Keep `warn`/
`bad`/`info` legible against `bg1`–`bg3`, and `slab-tx` against `slab`.

### `[narrative]` — the entire voice of the course
| key | notes |
|---|---|
| `objective` | **REQUIRED.** One or two sentences stating what the whole tome builds toward — the project the player ships. Shown as THE GREAT WORK at the top of the Ledger. The server refuses to load a tome without it |
| `title` | browser-tab title, e.g. `"ARCANUM // LIBER VERITATIS"` |
| `logo` | the spine text at the table's top edge |
| `opsLabel` | contents-rail heading over the chapter list (default `"CHAPTERS"` — e.g. `"CANTOS"`, `"MOVEMENTS"`) |
| `graderLabel` | tolerated but NOT rendered — the tower name-plate is derived live as `<selected grader model> // graderPersona`, so it always names the model actually grading. Omit this key |
| `graderPersona` | the mentor's codename; used in the grading prompt AND the UI (including the tower name-plate) |
| `studentTerm` | what the mentor calls the player (`"apprentice"`, `"novice"`) |
| `currency` | the coin's long name (default `"coin"` — e.g. `"gold"`). The coin's *icon* is per-palette: `coin = "<face>"` on a `[[themes]]` entry (§ `[[themes]]`) |
| `currencyShort` | its suffix on amounts (default `"gp"` — renders as `400gp`) |
| `gradeScale` | `"S\|A\|B\|C\|D\|F"` (keep this scale; the engine's thresholds assume it) |
| `bootLines` | array of lines written by candlelight on first load. `{N}` is replaced with the chapter count. 8–12 lines; establish the fiction, the mentor, and the commission |
| `gradingLines` | array of flavor lines cycled while the AI grades (6–8, in-character) |
| `completeText` | banner when every chapter is sealed (optional) |

The persona matters: the grader LLM literally role-plays `graderPersona` speaking
to `studentTerm`, so write bootLines/gradingLines in one consistent voice — gruff,
terse, fair is the house style, but invent your own character per tome.

### `[progression]` — the two timed minigames
```toml
[progression]
attackTime = 180             # SPELL DUEL: total seconds in the sandglass
attackStages = [0, 60, 120]  # seconds at which the rival's demands 1/2/3 arm
blackIceThreshold = 10       # qualifying duel wins to earn the exclusive palette
blackIcePerDiffCap = 2       # per-circle cap on wins that count toward it

[progression.earnedTheme]    # optional — the duel-exclusive palette
id = "starlit"               # must match an `earned = true` [[themes]] entry
name = "STARLIT FOLIO"
desc = "Proof you answered every rival who came calling."

[[progression.intrusionTiers]]    # HEX DEFENSE: rivals' hexes arrive while studying
min = 0                      # sections passed before this tier can fire
time = 90                    # seconds to solve
bounty = 60                  # coin for shattering it
[[progression.intrusionTiers.pool]]  # 5+ challenges; one is picked at random
t = "THE COUNTERSIGN"           # title
brief = "A rival mimics our secret countersign. Compute the true key."
starter = '''
int a = 7;
int b = 6;
// print exactly:  KEY <a times b>   (compute it, don't hardcode)
'''
expect = "KEY 42"               # exact required stdout (single- or multiline)
solution = '''
int a = 7;
int b = 6;
// … the full working program. Never shown to the student; the validator RUNS it
// and errors if its output is not `expect` — proof the challenge is winnable.
'''
```
Author 4–6 hex tiers spanning the whole course; each tier's challenges must be
solvable with ONLY the concepts taught by chapter `min`. Briefs are one sentence
of fiction + the starter comments state the exact required output. **Always demand
computed values, never hardcodable ones** (the starter's variables force it).
Every challenge carries a `solution` (§3's write-lab rule) so the validator can
prove its `expect` is achievable.
