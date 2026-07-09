# Phase 4 — Minigames

Read **§2 [progression]** and **§4**. Author the intrusion tiers gated by `min` to
match the syllabus, and the duel bank via `attacks_src.toml` + `python3
tools/gen_attacks.py <id>` (server up). Both must be in the course's OWN voice.
Intrusions use `[[tiers]]` with an **integer** `min` and a `[[tiers.pool]]` of stdout
challenges (never a flat `[[intrusions]]` shape — the engine reads only `tiers`).
Both banks span the course: **5+ challenges per tier** (fewer makes repeat duels/hexes
at the same tier feel identical), and enough tiers that the
later sections still unlock new hexes/duels (the validator WARNs when they don't).

→ **Produce:** `intrusions.toml`, `generated/attacks.toml`.
