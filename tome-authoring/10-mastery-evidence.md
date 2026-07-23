# Mastery evidence contract (future tomes)

This section applies when `tome.toml` contains the following table. Tomes without it remain on
the legacy progression and grading path; never retrofit or partially imitate this contract.

```toml
[mastery]
evidenceVersion = 1
level = 3 # the sealed Phase-0 answer; 1 through 5
```

The engine-wide floors live in `global-configs/mastery-evidence.toml`. A tome may describe its
subject, language, and context, but it may not lower required completion, the 80/B Working gate,
essential checks, performance counts, aid limits, context distance, rationale counts, variation
axes, or verified-pool sizes. Capability IDs remain language-neutral engine data; language-specific
coverage stays in the sealed course map and language profile.

## Exercise evidence metadata

Every exercise in an evidence-version tome has these six fields in addition to its ordinary
renderer fields:

```toml
[[lessons.exercises]]
id = "s02-l01-e1"
type = "write"
required = true
capabilities = ["language-control"]
cognitiveTask = "modify"
scaffold = "guided"
contextFamily = "harbor-records"
aidPolicy = "learning"
```

- `required` separates course completion from optional enrichment.
- `capabilities` names only sealed capability IDs materially exercised here.
- `cognitiveTask` is one of `recall`, `recognize`, `predict`, `trace`, `explain`, `complete`,
  `modify`, `debug`, `test-design`, `build`, `integrate`, `refactor`, `profile`,
  `evaluate-tradeoff`, or `design-defense`. It is independent of renderer type.
- `scaffold` is `worked`, `completion`, `guided`, `independent`, or `cold`.
- `contextFamily` is a stable kebab-case family used to prove varied retrieval.
- `aidPolicy` is `learning`, `limited`, `documentation-only`, or `cold`.

A typing/copying drill is never independent evidence. `documentation-only` and `cold` work cannot
ship an answer-producing hint. For reviewable work, add at least two materially different
`reviewVariants` records; a missed review remains due until the learner answers a varied form
correctly.

## Working public contract

Keep a Working creative: publish outcomes, constraints, observable behavior, and stable criteria,
not a private implementation. Replace prose-only requirements with exact records:

```toml
[[freestyle.requirements]]
id = "reject-invalid-record"
text = "Reject an invalid record without losing the previously accepted records."
essential = true
capabilities = ["language-failure", "language-data"]

[[freestyle.rubric]]
id = "invalid-record-behavior"
criterion = "Invalid input is rejected while accepted state remains intact."
weight = 70
kind = "deterministic"
assessmentIds = ["builds", "rejects-invalid-record"]

[[freestyle.rubric]]
id = "design-rationale"
criterion = "The learner explains the chosen failure boundary and verification strategy."
weight = 30
kind = "qualitative"
assessmentIds = []
```

Requirement keys are exactly `id`, `text`, `essential`, and `capabilities`. Rubric rows require
`id`, `criterion`, `weight`, `kind`, and `assessmentIds`; weights total 100. Every essential
requirement must have deterministic scenario coverage. Qualitative review may judge explanation,
tradeoffs, maintainability, and design quality, but cannot override a failed build or essential
scenario. Source similarity is never a criterion.

When `[mastery].sourceEvidenceVersion = 1`, every essential requirement also needs at least two
distinct non-build scenarios and each must be linked from a deterministic rubric row. Use varied
inputs, a boundary, a failure mode, or an alternate command path. Compilation plus one happy-path
run is insufficient evidence for essential behavior.

## Hidden Working assessment

Place `assessment.toml` beside each section's `freestyle.toml`. It is authoring-only and the HTTP
loader must never serve it. The top-level shape is exactly `version = 1` plus scenarios:

```toml
version = 1

[[scenarios]]
id = "builds"
kind = "build"
requirementIds = ["reject-invalid-record"]
capabilityIds = ["language-failure", "language-data"]
commandRef = "build"
args = []
stdin = ""
expect = { exitCode = 0 }
timeout = 30
public = true

[[scenarios]]
id = "rejects-invalid-record"
kind = "run"
requirementIds = ["reject-invalid-record"]
capabilityIds = ["language-failure", "language-data"]
commandRef = "run"
args = []
stdin = "invalid\n"
expect = { exact = "REJECTED\nrecords=0", exitCode = 0 }
timeout = 30
public = false
```

Allowed kinds are `build`, `run`, `structured-output`, `produced-file`, `driver`, `package`,
`cold-launch`, and `guided-observation`. `commandRef` names `run`, `build`, or a key in the selected
generic runtime's `assessmentCommands`; never put authored shell in a tome. A final Working also
needs `cold-launch`, and a promised package needs `package`. Hidden scenarios may vary inputs and
edge cases only within the public requirement. If a hidden check inspects a produced path, the
public requirement must name that path. Do not require private architecture, names, or source
shape.

The server snapshots the actual learner workspace, rejects escapes, symlinks, secrets, stale
hashes, excessive size, time, or output, then runs scenarios without network in an isolated copy.
External workspaces are read-only sources and are never changed by assessment. Reference replay
proves the course solution; it is never learner evidence.

## Standalone mastery-lab family

For each sealed `sNN.labNN`, create:

```text
sections/sNN/mastery-labs/<family>.toml
sections/sNN/mastery-labs/<family>/
├── public/       # optional shared public starter overlay
├── hidden/       # author-only family material
└── blueprints/   # one or more candidate JSON files
```

The TOML must align exactly with the sealed performance:

```toml
[masteryLab]
version = 1
id = "record-transfer"
nodeId = "s08.lab01"
performanceId = "late-record-transfer"
title = "Reconcile a foreign record stream"
performanceKind = "novel-transfer"
capabilityIds = ["language-data", "language-failure", "language-verification"]
cognitiveTasks = ["build", "debug", "explain"]
contextFamily = "foreign-record-stream"
contextRelation = "unrelated"
aidPolicy = "documentation-only"
estimatedMinutes = 45
rationaleRequired = true
variantFamilyId = "record-transfer"

[generator]
mode = "hybrid-ai-verified"
minimumBlueprints = 2
minimumVerifiedVariants = 8
variationAxes = ["domain", "input-shape", "failure-mode"]
newVariantOnRetry = true
```

Use the central level floors even if this example's numbers are lower. The lab is isolated from the
cumulative project unless the sealed performance is explicitly a project change. Refreshing never
rerolls. Assignment is persisted before its brief is shown; a failed or supported attempt may use
the retry action to receive another already-verified variant.

## Blueprint candidate schema

Every `blueprints/*.json` object uses exactly these keys:

```json
{
  "version": 1,
  "id": "record-transform",
  "title": "{{domain}} {{input-shape}} reconciliation",
  "brief": "Implement the public behavior for the assigned record stream.",
  "difficulty": "novel transfer",
  "starterBuildable": true,
  "axes": {
    "domain": ["harbor", "clinic"],
    "input-shape": ["rows", "events"],
    "failure-mode": ["reject", "quarantine"]
  },
  "publicFiles": {"src/main.ext": "a buildable but incomplete starter"},
  "publicExamples": ["One input/output example that does not reveal an edge case."],
  "hiddenFiles": {},
  "referenceFiles": {"src/main.ext": "the complete private solution"},
  "mutations": {
    "drops-invalid": {"src/main.ext": "a deliberately deficient solution"},
    "loses-state": {"src/main.ext": "a different deficient solution"}
  },
  "dependencies": [],
  "assessment": {
    "version": 1,
    "requirements": [],
    "scenarios": [],
    "rubric": []
  }
}
```

Every declared axis has at least two unique values and every `{{slot}}` must resolve. The embedded
assessment uses the same exact requirement/scenario/rubric JSON contract described above. Include
at least two mutations attacking different essential behavior. Generation rejects a starter that
already passes, a promised buildable starter that does not build, a failing reference, any mutation
that passes, semantic mismatch, leakage, unsafe paths, undeclared dependencies, near duplicates,
or insufficient structural diversity.

In Phase 7, generate and prove the offline bank before strict validation:

```text
python3 tools/gen_mastery_labs.py CURRENT_TOME --build-id BUILD_ID
python3 tools/validate_phase3.py tomes/CURRENT_TOME --plan .tome-build/BUILD_ID.plan.md --tooling TOOLING --strict
python3 tools/smoke_tome.py CURRENT_TOME
```

The build ID selects the already-sealed Phase 3-7 author provider/model. Explicit `--provider` and
`--model` are available for a standalone operator run. Verified generated packages live below
`generated/mastery-labs/` and ship for offline completion. Public APIs expose only the brief,
requirements, examples, aid policy, assigned axes, and public files; blueprints, hidden scenarios,
reference solutions, mutations, and proof details remain server-owned.

## Phase 8 semantic congruence receipt

After executing the course as a first-time learner, write
`.tome-build/BUILD_ID.mastery-semantic-review.json`. Its keys are exactly:

```json
{
  "version": 1,
  "reviewMode": "semantic-congruence",
  "capabilities": [
    {"id": "language-data", "evidence": ["sections/s02/lessons/l01.toml concept and exercise"], "judgment": "congruent"}
  ],
  "performances": [
    {"id": "late-transfer", "nodeId": "s08.lab01", "evidence": ["sections/s08/mastery-labs/transfer.toml and verified bank"], "judgment": "congruent"}
  ],
  "findings": [
    {"location": "sections/s04/lessons/l02.toml", "issue": "The task label overstated its work.", "resolution": "Reauthored the prompt and evidence mapping, then reran all gates."}
  ],
  "unresolvedFindings": [],
  "independenceJudgment": "A concrete answer tied to the original prompt and the visible learner path.",
  "summary": "A concise conclusion about semantic alignment and claim scope."
}
```

List every sealed capability and performance once, in sealed order. Evidence must cite concrete
learner-visible teaching, work, and executable proof—not IDs or green status alone. Only
`judgment = "congruent"` is shippable, every finding must state its repair, and
`unresolvedFindings` must be empty. The reviewer does not declare PASS; the harness validates this
receipt and combines it with strict executable evidence.
