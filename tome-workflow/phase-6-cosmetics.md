# Phase 6 — Cosmetics

Read **§2 [[themes]] / [[shop]] / [[badges]]**. 3–5 palettes with genuinely different
paper tints, accent inks, candle colors, and sigil inks (22 vars each, one `earned`); shop entries
wiring the themes + the six engine consumables **reflavored to this course's world**.
Themes only — never a skin (nothing under `skins/`).

⚠️ **The signature palette must be DESIGNED, not inherited — the scaffold's
placeholder vars ARE Sepia Vellum's values.** A past run shipped the scaffold palette
untouched, renamed "…Vellum", as its signature look: a byte-for-byte replica of the
global baseline, zero identity. The validator now measures every palette's color
distance from the global vellum palette AND from this tome's other palettes, and
hard-gates a near-copy. Replace ALL 22 vars in EVERY palette with values chosen for
this course's world — different paper tint, different accent ink, different candle —
while staying inside the parchment staging rules below.

⚠️ **A theme RECOLORS the candlelit parchment study — it must not abandon that
material, and you can abandon it with the 22 vars alone (no CSS needed).** The trap:
setting `bg0` to pure black and the accents to neon turns the wizard's desk into a
neon-on-black terminal — that's a *skin's* job (restaging the desk), forbidden to a
tome, even though technically you only touched the palette. Stay inside the staging:
- `bg0` is the table **wood** — a timber/earth tone, dark is fine but **never `#000000`
  void**; `bg1`–`bg3` are **parchment** — tinted paper you could still read as paper
  (a "night vellum" is deep and muted, not a black screen).
- `candle` is **candlelight**: a warm-ish glow, and it MUST be a bare **`r, g, b`
  triple** (e.g. `"255, 172, 66"`), never a hex or `rgb()` — it's used as
  `rgba(var(--candle), …)`, so a hex renders NO candlelight (now a validator ERROR).
  Neon-green/red/cyan "candlelight" isn't candlelight; tint it, don't replace it.
- Recolor accents/inks freely and boldly per course — just keep the desk a desk.

→ **Produce:** `themes.toml`, `shop.toml`, `badges.toml`.
