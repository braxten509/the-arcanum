#!/usr/bin/env python3
"""Keep the harness-owned build contracts in step with an authored tome.

Three actions, all for a tome that is edited after its build finished:

``adopt``  materialize whatever contracts this build never had -- the sealed course map
           and the per-section continuity handoffs. Creates nothing that already exists.
``plan``   ``adopt`` plus the Phase-1 build plan itself, reconstructed from the tome, for
           a tome finished before plans existed. Every other contract hangs off the plan,
           so this is the one action that moves a tome onto the full shipping gate; it
           refuses rather than write a plan the sealed map cannot be built against.
``reseal`` reconcile an ADOPTED course map with the tome after an authorized structural
           edit, through the audited amendment path. A planned map is left alone.

This exists as a command because the server side is forbidden from importing buildlib
(``architecture-policy.toml``: serverForbiddenImports), so the Binder's harness reaches
these the same way it reaches every validator -- as a subprocess.
"""
import argparse
import os
import sys

# Direct execution puts ``tools/`` on sys.path but not the repository root, which the
# course-map code needs to reach the server-side ``arcanum`` package.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from buildlib.course_map.adopt import (  # noqa: E402
    AdoptionError, adopt_build, reconcile_adopted_map)
from buildlib.workflow.adopted_plan import adopt_plan  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("adopt", "plan", "reseal"))
    parser.add_argument("tome", help="tome id, e.g. homunculus")
    parser.add_argument("--build-id", default="",
                        help="authoring build id; defaults to the tome id")
    parser.add_argument("--reason", default="",
                        help="why the map is being re-sealed (required by reseal)")
    args = parser.parse_args()
    build_id = args.build_id or args.tome
    try:
        if args.action in ("adopt", "plan"):
            # A plan that cannot be reconstructed is a fact about the tome, not a failed
            # command: the tome simply stays on the gate it already had. Reporting it as an
            # error would abort the ordinary adoption below and reach the Binder as though
            # the amendment itself could not be prepared.
            notes = []
            if args.action == "plan":
                try:
                    notes += adopt_plan(build_id, args.tome)
                except AdoptionError as exc:
                    notes.append("this tome cannot be put under the full shipping gate yet, "
                                 f"so it keeps the gate it already had: {exc}")
            notes += adopt_build(build_id, args.tome)
        else:
            note = reconcile_adopted_map(build_id, args.tome, args.reason)
            notes = [note] if note else []
    except (AdoptionError, ValueError) as exc:
        print(f"ERROR {args.action}: {exc}", file=sys.stderr)
        return 1
    for note in notes:
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
