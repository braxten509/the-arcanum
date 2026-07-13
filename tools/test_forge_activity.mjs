import assert from "node:assert/strict";

import {
  describeForgeStatus,
  forgeActivityKey,
  forgeActivityOptions,
  forgeStatusLines,
  forgeTraceLines,
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
assert.deepEqual(forgeActivityOptions({ phase: 3, awaitingRunner: { phase: 3 } }), [
  "Waiting for you to choose a new hand",
]);

const sectionKey = forgeActivityKey({ phase: 3, sections: "2/8", logtail: "" });
assert.notEqual(sectionKey, forgeActivityKey({ phase: 3, sections: "3/8", logtail: "" }));

assert.deepEqual(forgeTraceLines(["", " exec ", "line one", "line two", "line three"]), [
  "line one", "line two", "line three",
]);

console.log("forge activity: OK");
