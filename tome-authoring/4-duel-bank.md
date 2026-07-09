# 4. The SPELL DUEL bank (optional) — `attacks_src.toml` → `generated/attacks.toml`

You author `attacks_src.toml` (reference solutions); the tooling generates
`generated/attacks.toml` (never hand-edit that). The shape shown below is the
generated file; §4's tail explains authoring the source.

Player-initiated, timed, staked-credits code challenges. In ARCANUM's voice: a
rival caster hurls a hex and the player casts the exact counter to turn it, told
in the study's own tongue (sigils, wards, leylines, rites), never the old hacker cant.

**Duels must be in the course's OWN voice — same reflavor-per-course rule as shop
items (§2): the concept repeats, the flavor must not.** Titles, briefs, variable
names, and every printed token carry the tome's world. Never ship raw/technical
worksheet content or borrowed-genre leftovers (the old GH0STSHELL "IDENT / NODE /
BREACH" cant was exactly this mistake). The example below is arcanum's; a different
course dresses the same C# concepts in its own.

```toml
[[tiers]]              # difficulty = position (tier N unlocks after N sections passed)
[[tiers.pool]]         # 5+ challenges per tier; one picked at random
t = "THE NAME-FORGING"
starter = '''
string name = "vael";
int ward = 12;
// THE FIRST BINDING is set. Further demands may arm as the glass runs.
'''
[[tiers.pool.stages]]  # exactly 3 stages, arming at [progression].attackStages seconds
brief = "Forge the sigil block. Print exactly: «SIGIL vael @ WARD 12» — computed, not hardcoded."
expect = '''
SIGIL vael @ WARD 12'''
[[tiers.pool.stages]]
brief = "Append «KEY 48» (ward * name.Length, computed)."
expect = '''
SIGIL vael @ WARD 12
KEY 48'''
# …third stage: the full transcript again + its new lines
```

**The append invariant (critical):** each stage's `expect` is the COMPLETE
required stdout at that stage — `stages[n].expect` = `stages[n-1].expect` + new
lines. Each new hex only adds output; it never edits earlier lines. Stakes:
`diff * attackStakePerDiff` credits risked per duel (capped at the player's
purse). Winning pays no coin directly — wins bank toward the `earnedTheme`
palette; see `attackWinPerDiff` in §2 for the post-theme trickle.

**Generate this bank mechanically — it works for any language.** Author your
reference solutions in `tomes/<id>/attacks_src.toml` (in *your* tome's language,
whatever it is), then run `python3 tools/gen_attacks.py <tome_id>` with the server
up. The generator is language-neutral: it runs each `solution` through *this tome's*
runtime and slices the verified stdout into the stage `expect`s — C#, Python, Java,
Odin, all the same way. Each `[[challenge]]` needs `tier`, `title`, `starter`,
`briefs` (one per stage), `solution`, and `cuts` (the cumulative stdout line count at
the end of each stage; `len(cuts) == len(briefs)`, last == total lines). Do NOT
hand-edit the generated `attacks.toml` — edit `attacks_src.toml` and regenerate.
Hand-author `generated/attacks.toml` directly only when running solutions is impractical
(obey the append invariant above either way — and know a regenerate will overwrite it).
