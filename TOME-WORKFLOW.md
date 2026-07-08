# TOME-WORKFLOW — the runbook for generating a tome

**This is the ENTRY POINT.** `TOME-AUTHORING.md` is the full reference; this file is
the *order* to work in, so you execute the procedure instead of one-shotting a
thousand-line spec and dropping steps. Load each spec section only when its phase
calls for it — do not read the whole reference up front and start emitting TOML.

Work the phases in order. **Finish and check each phase before starting the next**;
do not batch them. Some phases loop back (the economy can't be summed until the
sections exist) — that's expected and the order below accounts for it.

---

## Phase 0 — 🚦 GATE: three questions (NEVER skip)

Read **§0** and **§6 step 0**. Ask the user at least **three** clarifying questions
(prior knowledge, scope/depth, tooling) and **WAIT for their real answers.** The
**Tooling** answer (internal / external / both) is expanded into a **Tooling policy**
block in the plan — obey it: it decides whether `externalWorkspace` is allowed and
whether the real external tools must be taught.

This gate is absolute. **Even in an autonomous / automode run, interrupt the run and
ask** — you can break out of automode, so do it. Never answer for the user, never
assume defaults, never proceed unanswered.

→ **Produce:** the user's three answers. Nothing else exists until they arrive.

## Phase 1 — Concept & arc

Read **§1** (and **§2 [content]**). Decide the finished tool the student ships, the
language, the fiction (operation name, mentor persona, student term), and the visual
identity. Fix ONE spelling of the project name and derive every other form from it
(`ManaWeaver` → `mana-weaver`), **never the user's request phrasing** (a past run
shipped `teach-me-how-to-make` as the id). **Do NOT rename or move the tome folder** —
it is already `untitled` (the harness scaffolded it after Phase 0) and must STAY that
way until the harness renames it. Record the chosen name in `[runtime] project` (you
write that in Phase 2); the HARNESS renames the folder AND `meta.id` to its kebab-case
after Phase 2 — never `mv`/`cp` the tome directory yourself, in this phase or any other.
Design the op arc **backwards from the finished tool** — what capability does each op
add? The section count is an **outcome of that arc, not a target**; do not pad or
trim to a round number.

⚠️ **The end product must be REAL — never simulate away the skill the course is
about.** The worst failure here is not a short course, it's a *hollow* one: it
teaches *about* the subject with mocks the engine can conveniently compile, instead
of teaching the student to actually *do* it. If the course promises the student can
DO X, then X's real tools and load-bearing fundamentals ARE the syllabus, however
hard they are to teach.
- **Concretely (the pattern, not a template to copy):** a reverse-engineering course
  whose "memory reads" and "function hooks" are plain-language stand-ins — no real
  disassembler, debugger, binary format, or artifact that actually loads — leaves the
  student able to *recognize* the ideas, not *perform* them. The real syllabus was the
  format, the calling conventions, the debugger, real hooking, a loadable build. The
  same trap exists in any tool-centric domain (OS internals with no boot, networking
  with no real packet, embedded with no flashed board).
- **Teach RECONNAISSANCE, not just the action.** The commonest half-course teaches how
  to *act on* a target but not how to *find* it. A reverse-engineering course that hands
  the student the addresses (`0x00401000`) and teaches only how to write the hook has
  skipped ~70% of the real job — *finding* the function and struct offsets with a
  disassembler (Ghidra/IDA), a debugger (x64dbg), and a memory scanner is the actual
  skill. Same shape everywhere: teach how to *find* the bug/packet/leak/offset, not only
  what to do once someone hands it to you.
- **Smell test, applied at concept time:** after the last op, could the student sit
  down with the *real* tool and a *real* target and do this unaided — including finding
  the target themselves? If every lab is a mock the engine ran for convenience, or every
  address is handed to them, the answer is no — and `meta.description` is promising an
  artifact the course never builds.
- **If the real toolchain can't run in the built-in workbench, that is precisely what
  `externalWorkspace` (§5) is for — commit to it HERE.** Downgrading to a mock to stay
  inside the default editor is the trap, not the workaround. If you genuinely must
  simulate part of it, say so plainly and don't promise a real deliverable you didn't
  build.
- **Obey the plan's Tooling policy (internal / external / both).** INTERNAL forbids
  `externalWorkspace` and any external download/install — everything runs in-browser.
  EXTERNAL and BOTH require teaching the real external tools (named in section 1 with
  `[[lessons.readings]]` links); set `externalWorkspace = true` where the real toolchain
  can't run in the browser. The validator enforces these; don't fight it.
- A deep, tool-centric domain taught to a newcomer is therefore a **from-zero course
  sized to its fundamentals and toolchain** — the fundamentals are their own chapters,
  not footnotes folded into one small artifact's build.

→ **Produce:** the ordered section list + one line on what each op contributes.

## Phase 2 — Skeleton & voice

Read **§2**. The harness already scaffolded `tomes/<id>/` (a green 1-section skeleton)
after Phase 0 — do NOT run new_tome.py or create the folder. Fill in the skeleton: meta →
runtime → content → **narrative (write the VOICE first — everything else quotes it)** →
defaults. Set `[content] sections` to your full arc's list and create each further section
by mirroring `sections/s01/` (`section.toml` + `lessons/l01.toml` + `freestyle.toml`, with
tome-unique ids) as a green skeleton — Phase 3 authors them one at a time.

→ **Produce:** a valid `tome.toml` skeleton.

## Phase 3 — Sections (one at a time)

Read **§3** (including the anti-template and learning-design rules). For each section
in order: brief → lessons (§3a, vary 3–8 by material) → exercises per lesson (vary
4–6, mix all five types, diagnostic `mc` distractors + `whyWrong`) → the freestyle
(§3b) that extends the ONE evolving project. Concepts strictly cumulative — never
test what no earlier lesson taught.

⚠️ **Harness / subagent runs: the unit of content work is one SECTION, never one
lesson.** A per-lesson worker fed a templated brief produces the ~100-word-stub tome —
28 workers, one implicit length budget, 28 identical stubs that pass structure and
teach nothing. Each section worker's prompt MUST carry, in full:
1. **§3 + its learning-design rules VERBATIM** — not summarized. Whatever stays
   behind in the reference never reaches the writer; the past run honored exactly
   the rules that were pasted into its prompts and dropped the rest (word count,
   field-notes, code-first prose).
2. **The `[narrative]` voice and the Phase 1 arc line for this op** — so the section
   knows what it contributes to the finished tool and speaks in the mentor's voice.
3. **The previous section's finished TOML** — so concepts stay cumulative, callbacks
   reach backward (interleaving), and no sentence repeats verbatim.
A worker that can't see the pedagogy spec can't follow it.

⚠️ **Do NOT spawn your own subagents.** The harness owns all parallelism — it is
what splits this phase into per-section workers (above). Inside your worker, author
the section yourself; never call a Task/Agent/subagent tool to farm out a section,
a lesson, or an exercise. Every sub-worker you spawn is one WE did not configure,
does not see the pedagogy spec, and cannot be steered or resumed — it is exactly the
templated-stub failure mode. One worker, one section, written in-place.

⚠️ **The three anti-template rules that get shipped broken most — do NOT skip.
Varying one of these while cloning another is NOT a win: a past run fixed shape and
mc-index but then stamped one canned hint/prompt per type across all 14 sections,
which is the same machine-generated failure wearing a different hat.**
1. **Vary the shape.** Not every section 3 lessons × 4 exercises in the same
   `mc … write` order. Lesson counts differ (3–8), exercise counts differ (4–6),
   order differs. An identical grid down the whole tome is a review failure.
2. **Spread mc `answer` indices across 0–3.** Never leave every correct answer on
   the same index — especially not all `0`, the default an AI drifts to.
3. **Every hint, prompt, whyWrong, and explain is written for THAT exercise.** ~180
   exercises ⇒ ~180 distinct hints/prompts. The trap is a generic per-type stem
   reused with no specifics — it passes a glance but teaches nothing:
   - ❌ canned: every write lab prompted *"Write a Python snippet that computes the
     observation from the provided values and prints it."* (same 52 times)
   - ✅ specific: *"The catalog lists 3 archive entries at sizes 40, 40, 512. Print
     `TOTAL 592` — sum them, don't hardcode."* (names this lab's data + output)
   Same for hints (name THIS exercise's token/offset/rule), whyWrong (name the
   specific misconception THIS distractor encodes), and explain. If you could paste
   the sentence onto a different exercise unchanged, it's too generic — rewrite it.

   After the last section, tally all four across the tome and fix them, then let
   `validate_tome.py` confirm (it WARNs on a uniform shape, a fixed mc index, or a
   hint/prompt/whyWrong/explain string reused too often).

⚠️ **`whyWrong` is MANDATORY on every `mc` — this is now a validator ERROR, not a
nicety.** It is the highest-value feedback channel: one sentence naming the specific
misconception the wrong answers encode. That only works if the distractors are worth
diagnosing — the two go together:
- **Distractors must be plausible misconceptions, never joke/filler.** "Uploads it to
  the cloud", "Transforms it into HTML", a keyword that doesn't exist — nobody picks
  these, so they test nothing. Every wrong choice should be a mistake a real learner
  would actually make (an off-by-one, a swapped side, the almost-right API name).
- **The mix per lesson must vary too** — not one of each of mc/text/fill/type/write in
  every single lesson. Identical composition across all lessons is the same grid tell
  as identical counts (the validator now WARNs on it).

⚠️ **Recall-drill the DOMAIN's un-labbable concepts, not generic language 101.** A
`write` lab runs one plain file, so it can never exercise the framework/RE material a
course is actually about (memory layout, hooks, a registry, client-vs-server). That
material has to be carried by `mc`/`text` recall — so make those questions about the
domain (which side runs this? what's the struct offset? when does this event fire?),
not "what keyword returns a value". A reverse-engineering course whose recall is C# 101
drilled the wrong thing.

⚠️ **Honor the Phase 1 "real, not simulated" decision here too.** If the course
commits to a real artifact/toolchain (`externalWorkspace`), the labs and brief drill
the real thing; if any part is genuinely simulated, the lesson says so plainly rather
than implying the student ships something they didn't build.

⚠️ **Fade worked examples into problems — the type→fill→write ladder (§3 learning
design).** For a concept the student meets for the FIRST time, don't jump lesson prose
straight to a blank editor. Introduce it as a `type` drill (copy a correct, complete
example), then a `fill` (the same code with one load-bearing token blanked), then a
`write` lab (build it from scratch). The fully-worked example first, the from-zero lab
last — the advantage of a blank editor only appears once the student already has some
skill. A brand-new idea whose only practice is a from-scratch lab teaches worse.

⚠️ **Write labs: the starter sets up the scenario, the STUDENT writes the logic.**
Two hard rules the validator now enforces (`--run` executes every starter):
- **Never ship a pre-solved starter.** If the untouched starter already prints the
  target `expect`, the exercise is dead. Put a `// TODO`/comment where the student
  codes; the starter provides the data and the required output format, not the answer.
- **The starter must compile/run as given** — a scaffold with a syntax hole wastes the
  student's time on repair, not learning. It should build and run (printing nothing or
  a placeholder) until they add the real logic.
- Outside section 1, a lab whose `expect` can be satisfied by printing a string literal
  with no computation is hollow — force real work (compute from named inputs in the
  prompt/starter).

**ACCEPTANCE FLOOR (the validator hard-gates these at Phase 7 — build to them now, don't
discover them later):** every section ≥3 lessons (vary 3–8), every lesson ≥4 exercises
(vary 4–6), every lesson body 300–600 visible words with a FIELD NOTES appendix, every
`mc` a `whyWrong`, and each section's freestyle a distinct rubric summing to 100.

**END-OF-PHASE SELF-AUDIT (produce this, in the plan, before you stop).** After the
last section, tally and paste into the plan file — do not hand-wave it:
1. Per-section **lesson counts** and per-lesson **exercise counts** (prove they vary —
   an identical grid is a fail).
2. The tome-wide **mc `answer`-index tally** (0/1/2/3 each used a comparable amount).
3. A one-line confirmation you checked **no `write` starter is pre-solved** and each
   **compiles as given**, and that later sections **reach back** to earlier concepts
   (interleaving), not only test the current lesson.
If any tally shows the grid, a stuck index, or zero interleaving, fix it before Phase 4.

→ **Produce:** `sections/<sid>/…` for every section, built section by section, plus the
end-of-phase self-audit appended to the plan.

## Phase 4 — Minigames

Read **§2 [progression]** and **§4**. Author the intrusion tiers gated by `min` to
match the syllabus, and the duel bank via `attacks_src.toml` + `python3
tools/gen_attacks.py <id>` (server up). Both must be in the course's OWN voice.
Intrusions use `[[tiers]]` with an **integer** `min` and a `[[tiers.pool]]` of stdout
challenges (never a flat `[[intrusions]]` shape — the engine reads only `tiers`).
Both banks span the course: **3+ challenges per tier**, and enough tiers that the
later sections still unlock new hexes/duels (the validator WARNs when they don't).

→ **Produce:** `intrusions.toml`, `generated/attacks.toml`.

## Phase 5 — Economy pass

Read **§2 [economy]**. Sum all earnable credits (exercise points + freestyle rewards
+ intrusion bounties; duel coin is a late trickle). Set ranks, prices, rewards, and
hint/oracle costs so mid-course purchases and late-game trophies both exist.

→ **Produce:** a balanced `[economy]`.

## Phase 6 — Cosmetics

Read **§2 [[themes]] / [[shop]] / [[badges]]**. 3–5 palettes with genuinely different
paper tints, accent inks, and candle colors (18 vars each, one `earned`); shop entries
wiring the themes + the six engine consumables **reflavored to this course's world**.
Themes only — never a skin (nothing under `skins/`).

⚠️ **The signature palette must be DESIGNED, not inherited — the scaffold's
placeholder vars ARE Sepia Vellum's values.** A past run shipped the scaffold palette
untouched, renamed "…Vellum", as its signature look: a byte-for-byte replica of the
global baseline, zero identity. The validator now measures every palette's color
distance from the global vellum palette AND from this tome's other palettes, and
hard-gates a near-copy. Replace ALL 18 vars in EVERY palette with values chosen for
this course's world — different paper tint, different accent ink, different candle —
while staying inside the parchment staging rules below.

⚠️ **A theme RECOLORS the candlelit parchment study — it must not abandon that
material, and you can abandon it with the 18 vars alone (no CSS needed).** The trap:
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

## Phase 7 — Validate (mandatory)

Run `python3 tools/validate_tome.py tomes/<id>` and **fix every ERROR** — a tome that
still emits one is not done. **Every `anti-template` AND `content` WARN is also a
hard gate here, not advisory** — a uniform shape, a fixed or starved mc index, a
reused hint/prompt/whyWrong/explain string, thin bootLines/gradingLines, missing
field-notes, a sub-300-word body median, or a naming drift between id and project
all mean the tome is machine-generated boilerplate; fix them until those WARNs are
gone. **The validator also hard-fails a *hollow* tome** once its TODOs are cleared:
a section under 3 lessons, a lesson under 4 exercises, a stub body (<180 visible
words; §3 wants 300–600), or one freestyle rubric cloned across sections all ERROR
as `density` — thinness is machine-generated boilerplate too, and these are the
floors of the §3 ranges, not new rules. It also ERRORs an `earned = true` palette
nothing grants, and an `externalWorkspace` tome whose first section links no
install resources (§5's MUST). It further ERRORs every file outside the layout
contract (a nested tome folder, backups, scratch, sections the manifest no longer
lists), a badge bank missing an engine-granted id (`grantBadge` literals in
web/app.js), a shop item selling the earned theme, an attack starter with
unbalanced braces, a `generated/attacks.toml` out of sync with `attacks_src.toml`,
and readings without an http(s) url; TODO/FIXME placeholder text anywhere is a
hard-gate `content` WARN. (Other WARNs stay advisory, but read each one.) Then run the
human-judgement checklist in **§7** (voice, anti-template variety, balance,
coverage/no untaught dependencies, learning design). Smoke-test live: drop the folder
in `tomes/`, open `http://localhost:8777/?tome=<id>`, and walk the boot, a lesson, a
code lab, and the freestyle grader.

**Editing discipline (the badge-massacre rule):** fix each finding with the smallest
edit that removes it — NEVER rewrite a whole file to fix one line. After every edit
re-read the file and confirm every `[[array]]` kept its length and every id that
existed still exists; the harness diffs the file tree and content counts around each
phase and re-invokes you on unjustified shrinkage. **Renames:** the machine id is the
kebab-case of `[runtime] project` (§6); the harness derives it and renames the folder
(and `meta.id`) FOR YOU after Phase 2 — never `mv`/`cp` the tome folder yourself, in any
phase. The folder stays `untitled` until then; do not try to fix its name.

→ **Produce:** a tome with zero ERRORs and zero `anti-template`/`content` WARNs, that plays.

## Phase 8 — Student review & gap-fill (mandatory)

Validation proves the tome is well-*formed*; it cannot prove it actually *teaches*.
That last question — "would a real beginner come out able to DO this?" — is the one
that keeps failing (a course that drills C++ 101 instead of the domain; two payoff
chapters left hollow; the hook taught but never how to find what to hook). So close
the loop with a fresh set of eyes.

**The review needs clean eyes** — a first-time-student reviewer who knows only what the
tome's own prerequisites assume, not what the author knows. If you authored earlier
phases in THIS same context, spawn ONE clean-context subagent to be that student. If you
are a fresh worker with no authoring context (the harness case), you already ARE the
clean eyes — do the read yourself; spawning a child just reads the tome twice at double
cost. Either way, the student lens works like this:

- **Read EVERY chapter, cover to cover, in order — no sampling, no skimming, no
  reading only titles.** Every section brief, every lesson `body`, every exercise, every
  freestyle, from `s01` to the last. A review that skipped a chapter is void; the two
  chapters most likely to be broken are the *last* ones, exactly the ones a lazy review
  skips.
- Play it straight as a learner: at each chapter, note **what you can now actually do**,
  **what was used or assumed but never taught** (an untaught prerequisite, an address
  handed to you with no method to find it, a tool named but never shown), and **where the
  prose is missing, placeholder, or hollow**.
- End with the blunt verdict: **after the final chapter, could you sit down with the real
  tools and a real target and do the thing `meta.description` promises — unaided?** If
  no, name precisely what's missing.
- **Audit the artifact, not the story.** List every file under the tome folder
  (`find tomes/<id> -type f`) and justify each against the layout contract — a nested
  folder, a backup copy, or a scratch file is a blocking finding. Verify every claim
  in the build plan against the disk: a phase that logged "registered the 6 badges"
  must have six `[[badges]]` present NOW; claims are not evidence. Confirm the engine
  contracts: the badge bank defines every engine-granted id, shop theme items point at
  real `[[themes]]`, attack starters run as given. The meta files — badges, themes,
  shop, intrusions, attacks — are content too: read them in the tome's voice, not just
  the chapters.

**The same pass (or a second clean-context reviewer) also runs the §7 human-judgement
checklist as an editor** — voice consistency, anti-template variety, balance, coverage,
learning design — over the WHOLE assembled tome. This reviewer has the authority to
FAIL the run: a blocking finding from either lens (student gap or editorial checklist)
means the tome is not done, no matter what the validator said. The validator is the
structural gate; this is the editorial one — a harness run that ends at Phase 7 has
shipped unreviewed content. write the missing lesson bodies,
add the untaught fundamentals/reconnaissance as their own lessons or chapters, repair the
hollow chapters. Re-run **Phase 7**, then send the *revised* tome back through another
student pass. Loop until the student, having read every chapter, reports no blocking gap.
(Under the harness this loop is EXTERNAL: each invocation does ONE review + fix round and
writes its verdict; the harness re-runs the phase, scoped to the findings. Do not nest
your own loop inside a harness round.)

→ **Produce:** the student's per-chapter gap report + the revisions that answer it — a
tome that doesn't just validate, but actually teaches the thing it promises.
