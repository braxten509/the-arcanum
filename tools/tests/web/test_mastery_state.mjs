import assert from "node:assert/strict";
import { applyAssessmentReceipt, migrateState, recordAttempt, recordSupport } from "../../../web/app/mastery/evidence.js";
import { blockingReviewCount, deriveMasteryStatus, lessonResolved, workingPassed } from "../../../web/app/mastery/policy.js";
import { abandonVariant, assignVariant } from "../../../web/app/mastery/variants.js";

const exercise = { id: "x1", type: "write", required: true, scaffold: "independent", capabilities: ["language-data"] };
const tome = { mastery: { evidenceVersion: 1, level: 3 }, sections: [{ lessons: [{ id: "l1", exercises: [exercise] }] }] };
const state = migrateState({ v: 1, ex: { x1: { ok: true, a: 2 } }, read: {} }, tome);
assert.equal(state.v, 2);
assert.equal(state.exerciseEvidence.x1.resolved, true);
assert.equal(state.exerciseEvidence.x1.independent, null, "legacy success must not become mastery");
assert.equal(lessonResolved(tome.sections[0].lessons[0], state), true);
assert.equal(migrateState(state, tome).v, 2, "migration is idempotent");

const fresh = migrateState({ ex: {}, read: {} }, tome);
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

console.log("mastery state/progression tests: OK");
