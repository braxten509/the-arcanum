"""Section and hidden-assessment templates for future tome scaffolds."""

# sections/<sid>.toml — one section, one lesson, one of every core exercise type.
SECTION_TEMPLATE = r"""
# Section @@SID@@ — scaffolded by tools/new_tome.py. Replace every TODO.
# One lesson with one of each core exercise type is shown; author 3-5 lessons per
# section and 4-6 mixed exercises per lesson (see § sections/<sid>.toml).
id = "@@SID@@"
codename = "CHAPTER @@ROMAN@@ // TODO"
short = "TODO"                     # optional: compact contents-rail label
title = "TODO: chapter title"
build = "TODO: one line — what this chapter adds to the evolving project"
brief = "TODO: HTML intro card for the chapter."

[proof]
mode = "run"                       # run | build | guided | package (package only in final section)
expectedFiles = ["replace-me.txt"] # TODO: source/config files that must exist after this chapter
runArgs = ["--arcanum-proof", "@@SID@@"]
expect = "TODO: exact deterministic milestone output"

# Media is NEVER authored by the tome AI. When this chapter needs a sprite, sound,
# music track, font, image, or video, add one or more [[assets]] sourcing guides:
# [[assets]]
# id = "player-sprite"
# kind = "sprite"
# lesson = "@@SID@@-l01"
# destination = "assets/player.png"
# sourceGuidance = "Explain how the learner chooses, downloads, renames, and places it."
# licenseGuidance = "Explain the license/attribution step the learner must perform."
# sources = [{ label = "Trusted asset library", url = "https://...", license = "..." }]

[freestyle]
title = "THE WORKING: TODO"
brief = "TODO: the complete learner-visible chapter project assignment. State the outcome, flexible implementation choices, constraints, commands, diagnostics, and observable acceptance here.<ul><li>TODO requirement one</li><li>TODO requirement two</li></ul>"
requires = ["replace-me"]           # TODO: exact ids taught by this/earlier lessons
reward = 150
xray = "TODO: the grader's private notes — the specific pitfalls it docks and the style it rewards, truthful to the rubric below."

[[freestyle.requirements]]
id = "replace-essential-behavior"
text = "TODO: one observable public requirement; preserve learner implementation freedom."
essential = true
capabilities = ["replace-me"]

[[freestyle.referenceSteps]]        # hidden from learners; validator replays a real solution
id = "@@SID@@-freestyle-reference"
path = "replace-me.txt"
mode = "rewrite"
preserves = "all-active"
instruction = "TODO: exact private reference edit that satisfies this Working."
content = '''
TODO: complete reference content
'''

[freestyle.badge]
id = "badge-@@SID@@"
name = "TODO BADGE"
desc = "TODO: one sentence."

[[freestyle.rubric]]               # weights MUST sum to exactly 100
id = "build-evidence"
criterion = "Compiles & runs"
weight = 40
kind = "deterministic"
assessmentIds = ["replace-build-check"]
desc = "TODO: build succeeds; runs without crashing on normal input."

[[freestyle.rubric]]
id = "behavior-evidence"
criterion = "Meets the brief"
weight = 40
kind = "deterministic"
assessmentIds = ["replace-behavior-check"]
desc = "TODO: every requirement in the checklist is present and correct."

[[freestyle.rubric]]
id = "design-quality"
criterion = "Clean style"
weight = 20
kind = "qualitative"
assessmentIds = []
desc = "TODO: name this language's real naming AND layout conventions (research its style guide)."

[[lessons]]
id = "@@SID@@-l01"
title = "TODO: lesson title"
teaches = ["replace-me"]            # TODO: stable kebab-case capabilities this lesson teaches
# Every authored lesson cites one or more IDs from this section's research.toml.
# Phase 3 replaces this placeholder with receipts for the facts it actually teaches.
researchSources = ["replace-source"]
body = '''
<p>TODO: 340-500 meaningful visible words of code-first teaching, leaving margin above the 300-word cumulative median gate.</p>
<pre><code data-kind="runnable"><span class="k">print</span>(<span class="s">"TODO"</span>)</code></pre>
<div class="field-notes"><div class="fn-head">FIELD NOTES // TODO</div>
<p>TODO: an optional deeper-cut appendix.</p></div>
'''

[[lessons.concepts]]                # one complete first-use proof for every `teaches` id
id = "replace-me"
purpose = "TODO: plain-language purpose."
anatomy = "TODO: read its parts or procedure in order."
example = "TODO: point to the complete worked example in this lesson."
observable = "TODO: what the learner sees when the example works."
failure = "TODO: one likely failure and how to recognize it."
practice = "@@SID@@-l01-e1"

[[lessons.readings]]               # optional: 1-2 high-quality official docs
label = "TODO: official docs"
url = "https://example.com/TODO"

[[lessons.exercises]]
id = "@@SID@@-l01-e1"
type = "mc"
required = true
capabilities = ["replace-me"]
cognitiveTask = "predict"
scaffold = "guided"
contextFamily = "replace-context"
aidPolicy = "learning"
points = 15
prompt = "TODO: a multiple-choice question?"
choices = ["TODO correct answer", "TODO distractor A", "TODO distractor B", "TODO distractor C"]
answer = 0                         # 0-based index of the correct choice (vary across 0–3, not always 0)
whyWrong = "TODO: name the misconception the wrong choices betray."   # required on every mc
hint = "TODO: an exercise-specific hint."
explain = "TODO: shown after solving."

[[lessons.exercises]]
id = "@@SID@@-l01-e2"
type = "text"
required = true
capabilities = ["replace-me"]
cognitiveTask = "explain"
scaffold = "guided"
contextFamily = "replace-context"
aidPolicy = "learning"
points = 20
prompt = "TODO: a free-text question."
answer = "TODO"
# accept = ["TODO alternate"]      # optional true alternates only
hint = "TODO: an exercise-specific hint."

[[lessons.exercises]]
id = "@@SID@@-l01-e3"
type = "fill"
required = true
capabilities = ["replace-me"]
cognitiveTask = "complete"
scaffold = "completion"
contextFamily = "replace-context"
aidPolicy = "learning"
points = 20
prompt = "TODO: fill the blank."
code = 'answer = ____'             # the ____ marks where the answer goes
answer = "TODO"
hint = "TODO: an exercise-specific hint."

[[lessons.exercises]]
id = "@@SID@@-l01-d1"
type = "type"                      # typing drill: retype the code; no point decay
required = true
capabilities = ["replace-me"]
cognitiveTask = "recall"
scaffold = "worked"
contextFamily = "replace-context"
aidPolicy = "learning"
points = 12
reps = 2
prompt = "TODO: retype this exactly. (Ctrl+Enter submits.)"
code = 'print("TODO")'

[[lessons.exercises]]
id = "@@SID@@-l01-w1"
type = "write"                     # CODE LAB: runs on the real runtime; no point decay
required = true
capabilities = ["replace-me"]
cognitiveTask = "build"
scaffold = "guided"
contextFamily = "replace-context"
aidPolicy = "learning"
points = 30
prompt = "TODO: a CONCRETE task — name the exact values and the exact required output."
# starter = '''
# TODO: prefilled editor code / the exercise's data
# '''
expect = '''
TODO EXACT OUTPUT'''
# REQUIRED before shipping: a complete program that passes. Never shown to the
# student; the validator RUNS it to prove expect is achievable (tome-authoring §3).
# solution = '''
# TODO
# '''
hint = "TODO: an exercise-specific hint."
"""


ASSESSMENT_TEMPLATE = r"""
# Hidden deterministic Working assessment. Never served to the learner.
version = 1

[[scenarios]]
id = "replace-build-check"
kind = "build"
requirementIds = ["replace-essential-behavior"]
capabilityIds = ["replace-me"]
commandRef = "build"
args = []
stdin = ""
exitCode = 0
timeout = 20
public = true

[[scenarios]]
id = "replace-behavior-check"
kind = "run"
requirementIds = ["replace-essential-behavior"]
capabilityIds = ["replace-me"]
commandRef = "run"
args = []
stdin = ""
expectRegex = "TODO: observable varied behavior"
exitCode = 0
timeout = 20
public = false
"""


# Section-local technical-source receipts. This is author evidence, not learner assessment.
RESEARCH_TEMPLATE = r"""
version = 1

[[sources]]
id = "replace-source"
url = "https://example.com/TODO"
authority = "TODO: primary official documentation or release notes."
claims = ["TODO: the specific API, command, version, or behavior verified from this source."]
"""
