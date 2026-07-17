"""Thin public adapters kept outside the core course-map validator."""
import os
import re


BUILD_ID = re.compile(r"[A-Za-z0-9_-]+\Z")


def build_id_from_plan(plan_file):
    name = os.path.basename(str(plan_file or ""))
    suffix = ".plan.md"
    candidate = name[:-len(suffix)] if name.endswith(suffix) else ""
    return candidate if BUILD_ID.fullmatch(candidate) else ""


def validate_tome_alignment(build_id, tome_path, through=None):
    from ..course.alignment import validate_tome_alignment as validate_alignment
    return validate_alignment(build_id, tome_path, through)


def validate_map_locations(build_id, value):
    """Resolve paths against the course-map module's patchable build roots."""
    from .. import course_map
    from .locations import validate_locations
    return validate_locations(build_id, value, build_dir=course_map.BUILD_DIR,
                              repo=course_map.REPO)


def amend_course_map(build_id, candidate, reason):
    from ..course.amend import amend_course_map as amend
    return amend(build_id, candidate, reason)
