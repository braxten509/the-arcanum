"""The Phase-1 Arc contract: the required parts and the boilerplate written into the plan.

Kept apart from checkpoints.py so the gate logic and the long contract text each stay
navigable. checkpoints.py re-exports these names, so importers can keep reaching them there."""

# The arc's REQUIRED parts — the gate checks each appears as a bold `**Label:**` line.
# Difficulty spine + Graduate ledger are plan deliverables Phase 1 has skipped before.
ARC_PARTS = ("Finished tool", "Language", "Project name", "Mentor persona", "Student term",
             "Visual identity", "Tooling fit", "Difficulty spine", "Graduate ledger", "Mastery proof",
             "Daily drivers",
             "Continuity map", "Artifact lifecycle", "Acceptance proof",
             "Acceptance scenarios", "Lesson counts", "Section list")
# The plan's daily-driver kit, machine-checked: each must be assigned CAN or CANNOT in
# the arc (Phase 1 has silently dropped the key-value type twice), and a CANNOT is a
# declared scope cut repeated in the Graduate ledger — never public catalog copy.
DAILY_DRIVERS = ("growable collection", "key-value", "strings", "errors")
ARC_HEADING = "## Arc (Phase 1 fills this in, later phases read it)\n"
# Written into the plan right under the heading, so the contract sits exactly where
# Phase 1 must write. Labels are listed WITHOUT the **…:** shape the gate matches on,
# or the instructions themselves would satisfy the gate.
ARC_CONTRACT = (
    "_Phase 1: write the arc below this line. The harness gates on these parts, each as\n"
    "its own bold `**Label:** value` line, labels spelled exactly: Finished tool;\n"
    "Language; Project name; Mentor persona; Student term; Visual identity; Tooling fit\n"
    "(exactly `<gate answer> — COMPATIBLE: evidence`; construction cannot pause to change it); Difficulty\n"
    "spine (the 3-6 concepts practitioners of this language/tool find hard and idiomatic\n"
    "at the target level); Graduate ledger (repeat the exact Language value verbatim and\n"
    "state `the student CAN … / still CANNOT …` with uppercase CAN and CANNOT); Language mastery (exactly `<Language> —\n"
    "Finish N/5: language exit ability`); Language capability spine (one physical line\n"
    "of unique stable `language-*` ids separated by ` -> `, meeting the selected Finish's\n"
    "generic count floor and every matching versioned language-profile area); Language performances\n"
    "(one physical semicolon-separated line of `sNN.working = <kind> [+ rationale]:\n"
    "description`, using guided-modification, familiar-independent-task, novel-transfer,\n"
    "unfamiliar-tradeoff, or architecture-defense as the selected level requires; make\n"
    "multiple tasks genuinely different and complementary, with each description limited\n"
    "to capabilities its task materially exercises and the combined set covering the\n"
    "required spine rather than repeating the whole checklist in every task);\n"
    "Mastery cognitive tasks (one physical line containing the exact central task ids\n"
    "for the selected Finish, separated by ` -> `); Mastery evidence performances\n"
    "(one physical semicolon-separated line of `id @ sNN.working|labNN = kind |\n"
    "context | aid | rationale|no-rationale | family|none | capability-id, ...`;\n"
    "Working entries use family `none`; lab entries use a stable kebab family id;\n"
    "use project, different, unrelated, or unfamiliar context and learning, limited,\n"
    "documentation-only, or cold aid exactly as the selected central profile permits);\n"
    "Mastery retention (one physical `language-* -> language-*` line covering every\n"
    "capability whose later varied retrieval is required by the selected Finish);\n"
    "Language foundation coverage (one physical semicolon-separated line mapping each\n"
    "universal role exactly once: `data = language-*; control = language-*;\n"
    "decomposition = language-*; failure = language-*; verification = language-*`;\n"
    "at Finish 3–5 also map `abstraction = language-*; modularity = language-*`, with\n"
    "a concrete structured-abstraction idiom and module/package/boundary mechanism; each\n"
    "role maps to a distinct idiomatic language capability, never a framework feature);\n"
    "Mastery proof (the named late language performances that satisfy the selected Finish\n"
    "level, how scaffolding fades before them, what novel language transfer they require,\n"
    "and how the learner's choices are justified—the finished reference\n"
    "artifact alone is not learner evidence); Daily drivers (this language's daily-driver kit, every item\n"
    "assigned as `item = CAN` or `item = CANNOT`, items spelled exactly: growable\n"
    "collection; key-value; strings; errors — a CANNOT is a deliberate scope cut and\n"
    "must be repeated in the Graduate ledger); Continuity map (one-line `sNN -> sMM:`\n"
    "edges for every non-adjacent API/data/file reuse and every promise a later section\n"
    "must honor; every edge names real sequential sections and points forward);\n"
    "Artifact lifecycle (the canonical files/\n"
    "entrypoints plus every temporary prompt, fixture, demo call, placeholder, or debug\n"
    "behavior, with the section that retires or deliberately ships it; wrap every inventory\n"
    "artifact—and no other token in this field—in backticks);\n"
    "Artifact ownership (one physical semicolon-separated exhaustive inventory using\n"
    "`path @ sNN.working -> ships` or `path @ sNN.working -> retires@sNN`; use stable\n"
    "relative paths or identifiers and include every Working learner-owned artifact;\n"
    "at every section at least one artifact must already be owned and not yet retired);\n"
    "Delivery contract (one physical line exactly `mode = runtime|package; artifact = path;\n"
    "requirements = path|none`; select package whenever the Arc promises a packaged,\n"
    "standalone, installable, or distributable result, and declare its paths as ships;\n"
    "all paths are normalized project-relative POSIX identifiers with no leading, trailing,\n"
    "or doubled slash and no `.` or `..` segment);\n"
    "Acceptance proof\n"
    "(a literal clean-start user journey from launch through the promised final outcome,\n"
    "including delivery outside the authoring surface when applicable); Acceptance scenarios\n"
    "(one physical line of unique stable kebab ids separated by ` -> `, matching every\n"
    "observable stage the executable acceptance adapter must report); Lesson counts\n"
    "(one physical line with every section id in order as `s01=5; s02=4`; each count\n"
    "must be 3 through 8 and becomes immutable in Phase 2); Section list\n"
    "(2 through 40 physical lines, each necessary to a named graduate or acceptance\n"
    "requirement and ordered by a cold-start walk from foundations to dependent milestone\n"
    "demands, sequential, in the exact form "
    "`1. **s01 — Title:** capability/build promise`; each promise must be 20 through\n"
    "360 characters because it also becomes the sealed project milestone; the harness deterministically "
    "scaffolds those entries)._\n")
ARC_MIN_CHARS = 500  # of the striker's own content, contract lines excluded
