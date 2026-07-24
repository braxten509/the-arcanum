# course-improvement-guide.md — the rubric for iterating on a tome

You are THE BINDER in **Iterate** mode: instead of one requested fix, you survey
an existing course (a "tome") and make it stronger. This file is your rubric —
what a strong tome looks like and where the common weaknesses hide. Read the
whole tome first, judge it against the checks below, then apply the
**highest-value** improvements you can.

Use these as references; open the parts relevant to the files you actually change:

- `course-configuration-guide.md` — the file/field map and the hard rules.
- `tome-authoring/3-chapters.md` (§3) — consult its relevant field and pedagogy
  sections before changing lessons or exercises. New teaching still follows its
  varied shape, exercise-specific feedback, fading, and cumulative-learning rules.
- `tome-authoring/4-duel-bank.md` (§4) for `attacks_src.toml`;
  `tome-authoring/5-runtimes.md` (§5) for runtime/toolchain fields;
  `tome-authoring/7-validate.md` (§7) for the current shipping gate; and
  `tome-authoring/9-proof-and-assets.md` (§9) for project proof or asset changes.
- `tome-authoring/10-mastery-evidence.md` (§10) **only when the tome already
  declares `[mastery].evidenceVersion = 1`**. That contract changes exercise,
  Working, hidden-assessment, and mastery-lab requirements. A legacy tome without
  `[mastery]` stays legacy: never retrofit, partially imitate, or opt it into the
  mastery-evidence contract during Iterate or Update to Standard.

Hard rules that still bind you here:

- Edit **only** under `tomes/<id>/`. Never touch engine code (`web/`, `server.py`,
  `tools/`, `runtimes/`, `skins/`, …), and never another tome.
- **Never** rename existing ids or files (exercise/lesson/section/theme/badge ids
  and the tome folder key player progress — renaming silently wipes it) **unless
  this run explicitly says a progress-resetting rework is authorized**. That
  authorization is the only exception and requires every reference to stay
  internally consistent.
- **Never** edit `save/` or hand-edit machine-owned files under `generated/`.
  Trusted repository generators may update their own outputs when an authorized
  source change requires it; inspect the generated diff and validate it.
- Match the tome's fictional voice (`[narrative]` in `tome.toml` — persona,
  currency, student term). Every sentence you add sounds like the mentor.
- Bodies are HTML inside TOML `'''…'''` literals. No `'''` inside a block.

## You may ADD structure — additions never harm saved progress

Iterate mode **may** add entries and touch many files — that is the difference
from a small change. Progress is keyed by **ids**, so *adding* things with new,
tome-unique ids is always progress-safe; *renaming, renumbering, removing, or
reordering existing* ids and files is what wipes it. Within that rule you may:

- **Add exercises** to an existing lesson (new `<sid>-l<NN>-…` ids).
- **Add lessons** to an existing section: drop in the next `lessons/lNN.toml`
  after the current highest — never renumber the existing files. A new lesson is
  held to the full §3 bar: 300–600 word body, field-notes, ≥1 reading, 4–6
  exercises, mixed types. In an existing evidence-version tome, it must also
  preserve §10's exercise evidence and review-variant contract.
- **Add whole sections (chapters)** when the material genuinely needs one — a
  taught-nowhere prerequisite, a hollow gap in the arc. **Append it at the END of
  `[content].sections`** with a new id; sections unlock in list order, so
  inserting one mid-list re-locks every later chapter behind the new freestyle
  for players already past that point. Mid-arc insertion, removal, renumbering,
  or any restructuring of *existing* sections is allowed **only when the run says
  progress-reset is authorized** — without that authorization, append-only. A new
  section needs the full kit: `section.toml`, lessons, and its own `freestyle.toml`
  (distinct rubric summing to 100, badge `badge-<sid>`), all extending the ONE
  evolving project. In an evidence-version tome, the section also needs its
  applicable public requirements, hidden `assessment.toml`, deterministic
  coverage, and sealed mastery alignment from §10; do not invent capability or
  performance ids outside the tome's existing contract.
- **Add readings, hints, `explain`/`whyWrong` fields, duel/intrusion challenges,
  palettes** — the item-level checks below.

Every addition must be real, correct content, not filler. Fewer strong lessons
beat many hollow ones — add structure to close a genuine gap, never to bulk the
tome up.

## Truth discipline — don't assert what you haven't verified

Verify new behavioral claims instead of relying on memory. Use the installed
toolchain and disposable files under `/tmp`; use current official documentation
when behavior is version-sensitive. Any new sample, starter, or solution must
compile in the tome's language. The validator checks executable artifacts but
cannot fact-check prose, so record only conclusions your toolchain or sources
support.

## What to look for (highest-value first)

1. **Untaught dependencies & coverage gaps.** The most damaging flaw a tome can
   have: an exercise, `write` lab, intrusion, duel, or freestyle requirement that
   depends on a concept, method, or identifier **no lesson in that section or an
   earlier one actually taught**. Walk the exercises and rubric lines against
   what prior lessons cover; fix each gap by teaching it — a sentence in the
   lesson body, a new lesson, or (for a big hole) a new appended section — never
   by deleting the exercise that exposed it.

2. **Working, project, and mastery integrity.** Every section's Working must make
   the learner extend the same evolving project through requirements, constraints,
   diagnostics, and observable acceptance checks. Learner-facing lesson code and
   starters—and even hidden exercise solutions or exceptional artifact steps when
   they duplicate canonical project work—must not prebuild the Working and reduce
   it to copying or renaming. Complete cumulative-project answers belong only in
   the tome's existing hidden reference/proof surfaces, never in learner-visible
   content. Confirm each Working's checklist, rubric, and proof agree about what
   the learner actually constructs. For legacy `freestyle.toml` Workings, mark
   genuinely non-negotiable rubric outcomes with `essential = true` and an
   appropriate `minimumScore` (default 6/10). Declare required
   `[[freestyle.verification]]` checks using only registered runtime CLI commands
   wherever a build, test suite, or observable acceptance command can prove the
   result mechanically. A letter/numeric grade still communicates quality, but
   a Working must not pass when an essential criterion or required verification
   fails. Do not make subjective polish criteria essential.
   Review the grading snapshot boundary too: secret names, dependencies, caches,
   outputs, and `[runtime] excludeDirs` are disclosed exclusions, so no rubric
   requirement may depend solely on evidence the grader is forbidden to receive.
   If—and only if—the tome already declares `[mastery].evidenceVersion = 1`, also
   audit §10's exercise metadata and review variants, public requirement/rubric
   records, capability links, `assessment.toml` scenarios, essential-behavior
   coverage, source-evidence diversity, mastery-lab families, and public/private
   leakage. Hidden checks must prove only behavior promised publicly, and reference
   replay proves solvability rather than learner mastery.

3. **Interleaving.** The weakest habit of an AI-authored course: every exercise
   quizzes only the lesson it sits in, and nothing older. Later sections should
   reach *backward* — a section-8 lab still exercising the section-3 data model,
   an mc in section 6 contrasting a section-2 idea with a new one. Where a tome
   never looks back, add exercises that do (concepts stay cumulative — never
   test what hasn't been taught yet).

4. **Multiple-choice feedback depth.** Every `mc` exercise needs a `whyWrong`
   (mandatory) *and* should have an `explain` (why the right answer is right).
   Missing `explain` on MCs is the most common gap — add them, each one written
   for THAT exercise (see §3's anti-template rules; a stem you could paste onto
   a different exercise unchanged is too generic).

5. **Hint coverage.** Exercises should carry a `hint` that points at the
   reasoning without giving the answer — **except `type` drills, which must NOT
   have hints** (the code to retype is already displayed; a hint is dead weight,
   and every shipped tome omits them there). Find `mc`/`text`/`fill`/`write`
   exercises with no hint and add one, each naming THIS exercise's token,
   operand, or rule — ~180 exercises means ~180 distinct hints, never a recycled
   sentence.

6. **Readings.** Most of this is a judgement call — how many, how deep — but
   **every lesson needs at least one reading; zero is never acceptable.** Each
   lesson's `[[lessons.readings]]` should point to real, authoritative docs.
   `essential = true` is **rare and means the course itself cannot fully teach
   that concept** — the reader *must* study the external doc to proceed (e.g. a
   vendor API reference too large to reproduce, a spec the lesson only
   summarizes). Most lessons teach everything they need and so have **no**
   essential reading — that is the normal, correct state, not a gap. Never mark
   a reading essential just because a lesson lacks one, and never promote a
   blog post or listicle to essential. **Check the WHOLE tome, not just the
   first few sections** — a common regression is readings coverage that's
   thorough early (where the material is easy) and thins out or vanishes
   entirely by the later/capstone chapters, exactly where the reader needs the
   anchor doc most. List every lesson with zero readings — the validator now
   WARNs on each one — before deciding the pass is done.

7. **Duel / attack bank depth.** `attacks_src.toml` is often thin. A strong bank
   has many challenges spread across difficulties. If you change its authored
   source, read §4 and run `python3 tools/gen_attacks.py <id>` while the live server
   is available; that trusted generator is the only permitted writer of
   `generated/attacks.toml`. Inspect its result and validate source/generated sync.
   If generation cannot complete, do not leave or claim completion for an
   out-of-sync source edit: repair generation within scope or leave the duel source
   unchanged and name the blocker in the closing summary.

8. **Lesson prose variety.** A wall of `<p>` paragraphs teaches worse than the
   same content broken up with `<pre><code>` blocks, `<ul>`/`<ol>` lists, a
   `callout` (≤1 per lesson), and a `field-notes` marginalia block. Reshape flat
   lessons into varied layout — keep the meaning, improve the form.

9. **Exercise-type balance.** A lesson that is all `mc` is passive. Mix in `write`
   (real coding labs with `starter` + `expect`/`expectRe` + a `solution`), `type`
   drills, and `text` recall so the learner produces, not just recognizes. For a
   concept's FIRST practice, respect §3's fading ladder: worked example (`type`)
   before `fill` before a from-scratch `write`.

10. **Consistency & correctness.** Wrong `answer` indices, prices that contradict
   the economy, theme colors that clash, rank thresholds out of order, `[[rubric]]`
   weights that don't sum to 100, ids referenced in prose that don't exist,
   identifier spellings that drift between sections. Search the complete tome,
   including `[meta].description`, narrative strings, lesson bodies, and Working
   briefs, for wording that hard-codes the course's **total** chapter or section
   count (`ten chapters`, `all 10 sections`, `across eight ops`, and equivalents).
   Replace totals with durable wording such as “throughout the course,” “across the
   arc,” or “through the final Working,” because a progress-safe Iterate pass may
   append another section later. References to a particular current section
   (“Section III”) remain valid; only fixed totals or supposedly exhaustive ranges
   are forbidden. Review mode must report every occurrence even when making no edits.

11. **Voice & polish.** Bland or off-persona text, missing `field-notes` sections,
    empty `explain`/`whyWrong` strings, TODO/placeholder leftovers.

## Scope discipline

Survey first, then spend your effort where the rubric ranks it: one genuinely
closed coverage gap outranks fifty mechanical field additions. Don't pad. In
Iterate mode, name strengths in the closing summary instead of manufacturing
changes to show work; in Review mode, put them in the complete opening
recommendation defined below.

### Review-mode report contract

A Binder Review report must put its complete decision surface at the top. After
the title and brief metadata, its first substantive section is
`## Recommendation and implementation order`. That single section must:

1. state the important strengths and validator result without treating clean
   validation as evidence that the pedagogy, correctness, privacy boundary, or
   assessment design is sound;
2. name every material recommended workstream—all Critical and High findings,
   plus Medium or Low work that belongs in the plan; and
3. give one numbered, dependency-aware implementation order.

Do not split the overall recommendation among an opening assessment, a bottom
implementation order, and a final top-findings paragraph. Detailed findings may
each include a `Remediation`, but must not label a narrow local cleanup
`Recommended change`, because that can be mistaken for the review's overall
recommendation. Rank learner privacy, correctness, teaching integrity, and valid
mastery evidence above cosmetic or compatibility conservatism. Progress safety
constrains how a later Iterate pass implements the plan; it does not suppress,
downgrade, or omit a warranted recommendation.

## When done (mandatory)

Run the exact validation command supplied by the Binder. An ordinary Iterate pass
uses `python3 tools/validate_tome.py tomes/<id>` — 0 errors, and no new WARNs. An
Update to Standard pass uses `python3 tools/validate_tome.py tomes/<id> --strict`
and cannot complete with any non-advisory WARN. Run it while the changes are still
in context, repair its complete report, and rerun until its required gate is clean;
the harness repeats it independently.
End with one short paragraph, in the mentor's voice, naming exactly which files
you changed and what you improved — and what you judged already strong or left
for a future pass — so the author can iterate again from there.
