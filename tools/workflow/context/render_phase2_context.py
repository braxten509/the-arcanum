#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "tools")]

from buildlib import BUILD_DIR
from buildlib.course_map import _read_json, seed_path
from buildlib.course_map.author_spec import spec_root
from buildlib.phase2_research import ledger_path


def main():
    parser = argparse.ArgumentParser(
        description="Render the bounded authoring context for Phase 2.")
    parser.add_argument("build_id", metavar="BUILD_ID")
    args = parser.parse_args()
    build_id = args.build_id
    plan_path = os.path.join(BUILD_DIR, f"{build_id}.plan.md")
    plan = Path(plan_path).read_text(encoding="utf-8")
    arc = re.split(r"(?m)^## Harness ground truth\b", plan, 1)[0]
    seed = _read_json(seed_path(build_id))
    root = spec_root(build_id)
    packet = {
        "buildId": build_id,
        "sealedLessonSpine": [
            {key: section.get(key) for key in ("id", "title", "promise", "lessonCount")
             if key in section}
            for section in seed.get("sections") or []
        ],
        "edit": {
            "course": os.path.relpath(os.path.join(root, "course.json"), REPO),
            "mechanisms": os.path.relpath(os.path.join(root, "mechanisms.json"), REPO),
            "obligations": os.path.relpath(os.path.join(root, "obligations.json"), REPO),
            "sections": os.path.relpath(os.path.join(root, "sections"), REPO) + "/sNN.json",
            "research": os.path.relpath(ledger_path(build_id), REPO),
        },
        "materialize": f"python3 tools/workflow/materialize_phase2_map.py {build_id}",
    }
    print("PHASE 2 BOUNDED CONTEXT")
    print(json.dumps(packet, ensure_ascii=False, indent=2))
    print("\nSEALED PHASE 1 ARC\n" + arc[-60000:])


if __name__ == "__main__":
    main()
