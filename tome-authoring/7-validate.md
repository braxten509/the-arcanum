# 7. Validate before you ship, then run the checklist

**Scaffold from `tools/new_tome.py` and validate mechanically first.** `python3
tools/new_tome.py <id>` writes a complete, valid skeleton (every required table
filled with placeholders and TODO markers) — begin there so you never fight a
structural error you introduced by hand. Before you ship, run:

```
python3 tools/validate_tome.py tomes/<id>
```

It machine-checks this spec: TOML parses; `meta.id` equals the folder name; runtime
resolves; ids are unique; every palette carries all 18 inks; rubric weights sum to
100; every `write` lab has a non-empty `expect`; attack stages obey the append
invariant; and more. It also gates *content* floors: lesson bodies clear a word
floor (§3's 300–600-word range), bootLines/gradingLines hit their counts,
field-notes coverage and mc answer-index balance are measured, an `earned = true`
palette must be granted by `[progression.earnedTheme]`, an `externalWorkspace`
tome must link its toolchain in the first section, and the tome id must be the
kebab-case of the project name (`ManaWeaver` → `mana-weaver`). It also audits the
*artifact*: every file must belong to the layout contract (a nested tome folder,
backups, or scratch files ERROR), the badge bank must define every engine-granted
id (the `grantBadge` literals in web/app.js), the earned theme must not be sold in
the shop, attack starters must have balanced braces, `generated/attacks.toml` must
match `attacks_src.toml`, readings need http(s) urls, and leftover TODO/FIXME text
or a dyed (non-parchment) `bg1` page color is a hard-gate `content` WARN
(`--strict` fails on those — the Phase 7 bar).
**Fix every `ERROR` — a tome that still emits one is not
done.** `WARN` lines are advisory (e.g. a consumable id outside the six engine
mechanics). The checker enforces *structure*, not *content* — the human-judgement
items below (voice, anti-template variety, balance) are still yours to run:

- [ ] Every TOML file parses (`python3 -c "import tomllib; tomllib.load(open(f,'rb'))"`)
- [ ] `meta.id` == folder name; every `[content].sections` id has a matching
      `sections/<id>/` folder (or flat `sections/<id>.toml`) whose `id` matches
- [ ] Every exercise id unique; ids follow `<sid>-l<NN>-{e|d|w}<N>`
- [ ] Every `[[freestyle.rubric]]` weight set sums to exactly 100
- [ ] Every `mc` `answer` index is in range; every `write` has a NON-EMPTY `expect`
      or `expectRe` (no `expect = ""` — unwinnable, since empty stdout reads as `(no output)`)
- [ ] `expect` strings are exact program output (verify mentally or via the runtime)
- [ ] Attack stages obey the append invariant; 3 stages per challenge
- [ ] Duel titles/briefs/tokens are in the course's OWN voice — no raw/technical
      worksheet text, no borrowed-genre leftovers (§4)
- [ ] intrusionTier/attack challenges solvable with only concepts taught by their gate
- [ ] `[defaults].theme` exists in `[[themes]]` (or is `"vellum"`, the global
      skin); shop `theme` references resolve; `earnedTheme.id` has `earned = true`
- [ ] All 18 theme vars present in every palette (incl. `slab`, `slab-tx`, `candle`)
- [ ] Themes only: every palette is a `[[themes]]` entry in this tome (in `themes.toml`,
      or inline in `tome.toml`) — nothing added under `skins/`, no structural CSS anywhere, and no palette
      re-creates the global Sepia Vellum or clones another of this tome's palettes
      (the validator measures both distances)
- [ ] Distinctive identity: the 3–5 palettes differ in paper tint, accent ink,
      and candle color; a palette wouldn't be mistaken for another course's
- [ ] Consumables reflavored: `name`/`desc` fit this course's world, not copied
      verbatim from another tome; every consumable id is one of the six engine
      mechanics (no dead cosmetic ids expecting an effect)
- [ ] Section count fits the material (arc built backwards from the finished tool),
      not padded or trimmed to a target number
- [ ] One evolving project: section 1 scaffolds it, each freestyle extends the
      SAME `runtime.project`, the last op ships the tool `meta.description` promised
- [ ] Economy: top rank ≈ total earnable; nothing unaffordable or trivially cheap
- [ ] Voice: bootLines, gradingLines, briefs, shop descs, badge descs all speak
      in the same persona
- [ ] One spelling: the machine id is the kebab-case of the project name
      (`ManaWeaver` → `mana-weaver`), never the requester's phrasing, and no
      `untitled` scaffold name survives to ship; caps branding, namespaces,
      translation keys, and artifact names all use the same letters — and every
      exercise/duel that DERIVES the id from a display string actually computes
      the id the rest of the tome uses
- [ ] Anti-template audit: no two `write` exercises share a prompt stem or starter;
      every lab prompt names its concrete inputs; `stdin` labs appear AND recur
      across later sections (not clustered in one); no lesson where mc/fill/text
      share one answer; no duplicated hint strings; mc answers not clustered on one
      index; no sentence repeated verbatim across lesson bodies
- [ ] Lab IntelliSense works: the resolved runtime carries a `[completions]`
      table (shipped language file, new language file, or `[runtime.completions]`
      inline) — open one code lab, type a taught receiver and `.`, and see members
- [ ] NEW language only: `[completions]` reaches full C# parity — all baseline
      keys populated, plus every parity key the language's features call for
      (`declTypes` if statically typed, `enumRegex`/`recordRegex` if it has those,
      `memberExtends`/`fallback`/`internalKeys`); `node tools/test_completions.js`
      passes with scenarios added for it (see §5's parity table)
- [ ] Nothing authored inside `save/`
- [ ] No stray files left outside `tomes/<id>/` — no generator/build/scratch
      scripts (`gen_*.py`, etc.), notes, or temp output anywhere in the repo

**To test live:** drop the folder into `tomes/`, open
`http://localhost:8777/?tome=<id>` — the boot sequence, first lesson, a code
lab, and the freestyle grader are the smoke test.
