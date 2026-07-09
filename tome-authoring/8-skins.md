# 8. Global skins — platform-level, NOT a tome deliverable (`skins/<id>/skin.toml`)

> **⚠ Tome authors: this section is reference, not license.** Generating a
> tome NEVER includes writing a skin. Skins deliberately break the constant
> parchment-and-candlelight staging, which is why only two exist — SEPIA VELLUM
> (the baseline palette, pinned to the top of the picker; palette-only, no
> structural CSS) and THE OPHIDIAN DEN — and why new ones are built only on a
> direct, separate request. If a tome needs a look, that's a `[[themes]]`
> entry (§2).

A tome theme swaps the inks. A **skin** swaps the entire visual identity:
typography, panel materiality, buttons, bars, the ambient layer — everything
except the mechanics. The engine's default look is already the candlelit study;
a skin can restage the whole desk without touching one line of `app.js` or
`index.html`. This section is the method for building one.

Skins are **platform-level**: they live outside `tomes/`, ship with every
tome's payload, and always appear in TRIM THE WICK → PALETTE (no shop
unlock), tagged in italics so they read apart from the tome's own inks —
*(theme)* when palette-only (no `css` key, like Sepia Vellum), *(skin)* when
structural CSS restages the desk (like The Ophidian Den).

### Anatomy

```
skins/<id>/
  skin.toml          # the whole skin: metadata + palette + structural CSS
  fonts/…            # any bundled assets — served at /skins/<id>/…
```

```toml
# skin.toml — NOTE: top-level keys (css) MUST come before the [vars] table,
# or TOML will parse them as members of [vars].
id   = "midnight-observatory"  # overwritten by the folder name — keep them equal
name = "MIDNIGHT OBSERVATORY"  # label in the TRIM THE WICK palette picker
desc = "Star charts and brass instruments in place of parchment and quills."
# light = true       # optional: skin is light-based (flips Monaco to its vs base)

css = '''
/* structural layer — see the method below */
'''

[vars]               # same 18 keys as a tome theme (§2 [[themes]]) — the
bg0 = "#100c07"      # engine AND Monaco read these; bg1/tx/ac/tx-faint/warn/info
# … all 18 …         # become the editor's colors automatically
```

The server ships every `skins/*/skin.toml` in the tome payload;
`tome-loader.js` injects `[vars]` as `body[data-theme="<id>"]{…}` plus the
`css` string verbatim; `editor.js` derives a Monaco theme from the vars. You
write TOML, the engine does the wiring.

### The method — how to restyle EVERYTHING without breaking anything

The engine's HTML/JS is the contract; the skin is pure CSS against it. Eight
rules — violate any one and you'll either leak styles into other skins or fight
the engine:

1. **Scope everything in one nested block.** The whole structural layer sits
   inside `body[data-theme="<id>"] { … }` using native CSS nesting. Nested
   rules automatically outrank the base stylesheet (they gain the attribute
   selector's specificity), and nothing can leak into other skins. Only
   `@font-face` and `@keyframes` go at top level — they can't nest.

2. **Restyle classes, never markup.** Every surface already has a stable class
   or id: `#hud`, `#parchment`, `#contents-rail`, the desk objects (`#candle`,
   `#obj-orb`, `#obj-grimoire`, `#obj-satchel`, `#obj-letter`, `#obj-wand`,
   `#obj-notes`, `#obj-tomes`), `.op-item`, `.btn`, `.exercise`, `.choice`,
   `.meter`, `.grade-card`, `.shop-item`, `.modal`, `.toast`, `.pop-menu`,
   `.tome-row`, `#boot`, `#term`… Read `web/css/` in the order `index.html`
   links it — one file per surface, and the filenames are the site map. If you
   think you need new HTML, you're designing a fork, not a skin.

3. **Re-declare the engine's knobs, then add your own.** Layout constants are
   CSS vars — override them inside your block: `--ctl-h` (control height),
   `--rad` (radius), `--hud-h`, `--rail-w` (contents rail). Then define the
   skin's private vocabulary as new vars. One place to tune, used everywhere.

4. **Split type into roles.** The base UI already splits four ways: `--arch`
   (archmage display — headings, labels), `--fell` (grimoire prose), `--hand`
   (the player's handwriting — every input), `--mono` (inscribed code: `pre`,
   `code`, `#term-out`, the editor). Override the role vars rather than
   per-element font-family. Bundle fonts as woff2 next to the TOML and
   reference them as `/skins/<id>/fonts/…` — never a CDN; the game must work
   offline. Keep subsets small.

5. **Repurpose `#tablelight` as your ambient layer.** It's a fixed,
   pointer-events-none, full-screen overlay the engine never touches after
   boot — the base skin breathes warm candlelight + vignette on it. Override
   its background and pseudo-elements for your atmosphere. Keep it GPU-cheap:
   one looping animation, `opacity`/`transform` only, and honor
   `@media (prefers-reduced-motion: reduce)`.

6. **Namespace new keyframes; explicitly kill inherited ones.** `@keyframes`
   are global — redefining a base name (`pulse`, `rise`, `sway`, `breathe`)
   would restyle every skin. Prefix yours (`obs-drift`, `obs-float`). And
   where the base skin *attaches* an animation you don't want, higher
   specificity is not enough — set `animation: none`.

7. **Respect the two engine invariants.** (a) Never put a *filling* transform
   animation (`animation-fill-mode: both/forwards`) on any ancestor of the
   Monaco editor — a filling transform becomes a containing block and breaks
   Monaco's fixed-position widgets (the base css documents this). (b) Don't
   restyle Monaco's internals (`.monaco-editor …`) — the editor themes itself
   from your `[vars]`; if the editor colors look wrong, fix the vars.

8. **Mind the TOML.** The `css` value is a literal `'''…'''` string: backslash
   escapes are NOT processed, so write CSS escapes raw (`content: "\25C6"`,
   one backslash), and the CSS may not contain `'''`. And again: `css` before
   `[vars]`.

### Skin validation checklist

- [ ] `skin.toml` parses; `css` key appears before `[vars]`; all 18 vars present
- [ ] Every rule (except `@font-face`/`@keyframes`) is inside the
      `body[data-theme="<id>"]` block; new keyframe names are prefixed
- [ ] Switch to every OTHER skin and confirm nothing changed (leak test)
- [ ] Walk every surface under the new skin: boot, the Ledger (title/meter/
      sigils/objective), chapter list, a lesson with each trial type, an
      inscription run, the Great Working (tabs, editor, speaking stone, chart,
      judgement card), the Peddler, the TRIM THE WICK modal, the tome switcher,
      a toast, a pop menu, the duel minigame
- [ ] Monaco: suggest widget opens crisply, cursor/selection colors match vars
- [ ] Fonts load from `/skins/<id>/…` with the network cable pulled (offline)
- [ ] `prefers-reduced-motion` stills the ambient layer
- [ ] Text contrast holds everywhere (`tx-faint` on `bg0` is the weakest pair —
      check it on the skin's actual backgrounds)

**To test live:** drop the folder into `skins/`, restart the server (skins are
read per request but the payload is fetched at page load), pick it under
TRIM THE WICK → PALETTE. The leak test — flipping back to VELLUM and seeing zero
difference — is the one that catches real bugs.
