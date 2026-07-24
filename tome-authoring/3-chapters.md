# 3. A chapter — `sections/<sid>/` (split) or `sections/<sid>.toml` (flat)

A chapter has three parts. **Split layout:** they live in separate files under
`sections/<sid>/` — `section.toml` (the keys below), `freestyle.toml` (the `[freestyle]`
table, §3b), and one `lessons/lNN.toml` per lesson (each holding a `[[lessons]]` block
+ its readings/exercises, §3a), ordered by filename. **Flat layout:** all three parts
sit in one `sections/<sid>.toml` as `[freestyle]` and repeated `[[lessons]]` tables.
The engine assembles either into the same chapter — write whichever you prefer.

Chapter keys (`section.toml`, or the top of the flat file):
```toml
id = "s01"                          # matches [content].sections and the folder/filename
codename = "CHAPTER I // THE FIRST FLAME" # heading label
short = "The First Flame"           # optional: compact label for the contents rail
title = "C# Basics & the Dev Environment"
build = "CLI shell skeleton — the tool's front door"  # one line: what this op adds to the build
brief = "Every tool starts with a heartbeat. …"       # HTML; section intro card
```

**Chapter titles are Title Case — one capital per word, never more, acronyms
excepted** (`"Java from Zero & the Ironwright CLI"`, never `"THE FIRST CUT"`).
All-caps styling belongs to the `codename`, which is the heading label; a `title`
whose every letter is a capital fails validation.

### `[[lessons]]` — 3–8 per section, sized by what the op teaches
`id` (`"s01-l01"`), `title`, `body` (HTML multiline literal string).

**Lesson titles follow the same Title Case convention as chapter titles.** Keep
acronyms such as `JSON` or `HUD` uppercase, but never use an all-caps lesson title;
all-caps styling belongs to labels such as the chapter `codename`.

**Let each section's material set its lesson count** — a setup op might need 3,
a dense op (state + config + events + sides, say) 5 or 6. Never more than 8:
past that, split the section. Uniform counts across every section read as
machine-generated (see the anti-template rules below).

**HTML vocabulary for `body`** (styled by the engine — use only these):
- `<p>`, `<strong>`, `<em>`, `<code>` inline
- `<pre><code>…</code></pre>` code blocks, with manual token tints:
  `<span class="k">keyword</span>`, `<span class="s">"string"</span>`,
  `<span class="c">// comment</span>`
- `<ul>/<ol>/<li>`
- `<div class="callout">…</div>` — a highlighted advice box (≤1 per lesson)
- `<div class="field-notes"><div class="fn-head">FIELD NOTES // …</div>…</div>` —
  an optional "deeper cut" appendix at the end of the body: edge cases, idioms,
  and pro details beyond the core lesson. Strongly recommended on every lesson.

Escape literal `<`/`>` in code samples as `&lt;`/`&gt;`. Lessons should be
300–600 words of body, concrete, code-first, and in the tome's voice.

When `[content].capabilityLedger = true`, every lesson also has
`teaches = ["stable-kebab-case-id", ...]`. Name observable abilities or implemented
boundaries, not vague subjects: `json-save-boundary`, `editor-play-mode`, and
`inventory-add-receipt` can be traced to code or tool actions; `saving` or `advanced`
cannot. These ids are the mechanical bridge to the freestyle's `requires` list.

**Every code sample must compile in the language the tome teaches.** The validator
builds each `<pre><code>` block that is a whole program through the real toolchain
(see §7), because the failure mode is not typos — it is writing the language you know
best while claiming to teach another. Odin is not Go: `make([]T, 0, 8)` takes an
allocator as its third argument, not a capacity; `v, ok := f()` needs `f` to return
two values; `a + b` does not concatenate strings; and Odin has no methods, so
`entry.show()` names nothing. Perl is not sed: a replacement containing a slash
(`s/x/<\/h1>/`) closes the substitution early — write `s{x}{</h1>}`. Before you write
a sample in a language you have not shipped before, build a scratch file with the
tome's `checkCommand` and confirm the idiom exists. A wrong sample teaches the wrong
thing far more loudly than a wrong exercise does.

**Prose claims are held to the same bar — and your prior will lie to you.** The
validator compiles code blocks; it cannot fact-check a sentence. Every claim about
the language's behavior — "this is a compile error", "this panics", "slices carry a
capacity", "`[a...b]` slices inclusively" — must be verified against the real
toolchain before it ships, exactly like a code sample: write the scratch file, run
it, watch it agree with you. The failure mode is specific: teaching a less-common
language, your training prior is polluted by its popular siblings, and the borrowed
fact *feels* true — Go's slice `cap`, Rust's debug-mode overflow panic, and C's
implicit-conversion rules have each been shipped as "Odin" by an author who never
checked. So prefer **demonstrating** a behavior claim in a code block over asserting
it in prose: a demonstrated claim is machine-checked on every validation run; bare
prose is checked only by you, once — which is why it is where the lies survive.
This covers `whyWrong` and `explain` text too: a wrong-answer explanation that
misstates the language plants the misconception it exists to correct.

**A cumulative project has one canonical source of truth.** If a later lesson changes
an earlier class/module/file, either show a complete replacement that preserves every
still-required member/import/behavior, or show member-only edits with the exact target
file and insertion/replacement point. A whole `class` wrapper visually promises a
complete replacement; never put an incomplete excerpt inside one. After changing a
canonical API, re-read every exercise choice, answer, hint, `whyWrong`, `explain`, and
freestyle line that names it—old feedback is still teaching, even when the body is fixed.

**Cumulative does not mean immortal.** Temporary teaching scaffolds—terminal prompts,
smoke-test calls, seeded state changes, debug prints, mock data, placeholder resources,
and transitional APIs—must be listed in the Phase 1 Artifact lifecycle and explicitly
removed, replaced, isolated, or declared part of the finished artifact. At each chapter
boundary, trace execution from the entrypoint's first line; never preserve an old demo
that blocks or mutates the real program the student is now building.

New strict builds also carry a machine-owned `Artifact ownership` inventory. Every stable
learner-owned path or artifact identifier used by a Working must be declared with its first owner
and either `ships` or `retires@sNN`. The Phase 2 seal rejects undeclared Working artifacts,
missing owner evidence, temporary artifacts that survive their retirement boundary, and shipped
artifacts absent from the final Working. V2 also rejects an artifact used before its declared
owner and reconciles the exact backticked lifecycle inventory with the runtime entrypoint, proof
expected files, package requirements file, and packaged artifact path. This contract is language-
and toolchain-neutral.

V3 also seals a Phase 1 `Delivery contract`: runtime versus package, the exact delivered artifact,
and (for package mode) the exact requirements path. Phase 2 cannot change package acceptance to
source execution, change the final proof mode, or substitute another output path. A Phase 1 Arc
that promises a packaged, standalone, installable, or distributable result cannot select runtime
delivery merely to make validation easier.

**Multi-line code goes in a `'''…'''` block, never a `'…'` literal.** TOML's
single-quoted literal string does not interpret escapes, so `code = 'a\nb'` ships the
student one long line with a `\n` punched through it. It parses, so every structural
check passes — and a `type` drill will then ask them to retype the corruption. The
validator ERRORs on a `code`/`starter` whose `\n` sits outside a string literal.

### `[[lessons.readings]]` — external links
`label`, `url`. An optional `essential` bool exists but is **rare**: it means the
course itself cannot fully teach that concept and the reader must study the external
doc to proceed. Most lessons have no essential reading — that is the normal state,
never a gap to fill. (The engine renders essential readings with an accented
ESSENTIAL tag in place of the usual OPTIONAL one; the validator WARNs when a tome
over-flags them.)
1–2 per lesson, only high-quality official docs/videos. **Every lesson needs at
least one** — how many and how deep is a judgement call, but zero is not: a
lesson with no anchor doc is the most common regression in the later, denser
chapters (validator WARNs on any lesson with zero readings).

### `[[lessons.exercises]]` — 4–6 per lesson, mixed types
Common fields: `id` (convention `"<sid>-l<NN>-e<N>"`, drills `-d<N>`, labs `-w<N>`;
ids must be unique per tome — they key saved progress), `type`, `points`,
`prompt` (HTML), `hint` (revealed for `hintCost` credits — every exercise should
have one, except `type` drills: the code to retype is already displayed, so a
hint would be dead weight; every shipped tome omits them there), and optional
`whyWrong` — **elaborated feedback shown the moment the student answers wrong**
(recall items only: `mc`/`fill`/`text`). One or two sentences naming the specific
misconception the wrong answer betrays and correcting it ("You picked the client
side — but world data only exists on the server; the client holds a copy it must
be *told* about."). This is the highest-value feedback channel there is: a miss
becomes a micro-lesson instead of a dead end. **REQUIRED on every `mc` — a validator
ERROR without it** (an `mc`'s distractors always have a diagnosable cause, so there
is no excuse to omit it); strongly recommended on `fill`/`text` wherever the wrong
answer has a diagnosable cause. It also fires in the spaced REVIEW round, so it keeps
teaching long after the first attempt.

| `type` | extra fields | behavior |
|---|---|---|
| `mc` | `choices` (array of strings), `answer` (0-based index), optional `code` (a code block shown above the choices), optional `explain` (shown after solving) | multiple choice |
| `text` | `answer` (string), optional `accept` (array of alternate correct strings), optional `code` | free-text input. Matching is forgiving: trimmed, lowercased, whitespace collapsed, trailing `;` and surrounding quotes stripped — so `accept` only needs true alternates (synonyms, other valid answers), not case/punctuation variants |
| `fill` | same as `text` | fill-the-blank; put `____` in the `code` block where the answer goes |
| `type` | `code` (the text to type), optional `reps` (default 1) | typing drill: retype the code exactly (whitespace-normalized), `reps` times. No point decay |
| `write` | `expect` (exact required stdout, **must be non-empty**) **or** `expectRe` (JS regex, multiline flag), optional `stdin` (piped input, `\n`-separated), optional `starter` (prefilled editor code), `solution` (a complete program that passes — see below) | CODE LAB: a real Monaco editor + the actual runtime. The program must produce the expected output. No point decay |

**Every `write` lab (and every intrusion challenge) carries a `solution`** — a
complete program that solves the exercise as a student would. The engine never
shows it; it exists so the validator can RUN it and prove the `expect` is
actually achievable. A miscomputed `expect` ("print `KEY 42`" when the starter's
values multiply to 41) ships an unwinnable lab, and nothing else can catch it —
the validator only sees your arithmetic error when your own solution's output
disagrees with your `expect`. Write the solution honestly (use the starter's
data, obey the prompt); a lab without one is flagged as never-verified.

**Never author an empty-output lab** (`expect = ""`): the runtime reports empty
stdout as the literal `(no output)`, so an empty target is impossible to satisfy —
and a program with nothing to print verifies nothing. Every `write` lab prints at
least one concrete line.

**Output comparison** (labs, drills, intrusions, attacks): line ends are trimmed,
internal whitespace runs collapse to one space, blank lines drop. Everything else
is exact — so write `expect` as literal program output, and in prompts always show
the target output verbatim.

**Points guidance** (with `attemptMultipliers = [1,0.6,0.3]` economics):
mc/text 15–25 · fill 20–25 · type 12–14 (reps 2) · write 30–35. Escalate slightly
in later sections.

**Anti-template rules — an AI author's most common failure mode is uniformity.
These are hard requirements, checked in review:**
- Every `write` prompt states a CONCRETE task: the specific values, inputs, or
  transformation ("sum the bytes 3, 5, 7 and print SUM 15" — never "compute any
  stated values" with no values stated). If the program must compute something,
  the inputs live in the prompt or the `starter` — an expect that can be satisfied
  by printing a string literal is acceptable only in section 1.
- Vary `starter` code per lab: set up the exercise's actual data/scenario. One
  starter skeleton cloned into every lab teaches nothing.
- Use `stdin` **when the program under study actually reads input.** For a course
  whose end product reads stdin (a CLI, a REPL, a filter), once input reading is
  taught piped-input labs must appear **and keep appearing across the remaining
  sections** — not clustered in the one section that teaches it; such a course with
  zero stdin labs, or one that demos input once and never revisits it, is broken.
  But `stdin` is the lab harness's ONLY input channel, so do not mistake it for a
  universal requirement: a course whose end product takes input another way — a GUI
  app, an event-driven mod (Forge/SMAPI), a library, a game script — never reads
  `System.in` in the real artifact. There, stdin labs are a **fundamentals-practice
  vehicle** (parsing, branching, looping over variable data), not a model of how the
  product ingests input. Keep them if they drill genuine language skills, frame them
  in the course's domain (parse a registry name, classify resource paths), and add a
  one-line lesson note that the real artifact takes input by GUI/event/packet — so
  students don't form the wrong mental model. Judge stdin coverage by whether the
  *product* reads input, not by a fixed quota.
- The mc/fill/text exercises within a lesson must have DIFFERENT answers testing
  different facets — never one answer word rubber-stamped across all three types.
- `fill` blanks are real code from the lesson with one token removed — never an
  invented pseudo-trace like `CONTRACT = ____`.
- Hints are exercise-specific (name the instruction, operand, or line) — never a
  recycled generic sentence. 180 exercises should have ~180 distinct hints.
- **Freeze identifiers.** The first spelling of every type/proc/field name is
  canonical for the whole tome: lessons, hints, starters, solutions, freestyle
  briefs, and all later sections reuse those exact letters. `Push_Op` with a
  `value` field in one section must not resurface as `PushOp` with `val` two
  sections later — the student's cumulative build stops matching what the prompts
  name. Keep a name ledger while authoring, and verify cross-references against
  it: a hint claiming a struct "was defined in Operation 9" must point where the
  definition actually lives. (`validate_tome.py` WARNs on case/underscore
  spelling drift across a tome's code surfaces.)
- A `text`/`fill` answer must never appear verbatim in its own prompt — "the
  operand is stored as a byte offset… what is this value called?" (answer:
  `offset`) tests reading the question, not knowledge. Ask for something the
  prompt doesn't already say. (`validate_tome.py` WARNs on it.)
- Vary structure — the single most common AI tell, so treat it as a hard rule.
  Do NOT emit the same shape in every section: 3 lessons × 4 exercises in a fixed
  `mc … write` order repeated down the whole tome is a review failure even when
  each exercise is individually good. Lesson counts must genuinely differ section
  to section (some 3, some 5–6, sized to the material, hard cap 8), exercise counts
  too (some 4, some 5–6), and the type order must differ. After drafting, list your
  per-section lesson counts and per-lesson exercise counts; if they are all
  identical you built the grid — go vary it. (`validate_tome.py` WARNs when every
  section shares one shape.)
- Spread mc `answer` indices across 0–3 — and CHECK it before shipping. Every
  answer on the same index — above all every answer = `0`, the value an AI drifts
  to by default — is an automatic fail: it makes the correct choice guessable and
  screams machine-authored. After each section, tally its mc answer indices and
  rewrite choices until 0/1/2/3 are each used a comparable number of times across
  the tome. (`validate_tome.py` WARNs on a single fixed index.)
- Write every lesson body fresh — no sentence may appear verbatim in more than one
  lesson. The rule is about the writing, not the wording: do not draft one filler
  paragraph and reword it per lesson to slip past the check. A synonym swap leaves
  the function-word skeleton (`the … of … to …`) identical, which is exactly what
  the validator measures, and clearing a word floor with padding is what the floor
  exists to prevent. The 300-word floor is a floor, not a target.

### Learning design — sequence exercises so they actually teach

The anti-template rules keep a course from being *boring*; these make it *stick*.
They encode what the research on learning is most sure of — **retrieval practice
and spaced/interleaved practice** are the two highest-impact study techniques, and
**worked examples** are the best-known way to keep novices from drowning in
cognitive load. Apply all four:

**Starting level and mastery are orthogonal.** A low starting level requires more complete
early explanation; it does not license a guided finish. Mastery 1–5 applies to the declared
implementation language. The requested project is the cumulative practice and proof vehicle, not
the mastery target. The plan's `Language capability spine`, structured `Language performances`,
`Language foundation coverage`, and `Mastery evidence` line form the exit-performance contract.
The foundation coverage maps the language's idiomatic data, control, decomposition, failure, and
verification mechanisms to distinct capabilities; it never substitutes framework behavior. At
Finish 3–5, routine failure handling cannot be scoped out and the late graded performances must
exercise every mapped foundation. The learner creates or assembles
every canonical project artifact
from the first section onward. Fade support across the whole course by making early Workings
smaller and more explicit, increasing hint distance, and broadening later specifications—not by
first supplying production code and later
withholding it. Complete worked examples must be small and disposable, with different
identifiers, values, and problem shapes from the real project. The validator's hidden reference
solution and reconstructed final project prove that the task is solvable; only the student's
graded Working can prove independence.

Every section's Working must apply its sealed `languagePractice` capabilities so language learning
does not stop after introductory snippets. At Finish 3, use at least two late graded language
transfer performances across the course, including the final Working. They must require a novel
extension, integration, or diagnosis rather than mechanical copying, renaming, or constant
changes, and at least one must grade a recorded rationale for a taught language choice. Each
chapter Working is the learner-visible project work order and must preserve meaningful
implementation choices while stating requirements, constraints, commands, diagnostics, and
observable checks. Do not repeat that work order beneath every lesson. Omit lesson
`artifactSteps` unless a genuinely necessary intermediate prerequisite must occur before the
Working; even then it may not provide canonical interfaces, fixtures, tests, filled data, or code.
Every complete project answer belongs only in hidden `referenceSteps`. Finish 4–5 broadens and
complicates the learner-owned work; Finish 1–2 uses smaller Workings and more explicit checks
without giving away artifact content.

- **Interleave — don't only test the concept a lesson just taught.** The weakest
  habit of an AI author is a course where every exercise quizzes the current lesson
  and nothing older. Deliberately fold earlier concepts back into later sections: a
  section-8 lab that still exercises the section-3 data model, an `mc` in section 6
  that contrasts a section-2 idea with a new one. Concepts stay cumulative (never
  test what hasn't been taught), but reach *backward* often.
- **The engine now resurfaces solved exercises in spaced REVIEW rounds** (a
  Leitner queue keyed to how many sections the student has completed, shown before
  a freestyle unlocks). Two authoring consequences: (a) write each exercise to
  **stand on its own** — no "using the value from the exercise above" or "as we
  just saw", because it may reappear ten sections later out of context; (b) this is
  free spaced retrieval of *your* material at no extra content cost, so it is worth
  making each item a clean, self-contained test of one idea.
- **Fade worked examples into problems (novice-heavy courses especially).** For a
  concept a student meets for the first time, a fully worked example beats throwing
  them a blank editor — the advantage only reverses once they have some skill. Use
  the exercise types as a fading ladder within a lesson: `type` (copy a correct,
  complete example) → `fill` (the same code with one load-bearing token blanked) →
  `write` (build it from scratch). Don't jump lesson prose straight to a from-zero
  lab for a brand-new idea.
- **First use must be an introduction, not an appearance.** Starting level is the complete
  entry baseline; optional prior-knowledge details add only the concrete skills they name.
  At Start 1–3, before requiring any unlisted keyword,
  syntax form, operator, API, tool action, or technical term, explain its purpose in
  plain language, walk through its parts or steps, show a minimal worked example and
  observable result, name a likely failure, and provide guided practice. A reading
  link or unexplained code sample does not satisfy this rule. Start 2 reduces
  repetition compared with Start 1; it does not remove concepts from the syllabus.
- **Match lesson density to the selected start.** Follow the plan's `Lesson pacing` line.
  Start 1 introduces one foundational concept family per lesson and separates independently
  teachable language, API, and tool families. Start 2 introduces one major family with only
  tightly related supporting material. Start 3 may combine multiple closely related families
  once prerequisites are secure and each receives complete first-use teaching and guided
  practice. A broad mechanism label must not conceal several independently teachable concepts.
- **Drill what the labs physically can't run.** A `write` lab runs ONE plain file,
  so it can never exercise framework/API concepts — a Forge registry, a client vs.
  server side, an event lifecycle, a GUI callback. In a framework course the
  hardest, most-explained material is exactly the material labs can't touch, so it
  gets practiced least unless you compensate: cover those concepts with `mc`/`text`
  recall drills (which side runs this? what is the registry name for X? when does
  this event fire?). Recall-drilling the un-labbable concepts is not optional in a
  framework/mod course — it is the only practice channel they have.
- **Ask "why", not just "what".** Self-explanation is a cheap, well-supported
  booster. Use the `explain` field on `mc` items, and phrase some prompts as a
  reason rather than a lookup ("why must this be `@OnlyIn(CLIENT)`?" over "what does
  this annotation do?").
- **Make `mc` distractors diagnostic, then correct them.** Every wrong `mc` choice
  must be a **plausible misconception a real learner holds** — an off-by-one, a
  swapped client/server side, a confused operator, the almost-right API name — never
  random filler or a joke option. A distractor that nobody would pick tests nothing;
  a distractor that encodes a specific mistake means the *wrong* answer is
  informative. Pair this with `whyWrong` (above): the distractors set the trap, the
  `whyWrong` explains why it sprang. Together they turn multiple-choice from
  recognition-guessing into real diagnosis.
- **"Thorough" means no coverage gaps, NOT more words.** Do not pad lessons to feel
  complete — a 600-word lesson that teaches one idea cleanly beats a 1,200-word one
  that buries it (extra words are extraneous cognitive load). The thoroughness that
  IS mandatory is *coverage*: no exercise, `write` lab, intrusion, duel, or
  freestyle requirement may depend on a concept, method, or identifier that no
  lesson in this section or an earlier one actually taught. Testing something you
  never explained is the most common way an AI-authored course silently breaks
  learning. Before shipping a section, walk every exercise and rubric line and
  confirm its prerequisite was taught first.

### `[freestyle]` — the graded capstone (required per section)
```toml
[freestyle]
title = "BUILD: The Verisearch Shell"
brief = "Turn <code>Program.cs</code> into …<ul><li>requirement</li>…</ul>"  # HTML; the <ul> IS the requirements checklist (shown as "IT MUST")
requires = ["cli-entry-loop", "validated-command"] # cumulative lesson `teaches` ids
reward = 200            # pays reward * (score/100), * sRankMultiplier on an S;
                        # a re-grade pays only the improvement over the previous best
packages = []           # allowed package installs for this op (dotnet tomes)
xray = "The grader docks points for: … He gives style credit for …"
                        # in-fiction "the grader's private notes" — revealed to the
                        # STUDENT by the scrying-lens consumable. The grader AI never
                        # reads this text, so it must truthfully describe what the
                        # rubric already rewards/punishes. Write real, specific
                        # pitfalls & style bonuses consistent with the rubric.

[freestyle.badge]
id = "badge-s01"        # convention: badge-<sid>
name = "FIRST CONTACT"
desc = "Built the shell — the front door of the whole operation."

[[freestyle.rubric]]    # 4-6 criteria; weights MUST sum to exactly 100
criterion = "Compiles & runs"
weight = 25
desc = "build succeeds; runs without crashing on normal input."
essential = true        # optional hard gate; the percentage/letter grade is still recorded
minimumScore = 6        # optional, defaults to 6/10 when essential = true

[[freestyle.verification]]
id = "project-tests"
command = "test"        # build | run | a key in the named runtime's [assessmentCommands]
label = "Project tests"
required = true         # failure blocks passing but does not erase the letter grade
args = []
stdin = ""
timeout = 120
expect = { exitCode = 0 }
```
**Every rubric must include one style/craft criterion (weight 10–20)** whose
`desc` names the language's actual conventions at the student's current level —
both NAMING and LAYOUT (e.g. "camelCase locals, PascalCase methods, Allman
braces" for C#; "snake_case, 4-space indent, no mutable globals" for Python).
**Research the language's current official/community style guide online while
authoring** (Microsoft's C# Coding Conventions, PEP 8, gofmt, the Ruby Style
Guide, …) and encode its load-bearing rules into these descs — the grader AI
runs WITHOUT web access, so the rubric is the only channel by which researched,
language-accurate conventions reach it. Rubrics live entirely in the section
TOMLs, so language-specific rules like brace style belong HERE, per tome —
the engine only adds one generic rule telling the grader to anchor style
judgments in the language's official style guide (from its own knowledge) and
to name each breach with the pattern to follow. This row is how students learn
good coding patterns, not just working code; be strictest about it in the
first two sections, where habits form.
The harness first creates an immutable project snapshot. Secret-named files,
dependency/cache/output directories, and `[runtime] excludeDirs` are omitted and
shown explicitly to the learner before consent. Declared verification commands
run against a writable copy of that snapshot inside a no-network Bubblewrap
sandbox; they never run against or modify the original workbench. The grader
then receives recursive **read-only** access to the verified copy plus `brief`,
`rubric`, and the verification output. Symlinks, non-regular paths, unreadable
files, and snapshot size-limit violations block grading.

The percentage and letter grade are always computed and shown. Passing is a
separate verdict: the score must be at least 60/D, every `essential = true`
criterion must reach its `minimumScore`, and every `required = true`
verification must pass. Thus a Working can receive an A while remaining
incomplete because one essential safety requirement failed. A passing C (70+)
also grants the badge; a passing S multiplies the reward. The freestyle unlocks
after 70% of the section's exercises are solved.

**Themed briefs vs. exact requirements — read this before writing the `<ul>`.**
The brief is written in the in-world voice, and the grader is told to read each
requirement by INTENT and resolve vague wording in the student's favour (it will
NOT dock points for missing atmospheric flavor). That means: **if a requirement is
actually strict, state it concretely — the flavor text alone will not be enforced.**
- Exact output? Put the literal string in `<code>` or quotes: `<code>Verisearch v0.1</code>`, `You asked: "…"`.
- Exact command/token? Name it: <code>quit</code>, the <code>&gt;</code> prompt.
- A required edge case? Spell it out: "an empty line must not crash or echo."
- Only atmospheric ("greets the seeker warmly")? The grader accepts any reasonable take — fine for soft goals, useless as a hard gate.
Anything that MUST pass to earn the grade belongs in a rubric criterion too; the
`<ul>` tells the student what to build, the `rubric` is what actually scores it.
When the capability ledger is enabled, every checklist item and rubric criterion must
trace to one or more ids in `freestyle.requires`; every required id must already appear
in a lesson's `teaches` list in this or an earlier section. The validator enforces the
ordering and spelling; the Phase 8 student audit verifies the lesson genuinely teaches
what the id claims.

**The through-line: one project, built up op by op.** Every section's freestyle
extends the SAME evolving project (`runtime.project`) — section 1 stands up a
skeleton, each later section adds one real capability to it, and the final
section's freestyle ships the complete tool the tome's `description` promised.
Different courses have different end products (a search CLI, a byte inspector, a
task tracker, an interpreter…), but within a course it is always ONE codebase
growing, never a set of disconnected toy exercises. Plan this arc first — decide
the finished tool, then work backwards to what each op must contribute — and size
the section count to that arc (§2, `[content]`), not to a target number.

**The Working is where the project is constructed, not where lesson code is recopied.** Apply this
to every section, not only late mastery sections. Compare its checklist with all learner-visible
code, exercise solutions, starters, and any exceptional artifact steps. If those surfaces already
implement any canonical project requirement—or a version needing only renamed identifiers or changed
constants—the learner did not author that part of the artifact. Keep the hidden `referenceSteps`
complete so the harness can prove the task, while the learner receives requirements, constraints,
diagnostics, and observable acceptance checks.
