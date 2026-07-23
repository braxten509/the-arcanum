# 5. Runtimes — teaching any language

**No language is built into Python.** One engine — `runtimes/generic.py` — runs
every language from TOML alone: commands, placeholders, and regex diagnostics that
cover interpreted AND compiled languages. A language is one file under
`global-configs/runtimes/`, optionally grouped in a category directory; a tome selects
the file by its basename with `[runtime] name = "<name>"`. Basenames are unique across
the tree, and any key in that file is a default the tome's `[runtime]` table overrides.
**Four ship: `dotnet`, `python`, `java`, and `odin`** — `odin.toml` is the canonical
"add a language with zero code" example (read them all).

**The module docstring at the top of `runtimes/generic.py` is authoritative for ordinary
run/build configuration; `runtimes/delivery.py` is authoritative for package delivery.** Every
key is optional unless marked; each is a top-level
key of the language TOML (and equally of a tome's `[runtime]` table):

| key | purpose |
|---|---|
| `command` | argv that runs ONE file. **REQUIRED unless `runCommand` is set.** The path is appended, or use a `"{file}"` placeholder for a trailing-flag language: `["odin", "run", "{file}", "-file"]` |
| `runCommand` | run the whole project, cwd = project dir; `{dir}`/`{entry}` substituted. Default: `command` + `entryFile` |
| `snippetRunCommand` | run a snippet after `buildCommand` (e.g. dotnet `--no-build`); `{dir}`/`{entry}` substituted, cwd = the snippet scratch dir. Default: `command` + `entryFile`, else `runCommand` |
| `buildCommand` | whole-project compile/check, cwd = project dir |
| `checkCommand` | per-FILE syntax check; path appended or `"{file}"`; exit 0 = clean → editor squiggles |
| `diagRegex` | single-quoted regex, Python named groups `(?P<file>)(?P<line>)(?P<col>)(?P<sev>)(?P<code>)(?P<msg>)` (all optional), matched over check/build output |
| `scaffoldCommand` | create a project; `{project}`/`{dir}` substituted. Default: write `entryFile` = `starterCode` |
| `projectFile` | file that marks a scaffolded project; `{project}` substituted (e.g. `"{project}.csproj"`). Default: `entryFile` |
| `commandTargetTools` | optional array of task runners whose non-option positional arguments name distinct target/rule mechanisms. Make is inferred automatically from a `Makefile` or direct `make` runtime command |
| `packageCommand` | install a package; `{dir}`/`{package}` substituted. Default: packages unsupported |
| `validationDependencies` | **tome-level** array of packages required by authored solutions, starters, or executable samples. This declares what validation needs; keep it out of the reusable language TOML |
| `validationCreateCommand` | create a shared isolated validation environment; `{dir}` substituted. Optional when `validationPackageCommand` can populate a plain directory |
| `validationPackageCommand` | install one environment-scoped validation dependency; `{dir}`/`{package}` substituted. Runs once per package in a content-addressed directory under `.tome-build/validation-envs` |
| `validationEnv` | environment-name → value table applied to the worker and independent harness gates; `{dir}` and existing environment placeholders such as `{PATH}` are expanded |
| `validationProjectPackageCommand` | install one dependency into each validator-created scratch project; `{dir}`/`{package}` substituted. Defaults to `packageCommand` when no environment installer is configured |
| `deliveryCreateCommand` | create a fresh final-proof environment; `{env}` substituted |
| `deliveryResolveCommand` | optional dependency-resolution preflight using `{env}`/`{requirements}` |
| `deliveryInstallCommand` | install the learner project's exact manifest; `{env}`/`{requirements}` substituted |
| `deliveryBuildCommand` | real packager argv; final `[proof].packageArgs` are appended |
| `deliveryArtifact` / `deliveryRequirements` | optional paired clean-staging declarations; when present they must exactly equal the sealed proof paths and `deliveryBuildCommand` must consume `{artifact}` and `{env}` |
| `entryFile` | the file `command` runs / the scaffold writes (e.g. `"main.py"`) |
| `starterCode` | the entry file's contents written by the default scaffold |
| `newFileExt` | default extension for the NEW FILE button |
| `codeExt` | array of extensions collected for grading/the editor |
| `excludeDirs` | extra dirs skipped while collecting (dot-dirs and `node_modules/__pycache__/venv/bin/obj/build/out/target` are always skipped) |
| `editorLang` | Monaco language id (any id; an id Monaco doesn't ship gets a generated tokenizer — see `[syntax]`) |
| `language` | display name, used in grader/oracle prompts |
| `buildTimeout` / `runTimeout` / `deliveryTimeout` | seconds for build/scaffold, project runs, and clean packaging |
| `snippetEntry` | regex: a lesson `<pre><code>` block matching it is a whole program, so §7 builds it. Absent → the language's samples are never compiled |
| `snippetPrelude` | text prepended to such a block when its first line is missing (Odin's `package main`). Usually unset |
| `diagIgnore` | regexes for diagnostics that are artifacts of judging a snippet alone: names the prose declared earlier, sibling modules a single-file build cannot see |
| `snippetFragment` | regex: a block that is NOT a whole program but matches this is a code FRAGMENT — §7 wraps it in `snippetWrap` and compiles it too (failures are hard-gate WARNs, not ERRORs). Blocks matching neither regex (shell transcripts, program output, diagrams) stay unchecked. Requires `snippetWrap`; absent → fragments are never compiled |
| `snippetWrap` | template containing `{code}`: the scratch shell a fragment is compiled inside (Odin: `"main :: proc() {\n{code}\n}"`) |
| `snippetHoist` | regex: fragment lines lifted above the wrap before compiling (imports, package headers) |
| `snippetFragmentSkip` | regex: fragment shapes no wrap can make judgeable (Odin: a `case` list whose `switch` header lives in the prose) — skipped outright |
| `snippetFragmentIgnore` | extra `diagIgnore`-style regexes applied to fragments only: the cascades a forgiven undeclared name causes downstream (`invalid type` fields, ambiguous overloads on unknown-typed arguments). Whole programs never get these passes |

### Package-delivery execution model

`runtimes/delivery.py` executes create, resolve, install, and build argv in that order, always with
cwd set to the learner project. It expands `{dir}` to that project, `{env}` to its fresh
`.arcanum-delivery-env`, and `{requirements}`/`{artifact}` to absolute paths inside the project.
The fresh environment is not a copy of the learner source tree. Do not change cwd to `{env}` and
expect a project file or source to exist there: build from project cwd, or explicitly stage inputs
by path. The final proof's `packageArgs` are appended verbatim to `deliveryBuildCommand`; a direct
target-style command such as `["make"]` therefore treats `packageArgs = ["package"]` as the
`package` target and the Phase-2 mechanism contract must own that exact target.

When the runtime owns a clean-location copy, set both `deliveryArtifact` and
`deliveryRequirements`, then use `{artifact}` as the source and `{env}` as the destination in the
build argv. Those declarations are an executable audit contract, not descriptive metadata.

```toml
# global-configs/runtimes/odin.toml — the zero-code language example
language = "Odin"
entryFile = "main.odin"
newFileExt = ".odin"
editorLang = "odin"                                  # Monaco has no Odin mode — [syntax] below generates one
command = ["odin", "run", "{file}", "-file"]         # {file} → the path
checkCommand = ["odin", "check", "{file}", "-file"]  # exit 0 = clean → editor squiggles
diagRegex = '^(?P<file>[^(\n]+)\((?P<line>\d+):(?P<col>\d+)\) (?:\w+ )?Error: (?P<msg>.*)$'
starterCode = '''
package main
import "core:fmt"
main :: proc() { fmt.println("hello") }
'''
```
Any command the host can run works: `["bash"]`, `["deno", "run"]`, `["lua"]`, … The
engine accepts `command`/`runCommand` (and the other keys) declared directly in a
tome's `[runtime]` table, but a SHIPPED tome always names a language file: the
validator hard-fails a `[runtime] name` with no matching TOML anywhere under
`global-configs/runtimes/` (create one — it's zero code), and any runtime command whose binary isn't installed
on the host. Keep the tome's own `[runtime]` table for tome-specific overrides. Omit
both `checkCommand` and `buildCommand` and the course simply has no editor squiggles.

### Isolated validation dependencies

When course code needs a third-party library, declare it in the tome rather than hiding
an installation in a runtime command:

```toml
[runtime]
name = "python"
project = "MyProject"
validationDependencies = ["some-library"]
```

The Python runtime, for example, creates a content-addressed virtual environment and makes
its `python3` visible through `PATH` to the warm author worker and every harness-owned gate.
A project package manager such as NuGet or Cargo instead applies the dependency inside each
temporary scaffold used for validation. Both paths are runtime-declared argv arrays (never a
shell string), cached where safe, and isolated from the learner's workspace and system runtime.
If a new ecosystem needs packages, define the appropriate environment or scratch-project
commands in its reusable runtime TOML; tome authors should only list package names.

### Calibrating `snippetEntry` for a new language

`checkCommand` + `diagRegex` already build a file and parse the result, so the
validator can compile the lesson's own code samples. The only per-language judgement
is *which blocks are whole programs* and *which diagnostics don't count*. Same
procedure every time:

1. Set `snippetEntry` to a regex matching a block that stands alone — Odin needs
   `main :: proc`, Perl accepts any statement keyword. Add `snippetPrelude` only if
   the language demands a header the samples omit (Odin's `package main`).
2. Run `python3 tools/validate_tome.py tomes/<a tome already known good>`.
3. Every surviving diagnostic is either a **real bug in that tome** or an **artifact**
   of judging a fragment alone. Fix the first; add the second to `diagIgnore`.
4. Repeat until the known-good tome reports zero. Only then is the language calibrated.

The same procedure calibrates **fragment checking** (`snippetFragment` +
`snippetWrap`): pick a fragment regex too narrow to catch transcripts or output
(odin uses `':=|::|\bfmt\.'`), wrap in the smallest shell that makes a statement
list legal, and run against a known-good tome. Each surviving diagnostic is a real
bug, an artifact to name in `snippetFragmentIgnore` (cascades from names the wrap
forgave: `invalid type`, ambiguous overloads), or an excerpt shape no wrap fixes —
name that in `snippetFragmentSkip`. Repeat until the known-good tome reports zero.

Two rules keep this honest. **Start narrow.** Lesson bodies also put shell transcripts
and ASCII diagrams inside `<pre><code>`, and a `snippetEntry` of "any unindented line"
drags them in as false positives — that is why `python` and `nasm` only accept blocks
with an obvious entry point, and why `perl` (whose blocks are always code) can accept
any statement. **Leave it unset when in doubt.** A language with no `snippetEntry` is
skipped silently, which is strictly better than a check nobody trusts; `java` ships
that way on purpose, since its samples trail loose statements after a class and extend
supertypes that live outside the file.

### `[syntax]` — highlighting for a language Monaco doesn't ship (optional)

When `editorLang` names a language Monaco has no mode for, the editor
(`web/editor.js` `buildMonarch`) auto-registers it and generates syntax
highlighting and auto-closing pairs from an optional `[syntax]` table; its
`keywords` also double as bare-keyword completions, which keeps a minimal
language usable — but real IntelliSense (dot-members, snippets, type inference)
still comes only from `[completions]` below.
`global-configs/runtimes/odin.toml` is the reference example:

```toml
[syntax]
lineComment = "//"            # optional: the line-comment token
blockComment = ["/*", "*/"]   # optional: a 2-element [open, close] array
strings = ["\"", "`", "'"]    # optional: string delimiters, each exactly ONE character (default ["\"", "'"])
keywords = ["package", "import", "proc", "struct", "if", "else", "for"]   # highlighted AND offered as completions
types = ["int", "string", "bool", "rune", "true", "false", "nil"]         # highlighted as types
```
If `editorLang` is an id Monaco already ships (`python`, `csharp`, `go`, …), the
editor keeps Monaco's own tokenizer and `[syntax]` is ignored.

### `[completions]` — editor IntelliSense (REQUIRED for every language)
**Every language gets IntelliSense from this table alone — csharp included**
(one generic, TOML-driven provider in `web/editor.js` serves them all; no
language data lives in JS). Monaco ships *tokenizers* (syntax colors) for ids
like `csharp`, `java`, and `python`, but never completions — an id with no
`[completions]` gives the student a lab editor that suggests nothing, which is
a review failure, not a cosmetic gap. Coverage rules:
- The shipped language TOMLs (`dotnet`, `python`, `java`, `odin`) already carry
  thorough tables — a tome whose `[runtime] name` points at one is covered with
  zero work. **Prefer this** over rolling your own runtime for a language the
  platform already ships.
- A NEW `global-configs/runtimes/<name>.toml` MUST include one: full keyword
  list, 8–12 snippets, the dot-members a beginner meets, and a returns map.
- A runtime declared **inline** in the tome's `[runtime]` table (no language
  file) needs it too — the table nests as `[runtime.completions]` and merges
  into the payload the same way. An inline runtime without it ships a dead
  editor.
`[syntax].keywords` alone are the bare-keyword fallback, not IntelliSense. See
`global-configs/runtimes/python.toml` for the canonical worked example and
`dotnet.toml` for the richest one — it also exercises the optional
power keys: `declTypes` (declared-type → member key, for C-family `List<string>
xs = …`), `enumRegex`/`recordRegex` (user enums complete their values,
positional records their params), `memberExtends` (share one member surface,
e.g. LINQ, across several keys), `fallback` (member table guessed for unknown
receivers), `internalKeys` (member keys hidden from top-level suggestions), and
`staticRewrites` (accepting `x.IsNullOrEmpty()` rewrites to
`string.IsNullOrEmpty(x)`):

```toml
[completions]
keywords = ["def", "return", …]           # keyword + builtin suggestions
snippets = [["for", "for loop", "for ${1:item} in ${2:items}:\n\t$0"], …]
                                          # [prefix, description, Monaco snippet]
types = [["^(f?[\"']|input\\()", "str"], …]  # ORDERED rhs-regex → member key: infers a
                                          # variable's type from its last `x = <rhs>`
declTypes = [["^List<", "list"], …]       # ORDERED declared-type-regex → member key:
                                          # types `List<int> xs = …` from the DECLARATION,
                                          # for languages that write the type before the name
classRegex = '^class\s+(\w+)[^\n]*:\n(…)' # find user classes; groups = (name, body)
methodRegex = 'def\s+(\w+)'               # methods in the body → completed after `obj.`
propRegex = '(\w+)\s*:'                   # or fields (e.g. struct members)
ctorRegex = '^(\w+)\s*\('                 # maps `d = Dog()` back to class Dog
enumRegex = '\benum\s+(\w+)\s*\{([^}]*)\}'    # user enums complete their members (groups: name, body)
recordRegex = '\brecord\s+(\w+)\s*\(([^)]*)\)' # positional params → properties (groups: name, params)
memberExtends = { list = "linq", array = "linq" }  # a key inherits another key's members
fallback = "linq"                         # member table guessed for an unknown receiver
internalKeys = ["str", "list", "linq"]    # member keys that are receiver-only (hidden from top level)

[completions.members]                     # dot-completions per receiver/type key
str = [["upper()", "m", "str — uppercase copy", "upper()"], …]
                                          # [label, kind m|p|f, detail, insert-snippet]
[completions.returns]                     # method → member key: resolves call chains
upper = "str"                             # text.strip().upper().  → still str members
split = "list"                            # parts = text.split(",") → parts. is a list
[completions.staticRewrites]              # instance member that is really a static call:
str = [["IsNullOrEmpty()", "bool — static", "string.IsNullOrEmpty({recv})"], …]
                                          # accepting `x.IsNullOrEmpty()` rewrites to
                                          # `string.IsNullOrEmpty(x)` ({recv} = the receiver)
```

**Full functional parity — the complete key set the generic provider reads.**
Every capability the old hand-written C# provider had is now one of these keys, so
a NEW language reaches identical treatment by populating them. Regexes compile
with JS `gm` flags (no inline `(?m)`); member tuples are `[label, kind (`m`
method / `p` property / `f` field), detail, insert-snippet]`.

| key | enables | tier |
|---|---|---|
| `keywords` | keyword/builtin completions at the top level | **baseline** |
| `snippets` | multi-line templates (`for`, `class`, entry-point…) — author 8–12 | **baseline** |
| `[completions.members]` | `receiver.` dot-completions per type key — cover every stdlib type a beginner meets | **baseline** |
| `types` | infer a variable's type from its assignment RHS (`x = <rhs>`) | **baseline** |
| `returns` | resolve call chains (`a.trim().upper().`) and RHS-ending calls | **baseline** |
| `classRegex`+`methodRegex`+`propRegex` | complete the student's OWN classes/structs (members from the body) | **baseline** |
| `ctorRegex` | map `d = new Dog()` / `d = Dog()` back to the user class | **baseline** |
| `declTypes` | type a variable from a written-before-name declaration (`Map<K,V> m = …`) — needed for C-family/Java/Go, not Python | **parity** (any statically-typed language) |
| `enumRegex` | user enums complete their members (`Color.` → `Red`…) | **parity** (if the language has enums) |
| `recordRegex` | positional record/data-class params complete as properties | **parity** (if the language has them) |
| `memberExtends` | one shared member surface (LINQ, iterator protocol) mixed into several keys without copy-paste | **parity** (if a family of types shares methods) |
| `fallback` | a sensible member guess when the receiver type is unknown | **parity** |
| `internalKeys` | keep receiver-only keys (`str`, `list`) out of the top-level type list | **parity** (cosmetic but expected) |
| `[completions.staticRewrites]` | an instance-looking member that is really a static call, rewritten on accept | **parity** (only where the language has this shape, e.g. C# `string.IsNullOrEmpty`) |

Baseline keys are REQUIRED for any new language. Parity keys are required
**wherever the language has the feature they serve** — a statically-typed
language without `declTypes`, or an enum-having language without `enumRegex`,
ships visibly worse IntelliSense than C# and is a review miss. `dotnet.toml` is
the reference for the full set; `python.toml` shows the dynamically-typed subset
(no `declTypes`/`staticRewrites`, since Python has neither shape). **After
authoring a language, prove it:** add a few scenarios to
`tools/tests/web/test_completions.js` (it stubs Monaco and drives the real provider with
your TOML) and run `node tools/tests/web/test_completions.js`.

### `externalWorkspace` — a project the player builds with their own external tools (optional)

Most tomes run and grade code the engine scaffolds inside `save/`. Set `[runtime]
externalWorkspace = true` **only** when the course teaches a real external
toolchain and the build must live in the player's own project instead:

> **The tome NEVER hardwires the location — the student always chooses it.**
> `externalWorkspace = true` *requires* external mode for the course (there is no
> built-in editor); on first entry to a Great Working the player is prompted to
> **CHOOSE PROJECT FOLDER** and points the run/grade/diagnostics machinery at a
> folder they built in their own IDE (stored per-tome in their save, not in the
> tome). The student can ALSO opt into external mode themselves on ANY tome via
> the workbench's **USE MY OWN EDITOR** control. The difference is only whether
> external mode is forced: the folder is the player's decision either way. Set
> `externalWorkspace` when the course is *designed* around an external toolchain
> (a Gradle mod, a Papyrus project); otherwise leave it unset and let students opt
> in only if they want to. (The old `workspaceDir` absolute-path key is removed —
> a course must not decide where a player's project lives.)

```toml
[runtime]
name = "dotnet"
externalWorkspace = true   # REQUIRE external mode; the player picks the folder
```
- Runs, diagnostics, and grading operate on the folder the player chose.
  `/api/scaffold` **refuses to touch it**, and the engine **never resets it** —
  the player's tools own it entirely.
- Grading collects at most **400** files, skipping dot-dirs, `node_modules`,
  `__pycache__`, `venv`, `bin`, `obj`, `build`, `out`, `target`, plus any
  `[runtime] excludeDirs`. Binary assets are not collected.

**The recipe is `externalWorkspace` + `[runtime]` overrides — nothing more.**
Because this tome's `[runtime]` table overrides every engine key (`runCommand`,
`buildCommand`, `checkCommand`, `diagRegex`, `codeExt`, `excludeDirs`,
`projectFile`), any toolchain drivable from a CLI works — and GUI-only tools (an
IDE, a game editor) work too, because grading only **reads** the workspace files;
the engine never launches the tool.

**Minigames never move into the workspace.** Every `write` lab, hex-defense
intrusion, and duel snippet still runs in the engine's scratch dir through
`command`/`snippetRunCommand` — and when `buildCommand` is set, it runs FIRST,
cwd = that scratch dir, before every snippet (it also feeds the lab editor's
squiggles). Two consequences for an `externalWorkspace` tome:
1. It still needs a `command` that compiles/runs ONE plain file of the language,
   or every minigame in the tome is dead.
2. A project-only `buildCommand` such as `["./gradlew", "build"]` fails in the
   scratch dir and blocks every snippet. Wrap it so it degrades to a single-file
   compile when the project markers are absent, e.g.
   `["bash", "-lc", "if [ -f ./gradlew ]; then bash ./gradlew build; else javac Main.java; fi"]`.

A few shapes:
- **A Java mod (Gradle):** `name = "java"` (the shipped language file brings
  single-file compile-run, syntax checks, and editor completions), plus
  `externalWorkspace = true`, the conditional `buildCommand` above, and a javac
  `diagRegex`. `tomes/waymark/tome.toml` is the complete worked example — its
  `command` override pins `-source 8 -target 8`, and its `snippetRunCommand =
  ["java", "-cp", "{dir}", "Main"]` runs the class the scratch-dir build
  already compiled.
- **A Stardew Valley SMAPI mod (C#):** the `dotnet` runtime already covers it —
  just add `externalWorkspace = true`.
- **Skyrim Papyrus scripts:** `buildCommand` = the Papyrus compiler, a matching
  `diagRegex`, and `codeExt = [".psc"]`.
- **An Odin project built by real tooling** (not the built-in per-file compile):
  `name = "odin"`, `externalWorkspace = true`, and `runCommand = ["odin", "run", "."]`.

When there is no CLI build at all, **omit `buildCommand`** — the AI grader still
grades the collected source/text files, so set `codeExt` to the text formats that
matter (source, configs, notes); binary assets are never collected.

**A tome that uses `externalWorkspace` MUST tell the player which external tools to
install.** State them in the first lesson (and each freestyle brief that needs
them) with resource links. Mark a resource **optional** when solid official docs
exist online that the player can follow to install/set up; mark it **mandatory**
when you (the AI author) cannot verify enough online material to teach the setup
from — and in that case the tome's own lessons MUST carry the install/setup steps.
