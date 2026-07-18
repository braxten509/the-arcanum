/* Pure progression selectors for evidence-version tomes. No DOM, fetch, or globals. */
export const SAVE_VERSION = 2;
export const EVIDENCE_VERSION = 1;
export const MINIMUM_WORKING_SCORE = 80;

export function isEvidenceTome(tome) {
  return Number(tome && tome.mastery && tome.mastery.evidenceVersion) === EVIDENCE_VERSION;
}

export function requiredExercises(lesson) {
  return (lesson && Array.isArray(lesson.exercises) ? lesson.exercises : [])
    .filter((exercise) => exercise.required !== false);
}

export function exerciseEvidence(state, exercise) {
  const explicit = state && state.exerciseEvidence && state.exerciseEvidence[exercise.id];
  if (explicit) return explicit;
  const legacy = state && state.ex && state.ex[exercise.id];
  return legacy && legacy.ok
    ? { resolved: true, independent: null, supportUsed: !!legacy.skipped, retained: false }
    : { resolved: false, independent: false, supportUsed: false, retained: false };
}

export function lessonResolved(lesson, state) {
  const required = requiredExercises(lesson);
  return required.length
    ? required.every((exercise) => exerciseEvidence(state, exercise).resolved)
    : !!(state && state.read && state.read[lesson.id]);
}

export function sectionResolution(section, state) {
  const required = (section.lessons || []).flatMap(requiredExercises);
  const resolved = required.filter((exercise) => exerciseEvidence(state, exercise).resolved).length;
  return { required: required.length, resolved, fraction: required.length ? resolved / required.length : 1 };
}

export function completedLessonCount(sections, state) {
  return (sections || []).reduce(
    (count, section) => count + (section.lessons || []).filter((lesson) => lessonResolved(lesson, state)).length,
    0,
  );
}

export function blockingReviewCount(sections, state, now = Date.now()) {
  const clock = completedLessonCount(sections, state);
  let count = 0;
  for (const section of sections || []) for (const lesson of section.lessons || []) {
    for (const exercise of lesson.exercises || []) {
      const record = state && state.ex && state.ex[exercise.id];
      if (!record || !record.ok || exercise.required === false) continue;
      if (record.reviewUnresolved || (record.due != null && record.due <= clock)
          || (record.dueT != null && record.dueT <= now)) count += 1;
    }
  }
  return count;
}

export function workingUnlocked(section, sections, state, now = Date.now()) {
  return (section.lessons || []).every((lesson) => lessonResolved(lesson, state))
    && blockingReviewCount(sections, state, now) === 0;
}

export function workingPassed(best) {
  return !!(best && best.essentialPassed === true && Number(best.total) >= MINIMUM_WORKING_SCORE);
}

export function workingStatus(best, ready) {
  if (!best) return ready ? "ready" : "not ready";
  if (!best.essentialPassed) return "incomplete";
  return workingPassed(best) ? String(best.grade || "B").toUpperCase() : "incomplete";
}

export function evidenceCounts(state, capabilityIds) {
  const evidence = (state && state.capabilityEvidence) || {};
  const ids = Array.isArray(capabilityIds)
    ? [...new Set(capabilityIds.filter((id) => typeof id === "string" && id.length > 0))]
    : Object.keys(evidence);
  const records = ids.map((id) => evidence[id] || {});
  return {
    total: ids.length,
    demonstrated: records.filter((record) => record.independent).length,
    due: records.filter((record) => record.due).length,
    retained: records.filter((record) => record.retained).length,
  };
}

export function deriveMasteryStatus(state, requiredPerformanceIds = []) {
  const receipts = (state && state.assessmentReceipts) || {};
  const complete = requiredPerformanceIds.length > 0 && requiredPerformanceIds.every((id) => {
    const receipt = receipts[id];
    return receipt && receipt.independent && receipt.essentialPassed && Number(receipt.weightedTotal) >= 80;
  });
  if (!complete) return "learning";
  const counts = evidenceCounts(state);
  return counts.total > 0 && counts.retained === counts.total ? "retained" : "provisional";
}
