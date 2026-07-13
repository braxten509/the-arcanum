"""Regression checks for continuity, Arc/scaffold, and editorial-review contracts."""
import json
import os
import shutil
import subprocess
import sys
from unittest.mock import patch

from .. import BUILD_DIR, REPO
from .. import review as review_module
from ..checkpoints import (ARC_CONTRACT, ARC_HEADING, ARC_PARTS, DAILY_DRIVERS,
                           arc_written, finalize_arc, reset_arc)
from ..continuity import (continuity_prompt, handoff_dir, prepare_handoff,
                          reconciliation_prompt, validate_all_handoffs,
                          validate_handoff)
from ..measure import runtime_config_inventory, validator_argv
from ..prompts import (read_findings, read_verdict, review_findings_clear)
from ..sections import section_ids
from ..skeleton import parse_section_list, scaffold_sections


def run():
    # Fresh section workers communicate through exact, schema-checked handoffs. A
    # distant obligation remains visible and must be closed by its named target.
    ctid = "selftest-continuity-xyz"
    cids = ["s01", "s02", "s03"]
    croot = os.path.join(REPO, "tomes", ctid)
    cplan = os.path.join(BUILD_DIR, f"{ctid}.plan.md")
    try:
        with open(cplan, "w", encoding="utf-8") as f:
            f.write("**Continuity map:**\n- s01 -> s03: Reuse the health route in the final "
                    "encounter.\n**Artifact lifecycle:** tested\n")
        for sid in cids:
            section = os.path.join(croot, "sections", sid)
            os.makedirs(section, exist_ok=True)
            with open(os.path.join(section, "lesson.toml"), "w", encoding="utf-8") as f:
                f.write("# evidence\n")

        def write_handoff(sid, future=(), temporary=(), fulfills=()):
            path = prepare_handoff(ctid, sid, reset=True)
            payload = {
                "version": 1,
                "section": sid,
                "artifact_state": f"The cumulative artifact after {sid} has a stable tested route.",
                "public_contracts": [{"name": f"{sid}.contract", "location": "lesson.toml",
                                      "promise": "Later sections preserve this exact behavior."}],
                "future_obligations": list(future),
                "temporary_artifacts": list(temporary),
                "fulfills": list(fulfills),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f)

        write_handoff("s01")
        assert not validate_handoff(ctid, "s01", cids, cplan)[0]
        write_handoff("s01", future=[{
            "id": "s01-plan-s03-01", "target": "s03", "location": "lesson.toml",
            "requirement": "Reuse the health route in the final encounter.",
            "reason": "The learner already owns this state transition.",
        }], temporary=[{
            "id": "s01-debug-caption", "target": "s02", "location": "lesson.toml",
            "artifact": "Temporary caption used as visible diagnostics.",
            "retirement": "Replace the caption with the taught HUD.",
        }])
        assert validate_handoff(ctid, "s01", cids, cplan)[0]
        write_handoff("s02", fulfills=[{
            "id": "s01-debug-caption", "location": "lesson.toml",
            "evidence": "The HUD replacement and caption removal are both explicit.",
        }])
        assert validate_handoff(ctid, "s02", cids, cplan)[0]
        write_handoff("s03")
        assert not validate_handoff(ctid, "s03", cids, cplan)[0]
        briefing = continuity_prompt(ctid, "s03", cids, cplan)
        assert "s01-plan-s03-01" in briefing and "DUE NOW" in briefing
        write_handoff("s03", fulfills=[{
            "id": "s01-plan-s03-01", "location": "lesson.toml",
            "evidence": "The final encounter calls the stable health transition.",
        }])
        assert validate_all_handoffs(ctid, cids, cplan)[0]
        assert "Deterministic handoff gate: CLOSED" in reconciliation_prompt(
            ctid, cids, cplan)
    finally:
        shutil.rmtree(croot, ignore_errors=True)
        shutil.rmtree(handoff_dir(ctid), ignore_errors=True)
        try:
            os.remove(cplan)
        except OSError:
            pass

    tid = "selftest-resume-xyz"
    plan = os.path.join(BUILD_DIR, f"{tid}.plan.md")
    header = "## Gate answers\n- **Tooling:** internal\n\n" + ARC_HEADING + ARC_CONTRACT
    drivers = "; ".join(f"{driver} = CAN" for driver in DAILY_DRIVERS)
    values = {
        "Daily drivers": drivers,
        "Tooling fit": "internal — COMPATIBLE: every required learner action runs in-browser",
        "Continuity map": "s01 -> s02: preserve the exact forge contract",
        "Section list": ("\n1. **s01 — First Forge:** establish the project shell\n"
                         "2. **s02 — Second Forge:** deliver the finished artifact"),
    }
    full = "".join(f"**{part}:** {values.get(part, 'hammered out in ample forge-detail')}\n"
                   for part in ARC_PARTS)
    parsed = parse_section_list(full)
    assert [spec.sid for spec in parsed] == ["s01", "s02"]
    cases = (("", False), ("\n\n", False), (full, True),
             (full.replace("**Graduate ledger:**", "ledger"), False),
             (full.replace("key-value = CAN", "key-value"), False),
             (full.replace("s01 -> s02:", "s02 -> s01:"), False),
             (full.replace("s01 -> s02: preserve", "s01 -> s02:\npreserve"), False),
             (full.replace("internal — COMPATIBLE:", "external — COMPATIBLE:"), False),
             (full.replace("2. **s02 —", "3. **s03 —"), False),
             ("".join(f"**{part}:** x\n" for part in ARC_PARTS), False))
    for extra, expected in cases:
        with open(plan, "w", encoding="utf-8") as f:
            f.write(header + extra)
        assert arc_written(plan, plan)[0] is expected
    blocked = full.replace(
        "internal — COMPATIBLE: every required learner action runs in-browser",
        "internal — BLOCKED: the promised desktop tool requires an external workspace — REQUIRED: both")
    with open(plan, "w", encoding="utf-8") as f:
        f.write(header + blocked)
    ok, report = arc_written(plan, plan)
    assert not ok and "TOOLING_CONFLICT:" in report and "REQUIRED_TOOLING=both" in report
    invalid_blocked = blocked.replace("REQUIRED: both", "REQUIRED: internal")
    with open(plan, "w", encoding="utf-8") as f:
        f.write(header + invalid_blocked)
    ok, report = arc_written(plan, plan)
    assert not ok and "must REQUIRE a different Tooling mode" in report
    with open(plan, "w", encoding="utf-8") as f:
        f.write(header + full)
    assert finalize_arc(plan) and ARC_CONTRACT not in open(plan, encoding="utf-8").read()
    assert arc_written(plan, plan)[0]
    cli = subprocess.run([sys.executable, os.path.join(REPO, "tools", "validate_tome.py"),
                          "tomes/not-authored-yet", "--phase-1-plan", plan],
                         cwd=REPO, capture_output=True, text=True)
    assert cli.returncode == 0, (cli.stdout, cli.stderr)

    # The approved Section list becomes a deterministic, validator-green Phase-2 tree:
    # one placeholder lesson per section. Adding a second lesson crosses the phase
    # boundary and must fail the narrow gate even though it is legal finished content.
    skeleton_tid = "selftest-phase2-skeleton-xyz"
    skeleton_root = os.path.join(REPO, "tomes", skeleton_tid)
    skeleton_plan = os.path.join(BUILD_DIR, f"{skeleton_tid}.plan.md")
    shutil.rmtree(skeleton_root, ignore_errors=True)
    try:
        made = subprocess.run(
            [sys.executable, os.path.join(REPO, "tools", "new_tome.py"), skeleton_tid],
            cwd=REPO, capture_output=True, text=True)
        assert made.returncode == 0, (made.stdout, made.stderr)
        with open(skeleton_plan, "w", encoding="utf-8") as handle:
            handle.write("## Arc\n" + full)
        specs = scaffold_sections(skeleton_tid, skeleton_plan)
        assert [spec.sid for spec in specs] == ["s01", "s02"]
        assert section_ids(skeleton_tid) == ["s01", "s02"]
        for spec in specs:
            lesson_dir = os.path.join(skeleton_root, "sections", spec.sid, "lessons")
            assert os.listdir(lesson_dir) == ["l01.toml"]
        skeleton_check = subprocess.run(
            validator_argv(skeleton_tid, phase=2, tooling="internal"),
            cwd=REPO, capture_output=True, text=True)
        assert skeleton_check.returncode == 0, (skeleton_check.stdout, skeleton_check.stderr)
        assert "density" not in skeleton_check.stdout and "TODO/FIXME" not in skeleton_check.stdout
        first_lessons = os.path.join(skeleton_root, "sections", "s01", "lessons")
        shutil.copyfile(os.path.join(first_lessons, "l01.toml"),
                        os.path.join(first_lessons, "l02.toml"))
        overbuilt = subprocess.run(
            validator_argv(skeleton_tid, phase=2, tooling="internal"),
            cwd=REPO, capture_output=True, text=True)
        assert overbuilt.returncode != 0 and "expected exactly 1 placeholder lesson" in overbuilt.stdout
    finally:
        shutil.rmtree(skeleton_root, ignore_errors=True)
        try:
            os.remove(skeleton_plan)
        except OSError:
            pass

    reset_arc(plan)
    assert arc_written(plan, plan)[0] is False
    os.remove(plan)
    assert arc_written("/no/such/plan.md", "x")[0] is False

    verdict = os.path.join(BUILD_DIR, f"{tid}.verdict")
    for raw, expected in (("PASS\n", "PASS"), ("GAPS REMAIN\n", "GAPS REMAIN"),
                          ("NOT PASS\n", None), ("PASS - looks good\n", None)):
        with open(verdict, "w", encoding="utf-8") as f:
            f.write(raw)
        assert read_verdict(verdict) == expected
        assert os.path.exists(verdict) and os.path.getsize(verdict) == 0
    findings_path = os.path.join(BUILD_DIR, f"{tid}.findings.json")
    with open(findings_path, "w", encoding="utf-8") as f:
        json.dump([{"file": f"f{i}", "issue": "line one\nline two", "severity": "blocking"}
                   for i in range(50)], f)
    assert not review_findings_clear(findings_path)
    findings = read_findings(findings_path)
    assert len(findings.splitlines()) == 40 and "line one line two" in findings
    assert os.path.exists(findings_path) and os.path.getsize(findings_path) == 0
    assert review_findings_clear(findings_path)
    with open(findings_path, "w", encoding="utf-8") as f:
        f.write("[]\n")
    assert review_findings_clear(findings_path)
    with open(findings_path, "w", encoding="utf-8") as f:
        f.write("not json\n")
    assert not review_findings_clear(findings_path)

    # Exercise the loop seam itself: a clean PASS returns without another worker, while
    # the identical PASS attached to an authored repair schedules one fresh invocation.
    def clean_review_worker(*_args, **_kwargs):
        with open(verdict, "w", encoding="utf-8") as f:
            f.write("PASS\n")
        with open(findings_path, "w", encoding="utf-8") as f:
            f.write("[]\n")
        return 0

    def invoke_review(latest_edits):
        with open(verdict, "w", encoding="utf-8") as f:
            f.write("PASS\n")
        with open(findings_path, "w", encoding="utf-8") as f:
            f.write("[]\n")
        return review_module.run_student_review(
            "no-such-review-tome", "Test", "Body", ("fake", ["fake"], "stdin"),
            ("plan", "verdict", "findings"),
            (os.path.join(BUILD_DIR, "missing.plan"), verdict, findings_path,
             os.path.join(BUILD_DIR, "missing.shrink")),
            {"files": set(), "arrays": {}}, runtime_config_inventory(), 0,
            latest_edits, 0, "", "", 1, 1, 1, [])

    with (patch.object(review_module, "scoped_runner_command", return_value=["fake"]),
          patch.object(review_module, "validate", return_value=(True, "")),
          patch.object(review_module, "run_agent", side_effect=clean_review_worker) as agent):
        assert invoke_review([]) is None and agent.call_count == 0
        assert invoke_review(["MODIFIED: tomes/x/tome.toml"]) is None
        assert agent.call_count == 1
    os.remove(verdict)
    os.remove(findings_path)
