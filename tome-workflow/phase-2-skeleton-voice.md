# Phase 2 — Skeleton & voice

Read **§2**. The harness already scaffolded `tomes/<id>/` (a green 1-section skeleton)
after Phase 0 — do NOT run new_tome.py or create the folder. Fill in the skeleton: meta →
runtime → content → **narrative (write the VOICE first — everything else quotes it)** →
defaults. Set `[content] sections` to your full arc's list and create each further section
by mirroring `sections/s01/` (`section.toml` + `lessons/l01.toml` + `freestyle.toml`, with
tome-unique ids) as a green skeleton — Phase 3 authors them one at a time.

⚠️ **Pick a distinct fiction word for each structural level and never reuse
one across levels.** A past tome called both chapters AND lessons "rites"
(with lesson numbering resetting per chapter) — ~600+ ambiguous references
across the prose where a reader can't tell if "Rite III" means chapter 3 or
lesson 3 of the current chapter. Chapter-level and lesson-level terms
(`opsLabel` and whatever you call a lesson in prose) must be two different
words.

→ **Produce:** a valid `tome.toml` skeleton.
