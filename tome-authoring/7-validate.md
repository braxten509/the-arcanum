# 7. Validate before you ship, then run the checklist

**Scaffold from `tools/new_tome.py` and validate mechanically first.** `python3
tools/new_tome.py <id>` writes a complete, valid skeleton (every required table
filled with placeholders and TODO markers) — begin there so you never fight a
structural error you introduced by hand. Before you ship, run:

```
python3 tools/validate_tome.py tomes/<id>
```

It machine-checks this spec: TOML parses; `meta.id` equals the folder name; runtime
resolves; ids are unique; every palette carries all 22 inks; rubric weights sum to
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
or a dyed (non-parchment) `bg1` page color is a `content` WARN. Two §3 integrity
lints run tome-wide: **identifier drift** (the same type name spelled two ways
across the code surfaces — `PushOp` in a lesson, `Push_Op` in the freestyle —
which breaks the cumulative build) and **self-answering questions** (a
`text`/`fill` whose answer appears verbatim in its own prompt prose; code spans
are exempt, since a trace question shows its answer by design).

New scaffolds set `[content].capabilityLedger = true`. With that contract enabled,
every lesson must carry non-empty kebab-case `teaches` ids and every freestyle must
carry non-empty cumulative `requires` ids; a future or misspelled requirement is an
ERROR. External-workspace ledgers reserve `tool-install`, `tool-create-open`,
`tool-navigate`, `tool-edit-save`, `tool-run-test`, and `tool-diagnose` for the first
section, plus `tool-deliver` for the final lesson/capstone. The validator also warns
when a later whole C# class example drops members present in an earlier version: show
a complete cumulative replacement or an explicitly located member-only patch.

**`--strict` fails on EVERY WARN except `advisory` ones** (language-calibration
limits no tome author can fix). This is the Phase 7 bar, and the harness runs it
from Phase 7 on: a finished tome carries zero warnings, whatever their label.
**It also runs your code.** By default the validator puts every `write` lab starter,
every intrusion starter, every spell-duel starter, and every whole-program lesson code
sample through the tome's own toolchain (`--no-run` skips it; a missing toolchain
degrades to a WARN — but a hard-gate one, so `--strict` fails a tome validated without
its compiler installed). Five failures nothing else can see:

- a **starter that does not build** — a student under the timer repairs logic, not a
  broken scaffold. Only a *build* failure is an ERROR: a good starter is deliberately
  incomplete, so it may well crash when run, and that is not a defect.
- a **pre-solved starter** that already prints the target `expect` (or output the
  lab's `expectRe` already accepts) — checked for labs, intrusions, and a duel
  starter that already prints its stage-1 transcript.
- a **lesson code sample that does not compile** — the tome teaching, as correct, code
  the language rejects. This is where "Odin that is really Go" surfaces (§3). Whole
  programs are an ERROR; on a language calibrated for it (§5 `snippetFragment` +
  `snippetWrap`), **fragment samples are compiled too**, wrapped in a scratch shell
  with declaration noise forgiven — a fragment the toolchain still rejects (a builtin
  the language doesn't have, syntax borrowed from a sibling language) is a hard-gate
  WARN.
- a **corrupted `code`/`starter`** carrying a literal `\n` from a `'…'` TOML literal.
- an **unachievable `expect`** — every write lab and intrusion carries a `solution`
  (§3); the validator runs it and ERRORs when its output does not satisfy the
  `expect`/`expectRe`, the proof the exercise is winnable. A challenge with no
`solution` is a hard-gate `run` WARN when the runtime can execute one-file
solutions; project-only runtimes that cannot do so receive an advisory WARN.
- a **loader failure** — after file-level checks, the validator calls the same
  `assemble_tome()` path as `/api/tome`; a tome that cannot merge its sections,
  banks, and resolved runtime into the client payload is an ERROR.

Every judgment is driven by the runtime's own TOML (`command`/`checkCommand` build and
run, `diagRegex` reads the output, `stringDelims` names the quote characters), so no
check assumes a particular language's syntax. An `expectRe` that does not compile is an
ERROR (the engine grades with `new RegExp(expectRe, "m")`, so a bad pattern is an
unwinnable lab). A language not calibrated for snippet checking, or one that cannot
build a lone file at all (dotnet), degrades to an **advisory** WARN naming how many
samples went unchecked — silence never impersonates coverage, and `--strict` does not
punish a tome for its language's limits.

A lesson body built from the same **sentence frames** as another lesson's — filler
stamped from one template and reworded — is a hard-gate `anti-template` WARN
(`--strict` fails it). A shop power-up that reuses the same normalized display name
for the same mechanic in another installed tome is a hard-gate `content` WARN. The
validator discovers those collisions across `tomes/`; it does not compare against a
hardcoded list of names printed in this guide.

**Fix every `ERROR` — a tome that still emits one is not done — and then fix every
`WARN` too:** under `--strict` (the shipping bar) only `advisory`-labeled WARNs are
tolerated. The checker enforces *structure*, not *content* — the human-judgement
items below (voice, anti-template variety, balance) are still yours to run:

- [ ] Every TOML file parses (`python3 -c "import tomllib; tomllib.load(open(f,'rb'))"`)
- [ ] `meta.id` == folder name; every `[content].sections` id has a matching
      `sections/<id>/` folder (or flat `sections/<id>.toml`) whose `id` matches
- [ ] Every exercise id unique; ids follow `<sid>-l<NN>-{e|d|w}<N>`
- [ ] Every exercise has a non-empty `prompt`; MC choices are non-empty and distinct;
      every `fill` has a real `____` blank; every `type.reps`, when set, is a positive integer
- [ ] Section titles are Title Case (one capital per word, acronyms excepted) —
      an ALL-CAPS `title` is a hard-gate `content` WARN; all-caps lives in `codename`
- [ ] Lesson titles follow the same Title Case rule; acronyms may stay uppercase,
      but an ALL-CAPS lesson `title` is a hard-gate `content` WARN
- [ ] Every `[[freestyle.rubric]]` weight set sums to exactly 100
- [ ] Every `mc` `answer` index is in range; every `write` has a NON-EMPTY `expect`
      or `expectRe` (no `expect = ""` — unwinnable, since empty stdout reads as `(no output)`)
- [ ] `expect` strings are exact program output — proven by each lab's `solution`
      under `--run`, not by eye
- [ ] Code the validator never compiled is still correct: fragments in a language
      without `snippetFragment` calibration (and excerpt shapes its
      `snippetFragmentSkip` waves through), `type` drill and `fill` `code` (both are
      excerpts), and every sample in a language whose runtime file has no
      `snippetEntry` (`java`, `dotnet`, `cpp` today — see §5). A clean run means
      "nothing it can build is broken", never "the code is right"
- [ ] Prose claims about the language verified against the toolchain (§3): every
      "this is a compile error / panics / has a capacity" sentence was checked in a
      scratch file, not recalled — the validator compiles code, it cannot fact-check
      a sentence
- [ ] Attack stages obey the append invariant; 3 stages per challenge
- [ ] Duel titles/briefs/tokens are in the course's OWN voice — no raw/technical
      worksheet text, no borrowed-genre leftovers (§4)
- [ ] intrusionTier/attack challenges solvable with only concepts taught by their gate
- [ ] `[defaults].theme` exists in `[[themes]]` (or is `"vellum"`, the global
      skin); shop `theme` references resolve; `earnedTheme.id` has `earned = true`
- [ ] All 22 theme vars present in every palette (incl. `slab`, `slab-tx`, `candle`, and `sigil-1`–`sigil-4`)
- [ ] Every authored theme's four-color sigil set is unique across `tomes/` (global skins exempt)
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
