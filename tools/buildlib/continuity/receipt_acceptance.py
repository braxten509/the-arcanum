"""Read prior section acceptance without depending on course-state projection."""
import json
import os


def accepted_prior_sections(tid, sid, ids, course, handoff_digest, build_dir):
    """Consume durable receipts while course state itself is being rebuilt."""
    if not course:
        return set()
    build_id = course.get("buildId")
    accepted = set()
    for prior in ids[:ids.index(sid)]:
        path = os.path.join(build_dir, f"{build_id}.course-evidence", f"{prior}.json")
        try:
            with open(path, encoding="utf-8") as handle:
                receipt = json.load(handle)
        except (OSError, ValueError, TypeError):
            continue
        if (receipt.get("version") == 1
                and receipt.get("mapDigest") == course.get("digest")
                and receipt.get("handoffSha256") == handoff_digest(tid, prior)):
            accepted.add(prior)
    return accepted
