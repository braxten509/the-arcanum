/* State migration and evidence mutations. Callers own persistence and rendering. */
import { SAVE_VERSION, isEvidenceTome } from "./policy.js";

const own = (value) => (value && typeof value === "object" && !Array.isArray(value) ? value : {});
const array = (value) => (Array.isArray(value) ? value : []);

export function evidenceDefaults() {
  return {
    exerciseEvidence: {}, capabilityEvidence: {}, masteryLabs: {}, variantAssignments: {},
    assessmentReceipts: {}, masteryStatus: "learning",
  };
}

function allExercises(tome) {
  return (tome && tome.sections || []).flatMap((section) =>
    (section.lessons || []).flatMap((lesson) => lesson.exercises || []));
}

export function migrateState(input, tome) {
  const state = own(input);
  const defaults = evidenceDefaults();
  for (const [key, value] of Object.entries(defaults)) {
    if (key === "masteryStatus") state[key] = typeof state[key] === "string" ? state[key] : value;
    else state[key] = own(state[key]);
  }
  if (isEvidenceTome(tome)) {
    for (const exercise of allExercises(tome)) {
      if (state.exerciseEvidence[exercise.id]) continue;
      const legacy = own(state.ex)[exercise.id];
      if (!legacy || !legacy.ok) continue;
      state.exerciseEvidence[exercise.id] = {
        attempts: Number(legacy.a || 0), resolved: true,
        supportUsed: !!legacy.skipped, supportKinds: legacy.skipped ? ["scroll"] : [],
        independent: null, retained: false,
        capabilityIds: array(exercise.capabilities), lastVariantId: "",
      };
    }
  }
  state.v = SAVE_VERSION;
  return state;
}

export function ensureExerciseRecord(state, exercise) {
  state.exerciseEvidence = own(state.exerciseEvidence);
  if (!state.exerciseEvidence[exercise.id]) {
    state.exerciseEvidence[exercise.id] = {
      attempts: 0, resolved: false, supportUsed: false, supportKinds: [],
      independent: false, retained: false, capabilityIds: array(exercise.capabilities),
      lastVariantId: "",
    };
  }
  return state.exerciseEvidence[exercise.id];
}

function capabilityRecord(state, capabilityId) {
  state.capabilityEvidence = own(state.capabilityEvidence);
  return state.capabilityEvidence[capabilityId] || (state.capabilityEvidence[capabilityId] = {
    taught: false, practiced: false, supported: false, independent: false,
    retained: false, due: false, evidenceIds: [],
  });
}

export function recordSupport(state, exercise, kind) {
  const record = ensureExerciseRecord(state, exercise);
  record.supportUsed = true;
  if (!record.supportKinds.includes(kind)) record.supportKinds.push(kind);
  for (const capabilityId of record.capabilityIds) capabilityRecord(state, capabilityId).supported = true;
  return record;
}

export function recordAttempt(state, exercise, { resolved = false, variantId = "" } = {}) {
  const record = ensureExerciseRecord(state, exercise);
  record.attempts += 1;
  if (variantId) record.lastVariantId = variantId;
  if (!resolved) return record;
  record.resolved = true;
  const evidenceEligible = exercise.type !== "type"
    && ["independent", "cold"].includes(exercise.scaffold)
    && !record.supportUsed;
  record.independent = evidenceEligible;
  for (const capabilityId of record.capabilityIds) {
    const capability = capabilityRecord(state, capabilityId);
    capability.practiced = true;
    capability.supported = capability.supported || record.supportUsed;
    if (evidenceEligible) {
      capability.independent = true;
      capability.due = true;
      if (!capability.evidenceIds.includes(exercise.id)) capability.evidenceIds.push(exercise.id);
    }
  }
  return record;
}

export function recordTeaching(state, capabilityIds) {
  for (const capabilityId of capabilityIds || []) capabilityRecord(state, capabilityId).taught = true;
}

export function recordReview(state, exercise, passed) {
  const record = ensureExerciseRecord(state, exercise);
  if (!passed) return record;
  record.retained = record.independent === true;
  for (const capabilityId of record.capabilityIds) {
    const capability = capabilityRecord(state, capabilityId);
    if (capability.independent) {
      capability.retained = true;
      capability.due = false;
    }
  }
  return record;
}

export function applyAssessmentReceipt(state, performanceId, receipt) {
  if (!receipt || receipt.version !== 1 || receipt.performanceId !== performanceId) {
    throw new Error("assessment receipt does not match the performance");
  }
  state.assessmentReceipts = own(state.assessmentReceipts);
  state.assessmentReceipts[performanceId] = receipt;
  for (const capabilityId of receipt.capabilityIds || []) {
    const capability = capabilityRecord(state, capabilityId);
    capability.practiced = true;
    if (receipt.supportUsed) capability.supported = true;
    if (receipt.independent && receipt.essentialPassed && Number(receipt.weightedTotal) >= 80) {
      capability.independent = true;
      capability.due = true;
      if (!capability.evidenceIds.includes(receipt.receiptHash)) capability.evidenceIds.push(receipt.receiptHash);
    }
  }
  return receipt;
}
