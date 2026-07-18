# Mastery Evidence Engine learner-pilot protocol

Status: protocol ready; no learner-outcome claim has been made. Repository tests prove
contract and runtime behavior, not that the engine improves learning. Run this protocol
before advertising efficacy, retention, or transfer gains.

## 1. Purpose and study questions

This is a feasibility pilot, not a powered efficacy trial. It asks whether the evidence
engine can be studied safely and consistently and whether the observed signals justify a
larger comparison.

Primary questions:

1. Can learners independently pass unseen construction, debugging, and verification tasks
   after completing an evidence-version tome?
2. Can they transfer the same capability spine to a small project whose nouns, data, and
   decisive problem shape differ from the course project?
3. Does varied performance remain available seven to fourteen days later?
4. After using support during learning, can learners recover on a different cold variant
   without a permanent grade penalty?

## 2. Freeze the study artifact

Before enrollment, record this immutable study manifest:

- repository commit and dirty-worktree status;
- tome ID and version;
- `global-configs/mastery-evidence.toml` version and SHA-256;
- resolved runtime-profile version and toolchain version;
- mastery level, sealed capability IDs, performance IDs, and aid policies;
- verified variant-family IDs, counts, and manifest hashes;
- pretest, post-test, transfer-task, and delayed-test versions;
- rubric/assessment contract hashes;
- operating system and relevant accessibility settings.

Do not change content, thresholds, variants, or scoring mid-cohort. If a safety or blocking
defect requires a change, stop the affected condition, record the deviation, create a new
study-manifest version, and analyze it separately.

Useful capture commands:

```sh
git rev-parse HEAD
git status --short
sha256sum global-configs/mastery-evidence.toml
python3 tools/validate_code.py
python3 tools/tests/browser/test_mastery_journey.py
```

## 3. Participants and conditions

Recruit 12-20 consenting participants for the feasibility pilot, with enough participants
in each condition to expose procedural failures. This number is not intended to establish
statistical efficacy.

- Define the target experience band before recruitment.
- Record prior programming experience, prior experience in the selected language, and
  familiarity with the project domain.
- Exclude only using predeclared criteria, such as already having professional-level command
  of material intended for novices.
- Record requested accessibility accommodations and verify that both conditions support
  them before assignment.
- Prefer random assignment to the evidence engine or a prior/static-tutorial condition.
  If randomization is infeasible, match on pretest and experience and label the comparison
  exploratory rather than causal.
- Give both conditions the same time budget, runtime/tool access, public documentation,
  proctor contact, and task hardware.

Participants may stop at any time without penalty. Compensation must not depend on passing.

## 4. Procedure

### Session A: consent, setup, and pretest

1. Obtain informed consent and assign a pseudonymous participant ID.
2. Verify the toolchain with a neutral task unrelated to any scored capability.
3. Run a 35-50 minute pretest with unseen items covering:
   - code comprehension and prediction;
   - construction from a behavioral contract;
   - debugging from a failing test or trace;
   - test design and verification.
4. Permit only the assistance declared in the pretest protocol. Record every intervention.

### Course period

1. Have the participant complete the assigned condition.
2. Do not coach implementation. Proctors may resolve environment failures using a logged,
   non-answer-bearing script.
3. Preserve unlimited learning retries and normal learning-lane support.
4. Export local evidence at session boundaries from:

   ```text
   GET /api/evidence/export?tome=<tome-id>
   ```

5. Record completion, project pass, provisional mastery, and retained mastery separately.

### Immediate post-test

Within 24 hours of course completion, administer new tasks matched to the pretest by
capability and difficulty but not by surface wording or fixtures. Do not reuse course
examples or a previously assigned mastery-lab variant.

### Unrelated transfer task

Give a fresh 45-90 minute project or change request with different domain nouns, data shape,
and decisive problem structure. It must still require the sealed capability spine. Score
behavior deterministically first, then any declared qualitative tradeoff or rationale rows.

### Delayed post-test

Seven to fourteen days later, administer materially varied comprehension, debugging,
construction, and verification tasks. Wall-clock waiting never blocks course completion;
this separate visit is what tests retention.

## 5. Measures

Predeclare primary measures:

- first-attempt essential-check pass rate on immediate unseen tasks;
- independent B-or-better rate on the unrelated transfer task;
- delayed varied-retrieval pass rate;
- debugging success: fault localized, repair made, and regression evidence supplied;
- verification success: learner-authored checks that would catch a named deficient case.

Secondary and feasibility measures:

- time on task and time to first green essential check;
- attempts per task and correction after evidence-based feedback;
- hint, Scroll, Oracle, revealed-solution, and proctor intervention counts;
- successful cold recovery after a supported or failed attempt;
- compile/run/test invocations and public-check use;
- course, immediate-test, transfer-test, and delayed-test completion;
- participant-reported workload, clarity, confidence, and frustration;
- instrumentation loss, variant failures, sandbox failures, and accessibility blockers.

Completion and satisfaction are never substitutes for independent or retained evidence.

## 6. Scoring and analysis

- Score deterministic behavior from the frozen assessment contracts.
- Let the server calculate weighted totals and grades; an essential failure is INCOMPLETE.
- Blind human review to condition when a rubric includes qualitative judgment.
- Keep support history descriptive; do not reduce a later independent grade merely because
  help was used during learning.
- Analyze all assigned participants and separately report protocol-complete participants.
- Report denominators, missing data, medians/ranges, condition differences, and uncertainty.
- Treat effect sizes as planning estimates. Do not claim superiority from this small pilot.
- Inspect results by prior experience and accessibility needs without presenting tiny
  subgroups as conclusive.

## 7. Privacy and evidence handling

- Use pseudonymous participant IDs; keep the re-identification key outside the repository.
- Export only the learner-safe evidence projection. Do not collect ignored secrets, hidden
  reference solutions, raw home paths, unrelated workspace files, API keys, or model tokens.
- If source snapshots are required for rubric audit, obtain explicit consent, limit them to
  declared text files, encrypt them at rest, and define a deletion date.
- Record who can access raw data and the retention period before collection.
- Review evidence logs for accidental sensitive data before transfer.
- Report aggregate results; redact free-text comments that could identify a participant.

## 8. Feasibility gates and stopping rules

The pilot is operationally successful only if:

- at least 95% of scheduled scored tasks produce complete versioned evidence;
- every issued lab variant is verified, persistent across refresh, and different after a
  failed/supported retry;
- no hidden solution, secret, or unrelated local path reaches a learner or grader payload;
- no participant is blocked by a defect without a documented neutral recovery;
- delayed follow-up and attrition are reported rather than silently omitted.

Stop enrollment for a condition after any privacy leak, hidden-answer exposure, assessment
that mutates learner work, repeated invalid variant, or systematic accessibility blocker.
Repair, revalidate, version the study manifest, and restart that condition as a new cohort.

## 9. Tuning and reporting

Use the pilot to tune evidence timing, variant pool size, public-contract clarity, rubric
weights, and aid policy. Never tune by allowing supported work to masquerade as independent,
lowering the B/80 gate, averaging away essential failures, or reusing the same failed lab
variant.

The pilot report must include:

- frozen study manifest and all protocol deviations;
- recruitment, assignment, attrition, and follow-up flow;
- task-level results with denominators and uncertainty;
- assistance and recovery patterns;
- sandbox, instrumentation, accessibility, and variant incidents;
- participant feedback separated from performance evidence;
- changes proposed for the next version;
- an explicit statement that efficacy remains unproven unless a suitably powered study
  supports it.

