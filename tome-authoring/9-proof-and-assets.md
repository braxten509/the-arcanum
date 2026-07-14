# §9 — Executable course proof and human-sourced assets

Every newly scaffolded tome has `content.proofVersion = 1`. Do not remove or downgrade it.
This contract turns the learner journey into data the harness can replay. Prose, capability
ids, reviewer confidence, and files merely existing are never substitutes for this proof.

## One cumulative disposable project

The validator starts from the selected runtime's real scaffold. In Arc order it applies every
lesson's `artifactSteps`, then that section's hidden freestyle `referenceSteps`. After each
section it reruns that milestone **and every still-active earlier milestone** against the new
project state. The resulting project continues into the next section. A later chapter cannot
erase a working earlier feature merely because its own local receipt still prints.
Consequently:

- `write` creates a path that does not exist, including in the runtime scaffold. Reusing
  `write` for an existing path is a hard error.
- Prefer `replace` with `find` text that occurs exactly once. An unavoidable complete-file
  migration uses `mode = "rewrite"`, complete `content`, and `preserves = "all-active"`.
  Every active proof then reruns; the declaration is never accepted as evidence by itself.
- Every step names its project-relative `path`, a stable `id`, a specific learner-visible
  `instruction`, and one of `write`, `replace`, `rewrite`, `append`, or `delete`.
- `write`, `rewrite`, and `append` use `content`; `replace` uses both `find` and replacement `content`.
  `delete` names an existing file. Paths cannot be absolute, escape with `..`, or name media.
- No shell command is part of the proof schema. Commands shown to a learner use a code block
  with `data-kind="terminal"`; execution remains owned by the selected runtime.

Example lesson edit:

```toml
[[lessons.artifactSteps]]
id = "s02-add-player-state"
path = "game/player.py"
mode = "write"
instruction = "From the project root, create game/player.py with this complete content, then run the chapter check."
content = '''
# complete learner-visible source
'''
```

These steps are rendered beneath the lesson body. They are not hidden validator metadata.
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

Each `[freestyle]` has one or more `[[freestyle.referenceSteps]]` in the same edit format.
They are a complete private solution to that chapter's Working, are stripped from the HTTP
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
```

The source artifact must emit exactly one JSON object with `version = 1`, `status = "PASS"`,
and a `scenarios` object containing those ids in order, each exactly `true`. A package course
must emit the same result from the packaged executable. Test controls may supply deterministic
input, time, seed, or a frame limit; they must drive real domain methods. They may not assign a
win, boss health, inventory, or saved state merely to manufacture a receipt. Phase 8 audits the
adapter source while the harness owns command execution.

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
every active proof at every later checkpoint, source acceptance, and package acceptance where
required. Phase 8 may only acknowledge that read-only matrix and report cited semantic findings;
it never authors PASS. Empty findings derive PASS only while the matrix fingerprint still matches
the current tome, every row is green, the reviewer made no authored change, strict validation is
clean, and required sources remain usable.
