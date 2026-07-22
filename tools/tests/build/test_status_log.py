#!/usr/bin/env python3
"""Durable Forge validator history across server and build resumes."""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools.buildlib.status_log import (STATUS_LOG_LINES, append_status_line,
                                       clear_run_history, load_status_lines,
                                       rewind_status_log, rewind_status_log_sections,
                                       status_path)
from arcanum.authoring.read_models.durable_status import (clear_conversation,
                                                          load_conversation)


with tempfile.TemporaryDirectory() as folder:
    build = "resumable"
    append_status_line(build, "VALIDATOR COMMAND START [100.000] › first",
                       build_dir=folder, at=100)
    append_status_line(build, "AI VALIDATOR CALL COMPLETE [101.000] (PASS) › "
                       "section quality s01 › codex-cli luna",
                       build_dir=folder, at=101)
    assert load_status_lines(build, build_dir=folder) == [
        "VALIDATOR COMMAND START [100.000] › first",
        "AI VALIDATOR CALL COMPLETE [101.000] (PASS) › section quality "
        "s01 › codex-cli luna",
    ]
    append_status_line(
        build, "AI API-EQUIVALENT COST COMPLETE [102.000] › "
        "PHASE 3 SECTION s01 › $1.25", build_dir=folder, at=102)
    append_status_line(
        build, "AI API-EQUIVALENT COST COMPLETE [103.000] › "
        "PHASE 3 TOTAL · SUM OF 1 SECTIONS › $1.25", build_dir=folder, at=103)
    append_status_line(
        build, "AI API-EQUIVALENT COST COMPLETE [104.000] › "
        "PHASE 3 SECTION s01 › $1.40", build_dir=folder, at=104)
    cost_lines = [line for line in load_status_lines(build, build_dir=folder)
                  if line.startswith("AI API-EQUIVALENT COST")]
    assert cost_lines == [
        "AI API-EQUIVALENT COST COMPLETE [103.000] › "
        "PHASE 3 TOTAL · SUM OF 1 SECTIONS › $1.25",
        "AI API-EQUIVALENT COST COMPLETE [104.000] › "
        "PHASE 3 SECTION s01 › $1.40",
    ]
    # Two Phase-3 cost rows plus the two validator rows the rewind invalidated.
    assert rewind_status_log(build, 3, build_dir=folder) == 4
    assert load_status_lines(build, build_dir=folder) == []
    for index in range(STATUS_LOG_LINES + 5):
        append_status_line(build, f"VALIDATOR COMMAND START [{200 + index}.000] › {index}",
                           build_dir=folder, at=200 + index)
    assert len(load_status_lines(build, build_dir=folder)) == STATUS_LOG_LINES
    with open(status_path(folder, build), encoding="utf-8") as handle:
        # The clear marker rides along as a header, so bound the log rows themselves.
        assert len([line for line in handle
                    if "line" in json.loads(line or "{}")]) == STATUS_LOG_LINES

with tempfile.TemporaryDirectory() as folder:
    build = "legacy"
    with open(os.path.join(folder, f"{build}.launch.json"), "w", encoding="utf-8") as handle:
        json.dump({"validator": {"kind": "codex-cli"}}, handle)
    with open(os.path.join(folder, f"{build}.prerequisite-review.calls.jsonl"),
              "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": 250, "contract": 4, "section": "s01",
                                 "stage": "audit", "status": "FAIL", "model": "old"}) + "\n")
        handle.write(json.dumps({"at": 280, "contract": 1, "phase": 1,
                                 "unitKind": "phase", "unit": "phase-1",
                                 "auditKind": "planning", "stage": "audit",
                                 "status": "PASS", "model": "luna"}) + "\n")
        handle.write(json.dumps({"at": 300, "contract": 6, "section": "s03", "stage": "audit",
                                 "status": "PASS", "model": "luna"}) + "\n")
    recovered = load_status_lines(build, build_dir=folder)
    assert recovered == [
        "AI VALIDATOR CALL COMPLETE [280.000] (PASS) › "
        "phase 1 arc quality › codex-cli luna",
        "AI VALIDATOR CALL COMPLETE [300.000] (PASS) › "
        "section quality s03 › codex-cli luna",
    ]
    append_status_line(build, recovered[1], build_dir=folder, at=300.5)
    assert load_status_lines(build, build_dir=folder) == recovered

for durable_label in ("section quality s01 recovery-retry", "section quality s01"):
    with tempfile.TemporaryDirectory() as folder:
        build = "staged-call"
        with open(os.path.join(folder, f"{build}.launch.json"),
                  "w", encoding="utf-8") as handle:
            json.dump({"validator": {"kind": "codex-cli"}}, handle)
        with open(os.path.join(folder, f"{build}.prerequisite-review.calls.jsonl"),
                  "w", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "at": 400, "contract": 6, "section": "s01",
                "stage": "recovery-retry", "status": "FAIL", "model": "luna",
            }) + "\n")
        durable_line = ("AI VALIDATOR CALL COMPLETE [400.500] (FAIL) › "
                        f"{durable_label} › codex-cli luna")
        append_status_line(build, durable_line, build_dir=folder, at=400.5)
        assert load_status_lines(build, build_dir=folder) == [durable_line]

with tempfile.TemporaryDirectory() as folder:
    build = "phase-boundary"
    for phase in (1, 3, 4):
        append_status_line(
            build, f"AI API-EQUIVALENT COST COMPLETE [{phase}.000] › "
            f"PHASE {phase} TOTAL › ${phase}.00", build_dir=folder, at=phase)
    # Validator traffic describes work the rewind erased, so all of it goes while the
    # earlier phases keep their spend on the ledger.
    for at, line in ((0.5, "VALIDATOR COMMAND START [0.500] › python3 validate.py s01"),
                     (3.5, "AI VALIDATOR CALL COMPLETE [3.500] (FAIL) › section quality "
                           "s02 › claude-cli haiku")):
        append_status_line(build, line, build_dir=folder, at=at)
    assert rewind_status_log(build, 4, build_dir=folder) == 3
    assert [line.split(" › ")[1] for line in load_status_lines(
        build, build_dir=folder)] == ["PHASE 1 TOTAL", "PHASE 3 TOTAL"]
    assert rewind_status_log(build, 1, build_dir=folder) == 2
    assert load_status_lines(build, build_dir=folder) == []

with tempfile.TemporaryDirectory() as folder:
    build = "section-boundary"
    append_status_line(
        build, "AI VALIDATOR CALL COMPLETE [1.000] (PASS) › "
        "section quality s01 › codex-cli luna", build_dir=folder, at=1)
    append_status_line(
        build, "AI API-EQUIVALENT COST COMPLETE [2.000] › "
        "PHASE 3 SECTION s01 › $1.00", build_dir=folder, at=2)
    append_status_line(
        build, "AI VALIDATOR CALL COMPLETE [3.000] (FAIL) › "
        "section quality s02 › codex-cli luna", build_dir=folder, at=3)
    append_status_line(
        build, "AI API-EQUIVALENT COST COMPLETE [4.000] › "
        "PHASE 3 SECTION s02 › $2.00", build_dir=folder, at=4)
    append_status_line(
        build, "AI API-EQUIVALENT COST COMPLETE [5.000] › "
        "PHASE 3 TOTAL › $3.00", build_dir=folder, at=5)
    assert rewind_status_log_sections(build, ["s02"], build_dir=folder) == 3
    assert load_status_lines(build, build_dir=folder) == [
        "AI VALIDATOR CALL COMPLETE [1.000] (PASS) › "
        "section quality s01 › codex-cli luna",
        "AI API-EQUIVALENT COST COMPLETE [2.000] › PHASE 3 SECTION s01 › $1.00",
    ]

with tempfile.TemporaryDirectory() as folder:
    build = "abandoned"
    with open(os.path.join(folder, f"{build}.launch.json"), "w", encoding="utf-8") as handle:
        json.dump({"validator": {"kind": "codex-cli"}}, handle)
    with open(os.path.join(folder, f"{build}.prerequisite-review.calls.jsonl"),
              "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": 100, "contract": 6, "section": "s02",
                                 "stage": "audit", "status": "FAIL", "model": "luna"}) + "\n")
    append_status_line(build, "VALIDATOR COMMAND START [100.500] › python3 validate.py s02",
                       build_dir=folder, at=100.5)
    append_status_line(
        build, "AI API-EQUIVALENT COST COMPLETE [101.000] › PHASE 2 TOTAL › $7.80",
        build_dir=folder, at=101)
    assert len(load_status_lines(build, build_dir=folder)) == 3
    # Abandoning empties both panes. The validator's own call journal is never
    # truncated, so the clear must also stop it replaying.
    assert clear_run_history(build, build_dir=folder) == 2
    assert load_status_lines(build, build_dir=folder) == []
    append_status_line(build, "VALIDATOR COMMAND START [200.000] › after resume",
                       build_dir=folder, at=200)
    assert load_status_lines(build, build_dir=folder) == [
        "VALIDATOR COMMAND START [200.000] › after resume"]
    # A build with neither journal is left alone rather than given an empty log.
    assert clear_run_history("never-ran", build_dir=folder) == 0
    assert not os.path.exists(status_path(folder, "never-ran"))

with tempfile.TemporaryDirectory() as folder:
    build = "visible-cost"
    with open(os.path.join(folder, f"{build}.conversation.jsonl"),
              "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": 100, "kind": "assistant",
                                 "text": "Phase authored."}) + "\n")
        handle.write(json.dumps({"at": 103, "kind": "harness",
                                 "text": "Next phase assigned."}) + "\n")
    append_status_line(
        build, "AI API-EQUIVALENT COST COMPLETE [102.000] › "
        "PHASE 1 TOTAL › $0.86", build_dir=folder, at=102)
    visible = load_conversation(folder, build)
    assert [row["at"] for row in visible] == [100, 102.0, 103]
    assert visible[1] == {
        "at": 102.0,
        "kind": "harness",
        "text": "AI API-EQUIVALENT COST COMPLETE › PHASE 1 TOTAL › $0.86",
        "eventKey": "gpt-cost:1:total",
    }
    # Abandoning drops the transcript, and clearing the log takes the cost rows with it.
    assert clear_conversation(folder, build)
    assert [row["eventKey"] for row in load_conversation(folder, build)] == ["gpt-cost:1:total"]
    assert clear_run_history(build, build_dir=folder) == 1
    assert load_conversation(folder, build) == []
    assert not clear_conversation(folder, build)
    assert not clear_conversation(folder, "../escape")

print("durable forge status log: OK")
