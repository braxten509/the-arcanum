// Tome provider allowlist and role-aware restore check.
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
  { id: "claude-cli", kind: "claude-cli", roles: ["author", "validator", "reviewer"],
    models: [["claude-opus-4-8"], ["claude-haiku-4-5"]] },
  { id: "codex-cli", kind: "codex-cli", roles: ["author", "validator", "reviewer"],
    models: [["gpt-5.6-sol"], ["gpt-5.6-luna"]] },
  { id: "openai-api", kind: "openai-api", roles: ["validator"],
    models: [["gpt-5.6-sol"], ["gpt-5.6-luna"]] },
];
const at = (saved) => resolve(saved, fixture);

// The two CLIs and one API restore independently.
assert.strictEqual(at({ kind: "claude-cli", model: "claude-opus-4-8" }), "claude-cli");
assert.strictEqual(at({ kind: "codex-cli", model: "gpt-5.6-luna" }), "codex-cli");
assert.strictEqual(at({ kind: "openai-api", model: "gpt-5.6-luna" }), "openai-api");
assert.strictEqual(matchProvider(fixture, null), null, "no saved agent resolves to nothing");
assert.strictEqual(matchProvider(undefined, { kind: "claude-cli", model: "x" }), undefined,
  "a missing pool list must not throw");
console.log("restore: two CLIs and one API remain distinct");

// Both restore paths must use the shared helper. The failure picker in bindery.js was
// missed the first time this was fixed, which is how a resumed M3 author silently
// became opencode-go/deepseek-v4-flash. A local re-implementation there passes every
// test above while still being broken, so assert the wiring itself.
const bindery = read("web", "app", "forge", "bindery.js");
assert(/import \{[^}]*matchProvider[^}]*\} from "\.\/forge\.js"/.test(bindery),
  "bindery.js must import matchProvider from forge.js");
assert(/matchProvider\(activeAltProviders, current\)/.test(bindery),
  "bindery.js failure picker must resolve within the active role");
assert(!/altProviders\.find\(\(item\) => item\.kind === current\.kind\)/.test(bindery),
  "bindery.js still has the kind-only match that caused the downgrade");
console.log("wiring: bindery.js failure picker shares the helper OK");

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
  assert.deepStrictEqual(live.map((pool) => pool.id),
    ["claude-cli", "codex-cli", "openai-api"],
    "Tome census must expose exactly two CLIs and one API");
  assert.deepStrictEqual(live.find((pool) => pool.id === "openai-api").roles, ["validator"],
    "Codex API must remain a validator-only transport");
  for (const pool of live)
    assert.strictEqual(resolve({ kind: pool.kind, model: pool.models[0][0] }, live), pool.id);
  console.log("census: exact three-provider Tome allowlist OK");
}
console.log("ALL PROVIDER RESTORE TESTS PASS");
