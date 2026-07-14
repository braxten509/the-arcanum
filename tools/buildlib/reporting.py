"""Measured end-of-build facts appended to the durable build plan."""

from .continuity import handoffs_exist, planned_edges, validate_all_handoffs
from .measure import forecast_line, measure
from .sections import section_ids


def append_ground_truth(tid, plan_path, timings):
    """Record disk measurements and timing; model-authored claims are not evidence."""
    mv = measure(tid)
    ids = section_ids(tid)
    with open(plan_path, "a", encoding="utf-8") as handle:
        handle.write("\n## Harness ground truth (measured from disk)\n")
        handle.write(f"- {forecast_line(mv)}\n")
        handle.write(f"- exercise points {mv['ex_points']} · freestyle rewards {mv['fs_reward']} "
                     f"→ fixed face-value {mv['base_earnable']}\n")
        if mv["bounty_max"]:
            handle.write(
                f"- repeatable hex-defense bonus {mv['bounty_min']}–{mv['bounty_max']} "
                f"per win (tier schedule sum {mv['bounty']}; excluded from fixed total)\n")
        handle.write(f"- banks: {mv['themes']} themes · {mv['shop']} shop items · "
                     f"{mv['badges']} badges\n")
        if handoffs_exist(tid) and ids:
            continuity_ok, _ = validate_all_handoffs(tid, ids, plan_path)
            handle.write(f"- continuity: {len(ids)} section handoffs · "
                         f"{len(planned_edges(plan_path, ids))} planned edges · "
                         f"gate {'CLOSED' if continuity_ok else 'BROKEN'}\n")
        if timings:
            handle.write("\n### Phase timings\n")
            for phase, runner, seconds, tries in timings:
                handle.write(f"- phase {phase}: {seconds}s via {runner}"
                             + (f" ({tries} attempts)" if tries > 1 else "") + "\n")
