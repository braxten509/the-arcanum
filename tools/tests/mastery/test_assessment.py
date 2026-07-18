#!/usr/bin/env python3
"""Snapshot, sandbox, deterministic grading, caching, and variant assignment tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from arcanum.assessment.receipts import ReceiptStore
from arcanum.assessment.runner import AssessmentRequest, AssessmentService
from arcanum.assessment.sandbox import SandboxPolicy, SandboxRunner
from arcanum.assessment.snapshot import SnapshotError, SnapshotLimits, create_snapshot
from arcanum.assessment.variants import VariantRepository, _tree_hash
from arcanum_core.contracts.assessment import AssessmentContract
from runtimes.command_runtime import CommandRuntime


def contract(expect="READY"):
    return AssessmentContract.from_dict({
        "version": 1,
        "requirements": [
            {"id": "builds", "text": "The program builds.", "essential": True,
             "capabilityIds": ["language-verification"]},
            {"id": "runs", "text": "The program reports READY.", "essential": True,
             "capabilityIds": ["language-output"]},
        ],
        "scenarios": [
            {"id": "build-check", "kind": "build", "requirementIds": ["builds"],
             "capabilityIds": ["language-verification"], "commandRef": "build",
             "args": [], "stdin": "", "expect": {"exitCode": 0}, "timeout": 20,
             "public": True},
            {"id": "run-check", "kind": "run", "requirementIds": ["runs"],
             "capabilityIds": ["language-output"], "commandRef": "run", "args": [],
             "stdin": "", "expect": {"exact": expect, "exitCode": 0}, "timeout": 20,
             "public": False},
        ],
        "rubric": [
            {"id": "build-result", "criterion": "Build", "weight": 40,
             "kind": "deterministic", "assessmentIds": ["build-check"]},
            {"id": "run-result", "criterion": "Behavior", "weight": 60,
             "kind": "deterministic", "assessmentIds": ["run-check"]},
        ],
    })


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    workspace, save = root / "learner", root / "save"
    workspace.mkdir()
    save.mkdir()
    (workspace / "main.py").write_text("print('READY')\n", encoding="utf-8")
    (workspace / ".env").write_text("API_KEY=never-copy\n", encoding="utf-8")
    (workspace / "tokenizer.py").write_text("class Tokenizer: pass\n", encoding="utf-8")

    with create_snapshot(str(workspace)) as snapshot:
        paths = {item["path"] for item in snapshot.manifest}
        assert ".env" not in paths and "tokenizer.py" in paths
        (snapshot.work and Path(snapshot.work, "generated.txt")).write_text("isolated\n")
        assert not (workspace / "generated.txt").exists(), "assessment must not mutate the learner workspace"
        result = SandboxRunner().run(
            ["python3", "-c", "import pathlib; pathlib.Path('sandbox.txt').write_text('ok'); print('OK')"],
            cwd=snapshot.work)
        assert result["passed"] and result["output"] == "OK", result
        denied = SandboxRunner().run(
            ["python3", "-c", "open('/home/arcanum-sandbox-escape','w').write('bad')"],
            cwd=snapshot.work)
        assert not denied["passed"], denied
        clipped = SandboxRunner().run(
            ["python3", "-c", "print('x' * 300000)"], cwd=snapshot.work,
            policy=SandboxPolicy(output_bytes=1_000))
        assert clipped["passed"] and clipped["outputClipped"], clipped
        assert len(clipped["output"].encode()) <= 1_000
        marker = Path(snapshot.work, "escaped-after-timeout")
        timed_out = SandboxRunner().run(
            ["python3", "-c",
             "import os,time,pathlib; child=os.fork(); "
             "(time.sleep(2), pathlib.Path('escaped-after-timeout').write_text('bad')) "
             "if child == 0 else time.sleep(20)"],
            cwd=snapshot.work, timeout=1)
        assert timed_out["timedOut"] and not timed_out["passed"], timed_out
        time.sleep(2)
        assert not marker.exists(), "timed-out assessment child escaped process-group cleanup"

    runtime = CommandRuntime({
        "name": "test-python", "language": "Python", "command": ["python3"],
        "entryFile": "main.py", "runCommand": ["python3", "{entry}"],
        "buildCommand": ["python3", "-m", "py_compile", "main.py"],
    })
    service = AssessmentService(runtime, ReceiptStore(str(save)))
    request = AssessmentRequest(
        "fixture", 3, "s03.working", "final-transfer", str(workspace), "cold", False,
        ("language-verification", "language-output"), language="Python")
    passed = service.assess(request, contract())
    assert passed["grade"] == "A" and passed["weightedTotal"] == 100
    assert passed["essentialPassed"] and passed["independent"]
    assert len(passed["receiptHash"]) == 64
    cached = service.assess(request, contract())
    assert cached["cached"] and cached["receiptHash"] == passed["receiptHash"]
    failed = service.assess(request, contract("DIFFERENT"))
    assert failed["grade"] == "INCOMPLETE" and not failed["essentialPassed"]
    assert not failed["independent"]
    assert (workspace / "main.py").read_text() == "print('READY')\n"

    try:
        create_snapshot(str(workspace), limits=SnapshotLimits(max_files=1))
    except SnapshotError:
        pass
    else:
        raise AssertionError("snapshot file-count limit was not enforced")

    variant_root = root / "tome" / "generated" / "mastery-labs" / "transfer"
    for number in (1, 2):
        package = variant_root / f"v{number}"
        (package / "public").mkdir(parents=True)
        (package / "hidden").mkdir()
        (package / "public" / "starter.py").write_text(f"VALUE = {number}\n")
        (package / "hidden" / "answer.txt").write_text("never serve me\n")
        manifest = {"version": 1, "familyId": "transfer", "variantId": f"v{number}",
                    "verified": True, "title": f"Variant {number}", "brief": "Solve it.",
                    "requirements": [], "axes": {"domain": str(number)}}
        manifest["contentHash"] = _tree_hash(str(package))
        (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    repository = VariantRepository(str(root / "tome"), str(save))
    first = repository.assign("transfer")
    assert repository.assign("transfer") == first, "refresh rerolled the assignment"
    public = repository.public_package("transfer", first["variantId"])
    assert all("answer" not in row["path"] for row in public["files"])
    repository.abandon("transfer")
    second = repository.assign("transfer", exclude=(first["variantId"],))
    assert second["variantId"] != first["variantId"]

print("mastery snapshot/assessment/variant tests: OK")
