import assert from "node:assert/strict";
import { applyAssessmentReceipt, migrateState, recordAttempt, recordSupport } from "../../../web/app/mastery/evidence.js";
import { blockingReviewCount, deriveMasteryStatus, evidenceCounts, lessonResolved, workingPassed } from "../../../web/app/mastery/policy.js";
import { abandonVariant, assignVariant, syncVariantAssignment } from "../../../web/app/mastery/variants.js";
import { cognitiveTasks, independentEvidenceEligible } from "../../../web/app/mastery/cognitive.js";

const exercise = { id: "x1", type: "write", required: true, scaffold: "independent", capabilities: ["language-data"] };
const tome = { mastery: { evidenceVersion: 1, level: 3 }, sections: [{ lessons: [{ id: "l1", exercises: [exercise] }] }] };
const state = migrateState({ v: 1, ex: { x1: { ok: true, a: 2 } }, read: {} }, tome);
assert.equal(state.v, 2);
assert.equal(state.exerciseEvidence.x1.resolved, true);
assert.equal(state.exerciseEvidence.x1.independent, null, "legacy success must not become mastery");
assert.equal(lessonResolved(tome.sections[0].lessons[0], state), true);
assert.equal(migrateState(state, tome).v, 2, "migration is idempotent");

const fresh = migrateState({ ex: {}, read: {} }, tome);
assert.deepEqual(evidenceCounts(fresh, ["language-data", "language-control"]), {
  total: 2, demonstrated: 0, due: 0, retained: 0,
}, "the sealed capability contract supplies the fresh-ledger denominator");
assert.deepEqual(evidenceCounts({ capabilityEvidence: {
  "language-data": { independent: true, due: true },
  stale: { independent: true, retained: true },
} }, ["language-data", "language-control", "language-data"]), {
  total: 2, demonstrated: 1, due: 1, retained: 0,
}, "undeclared and duplicate capability records cannot distort contract counts");
recordSupport(fresh, exercise, "hint");
assert.equal(recordAttempt(fresh, exercise, { resolved: true }).independent, false);
assert.equal(fresh.capabilityEvidence["language-data"].supported, true);

const receipt = { version: 1, performanceId: "transfer", capabilityIds: ["language-data"],
  supportUsed: false, independent: true, essentialPassed: true, weightedTotal: 86, receiptHash: "abc" };
applyAssessmentReceipt(fresh, "transfer", receipt);
assert.equal(fresh.capabilityEvidence["language-data"].independent, true);
assert.equal(deriveMasteryStatus(fresh, ["transfer"]), "provisional");
assert.equal(workingPassed({ total: 80, essentialPassed: true }), true);
assert.equal(workingPassed({ total: 99, essentialPassed: false }), false);

fresh.ex.x1 = { ok: true, due: 0, reviewUnresolved: true };
assert.equal(blockingReviewCount(tome.sections, fresh, 0), 1);

const assignment = assignVariant(fresh, { familyId: "transfer-family", variantId: "v1", variantHash: "f".repeat(64) });
assert.equal(assignVariant(fresh, { familyId: "transfer-family", variantId: "v2", variantHash: "e".repeat(64) }), assignment,
  "refresh cannot reroll an active assignment");
abandonVariant(fresh, "transfer-family", "now");
assert.equal(assignVariant(fresh, { familyId: "transfer-family", variantId: "v2", variantHash: "e".repeat(64) }).variantId, "v2");
const serverAssignment = syncVariantAssignment(fresh, {
  familyId: "transfer-family", variantId: "v3", variantHash: "d".repeat(64), attempt: 3,
});
assert.equal(serverAssignment.variantId, "v3", "server authority replaces stale browser assignment");

for (const task of cognitiveTasks.names().map((id) => cognitiveTasks.get(id))) {
  assert.equal(task.version, 1);
  assert.ok(task.capabilities.length, `${task.id} declares capabilities`);
}
assert.equal(independentEvidenceEligible({ interaction: "runnable-code", cognitiveTask: "build", scaffold: "cold" }), true);
assert.equal(independentEvidenceEligible({ interaction: "copy-code", cognitiveTask: "build", scaffold: "cold" }), false);
assert.equal(independentEvidenceEligible({ interaction: "runnable-code", cognitiveTask: "recall", scaffold: "cold" }), false);
assert.equal(independentEvidenceEligible({ interaction: "runnable-code", cognitiveTask: "build", scaffold: "guided" }), false);

console.log("mastery state/progression tests: OK");
