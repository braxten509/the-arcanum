"""Reusable manifests, sections, and finding assertions for proof tests."""
import tempfile

from validatelib import _findings
from validatelib.proof import check_future_tome_proof

def manifest():
    return {
        "content": {"proofVersion": 1, "sections": ["s01"]},
        "runtime": {"name": "python", "project": "ProofProject", "language": "Python"},
        "acceptance": {"version": 1, "mode": "run", "artifact": "runtime",
                       "runArgs": ["--arcanum-acceptance"],
                       "scenarios": ["launch", "finished-result"],
                       "controls": ["input", "clock"]},
    }


def section():
    lesson_source = '''import json
import os
import sys

def result():
    return "guided"

def acceptance_report():
    challenge = os.environ.get("ARCANUM_ACCEPTANCE_CHALLENGE")
    value = result()
    launched = bool(value) and challenge != "launch"
    finished = launched and value == "milestone" and challenge != "finished-result"
    scenarios = {"launch": launched, "finished-result": finished}
    status = "PASS" if all(scenarios.values()) else "FAIL"
    print(json.dumps({"version": 1, "status": status, "scenarios": scenarios}, separators=(",", ":")))

if "--arcanum-acceptance" in sys.argv:
    acceptance_report()
elif "--arcanum-proof" in sys.argv:
    print(result())
else:
    print(result())
'''
    final_source = lesson_source.replace('return "guided"', 'return "milestone"')
    return {
        "id": "s01",
        "proof": {
            "mode": "run",
            "expectedFiles": ["main.py"],
            "runArgs": ["--arcanum-proof", "s01"],
            "expect": "milestone",
        },
        "lessons": [{
            "id": "s01-l01",
            "title": "A real first edit",
            "teaches": ["define-result"],
            "body": '<p>Write and run the function.</p><pre><code data-kind="runnable">print("guided")</code></pre>',
            "concepts": [{
                "id": "define-result",
                "purpose": "Put one reusable result behind a meaningful name.",
                "anatomy": "Read def, the function name, parentheses, colon, and indented body.",
                "example": "The complete main.py project step below defines and calls result.",
                "observable": "The proof run prints the word guided on its own line.",
                "failure": "Missing indentation raises an IndentationError before the program runs.",
                "practice": "s01-l01-e1",
            }],
            "artifactSteps": [{
                "id": "s01-main",
                "path": "main.py",
                "mode": "rewrite",
                "preserves": "all-active",
                "instruction": "From the ProofProject root, replace main.py with this complete file and run it.",
                "content": lesson_source,
            }],
            "readings": [],
            "exercises": [{"id": "s01-l01-e1", "type": "mc"}],
        }],
        "freestyle": {
            "requires": ["define-result"],
            "referenceSteps": [{
                "id": "s01-reference",
                "path": "main.py",
                "mode": "replace",
                "instruction": "Replace the guided return value with the independent milestone value.",
                "find": lesson_source,
                "content": final_source,
            }],
        },
    }


def findings_for(data, run=False, manifest_data=None, source_only=False):
    _findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(
            root, manifest_data or manifest(), [data], run=run,
            source_only=source_only)
    return list(_findings)


def assert_error(data, needle):
    findings = findings_for(data)
    assert any(level == "ERROR" and needle in message for level, _label, message in findings), findings
