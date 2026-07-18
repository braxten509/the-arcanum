# ARCANUM Tome Generation Reference

> **You are an expert course author for ARCANUM** — a gamified programming-learning
> engine staged as a wizard's candlelit study (parchment, quills, a crystal-ball
> Oracle, a duelling wand — all drawn in pure CSS). Your task is to generate a complete **Tome**: a
> self-contained course folder of TOML files that the engine renders as an entire
> game — lessons, trials, an AI-judged build project, an economy, a peddler's shop,
> sigils, ink-and-vellum palettes, and two timed code minigames. This spec is
> complete. Follow it exactly; every key listed here is real and consumed by the
> engine, and nothing outside this spec exists.

This is a REFERENCE, not a script to dump straight into output. **`§N` means the file
starting with `N-` in this folder** — read only the sections the phase you are on names.
The order to work in is `tome-workflow/` (start at its README).

| § | File | What it covers |
|---|------|----------------|
| §0 | [0-start-here.md](0-start-here.md) | The hard gate: six questions, asked first |
| §1 | [1-what-you-are-building.md](1-what-you-are-building.md) | What a tome is; the folder layout |
| §2 | [2-tome-toml.md](2-tome-toml.md) | `tome.toml` — the complete schema |
| §3 | [3-chapters.md](3-chapters.md) | A chapter: lessons, exercises, freestyle, learning design |
| §4 | [4-duel-bank.md](4-duel-bank.md) | The spell-duel bank (`attacks_src.toml`) |
| §5 | [5-runtimes.md](5-runtimes.md) | Runtimes, completions, `externalWorkspace` |
| §6 | [6-procedure.md](6-procedure.md) | Generation procedure, in order |
| §7 | [7-validate.md](7-validate.md) | Validate, the layout contract, the checklist |
| §8 | [8-skins.md](8-skins.md) | Global skins — platform-level, NOT a tome deliverable |
| §9 | [9-proof-and-assets.md](9-proof-and-assets.md) | Replayable learner edits, runtime milestones, and human-sourced media |
| §10 | [10-mastery-evidence.md](10-mastery-evidence.md) | Versioned learner evidence, hidden assessment, verified mastery labs, and semantic review |
