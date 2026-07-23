#!/usr/bin/env python3
"""Fresh Mastery 1-5 evidence tomes traverse the Phase 0-8 mechanical contracts."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from runtimes import for_config
from buildlib import course_map
from buildlib.authoring import standard_phase_registry
from buildlib.mastery_evidence import (export_mastery_contract, load_policy,
                                       validate_semantic_review)
from buildlib.mastery_evidence.map_contract import validate_map_contract
from buildlib.mastery_evidence.review import review_path
from buildlib.mastery_evidence.variants import VariantGenerator
from buildlib.workflow.prompts import MASTERY_DEPTH_FLOORS, GATE_QS, gate_errors, write_plan
from tools.tests.mastery.authoring.fixture import (
    PythonProofSandbox, SemanticPass, authored_sections, semantic_report,
    write_labs, write_working_assessments,
)
from tools.tests.mastery.fixtures import future_map
from tools.validatelib.mastery_evidence import validate_mastery_evidence


registry = standard_phase_registry()
definitions = registry.definitions()
assert [item.phase for item in definitions] == list(range(1, 9))
assert all(item.version == 1 and item.capabilities for item in definitions)
registry.validate_references(tuple(range(1, 9)))
try:
    registry.get(9)
except ValueError as error:
    assert "available: 1, 2, 3, 4, 5, 6, 7, 8" in str(error)
else:
    raise AssertionError("unknown authoring phase silently fell back")

phase5 = (ROOT / "tome-workflow" / "phase-5-economy.md").read_text().lower()
phase4 = (ROOT / "tome-workflow" / "phase-4-minigames.md").read_text().lower()
phase6 = (ROOT / "tome-workflow" / "phase-6-cosmetics.md").read_text().lower()
assert "support" in phase5 and "cannot bypass" in phase5
assert "not mastery evidence" in phase4
assert "independent-evidence" in phase6 and "cosmetic" in phase6

policy = load_policy()
old_build, old_repo = course_map.BUILD_DIR, course_map.REPO
try:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        build_root, tomes_root = root / ".tome-build", root / "tomes"
        build_root.mkdir(); tomes_root.mkdir()
        course_map.BUILD_DIR, course_map.REPO = str(build_root), str(root)
        for level in range(1, 6):
            build_id = f"synthetic-m{level}"
            tome_root = tomes_root / build_id
            tome_root.mkdir()
            answers = [
                (GATE_QS[0][0], "basic command-line use"),
                (GATE_QS[1][0], "3"),
                (GATE_QS[2][0], "2"),
                (GATE_QS[3][0], str(MASTERY_DEPTH_FLOORS[level])),
                (GATE_QS[4][0], str(level)),
                (GATE_QS[5][0], "internal"),
            ]
            assert gate_errors(answers) == []
            plan_path = build_root / f"{build_id}.plan.md"
            write_plan(str(plan_path), build_id, answers, "Build a synthetic verified tool.")
            plan_text = plan_path.read_text(encoding="utf-8")
            assert f"- **Mastery (1-5):** {level}" in plan_text
            assert "- **Mastery evidence contract:** 1" in plan_text
            assert "- **Language practice contract:** 1" in plan_text

            contract, map_sections = future_map(level)
            assert validate_map_contract(contract, map_sections) == []
            sealed = {"masteryEvidence": contract, "sections": map_sections}
            Path(course_map.map_path(build_id)).write_text(json.dumps(sealed), encoding="utf-8")
            manifest = {"mastery": {"evidenceVersion": 1, "level": level},
                        "runtime": {"name": "python"},
                        "acceptance": {"artifact": "runtime"}}
            (tome_root / "tome.toml").write_text(
                f'[mastery]\nevidenceVersion = 1\nlevel = {level}\n\n'
                '[runtime]\nname = "python"\n\n[acceptance]\nartifact = "runtime"\n',
                encoding="utf-8")
            sections = authored_sections(contract)
            write_working_assessments(tome_root)
            lab_paths = write_labs(tome_root, contract)

            phase3_findings = validate_mastery_evidence(
                str(tome_root), manifest, sections, build_plan=str(plan_path),
                include_variants=False)
            assert not phase3_findings, (level, [item.to_dict() for item in phase3_findings])

            export_mastery_contract(sealed, str(tome_root))
            generator = VariantGenerator(
                for_config({"name": "python"}), SemanticPass(), sandbox=PythonProofSandbox())
            for lab_path in lab_paths:
                result = generator.generate(str(tome_root), str(lab_path))
                assert len(result.variant_ids) >= policy.for_level(level).minimum_verified_variants
            phase7_findings = validate_mastery_evidence(
                str(tome_root), manifest, sections, build_plan=str(plan_path),
                include_variants=True)
            assert not phase7_findings, (level, [item.to_dict() for item in phase7_findings])

            Path(review_path(str(build_root), build_id)).write_text(
                json.dumps(semantic_report(contract)), encoding="utf-8")
            reviewed, report = validate_semantic_review(
                str(build_root), build_id, str(tome_root))
            assert reviewed, (level, report)
finally:
    course_map.BUILD_DIR, course_map.REPO = old_build, old_repo

print("Mastery 1-5 Phase 0-8 authoring contract lifecycle: OK")
