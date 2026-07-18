import assert from "node:assert/strict";
import { InteractionRegistry } from "../../../web/app/game/interactions/registry.js";
import { CognitiveTaskRegistry, cognitiveTasks } from "../../../web/app/mastery/cognitive.js";
import { dispatchCommand, registerCommand, resetCommandsForTest } from "../../../web/app/core/commands.js";

const validInteraction = { version: 1, capabilities: ["test"], create: () => ({}) };
const registry = new InteractionRegistry().register("valid", validInteraction);
assert.equal(registry.get("valid").version, 1);
assert.throws(() => registry.register("valid", validInteraction), /duplicate/);
assert.throws(() => registry.register("unversioned", { capabilities: ["x"], create() {} }), /version/);
assert.throws(() => registry.register("uncapable", { version: 1, create() {} }), /capabilities/);
assert.throws(() => registry.get("unknown"), /unsupported/);

for (const id of cognitiveTasks.names()) {
  const entry = cognitiveTasks.get(id);
  assert.equal(entry.version, 1);
  assert.ok(entry.capabilities.length);
}
assert.throws(() => new CognitiveTaskRegistry().register("bad", { version: 1 }), /capabilities/);

resetCommandsForTest();
registerCommand("sum", (left, right) => left + right);
assert.equal(dispatchCommand("sum", 2, 3), 5);
assert.throws(() => registerCommand("sum", () => 0), /duplicate/);
assert.throws(() => dispatchCommand("missing"), /not registered/);

// The real interaction composition can be imported without a browser boot. This checks
// every shipped renderer/alias, not only a fake registry entry.
globalThis.window = { addEventListener() {} };
globalThis.setInterval = () => 0;
const { interactions } = await import("../../../web/app/game/interactions/index.js");
for (const id of interactions.names()) {
  const entry = interactions.get(id);
  assert.equal(entry.version, 1, `${id} has a contract version`);
  assert.ok(entry.capabilities.length, `${id} declares capabilities`);
  assert.equal(typeof entry.create, "function", `${id} has a controller factory`);
}

console.log("frontend extensibility registry contracts: OK");
