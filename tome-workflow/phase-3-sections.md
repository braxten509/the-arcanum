# Phase 3 — Sections (one at a time)

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

⚠️ **Never introduce a brand-new language construct only inside an exercise's
starter/comment.** A past tome taught list-slice assignment nowhere except a
`write` starter's "NEW LIST TOOLS" comment — the lesson body never mentioned it,
so the grader silently tested a skill nobody taught. If any exercise (starter,
mc distractor, fill target) in a lesson uses syntax/API beyond what that lesson's
own body (or an earlier one) already explained, add a sentence teaching it to the
body — or its opening callout — BEFORE the exercise, every time, not just for
the section's headline concept.

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
lesson ≥1 `[[lessons.readings]]` link (count/depth/`essential` beyond that is a judgement
call, but zero is never acceptable — this is the floor that erodes first in later chapters),
every `mc` a `whyWrong`, and each section's freestyle a distinct rubric summing to 100.

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
