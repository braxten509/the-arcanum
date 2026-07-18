/* Pure learner-facing capability ledger rows; hidden evidence details never enter the model. */
export function ledgerRows(state, labels = {}) {
  return Object.entries((state && state.capabilityEvidence) || {})
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([id, evidence]) => ({
      id, label: labels[id] || id,
      taught: !!evidence.taught,
      practiced: !!evidence.practiced,
      supported: !!evidence.supported,
      independent: !!evidence.independent,
      due: !!evidence.due,
      retained: !!evidence.retained,
    }));
}

export function ledgerState(row) {
  if (row.retained) return "retained";
  if (row.due) return "due for varied review";
  if (row.independent) return "independently demonstrated";
  if (row.supported) return "completed with support";
  if (row.practiced) return "practiced";
  if (row.taught) return "taught";
  return "not started";
}
