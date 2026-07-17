"""Regression checks for implementation-free learner project work orders."""
import copy

from tome_proof import public_section
from validatelib import _findings
from validatelib.proof import _check_blank_learner_scaffold, _check_lesson


def check_learner_author_work_order(section_factory, findings_for, assert_error):
    authored = section_factory()
    final_source = authored["freestyle"]["referenceSteps"][0]["content"]
    authored["lessons"][0]["artifactSteps"] = [{
        "id": "s01-main-work-order",
        "path": "main.py",
        "mode": "author",
        "instruction": ("Author main.py from the taught function contract without copying "
                        "the disposable example."),
        "checks": ["The proof command prints milestone and exits successfully."],
    }]
    authored["freestyle"]["referenceSteps"] = [{
        "id": "s01-reference",
        "path": "main.py",
        "mode": "rewrite",
        "preserves": "all-active",
        "instruction": "Privately reconstruct the learner-authored milestone implementation.",
        "content": final_source,
    }]
    clean = findings_for(authored, run=True)
    assert not [finding for finding in clean if finding[0] == "ERROR"], clean
    public = public_section(authored)
    work_order = public["lessons"][0]["artifactSteps"][0]
    assert work_order["mode"] == "author" and work_order["checks"]
    assert "content" not in work_order and "referenceSteps" not in public["freestyle"]

    leaked = copy.deepcopy(authored)
    leaked["lessons"][0]["artifactSteps"][0]["content"] = "return 'milestone'"
    assert_error(leaked, "may not contain solution content")

    unchecked = copy.deepcopy(authored)
    unchecked["lessons"][0]["artifactSteps"][0].pop("checks")
    assert_error(unchecked, "needs one or more specific observable checks")

    hidden_noop = copy.deepcopy(authored)
    hidden_noop["freestyle"]["referenceSteps"][0] = copy.deepcopy(
        hidden_noop["lessons"][0]["artifactSteps"][0])
    hidden_noop["freestyle"]["referenceSteps"][0]["id"] = "s01-hidden-noop"
    assert_error(hidden_noop, "hidden referenceSteps must implement the solution")


def check_sealed_map_work_order_boundary(section_factory):
    authored = section_factory()
    lesson = authored["lessons"][0]
    _findings.clear()
    _check_lesson(authored, lesson, "sealed-map", set(), work_orders_only=True)
    assert any(level == "ERROR" and "mode 'author'" in message
               for level, _label, message in _findings), _findings

    work_order = copy.deepcopy(lesson)
    work_order["artifactSteps"] = [{
        "id": "s01-main-work-order", "path": "main.py", "mode": "author",
        "instruction": "Author main.py from the taught contract and run its focused proof.",
        "checks": ["The focused proof prints the required milestone and exits cleanly."],
    }]
    _findings.clear()
    _check_lesson(authored, work_order, "sealed-map", set(), work_orders_only=True)
    assert not [item for item in _findings if item[0] == "ERROR"], _findings

    _findings.clear()
    _check_blank_learner_scaffold({"runtime": {"name": "python"}})
    assert any(level == "ERROR" and "empty starterCode" in message
               for level, _label, message in _findings), _findings
    _findings.clear()
    _check_blank_learner_scaffold({
        "runtime": {"name": "python", "starterCode": "", "scaffoldCommand": []}})
    assert not [item for item in _findings if item[0] == "ERROR"], _findings
