# §9 — Executable course proof and human-sourced assets

Every newly scaffolded tome has `content.proofVersion = 1`. Do not remove or downgrade it.
This contract turns the learner journey into data the harness can replay. Prose, capability
ids, reviewer confidence, and files merely existing are never substitutes for this proof.

## One cumulative disposable project

The validator starts from the selected runtime's real scaffold. Learner-facing seed content is
limited to a blank editor file or unavoidable behavior-free tool metadata; it contains no project
structure, behavior, decisions, data, tests, or assets. In Arc order it
reads every lesson's learner-visible `artifactSteps`, applies only any explicitly replayable
non-solution edits, then applies that section's hidden freestyle `referenceSteps`. After each
section it reruns that milestone **and every still-active earlier milestone** against the new
project state. The resulting project continues into the next section. A later chapter cannot
erase a working earlier feature merely because its own local receipt still prints.
Consequently:

- Use `mode = "author"` for the normal lesson project step. It names the path, gives a precise
  learner work order, and lists one or more `checks`, but contains no `content`, `find`, or
  `preserves`. Replay deliberately makes no edit for this mode; the section's hidden
  `referenceSteps` reconstruct what the learner must author.
- `write` creates a path that does not exist, including in the runtime scaffold. Reusing
  `write` for an existing path is a hard error.
- Prefer `replace` with `find` text that occurs exactly once. An unavoidable complete-file
  migration uses `mode = "rewrite"`, complete `content`, and `preserves = "all-active"`.
  Every active proof then reruns; the declaration is never accepted as evidence by itself.
- Every step names its project-relative `path`, a stable `id`, a specific learner-visible
  `instruction`, and one of `author`, `write`, `replace`, `rewrite`, `append`, or `delete`.
- An `author` step also names specific observable `checks`. Its instruction may give paths,
  requirements, constraints, commands, diagnostics, and expected behavior, but never project
  implementation, ready-to-paste code, filled records, answer-bearing tests, or a rename-equivalent
  solution.
- `write`, `rewrite`, and `append` use `content`; `replace` uses both `find` and replacement `content`.
  `delete` names an existing file. Paths cannot be absolute, escape with `..`, or name media.
- No shell command is part of the proof schema. Commands shown to a learner use a code block
  with `data-kind="terminal"`; execution remains owned by the selected runtime.

Normal learner-authored lesson work order:

```toml
[[lessons.artifactSteps]]
id = "s02-add-player-state"
path = "game/player.py"
mode = "author"
instruction = "From the project root, author game/player.py so movement obeys the taught state and timing contracts. Do not copy the disposable lesson example."
checks = [
  "The focused movement check passes for both cardinal and diagonal input.",
  "The ordinary launch moves the player at the same speed across different frame times.",
]
```

These work orders are rendered beneath the lesson body. They are not hidden validator metadata.
Every canonical source/configuration/data/test/map/documentation/delivery answer belongs in the
Working's hidden `referenceSteps`, which are stripped from the learner payload. Use the older edit
modes in visible lesson steps only for genuinely non-solution setup; never use their `content` to
give away part of the promised artifact.
All HTML lesson code blocks must classify their promise as
`data-kind="runnable|replacement|patch|pseudocode|terminal"`. Pseudocode may explain an idea,
but acceptance-critical behavior must live in replayed source or a deterministic procedure.

## Structured teaching evidence

For every id in `lessons.teaches`, the same lesson carries exactly one
`[[lessons.concepts]]` entry with that `id` and all of:

- `purpose`: what it is for in plain language;
- `anatomy`: its syntax parts or tool actions read in order;
- `example`: where the complete worked example is;
- `observable`: what the learner sees when it succeeds;
- `failure`: one likely failure and how to recognize it;
- `practice`: an exercise id in this same lesson.

This is required at every start level. For Start 1–3 it directly enforces the first-use
teaching sequence; at higher levels the explanations may be more compact, but never fictional.

## Independent Working reference

Each `[freestyle]` has one or more `[[freestyle.referenceSteps]]` using the replayable edit modes
(`write`, `replace`, `rewrite`, `append`, `delete`; never `author`). They are a complete private
solution to that chapter's Working, are stripped from the HTTP
payload, and are applied only in the disposable validator project. They must satisfy every
requirement and leave the canonical project state on which the next section depends.

## Section milestone

Each section has one `[proof]` table:

```toml
[proof]
mode = "run"
expectedFiles = ["main.py", "game/world.py"]
runArgs = ["--arcanum-proof", "s04"]
expect = "S04_OK players=1 rooms=3"
```

- `run` first builds/checks the project, appends `runArgs` safely to the runtime command,
  requires exit 0, and compares normalized output exactly. `expectRegex` may replace `expect`
  when values are intentionally variable; it must full-match the output.
- `build` requires the real build/check command to exit 0 and is appropriate when starting the
  application would block or require a display.
- `guided` is only for inherently non-automatable tools in a tome whose runtime declares
  `externalWorkspace = true`. It still replays all textual project edits and requires at least
  two specific `guidedChecks` describing observable checks. Internal and ordinary projects
  cannot use it to evade a real build or run.
- `package` is final-section-only. It names `requirementsFile`, `packageArgs`, and
  `artifactPath`. The selected runtime creates a fresh delivery environment, installs the
  exact requirements file, runs its real packager without a shell, verifies the artifact is
  executable, launches it, and repeats the final acceptance journey from that artifact.
- `expectedFiles` lists source/config/text outputs, never sprites, audio, fonts, images, video,
  or other media.

The final section of every non-external tome must use `run` or `package`. Earlier sections may
use `build`, but a build-only course cannot certify the finished behavior.

Every section proof remains active through shipping. The harness derives its protected
capabilities from that section's `teaches`. A later proof may use `supersedes = ["s04"]` only
for a genuine interface migration; it must also declare `protects = [...]` containing every
capability introduced here and protected by the retired proof. Missing coverage is a hard error.

Interactive applications should implement a narrow deterministic proof argument that exercises
real game/domain logic, prints the declared result, and exits. It must not load optional human
assets, open a display, wait for input, or replace the real app with a fake. Ordinary launch
still follows the course's real path. A PyGame course, for example, can run model/collision/state
checks under `--arcanum-proof` while the normal command opens the game.

At every complete replay, the harness also persists the exact reconstructed project at
`.tome-build/<tome-id>.learner-project`, builds/checks it, and cold-starts the ordinary runtime
command with **no proof or acceptance arguments**. A normal zero exit passes. Interactive,
graphical, and server programs pass when they remain alive through the bounded observation window;
the harness then stops them. Any early nonzero exit is blocking. If an ordinary console launch
needs initial input, `[acceptance].launchStdin` may provide that learner-like text; otherwise the
harness leaves stdin open so waiting for a person is not mistaken for a crash.

## Executable acceptance journey

Phase 1 writes one `**Acceptance scenarios:**` line of stable kebab ids separated by ` -> `.
Phase 2 copies that exact ordered list into the manifest:

```toml
[acceptance]
version = 1
mode = "run"
artifact = "package" # or runtime
runArgs = ["--arcanum-acceptance"]
scenarios = ["launch", "move", "combat", "win", "save", "relaunch-load"]
controls = ["input", "clock", "seed", "frame-limit"]
# launchStdin = "1\n" # optional ordinary-launch input, not an acceptance shortcut
```

The source artifact must emit exactly one JSON object with `version = 1`, `status = "PASS"`,
and a `scenarios` object containing those ids in order, each exactly `true`. A package course
must emit the same result from the packaged executable. Test controls may supply deterministic
input, time, seed, or a frame limit; they must drive real domain methods. They may not assign a
win, boss health, inventory, or saved state merely to manufacture a receipt. Phase 8 audits the
adapter source while the harness owns command execution.

Every executable acceptance adapter must honor the harness variable
`ARCANUM_ACCEPTANCE_CHALLENGE=<scenario-id>`. For that run it withholds or invalidates one required
declared control, follows the same domain path, emits `status = "FAIL"`, and reports the challenged
scenario as `false` (all scenario values remain booleans in the planned order). The harness runs
one challenge per scenario for source and packaged artifacts. Do not branch directly to a prepared
FAIL object; use the challenge to alter input, clock, seed, or frame limit and let the ordinary
scenario observations derive the report. Source that embeds `status = "PASS"` together with every
scenario assigned literal `true` is rejected before execution.

## Absolute media rule

The tome AI must never create, draw, synthesize, record, compose, embed, base64-encode, or
procedurally generate a sprite, texture, image, animation, font, sound effect, voice, music
track, or video. No media file belongs anywhere in the tome. The proof project must succeed
without unsupplied media.

When the learner's final artifact benefits from media, the AI teaches the human how to source
it. Put an `[[assets]]` guide in the section that first uses it:

```toml
[[assets]]
id = "player-sprite"
kind = "sprite"
lesson = "s03-l02"
destination = "assets/player.png"
sourceGuidance = "Choose a 32x32 top-down character, download it, rename it player.png, and place it at the path above."
licenseGuidance = "Choose an asset whose page permits your intended use; record creator, URL, and required attribution in README.md."
sources = [
  { label = "A reputable human-made asset library", url = "https://example.org/library", license = "Choose and follow the license displayed on the asset page" },
]
```

The engine renders this guide in the named lesson. Every media path used in prose or code needs
a matching guide, at least one HTTPS source, license guidance, and an exact destination. The
validator checks source reachability at the full gate: confirmed 404/410 is blocking; transient
403/rate-limit/network failures are reported as advisory. Readings and asset sites supplement
the tome; mandatory knowledge must still be taught inside it.

## Who decides completion

For proof-v1 tomes, successful full replay writes a SHA-256-bound matrix under `.tome-build/`:
every active proof at every later checkpoint, final build/check, ordinary cold start, anti-constant
scan, positive and negative source acceptance, and equivalent package rows where required. Rows
record the actual argv and output, and the exact reconstructed project remains beside the matrix.
Phase 8 may only acknowledge those read-only artifacts and report cited semantic findings; it never
authors PASS. A green matrix is a prerequisite, not semantic proof. Empty findings derive a clean
candidate only while the fingerprint matches, every row is green, the reviewer made no authored
change, strict validation is clean, and required sources remain usable. A different configured
reviewer command must independently return a clean no-change report before the build completes.
