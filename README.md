# ARCANUM — a modular coding-tome platform

A coding learning game staged as a wizard's study: a parchment on a candlelit
table, desk tools around it (a crystal-ball Oracle, a grimoire, a peddler's
satchel, a duelling wand), everything drawn with pure CSS geometry — no image
assets. The engine is a neutral framework; every course — its chapters, lessons,
trials, rewards, shop, titles, narrative, grader persona, and even the
**programming language/runtime** — lives in a self-contained **Tome** under
`tomes/`. Included course:

- **The Liber Veritatis** (`tomes/verisearch/`) — learn C# from nothing by forging the *Book of True Words*: a real CLI that pulls verbatim, source-attributed quotes from trusted sources. 12 chapters, judged by "MAGISTER THORNE" (an AI grader).

Drop another tome folder into `tomes/` and switch between them from the
leaning tomes on the desk (**OTHER TOMES**). Each tome keeps its own progress,
satchel, and title.

## Run

Needs **Python 3.11+** and nothing else (stdlib only — no `pip install`, no build).

### Easiest: double-click a launcher

| OS | Double-click | Notes |
|----|--------------|-------|
| **Windows** | `start.bat` | Finds Python (or sends you to python.org if it's missing) and starts the game. |
| **macOS** | `start.command` | Opens in Terminal. First time, macOS may block it — **right-click → Open** once, or run `chmod +x start.command`. |
| **Linux** | `start.sh` | Also frees the port from a previous run. |

Each one checks for Python, starts the server, and your browser opens to the
game automatically. Close the window (or `Ctrl+C`) to stop it.

### Or run it by hand

**Windows** (PowerShell or CMD): `python server.py`
**macOS / Linux**: `python3 server.py`

The server starts and your browser opens automatically. If it doesn't, go to
http://localhost:8777. Stop it with `Ctrl+C`.

- Pick a different port: `python server.py 9000`
- Don't auto-open the browser: set `ARCANUM_NO_OPEN=1` first
  (`$env:ARCANUM_NO_OPEN=1` in PowerShell, `export ARCANUM_NO_OPEN=1` in bash/zsh)
- **Linux only**, `./start.sh` is a convenience wrapper that also frees the port
  from a previous run before starting.

If `python`/`python3` isn't found, install it from [python.org](https://www.python.org/downloads/)
(on Windows, tick **"Add Python to PATH"** in the installer) — or `brew install python`
on macOS, or your distro's package manager on Linux.

## Requirements

- Python 3.11+ (stdlib only, uses `tomllib`) — serves the game, assembles tomes
- A runtime for whichever tome you play:
  - **dotnet** tomes: .NET SDK 8+ (`dotnet`)
  - **python** tomes: `python3`
  - **odin** tomes: the Odin compiler (`odin`)
- `claude` CLI (optional) — judges the Great Workings with Opus 4.8; falls back to a local Ollama model

## Layout

- `server.py` — stdlib HTTP server: tome discovery/assembly, per-tome state, runtime dispatch, background grading
- `runtimes/` — the one config-driven language engine (`generic.py` + `common.py`); languages themselves are pure TOML in `global-configs/runtimes/<name>.toml` — add a TOML to add a language, no Python ever
- `web/` — the engine UI (vanilla JS + Monaco, no npm). The candlelit-table scene, the parchment views, the study sounds (no music — a hearthfire-crackle ambience plus one-shot SFX, part synthesized, part sampled). Reads everything from `window.TOME`; `tome-loader.js` picks and loads the active tome
- `sounds/` — every recorded sound the study plays (candle ambience, pen strokes, spell-cast charge/release/fail); the rest are synthesized in `web/audio.js`
- `global-configs/` — cross-tome, platform-level tuning TOMLs: `sigil.toml` (the drawn spell sigil + its sound), `particles.toml` (cast bursts), `audio.toml` (every GhostAudio sound knob), and `runtimes/<name>.toml` (one per language — add a TOML to add a language, no Python ever); edit and refresh, no rebuild
- `skins/<id>/skin.toml` — optional global, tome-independent skins for the TRIM THE WICK palette picker: palette `[vars]` + optional structural `css` (scoped to `body[data-theme="<id>"]`) + assets served at `/skins/<id>/`
- `tomes/<id>/` — a course. Split into `tome.toml` (core config), the banks `themes.toml`/`shop.toml`/`badges.toml`/`intrusions.toml`, per-chapter folders `sections/<sid>/` (`section.toml` + `freestyle.toml` + `lessons/*.toml`), the optional `attacks_src.toml` (spell-duel reference solutions you author), and `generated/` (machine-written output — `attacks.toml`; never hand-edit). A tome may also use the older flat layout (one big `tome.toml` + flat `sections/*.toml`); the engine loads both via `tome_layout.py`.
- `tomes/<id>/save/` — that tome's progress: `state.json` (autosaved, power-outage safe), `grades/`, `workspace/<Project>/` (your build project). Delete `save/` to reset the course — the server recreates a fresh one. Never served over HTTP.
- `.cache/` — ephemera (snippet-run scratch, `server.log`); safe to delete anytime
- `tome_layout.py` — the one source of truth for how a split/flat tome reassembles; imported by both the server and `validate_tome.py`
- `tools/` — author tooling: `validate_tome.py <tome>` (machine-checks a tome against `TOME-AUTHORING.md`; exits 1 on any error, CI-friendly), `new_tome.py <id>` (scaffolds a new split-layout tome that passes the validator), `split_tome.py <tome>` (converts a flat tome to the split layout, losslessly), `gen_attacks.py <tome>` (language-neutral: regenerates a tome's `attacks.toml` from its `attacks_src.toml` through the live server). Every tool is language-neutral and tome-agnostic — no per-tome or per-language generators.

## Authoring a tome

See **[TOME-AUTHORING.md](TOME-AUTHORING.md)** for the full TOML schema.
The theming contract: each tome ships `[[themes]]` palettes (parchment inks —
`bg1` is the parchment, `bg0` the table wood, `slab`/`slab-tx` the terminal
stone, `candle` the light color) and the engine draws the same candlelit study
around whichever course is open.
