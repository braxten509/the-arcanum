/* Pure cognitive-task registry; interaction rendering is deliberately orthogonal. */
export class CognitiveTaskRegistry {
  constructor() { this.entries = new Map(); }

  register(id, policy) {
    if (this.entries.has(id)) throw new Error(`duplicate cognitive task: ${id}`);
    if (!policy || !Number.isInteger(policy.version) || policy.version < 1) {
      throw new TypeError(`cognitive task ${id} needs a positive integer version`);
    }
    if (!Array.isArray(policy.capabilities) || !policy.capabilities.length
        || policy.capabilities.some((item) => typeof item !== "string" || !item)) {
      throw new TypeError(`cognitive task ${id} needs declared capabilities`);
    }
    this.entries.set(id, Object.freeze({ id, reviewable: false,
      independentEligible: false, ...policy }));
    return this;
  }

  get(id) { return this.entries.get(id) || null; }
  names() { return [...this.entries.keys()]; }
}

const task = (capabilities, policy = {}) => ({ version: 1, capabilities, ...policy });

export const cognitiveTasks = new CognitiveTaskRegistry()
  .register("recall", task(["review-evidence"], { reviewable: true }))
  .register("recognize", task(["review-evidence"], { reviewable: true }))
  .register("predict", task(["review-evidence", "independent-evidence"], { reviewable: true, independentEligible: true }))
  .register("trace", task(["review-evidence", "independent-evidence"], { reviewable: true, independentEligible: true }))
  .register("explain", task(["review-evidence", "independent-evidence"], { reviewable: true, independentEligible: true }))
  .register("complete", task(["review-evidence"], { reviewable: true }))
  .register("modify", task(["independent-evidence"], { independentEligible: true }))
  .register("debug", task(["review-evidence", "independent-evidence"], { reviewable: true, independentEligible: true }))
  .register("test-design", task(["review-evidence", "independent-evidence"], { reviewable: true, independentEligible: true }))
  .register("build", task(["independent-evidence"], { independentEligible: true }))
  .register("integrate", task(["independent-evidence"], { independentEligible: true }))
  .register("refactor", task(["independent-evidence"], { independentEligible: true }))
  .register("profile", task(["independent-evidence"], { independentEligible: true }))
  .register("evaluate-tradeoff", task(["independent-evidence"], { independentEligible: true }))
  .register("design-defense", task(["independent-evidence"], { independentEligible: true }));

export function cognitivePolicy(exercise) {
  return cognitiveTasks.get(exercise && exercise.cognitiveTask);
}

export function independentEvidenceEligible(exercise) {
  const policy = cognitivePolicy(exercise);
  const interaction = exercise && (exercise.interaction || exercise.type);
  return !!(policy && policy.independentEligible
    && !["type", "copy-code"].includes(interaction)
    && ["independent", "cold"].includes(exercise.scaffold));
}
