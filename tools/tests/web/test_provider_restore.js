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
const foundValidator = source.match(/export const chooseValidator = [\s\S]*?;\n/);
assert(foundValidator, "chooseValidator not found in forge.js - did validator restore move?");
const chooseValidator = new Function(
  `${foundValidator[0].replace("export ", "")}; return chooseValidator;`)();

// the shape /api/models actually returns (arcanum/ai/catalog.py model_census)
const fixture = [
  { id: "claude-cli", kind: "claude-cli", roles: ["author", "validator", "reviewer"],
    models: [["claude-opus-4-8"], ["claude-haiku-4-5"]] },
  { id: "codex-cli", kind: "codex-cli", roles: ["author", "validator", "reviewer"],
    models: [["gpt-5.6-sol"], ["gpt-5.6-luna"]] },
  { id: "opencode-go", kind: "opencode-cli", roles: ["author", "validator", "reviewer"],
    models: [["opencode-go/deepseek-v4-pro"]] },
  { id: "openrouter", kind: "opencode-cli", roles: ["author", "validator", "reviewer"],
    models: [["openrouter/deepseek/deepseek-v4-pro"]] },
];
const at = (saved) => resolve(saved, fixture);

// The two native CLIs and two OpenCode-hosted routes restore independently.
assert.strictEqual(at({ kind: "claude-cli", model: "claude-opus-4-8" }), "claude-cli");
assert.strictEqual(at({ kind: "codex-cli", model: "gpt-5.6-luna" }), "codex-cli");
assert.strictEqual(at({ kind: "opencode-cli", model: "opencode-go/deepseek-v4-pro" }), "opencode-go");
assert.strictEqual(at({ kind: "opencode-cli", model: "openrouter/deepseek/deepseek-v4-pro" }), "openrouter");
assert.strictEqual(matchProvider(fixture, null), null, "no saved agent resolves to nothing");
assert.strictEqual(matchProvider(undefined, { kind: "claude-cli", model: "x" }), undefined,
  "a missing pool list must not throw");
console.log("restore: native CLIs and OpenCode hosted routes remain distinct");

const luna = { kind: "codex-cli", model: "gpt-5.6-luna", effort: "medium" };
const sol = { kind: "codex-cli", model: "gpt-5.6-sol", effort: "high" };
assert.strictEqual(chooseValidator(luna, null, sol, null, null), luna,
  "a resumed Luna selection was replaced by the recommended default");
assert.strictEqual(chooseValidator(null, luna, sol, null, null), luna,
  "a locally saved Luna selection was replaced by the recommended default");
assert.strictEqual(chooseValidator(null, null, sol, null, null), sol,
  "Sol should remain the default only when no validator choice exists");
console.log("validator: explicit Luna survives restore; Sol remains empty-state default");

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
    ["claude-cli", "codex-cli", "opencode-go", "openrouter"],
    "Tome census must expose the two native CLIs and two hosted OpenCode routes");
  assert(live.find((pool) => pool.id === "opencode-go").models.every((row) =>
    row[0].startsWith("opencode-go/")), "OpenCode Go pool leaked a non-Go model");
  for (const pool of live)
    assert.strictEqual(resolve({ kind: pool.kind, model: pool.models[0][0] }, live), pool.id);
  console.log("census: exact four-provider Tome allowlist OK");
}
console.log("ALL PROVIDER RESTORE TESTS PASS");
