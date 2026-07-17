"""Global section bounds for every newly authored Arcanum course."""

MIN_SECTIONS = 2
MAX_SECTIONS = 40


def section_count_error(count):
    return (f"section count must be from {MIN_SECTIONS} through {MAX_SECTIONS}, "
            f"inclusive; found {count}")
