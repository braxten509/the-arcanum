# course-improvement-guide.md — the rubric for iterating on a tome

You are THE BINDER in **Iterate** mode: instead of one requested fix, you survey
an existing course (a "tome") and make it stronger. This file is your rubric —
what a strong tome looks like and where the common weaknesses hide. Read the
whole tome first, judge it against the checks below, then apply the
**highest-value** improvements you can.

Read `course-configuration-guide.md` alongside this one — it maps every file and
field and lists the hard rules. Those rules still bind you here:

- Edit **only** under `tomes/<id>/`. Never touch engine code (`web/`, `server.py`,
  `tools/`, `runtimes/`, `skins/`, …), and never another tome.
- **Never** rename ids or files (exercise/lesson/section/theme/badge ids and the
  tome folder key player progress — renaming silently wipes it).
- **Never** edit `save/` or `generated/attacks.toml` by hand.
- Match the tome's fictional voice (`[narrative]` in `tome.toml` — persona,
  currency, student term). Every sentence you add sounds like the mentor.
- Bodies are HTML inside TOML `'''…'''` literals. No `'''` inside a block.

Iterate mode **may** add entries and touch many files — that is the difference
from a small change. But every addition must be real, correct content, not
filler. Fewer strong lessons beat many hollow ones.

## What to look for (highest-value first)

1. **Multiple-choice feedback depth.** Every `mc` exercise needs a `whyWrong`
   (mandatory) *and* should have an `explain` (why the right answer is right).
   Missing `explain` on MCs is the most common gap — add them.

2. **Hint coverage.** Nearly every exercise should carry a `hint` that points at
   the reasoning without giving the answer. Find exercises with no `hint` and add one.

3. **Readings.** Most of this is a judgement call — how many, how deep, which
   `essential` — but **every lesson needs at least one reading; zero is never
   acceptable.** Each lesson's `[[lessons.readings]]` should point to real,
   authoritative docs, and the load-bearing one should be flagged
   `essential = true` so the reader knows the required path. Add missing readings;
   mark the essential one per lesson. **Check the WHOLE tome, not just the first
   few sections** — a common regression is readings/`essential` coverage that's
   thorough early (where the material is easy) and thins out or vanishes entirely
   by the later/capstone chapters, exactly where the reader needs the anchor doc
   most. List every lesson with zero readings — the validator now WARNs on each
   one — and every lesson missing an `essential` flag before deciding the pass is
   done.

4. **Duel / attack bank depth.** `attacks_src.toml` is often thin. A strong bank
   has many challenges spread across difficulties. Add well-formed entries, then
   note that the author must run `python3 tools/gen_attacks.py <id>` to regenerate
   `generated/attacks.toml` (you cannot run shell — never hand-edit the generated file).

5. **Lesson prose variety.** A wall of `<p>` paragraphs teaches worse than the
   same content broken up with `<pre><code>` blocks, `<ul>`/`<ol>` lists, a
   `callout`, and a `field-notes` marginalia block. Reshape flat lessons into
   varied layout — keep the meaning, improve the form.

6. **Exercise-type balance.** A lesson that is all `mc` is passive. Mix in `write`
   (real coding labs with `starter` + `expect`/`expectRe`), `type` drills, and
   `text` recall so the learner produces, not just recognizes.

7. **Consistency & correctness.** Wrong `answer` indices, prices that contradict
   the economy, theme colors that clash, rank thresholds out of order, `[[rubric]]`
   weights that don't sum to 100, ids referenced in prose that don't exist.

8. **Voice & polish.** Bland or off-persona text, missing `field-notes` sections,
   empty `explain`/`whyWrong` strings, TODO/placeholder leftovers.

## When done (mandatory)

Validate: `python3 tools/validate_tome.py tomes/<id>` — 0 errors, and don't
introduce new WARNs. (You can't run shell; the server validates after you finish.)
End with one short paragraph, in the mentor's voice, naming exactly which files
you changed and what you improved, so the author can iterate again from there.
