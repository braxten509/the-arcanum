#!/usr/bin/env python3
"""Recurring objective Phase-1 review defects are rejected mechanically."""
import os
import sys
from dataclasses import replace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools.buildlib.skeleton import SectionSpec
from tools.buildlib.workflow.checkpoints import phase1_operational_problems


PLAN = """
- **Starting level (1-10):** 1
- **Mastery (1-5):** 1
- **Tooling:** external
- **Language foundation contract:** 2
"""

BODY = """
**Finished tool:** A learner-built game delivered as a reproducible source archive.
**Language foundation coverage:** data = language-data; control = language-control; decomposition = language-decomposition; failure = language-failure; verification = language-verification
**Language performances:** s03.working = guided-modification + rationale: tighten the existing target validator so it accepts exactly three and rejects the prior range
**Mastery proof:** The learner changes the taught validator so only three is accepted, proves the result, and explains the branch.
**Acceptance proof:** From clean input, install the toolchain and verify its version, build and check the project, then create the package twice with sorted paths and normalized timestamps and compare SHA-256 hashes.
"""

SPECS = [
    SectionSpec(
        "s01", "Set Up",
        "Five ordered lessons each include guided practice: tool setup -> version verification "
        "-> language-data -> language-verification -> first build. Then the Working creates "
        "the minimal source."),
    SectionSpec(
        "s02", "Control and Failures",
        "Teach language-decomposition and language-control before language-failure, then use "
        "the ordered cleanup path in the Working."),
    SectionSpec(
        "s03", "Modify and Deliver",
        "The Working changes the validator to accept exactly three, explains the branch, and "
        "delivers the reproducible source archive."),
]


def problems(body=BODY, specs=SPECS):
    return phase1_operational_problems(PLAN + body, body, specs)


assert not problems(), "\n".join(problems())

missing_setup = [replace(SPECS[0], promise=SPECS[0].promise.replace("tool setup", "tool list")),
                 *SPECS[1:]]
assert any("installation/setup" in item for item in problems(specs=missing_setup))

missing_environment_proof = BODY.replace(
    "install the toolchain and verify its version", "use the available toolchain")
assert any("Acceptance proof" in item and "installation/setup" in item
           for item in problems(body=missing_environment_proof))

inverted = [SPECS[0], replace(
    SPECS[1], promise=SPECS[1].promise.replace(
        "language-decomposition and language-control before language-failure",
        "language-failure before language-control and language-decomposition")), SPECS[2]]
assert any("control foundation" in item for item in problems(specs=inverted))
assert any("decomposition foundation" in item for item in problems(specs=inverted))

weak_reproducibility = BODY.replace(
    "create the package twice with sorted paths and normalized timestamps and compare "
    "SHA-256 hashes", "create the package once")
reproducibility = problems(body=weak_reproducibility)
assert any("at least twice" in item and "normalize" in item and "hashes" in item
           for item in reproducibility)

vague_section_bound = [*SPECS[:2], replace(
    SPECS[2], promise=SPECS[2].promise.replace("exactly three", "a narrower range"))]
assert any("must repeat it" in item for item in problems(specs=vague_section_bound))

vague_mastery_bound = BODY.replace("only three", "a narrower range")
assert any("Mastery proof" in item and "same invariant" in item
           for item in problems(body=vague_mastery_bound))

no_guided_practice = [replace(
    SPECS[0], promise=SPECS[0].promise.replace("guided practice", "brief notes")),
    *SPECS[1:]]
assert any("guided practice" in item for item in problems(specs=no_guided_practice))

too_many_lessons = [replace(
    SPECS[0], promise=(
        "Nine ordered lessons each include guided practice: tool setup -> version verification "
        "-> language-data -> value widths -> variables -> expressions -> calls -> "
        "language-verification -> first build. Then the Working creates minimal source.")),
    *SPECS[1:]]
assert any("has 9 steps" in item for item in problems(specs=too_many_lessons))

print("Phase-1 operational planning contract: OK")
