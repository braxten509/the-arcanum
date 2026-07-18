/* Persist-first variant assignment helpers. */
export function currentAssignment(state, familyId) {
  return state && state.variantAssignments && state.variantAssignments[familyId] || null;
}

export function assignVariant(state, assignment) {
  if (!assignment || !assignment.familyId || !assignment.variantId || !assignment.variantHash) {
    throw new Error("variant assignment is incomplete");
  }
  state.variantAssignments = state.variantAssignments || {};
  const current = state.variantAssignments[assignment.familyId];
  if (current && !current.abandoned) return current;
  state.variantAssignments[assignment.familyId] = Object.freeze({ ...assignment, abandoned: false });
  return state.variantAssignments[assignment.familyId];
}

export function syncVariantAssignment(state, assignment) {
  if (!assignment || !assignment.familyId || !assignment.variantId || !assignment.variantHash) {
    throw new Error("variant assignment is incomplete");
  }
  state.variantAssignments = state.variantAssignments || {};
  state.variantAssignments[assignment.familyId] = Object.freeze({
    ...assignment, abandoned: false, authority: "server",
  });
  return state.variantAssignments[assignment.familyId];
}

export function abandonVariant(state, familyId, at = new Date().toISOString()) {
  const current = currentAssignment(state, familyId);
  if (!current) throw new Error("no assigned variant exists");
  state.variantAssignments[familyId] = { ...current, abandoned: true, abandonedAt: at };
  return state.variantAssignments[familyId];
}
