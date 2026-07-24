#!/usr/bin/env python3
"""Sealed-validator check: an author CLI can RUN the section gate but not READ it.

Every author prompt says "do not inspect validator implementation to guess at hidden
checks". agent_commands masks tools/validatelib and tools/buildlib/prerequisites with
sourceless-bytecode mirrors so that instruction is enforced rather than advisory.

Runs the real self-check inside the real bwrap sandbox:
    python3 tools/tests/forge/test_sealed_validator.py
Assert-based, no framework; exits non-zero on the first failure.
"""
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from arcanum.platform.agent_commands import SEALED_PACKAGES, _sealed_binds  # noqa: E402
from tools.buildlib.access.profiles import profile_paths  # noqa: E402


def sandbox(argv):
    """Same bwrap shape scoped_runner_command builds, with the sealed binds applied."""
    return subprocess.run(
        [shutil.which("bwrap"), "--die-with-parent", "--new-session", "--unshare-pid",
         "--ro-bind", "/", "/", "--proc", "/proc", "--dev-bind", "/dev", "/dev",
         "--bind", "/tmp", "/tmp", *_sealed_binds(REPO), "--chdir", REPO, *argv],
        capture_output=True, text=True, cwd=REPO)


def strict_author_sandbox(argv):
    """Run with the Phase-3 profile's actual allowlisted repository mounts."""
    permissions = profile_paths(
        "author-phase37", build_id="sealed-validator-test", tome_id="missing-test-tome",
        phase=3, section_id="s01", section_index=1, section_count=1,
        tooling="external")
    command = [
        shutil.which("bwrap"), "--die-with-parent", "--new-session", "--unshare-pid",
    ]
    for path in permissions["system_read"]:
        command.extend(("--proc", "/proc") if path == "/proc"
                       else ("--ro-bind", path, path))
    for path in permissions["system_both"]:
        if path == "/dev":
            command.extend(("--dev-bind", "/dev", "/dev"))
        else:
            command.extend(("--bind", path, path))
    allowed = []
    for access in ("read", "both", "execute"):
        allowed.extend(permissions[access])
    for path in dict.fromkeys(allowed):
        if os.path.exists(path):
            command.extend(("--ro-bind", path, path))
    command.extend((*_sealed_binds(REPO), "--chdir", REPO, *argv))
    return subprocess.run(command, capture_output=True, text=True, cwd=REPO)


assert shutil.which("bwrap"), "bubblewrap is required for the author sandbox"

# 1. the sealed packages still import and execute -- a mirror that breaks the gate is
#    worse than an unsealed one, since the author loses its only honest feedback loop
for package in SEALED_PACKAGES:
    module = package.replace("tools/", "").replace("/", ".")
    done = sandbox(["python3", "-c", f"import sys; sys.path.insert(0, 'tools'); "
                                     f"import {module}; print('imported', {module!r})"])
    assert done.returncode == 0, f"{package} is not importable when sealed:\n{done.stderr}"
print(f"import: {len(SEALED_PACKAGES)} sealed packages still load OK")

# 2. no .py source is reachable anywhere, and the greps a real author ran come back empty
for package in SEALED_PACKAGES:
    done = sandbox(["find", package, "-name", "*.py"])
    assert not done.stdout.strip(), f"{package} still exposes source:\n{done.stdout}"
for pattern, where in (("def check_", "tools/validatelib"),
                       ("^def ", "tools/validatelib"),
                       ("source_only", "tools/validatelib")):
    done = sandbox(["grep", "-rn", pattern, where])
    assert not done.stdout.strip(), f"grep {pattern!r} still reads {where}:\n{done.stdout}"

# 3. bytecode still leaks string literals, so the Validator AI's rubric must not reach
#    the sandbox as bytecode either -- prompt/result/transport ship as name-only stubs
#    Assert on real grading criteria, not incidental labels: modules kept as bytecode
#    still leak their own docstrings and error strings ("section-quality audit" appears
#    in review.py's error text), which say only that an audit exists -- something the
#    author prompt states outright. What must not leak is what the audit rewards.
done = sandbox(["sh", "-c", "cat tools/buildlib/prerequisites/*.pyc | strings"])
for phrase in ("The learner can copy the complete worked example",
               "Omit fundamentals covered by the selected Starting Level",
               "its only exercise reproduces the shown answer",
               "Replace it with a new-context construction"):
    assert phrase not in done.stdout, f"rubric criterion {phrase!r} is recoverable"
print("seal: no source readable, rubric criteria unrecoverable, 3 recon greps empty OK")

# 4. Every Phase-3 helper imports inside the strict allowlisted namespace. This catches a
#    profile that mounts an executable entrypoint without its ordinary Python dependencies.
for helper in (
        "tools/workflow/report_tome_progress.py",
        "tools/workflow/context/render_section_context.py",
        "tools/workflow/report_section_progress.py",
        "tools/validate_section.py"):
    done = strict_author_sandbox(["python3", helper, "--help"])
    assert done.returncode == 0, (
        f"{helper} cannot start in the strict Phase-3 author sandbox:\n"
        f"{done.stdout}{done.stderr}")
print("strict profile: all Phase-3 author helpers import and show help OK")

# 5. Import-only checks do not exercise lazily loaded policy data. Load every central
#    policy used by the Phase-3 gate inside the strict namespace so a missing data mount
#    fails here instead of trapping a live author in a no-progress retry.
done = strict_author_sandbox([
    "python3", "-c",
    "from tools.buildlib.mastery_evidence.policy import load_policy; "
    "from tools.buildlib.language_mastery.coverage import profile_for; "
    "load_policy(); profile = profile_for('Python', 3); "
    "assert not profile['error'], profile['error']",
])
assert done.returncode == 0, (
    "Phase-3 validator policy data is unavailable in the strict author sandbox:\n"
    f"{done.stdout}{done.stderr}")
print("strict profile: Phase-3 validator policy data loads OK")

# 6. the gate the author is told to run produces the same findings sealed as unsealed
CHECK = ["python3", "tools/validate_section.py", "tomes/register-rally-pong", "s01",
         "--plan", ".tome-build/untitled-7.plan.md", "--tooling", "external", "--source-only"]
if not os.path.isfile(os.path.join(REPO, ".tome-build", "untitled-7.plan.md")):
    print("gate: skipped (no untitled-7 plan on disk)")
else:
    sealed = sandbox(CHECK)
    plain = subprocess.run(CHECK, capture_output=True, text=True, cwd=REPO)
    assert "ModuleNotFoundError" not in sealed.stderr, (
        f"sealing broke the gate's imports:\n{sealed.stderr}")
    assert sealed.stdout == plain.stdout, (
        "sealed gate reported different findings than the unsealed gate")
    print("gate: sealed self-check output identical to unsealed OK")

print("ALL SEALED VALIDATOR TESTS PASS")
