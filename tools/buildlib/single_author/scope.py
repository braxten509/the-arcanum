"""Phase-aware writable and protected paths for the persistent tome author."""
import os

from .. import BUILD_DIR, REPO, VALIDATOR_FAILURE_DIR
from ..continuity import handoff_dir, handoff_path
from ..course_map import amendment_path, map_path, proposal_path, seed_path
from ..course_map.author_spec import spec_root
from ..phase2_research import ledger_path
from ..course.state import evidence_dir, failure_dir, state_path
from ..prerequisites.review import calls_path as prerequisite_calls_path


def author_paths(build_id, from_phase, tid, unit):
    phase = int((unit or {}).get("phase") or from_phase)
    progress = os.path.join(BUILD_DIR, f"{build_id}.progress")
    writable = [progress] if os.path.exists(progress) else []
    if phase == 1:
        writable.append(os.path.join(BUILD_DIR, f"{build_id}.plan.md"))
    else:
        tome = os.path.join(REPO, "tomes", tid)
        if phase == 2:
            writable.extend((tome, proposal_path(build_id), spec_root(build_id),
                             ledger_path(build_id),
                             os.path.join(REPO, "global-configs", "runtimes")))
        elif phase == 3 and (unit or {}).get("kind") == "section":
            writable.extend((os.path.join(tome, "sections", unit["section"]),
                             handoff_path(tid, unit["section"]),
                             os.path.join(BUILD_DIR, f"{build_id}.section-progress.json")))
        else:
            writable.append(tome)
            if phase >= 7:
                # Clean replay persists its operational project/evidence under BUILD_DIR.
                writable.append(BUILD_DIR)
    protected = [seed_path(build_id), map_path(build_id), state_path(build_id),
                 amendment_path(build_id), evidence_dir(build_id), failure_dir(build_id),
                 prerequisite_calls_path(build_id),
                 os.path.join(VALIDATOR_FAILURE_DIR, build_id),
                 os.path.join(BUILD_DIR, f"{build_id}.prerequisite-reviews"),
                 os.path.join(BUILD_DIR, f"{build_id}.phase-ai-reviews"),
                 os.path.join(BUILD_DIR, f"{build_id}.phase-snapshots"),
                 os.path.join(BUILD_DIR, f"{build_id}.course-control.log.jsonl")]
    if phase != 2:
        protected.extend((spec_root(build_id), ledger_path(build_id)))
    for suffix in ("launch.json", "session.json", "active.json", "result.json",
                   "cancelled.json", "conversation.jsonl", "status-log.jsonl"):
        protected.append(os.path.join(BUILD_DIR, f"{build_id}.{suffix}"))
    if phase != 1:
        protected.append(os.path.join(BUILD_DIR, f"{build_id}.plan.md"))
    if phase != 2:
        protected.append(proposal_path(build_id))
    if phase == 3 and (unit or {}).get("kind") == "section":
        current = handoff_path(tid, unit["section"])
        root = handoff_dir(tid)
        if os.path.isdir(root):
            protected.extend(os.path.join(root, name) for name in os.listdir(root)
                             if os.path.join(root, name) != current)
    elif os.path.isdir(handoff_dir(tid)):
        protected.append(handoff_dir(tid))
    return ([path for path in writable if os.path.exists(path)],
            [path for path in protected if os.path.exists(path)])


def author_hidden_paths(build_id):
    """Historical attempt data that a restarted author must never inspect."""
    paths = [
        os.path.join(VALIDATOR_FAILURE_DIR, build_id),
        os.path.join(BUILD_DIR, f"{build_id}.phase-ai-reviews"),
        os.path.join(BUILD_DIR, f"{build_id}.prerequisite-reviews"),
        prerequisite_calls_path(build_id),
        os.path.join(BUILD_DIR, f"{build_id}.phase-snapshots"),
        os.path.join(BUILD_DIR, f"{build_id}.reset-stash"),
        os.path.join(BUILD_DIR, f"{build_id}.author-usage.jsonl"),
        os.path.join(BUILD_DIR, f"{build_id}.conversation.jsonl.bak"),
    ]
    return [path for path in paths if os.path.exists(path)]
