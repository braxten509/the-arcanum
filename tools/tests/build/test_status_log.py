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
                                       load_status_lines, status_path)


with tempfile.TemporaryDirectory() as folder:
    build = "resumable"
    append_status_line(build, "VALIDATOR COMMAND START [100.000] › first",
                       build_dir=folder, at=100)
    append_status_line(build, "AI VALIDATOR CALL COMPLETE [101.000] (PASS) › "
                       "prerequisite completeness s01 › codex-cli luna",
                       build_dir=folder, at=101)
    assert load_status_lines(build, build_dir=folder) == [
        "VALIDATOR COMMAND START [100.000] › first",
        "AI VALIDATOR CALL COMPLETE [101.000] (PASS) › prerequisite completeness "
        "s01 › codex-cli luna",
    ]
    for index in range(STATUS_LOG_LINES + 5):
        append_status_line(build, f"VALIDATOR COMMAND START [{200 + index}.000] › {index}",
                           build_dir=folder, at=200 + index)
    assert len(load_status_lines(build, build_dir=folder)) == STATUS_LOG_LINES
    with open(status_path(folder, build), encoding="utf-8") as handle:
        assert len([line for line in handle if line.strip()]) == STATUS_LOG_LINES

with tempfile.TemporaryDirectory() as folder:
    build = "legacy"
    with open(os.path.join(folder, f"{build}.launch.json"), "w", encoding="utf-8") as handle:
        json.dump({"validator": {"kind": "codex-cli"}}, handle)
    with open(os.path.join(folder, f"{build}.prerequisite-review.calls.jsonl"),
              "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": 250, "contract": 4, "section": "s01",
                                 "stage": "audit", "status": "FAIL", "model": "old"}) + "\n")
        handle.write(json.dumps({"at": 300, "contract": 5, "section": "s03", "stage": "audit",
                                 "status": "PASS", "model": "luna"}) + "\n")
    recovered = load_status_lines(build, build_dir=folder)
    assert recovered == ["AI VALIDATOR CALL COMPLETE [300.000] (PASS) › "
                         "prerequisite completeness s03 › codex-cli luna"]
    append_status_line(build, recovered[0], build_dir=folder, at=300.5)
    assert load_status_lines(build, build_dir=folder) == recovered

print("durable forge status log: OK")
