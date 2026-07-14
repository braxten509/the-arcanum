import assert from "node:assert/strict";

import {
  describeForgeStatus,
  forgeActivityKey,
  forgeActivityLine,
  forgeActivityOptions,
  forgeStatusLines,
  forgeTraceLines,
  forgeTraceSectionProgress,
} from "../web/app/forge/activity.js";

const raw = [
  "> Phase 1 — Concept & arc   [runner: claude-cli claude-opus-4-8]",
  "+ a patch line that must stay diagnostic-only",
  "ok = False",
  "> Phase 2 — Skeleton & voice   [runner: codex-cli gpt-5.6-luna]",
  "worker narration that must not reach the activity line",
  "x gates failed (validator) -> re-running phase 2 (attempt 2)",
].join("\n");

assert.deepEqual(forgeStatusLines(raw), [
  "> Phase 1 — Concept & arc   [runner: claude-cli claude-opus-4-8]",
  "> Phase 2 — Skeleton & voice   [runner: codex-cli gpt-5.6-luna]",
  "x gates failed (validator) -> re-running phase 2 (attempt 2)",
]);

const phaseTwo = {
  phase: 2,
  phaseTitle: "Skeleton & voice",
  runner: "codex-cli gpt-5.6-luna",
  logtail: raw,
};
assert.deepEqual(forgeActivityOptions(phaseTwo), [
  "The gates found issues — repairing phase 2 (attempt 2)",
  "Building the lesson skeleton",
  "Setting the narrative voice",
  "Checking the project structure",
  "gpt-5.6-luna is still working",
]);

assert.equal(
  describeForgeStatus("· authoring s03 [3/8] on codex-cli gpt-5.6-terra", { phase: 3 }),
  "Authoring s03 — section 3 of 8",
);
assert.equal(
  describeForgeStatus("· authoring warm batch 2/4 [4-6/12] s04, s05, s06 on claude-cli claude-sonnet-5", { phase: 3 }),
  "Authoring warm batch 2 of 4 — sections 4–6 of 12",
);
assert.equal(
  describeForgeStatus("· Phase 3 full gate is clean — reconciliation worker not needed", { phase: 3 }),
  "The complete course gate is clean — skipping reconciliation",
);
assert.equal(
  describeForgeStatus("· Phase 3 resume: 2 incomplete section(s) assigned", { phase: 3 }),
  "Resuming only 2 incomplete sections",
);
assert.equal(forgeStatusLines("· Phase 3 resume gate is already clean — worker not needed").length, 1);
assert.deepEqual(forgeActivityOptions({ phase: 3, awaitingRunner: { phase: 3 } }), [
  "Waiting for you to choose a new hand",
]);

const sectionKey = forgeActivityKey({ phase: 3, sections: "2/8", logtail: "" });
assert.notEqual(sectionKey, forgeActivityKey({ phase: 3, sections: "3/8", logtail: "" }));
const exactProgress = {
  phase: 3,
  sections: "4-6/12",
  runner: "claude-cli claude-sonnet-5",
  sectionProgress: { section: "s05", index: 5, total: 12, state: "validating" },
  logtail: "",
};
assert.deepEqual(forgeActivityOptions(exactProgress), [
  "Validating s05 — section 5 of 12",
  "Writing lessons and exercises",
  "Checking continuity between sections",
  "Advancing the course project",
  "claude-sonnet-5 is still working",
]);
assert.equal(
  forgeActivityLine({ ...exactProgress, totalPhases: 9 }, 1),
  "Phase 3 / 9 — Writing lessons and exercises",
);
assert.notEqual(forgeActivityKey(exactProgress), forgeActivityKey({
  ...exactProgress,
  sectionProgress: { section: "s06", index: 6, total: 12, state: "authoring" },
}));

assert.deepEqual(forgeTraceLines(["", " exec ", "line one", "line two", "line three"]), [
  "line one", "line two", "line three",
]);
assert.deepEqual(forgeTraceSectionProgress({
  phase: 3,
  logtail: "· forecast: 12 sections · 51 lessons",
  toolTrace: [
    "14:21:04 read › /repo/tomes/example/sections/s03/section.toml",
    "14:21:52 write › /repo/tomes/example/sections/s09/lessons/l03.toml",
    "14:22:41 write › {}",
  ],
}), { section: "s09", index: 9, total: 12, state: "authoring", inferred: true });
assert.equal(forgeTraceSectionProgress({
  phase: 3,
  logtail: "· forecast: 12 sections",
  toolTrace: ["14:21:04 read › /repo/tomes/example/sections/s11/section.toml"],
}), null);

console.log("forge activity: OK");
