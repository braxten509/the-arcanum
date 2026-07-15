import assert from "node:assert/strict";
import { mergeForgeTraceLines } from "../web/app/forge/trace-lines.js";

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
  `VALIDATOR COMMAND START [${epoch(12, 45, 59, 654).toFixed(3)}] › python3 tools/validate_section.py tomes/hollowmere s06`,
  `VALIDATOR COMMAND COMPLETE [${epoch(12, 46, 6, 871).toFixed(3)}] (exit 0) › python3 tools/validate_section.py tomes/hollowmere s06`,
].join("\n"), new Date(2026, 6, 15, 12, 47).getTime());

assert.deepEqual(merged.map((line) => line.slice(0, 8)), [
  stamp(12, 39, 55), stamp(12, 40, 13), stamp(12, 40, 18), stamp(12, 42, 23),
  stamp(12, 43, 26), stamp(12, 44, 39), stamp(12, 45, 59), stamp(12, 46, 6),
]);
assert.match(merged[1], /^12:40:13  VALIDATOR COMMAND START ›/);
assert.match(merged[2], /^12:40:18  VALIDATOR COMMAND COMPLETE \(exit 0\) ›/);
assert.ok(merged.every((line) => !/\[\d{10}/.test(line)), merged.join("\n"));

const afterMidnight = mergeForgeTraceLines([
  "23:59:58  exec_command › before midnight",
  "00:00:02  apply_patch › after midnight",
], "", new Date(2026, 6, 16, 0, 1).getTime());
assert.deepEqual(afterMidnight.map((line) => line.slice(0, 8)), ["23:59:58", "00:00:02"]);

console.log("forge trace chronology: OK");
