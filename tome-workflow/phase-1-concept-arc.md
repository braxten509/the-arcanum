# Phase 1 — Concept & arc

Read **§1** (and **§2 [content]**). Decide the finished tool the student ships, the
language, the fiction (operation name, mentor persona, student term), and the visual
identity. Fix ONE spelling of the project name and derive every other form from it
(`ManaWeaver` → `mana-weaver`), **never the user's request phrasing** (a past run
shipped `teach-me-how-to-make` as the id). **Do NOT rename or move the tome folder** —
it is already `untitled` (the harness scaffolded it after Phase 0) and must STAY that
way until the harness renames it. Record the chosen name in `[runtime] project` (you
write that in Phase 2); the HARNESS renames the folder AND `meta.id` to its kebab-case
after Phase 2 — never `mv`/`cp` the tome directory yourself, in this phase or any other.
Design the op arc **backwards from the finished tool** — what capability does each op
add? The section count is an **outcome of that arc, not a target**; do not pad or
trim to a round number, and there is **no maximum** — add as many chapters as the arc
needs. Read the plan's **Starting level** block first: if it says the student does not
already know the course's language/tool, that language's fundamentals and toolchain are
their **own early chapters** (not assumed, not folded into the build) — a low starting
level legitimately makes the course longer.

⚠️ **The end product must be REAL — never simulate away the skill the course is
about.** The worst failure here is not a short course, it's a *hollow* one: it
teaches *about* the subject with mocks the engine can conveniently compile, instead
of teaching the student to actually *do* it. If the course promises the student can
DO X, then X's real tools and load-bearing fundamentals ARE the syllabus, however
hard they are to teach.
- **Concretely (the pattern, not a template to copy):** a reverse-engineering course
  whose "memory reads" and "function hooks" are plain-language stand-ins — no real
  disassembler, debugger, binary format, or artifact that actually loads — leaves the
  student able to *recognize* the ideas, not *perform* them. The real syllabus was the
  format, the calling conventions, the debugger, real hooking, a loadable build. The
  same trap exists in any tool-centric domain (OS internals with no boot, networking
  with no real packet, embedded with no flashed board).
- **Teach RECONNAISSANCE, not just the action.** The commonest half-course teaches how
  to *act on* a target but not how to *find* it. A reverse-engineering course that hands
  the student the addresses (`0x00401000`) and teaches only how to write the hook has
  skipped ~70% of the real job — *finding* the function and struct offsets with a
  disassembler (Ghidra/IDA), a debugger (x64dbg), and a memory scanner is the actual
  skill. Same shape everywhere: teach how to *find* the bug/packet/leak/offset, not only
  what to do once someone hands it to you.
- **Smell test, applied at concept time:** after the last op, could the student sit
  down with the *real* tool and a *real* target and do this unaided — including finding
  the target themselves? If every lab is a mock the engine ran for convenience, or every
  address is handed to them, the answer is no — and `meta.description` is promising an
  artifact the course never builds.
- **If the real toolchain can't run in the built-in workbench, that is precisely what
  `externalWorkspace` (§5) is for — commit to it HERE.** Downgrading to a mock to stay
  inside the default editor is the trap, not the workaround. If you genuinely must
  simulate part of it, say so plainly and don't promise a real deliverable you didn't
  build.
- **Obey the plan's Tooling policy (internal / external / both).** INTERNAL forbids
  `externalWorkspace` and any external download/install — everything runs in-browser.
  EXTERNAL and BOTH require teaching the real external tools (named in section 1 with
  `[[lessons.readings]]` links); set `externalWorkspace = true` where the real toolchain
  can't run in the browser. The validator enforces these; don't fight it.
- A deep, tool-centric domain taught to a newcomer is therefore a **from-zero course
  sized to its fundamentals and toolchain** — the fundamentals are their own chapters,
  not footnotes folded into one small artifact's build.

⚠️ **Calibrate `meta.description`/`bootLines` to the REAL prerequisite, not just
the language.** "No prior Python required" can be true of the *graded* exercises
while the *lesson prose* still assumes real-world/domain background (GPU
internals, ML math, networking) the student is expected to take on faith. If the
course is honestly "language from zero, domain assumed," say so — a one-clause
addition ("...some comfort with the idea of GPUs and machine learning will help")
costs nothing and prevents overselling.

→ **Produce:** the ordered section list + one line on what each op contributes.
