"""Global section bounds for every newly authored Arcanum course."""

MIN_SECTIONS = 2
MAX_SECTIONS = 40

# Finish 1 is the minimum honest route from the selected entry baseline to the
# requested project. Project Scope may enlarge the artifact, but low Starting
# Level changes lesson support rather than granting extra project milestones.
MASTERY_ONE_SECTION_CAPS = {1: 4, 2: 6, 3: 8, 4: 10, 5: 12}


def section_count_error(count):
    return (f"section count must be from {MIN_SECTIONS} through {MAX_SECTIONS}, "
            f"inclusive; found {count}")


def mastery_section_cap(mastery, project_scope):
    """Return the calibrated section ceiling for one Phase-0 selection."""
    mastery, project_scope = int(mastery), int(project_scope)
    if mastery == 1:
        return MASTERY_ONE_SECTION_CAPS.get(project_scope, MAX_SECTIONS)
    return MAX_SECTIONS


def mastery_section_count_error(count, mastery, project_scope):
    cap = mastery_section_cap(mastery, project_scope)
    if int(count) <= cap:
        return ""
    return (
        f"Mastery 1 is the minimum from-scratch project path: Project Scope "
        f"{int(project_scope)}/5 permits at most {cap} sections, found {int(count)}. "
        "Consolidate adjacent prerequisites into lessons inside the project milestone they "
        "enable, remove language material the requested project does not require, and keep "
        "Starting Level support inside lessons rather than creating extra sections."
    )
