// Bindery provider-restore check: four bindery pools share kind "opencode-cli"
// (Go, Zen, Local, OpenRouter), so restoring a saved {kind, model} by kind alone
// always lands on whichever is listed first. That downgraded a resumed OpenRouter
// author to the Go pool's first model and, since the harness only reuses a session
// when the model matches exactly, turned every resume into a restart. Drives the
// REAL matchProvider out of forge.js.
//   node tools/tests/web/test_provider_restore.js
// Assert-based, no framework; exits non-zero on the first failure.
const fs = require("fs");
const assert = require("assert");
const { execSync } = require("child_process");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..", "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");
const source = read("web", "app", "forge", "forge.js");

// pull the real implementation rather than restating it, so a regression here fails
const found = source.match(/export const matchProvider = [\s\S]*?;\n/);
assert(found, "matchProvider not found in forge.js - did the restore logic move?");
const matchProvider = new Function(
  `${found[0].replace("export ", "")}; return matchProvider;`)();
const resolve = (saved, pools) => (matchProvider(pools, saved) || {}).id;

// the shape /api/models actually returns (arcanum/ai/catalog.py model_census)
const fixture = [
  { id: "claude-cli", kind: "claude-cli", models: [["claude-opus-4-8"], ["claude-haiku-4-5"]] },
  { id: "codex-cli", kind: "codex-cli", models: [["gpt-5.6-sol"], ["gpt-5.6-luna"]] },
  { id: "opencode-cli", kind: "opencode-cli", models: [["opencode-go/deepseek-v4-flash"]] },
  { id: "opencode-zen", kind: "opencode-cli", models: [["opencode/big-pickle"]] },
  { id: "local", kind: "opencode-cli", models: [["ollama/qwen3:32b"]] },
  { id: "openrouter", kind: "opencode-cli", models: [["openrouter/minimax/minimax-m3"]] },
];
const at = (saved) => resolve(saved, fixture);

// the reported bug: every opencode-cli pool must resolve to its own provider
assert.strictEqual(at({ kind: "opencode-cli", model: "openrouter/minimax/minimax-m3" }),
  "openrouter", "OpenRouter model must restore the OpenRouter provider");
assert.strictEqual(at({ kind: "opencode-cli", model: "opencode/big-pickle" }),
  "opencode-zen", "Zen model must restore the Zen provider");
assert.strictEqual(at({ kind: "opencode-cli", model: "ollama/qwen3:32b" }),
  "local", "Local model must restore the Local provider");
assert.strictEqual(at({ kind: "opencode-cli", model: "opencode-go/deepseek-v4-flash" }),
  "opencode-cli", "Go model must restore the Go provider");

// unambiguous kinds still work, and a stale model falls back to the kind
assert.strictEqual(at({ kind: "claude-cli", model: "claude-opus-4-8" }), "claude-cli");
assert.strictEqual(at({ kind: "opencode-cli", model: "retired/model" }), "opencode-cli",
  "an unknown model falls back to the first provider of its kind, never undefined");
assert.strictEqual(matchProvider(fixture, null), null, "no saved agent resolves to nothing");
assert.strictEqual(matchProvider(undefined, { kind: "claude-cli", model: "x" }), undefined,
  "a missing pool list must not throw");
console.log("restore: 8 scenarios OK");

// Both restore paths must use the shared helper. The failure picker in bindery.js was
// missed the first time this was fixed, which is how a resumed M3 author silently
// became opencode-go/deepseek-v4-flash. A local re-implementation there passes every
// test above while still being broken, so assert the wiring itself.
const bindery = read("web", "app", "forge", "bindery.js");
assert(/import \{[^}]*matchProvider[^}]*\} from "\.\/forge\.js"/.test(bindery),
  "bindery.js must import matchProvider from forge.js");
assert(/matchProvider\(altProviders, current\)/.test(bindery),
  "bindery.js failure picker must resolve its provider through matchProvider");
assert(!/altProviders\.find\(\(item\) => item\.kind === current\.kind\)/.test(bindery),
  "bindery.js still has the kind-only match that caused the downgrade");
console.log("wiring: bindery.js failure picker shares the helper OK");

// Restore disambiguates by model id, so every pool needs ids that are its own. A few ids
// are legitimately served by two pools (OPENCODE_FREE_IDS appear in both the Go and Zen
// lists) - either provider runs the same model, so that ambiguity is harmless and skipped.
// What must hold is that each pool still owns ids that resolve back to it; a pool with
// none has become unreachable from a saved selection, which is exactly this bug.
let census;
try {
  census = JSON.parse(execSync(
    "python3 -c \"import sys, json; sys.path.insert(0, '.'); "
    + "from arcanum.ai.catalog import model_census; print(json.dumps(model_census()['bindery']))\"",
    { cwd: ROOT, stdio: ["ignore", "pipe", "ignore"] }).toString());
} catch { census = null; }
if (!census) {
  console.log("census: skipped (model census unavailable)");
} else {
  const live = census.filter((pool) => pool.installed !== false && (pool.models || []).length);
  const owners = new Map();
  const key = (pool, id) => `${pool.kind} ${id}`;
  for (const pool of live)
    for (const row of pool.models || [])
      owners.set(key(pool, row[0]), (owners.get(key(pool, row[0])) || []).concat(pool.id));
  for (const pool of live) {
    const own = (pool.models || []).filter((row) => owners.get(key(pool, row[0])).length === 1);
    assert(own.length, `every model in ${pool.id} is also served by another pool, `
      + `so no saved selection can restore it`);
    for (const row of own)
      assert.strictEqual(resolve({ kind: pool.kind, model: row[0] }, live), pool.id,
        `${row[0]} restores to the wrong provider`);
  }
  console.log(`census: ${live.length} live pools, every pool reachable OK`);
}
console.log("ALL PROVIDER RESTORE TESTS PASS");
