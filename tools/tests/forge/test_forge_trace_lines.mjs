import assert from "node:assert/strict";
import { fallbackForgeRunningCost, forgeHarnessValidationState, formatForgeRunningCost,
  formatForgeWeeklyUsage, mergeForgeConversationCosts,
  mergeForgeTraceLines } from "../../../web/app/forge/trace-lines.js";

const epoch = (hour, minute, second, millis = 0) =>
  new Date(2026, 6, 15, hour, minute, second, millis).getTime() / 1000;
const stamp = (hour, minute, second) =>
  [hour, minute, second].map((part) => String(part).padStart(2, "0")).join(":");

const merged = mergeForgeTraceLines([
  `${stamp(12, 39, 55)}  exec_command › rg -n hollowmere`,
  `${stamp(12, 42, 23)}  apply_patch › patch`,
  `${stamp(12, 43, 26)}  apply_patch › patch`,
  `${stamp(12, 44, 39)}  apply_patch › patch`,
], [
  `VALIDATOR COMMAND START [${epoch(12, 40, 13, 559).toFixed(3)}] › python3 tools/validate_section.py tomes/hollowmere s05`,
  `VALIDATOR COMMAND COMPLETE [${epoch(12, 40, 18, 876).toFixed(3)}] (exit 0) › python3 tools/validate_section.py tomes/hollowmere s05`,
  `AI VALIDATOR CALL START [${epoch(12, 41, 1).toFixed(3)}] › section quality s05 › codex-cli gpt-5.6-sol`,
  `AI VALIDATOR CALL COMPLETE [${epoch(12, 41, 9).toFixed(3)}] (PASS) › section quality s05 › codex-cli gpt-5.6-sol`,
  `AI API-EQUIVALENT COST COMPLETE [${epoch(12, 41, 10).toFixed(3)}] › PHASE 3 SECTION s05 › $1.44`,
  `VALIDATOR COMMAND START [${epoch(12, 45, 59, 654).toFixed(3)}] › python3 tools/validate_section.py tomes/hollowmere s06`,
  `VALIDATOR COMMAND COMPLETE [${epoch(12, 46, 6, 871).toFixed(3)}] (exit 0) › python3 tools/validate_section.py tomes/hollowmere s06`,
].join("\n"), new Date(2026, 6, 15, 12, 47).getTime());

assert.deepEqual(merged.map((line) => line.slice(0, 8)), [
  stamp(12, 39, 55), stamp(12, 40, 13), stamp(12, 40, 18), stamp(12, 41, 1),
  stamp(12, 41, 9), stamp(12, 41, 10), stamp(12, 42, 23), stamp(12, 43, 26),
  stamp(12, 44, 39), stamp(12, 45, 59), stamp(12, 46, 6),
]);
assert.match(merged[1], /^12:40:13  VALIDATOR COMMAND START ›/);
assert.match(merged[2], /^12:40:18  VALIDATOR COMMAND COMPLETE \(exit 0\) ›/);
assert.match(merged[3], /^12:41:01  AI VALIDATOR CALL START ›/);
assert.match(merged[4], /^12:41:09  AI VALIDATOR CALL COMPLETE \(PASS\) ›/);
assert.match(merged[5], /^12:41:10  AI API-EQUIVALENT COST COMPLETE › PHASE 3 SECTION s05 › \$1\.44/);
assert.ok(merged.every((line) => !/\[\d{10}/.test(line)), merged.join("\n"));

const conversation = mergeForgeConversationCosts([
  { at: epoch(12, 41, 9), kind: "harness", text: "Validation passed." },
  { at: epoch(12, 41, 11), kind: "assistant", text: "Starting the next unit." },
], [
  `AI API-EQUIVALENT COST COMPLETE [${epoch(12, 41, 10).toFixed(3)}] › PHASE 3 SECTION s05 › $1.44`,
].join("\n"));
assert.deepEqual(conversation.map((row) => row.kind), ["harness", "harness", "assistant"]);
assert.equal(conversation[1].eventKey, "gpt-cost:3:s05");
assert.equal(conversation[1].text,
  "Phase 3 section s05 › $1.44 (1.03% weekly usage)");

const resumedConversation = mergeForgeConversationCosts([
  ...conversation,
  { at: epoch(12, 41, 12), kind: "harness", text: "Unrelated checkpoint." },
], `AI API-EQUIVALENT COST COMPLETE [${epoch(12, 41, 13).toFixed(3)}] › PHASE 3 SECTION s05 › $1.51`);
assert.equal(resumedConversation.filter((row) => row.eventKey === "gpt-cost:3:s05").length, 1);
assert.equal(resumedConversation.find((row) => row.eventKey === "gpt-cost:3:s05").text,
  "Phase 3 section s05 › $1.51 (1.08% weekly usage)");

const phaseTotalConversation = mergeForgeConversationCosts([], [
  `AI API-EQUIVALENT COST COMPLETE [${epoch(12, 42, 0).toFixed(3)}] › PHASE 1 TOTAL › $3.82`,
].join("\n"));
assert.equal(phaseTotalConversation[0].text,
  "Phase 1 total › $3.82 (2.73% weekly usage)");
const requestedPhase2Format = mergeForgeConversationCosts([], [
  `AI API-EQUIVALENT COST COMPLETE [${epoch(12, 42, 1).toFixed(3)}] › PHASE 2 TOTAL › $3.04`,
].join("\n"));
assert.equal(requestedPhase2Format[0].text,
  "Phase 2 total › $3.04 (2.17% weekly usage)");

assert.equal(forgeHarnessValidationState({ kind: "harness",
  text: "Validation passed for Phase 1 — Concept & arc. Continuing with Phase 2." }), "pass");
assert.equal(forgeHarnessValidationState({ kind: "harness",
  text: "Validation failed for Phase 1 — Concept & arc. The report was returned." }), "fail");
assert.equal(forgeHarnessValidationState({ kind: "harness",
  text: "The author repaired Phase 1 and returned it to the harness." }), "");
assert.equal(forgeHarnessValidationState(phaseTotalConversation[0]), "");

const running = fallbackForgeRunningCost([
  { at: epoch(12, 30, 0), kind: "harness", eventKey: "gpt-cost:1:total",
    text: "AI API-EQUIVALENT COST COMPLETE › PHASE 1 TOTAL › $0.78" },
  { at: epoch(12, 31, 0), kind: "harness", eventKey: "gpt-cost:2:total",
    text: "AI API-EQUIVALENT COST COMPLETE › PHASE 2 TOTAL › $0.44" },
  { at: epoch(12, 32, 0), kind: "harness", eventKey: "gpt-cost:3:s01",
    text: "AI API-EQUIVALENT COST COMPLETE › PHASE 3 SECTION s01 › $1.00" },
  { at: epoch(12, 33, 0), kind: "harness", eventKey: "gpt-cost:3:s02",
    text: "AI API-EQUIVALENT COST COMPLETE › PHASE 3 SECTION s02 › $1.12" },
  { at: epoch(12, 34, 0), kind: "harness", eventKey: "gpt-cost:3:total",
    text: "AI API-EQUIVALENT COST COMPLETE › PHASE 3 TOTAL · SUM OF 2 SECTIONS › $2.12" },
], "");
assert.equal(running.displayUsd, 3.34);
assert.equal(formatForgeRunningCost(running), "$3.34");
assert.equal(formatForgeWeeklyUsage({ displayUsd: 4.07, gptPricedTurns: 1 }),
  "(2.91% weekly usage)");

const partialRunning = fallbackForgeRunningCost([], [
  `AI API-EQUIVALENT COST COMPLETE [${epoch(13, 1, 0).toFixed(3)}] › PHASE 1 TOTAL › $0.81+ · PARTIAL: 1 AI TURN LACKED TOKEN USAGE`,
].join("\n"));
const partialConversation = mergeForgeConversationCosts([], [
  `AI API-EQUIVALENT COST COMPLETE [${epoch(13, 1, 0).toFixed(3)}] › PHASE 1 TOTAL › $0.81+ · PARTIAL: 1 AI TURN LACKED TOKEN USAGE`,
].join("\n"));
assert.equal(partialConversation[0].text,
  "Phase 1 total › $0.81+ (0.58% weekly usage) · Partial: 1 AI turn lacked token usage");
assert.equal(formatForgeRunningCost(partialRunning), "$0.81");
assert.equal(formatForgeRunningCost({ displayUsd: 0, gptPricedTurns: 0,
  gptUnpricedTurns: 1 }), "UNAVAILABLE");
assert.equal(formatForgeWeeklyUsage({ displayUsd: 0, gptPricedTurns: 0 }),
  "(weekly usage unavailable)");

const afterMidnight = mergeForgeTraceLines([
  "23:59:58  exec_command › before midnight",
  "00:00:02  apply_patch › after midnight",
], "", new Date(2026, 6, 16, 0, 1).getTime());
assert.deepEqual(afterMidnight.map((line) => line.slice(0, 8)), ["23:59:58", "00:00:02"]);

const fullAuthorTrace = Array.from({ length: 80 }, (_, index) =>
  `${stamp(13, 0, index % 60)}  exec_command › author tool ${index}`);
const retainedValidator = `AI VALIDATOR CALL COMPLETE [${epoch(12, 59, 59).toFixed(3)}] (PASS) › section quality s01 › codex-cli gpt-5.6-luna`;
const retained = mergeForgeTraceLines(fullAuthorTrace, retainedValidator,
  new Date(2026, 6, 15, 13, 2).getTime());
assert.equal(retained.length, 81);
assert.ok(retained.some((line) => line.includes("AI VALIDATOR CALL COMPLETE")));

console.log("forge trace chronology: OK");
