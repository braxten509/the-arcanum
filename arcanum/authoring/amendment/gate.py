"""Grade an amended tome against the gates that actually decide whether it ships.

Everything here crosses into ``tools/`` by subprocess. That is not indirection for its
own sake: ``architecture-policy.toml`` forbids the server package from importing
buildlib, and the sealed-map and continuity gates live there.
"""
import os
import subprocess
import sys
import tomllib

from ...config import BUILD_DIR, ROOT

GATE_TIMEOUT = 1800


def _run(script, args, timeout=GATE_TIMEOUT):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", script), *args],
        capture_output=True, text=True, timeout=timeout, cwd=ROOT)


def plan_rel(tome):
    """The sealed build plan, or "" for a tome authored before plans existed."""
    rel = os.path.join(os.path.relpath(BUILD_DIR, ROOT), f"{tome}.plan.md")
    return rel if os.path.isfile(os.path.join(ROOT, rel)) else ""


def handoff_dir(tome):
    """The continuity handoff folder, or "" when this build never adopted one."""
    path = os.path.join(BUILD_DIR, f"{tome}.handoffs")
    return path if os.path.isdir(path) else ""


def section_ids(tome):
    try:
        with open(os.path.join(ROOT, "tomes", tome, "tome.toml"), "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(value) for value in ((data.get("content") or {}).get("sections") or [])]


def sync_contracts(action, tome, reason=""):
    """Create or re-seal the harness-owned build contracts; return (notes, error).

    Never fatal to the caller. A tome with no build plan cannot have contracts at all,
    and that is a fact about the tome, not a failure of the amendment.
    """
    args = [action, tome] + (["--reason", reason] if reason else [])
    try:
        done = _run("sync_contracts.py", args, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        return [], str(exc)
    if done.returncode != 0:
        return [], (done.stdout + done.stderr).strip()[-2000:]
    return [line for line in done.stdout.splitlines() if line.strip()], ""


def _shipping_report(tome, *, strict=False):
    """Run the release gate and the per-section sweep; return (ok, report).

    ``validate_tome`` is not the gate a tome ships against. It does no sealed-map
    alignment even when handed the plan, and its tome-wide pooling averages away
    per-section defects -- answer-position clustering inside one section reads as
    balanced once nine other sections are mixed in. So the whole-tome gate runs first
    and every section is then measured on its own, which is the only way those two
    classes of finding ever reach the Binder.
    """
    plan = plan_rel(tome)
    if not plan:
        return True, ""
    tome_rel = os.path.join("tomes", tome)
    lines, ok = [], True
    phase3 = _run("validate_phase3.py",
                  [tome_rel, "--plan", plan] + (["--strict"] if strict else []))
    lines.append((phase3.stdout + phase3.stderr).strip())
    ok = phase3.returncode == 0
    for sid in section_ids(tome):
        # --source-only: the whole-tome gate above already built the package once, and
        # this sweep is here for authored defects, not for a tenth rebuild of the same
        # project. It keeps the sweep under a second per section.
        one = _run("validate_section.py",
                   [tome_rel, sid, "--plan", plan, "--source-only"])
        if one.returncode != 0:
            ok = False
            lines.append(f"===== section gate {sid} =====\n"
                         + (one.stdout + one.stderr).strip())
    return ok, "\n".join(line for line in lines if line)


def validate_amendment(tome, *, strict=False):
    """Independently re-check an amended tome, as a ``CompletedProcess``.

    The Binder honestly reporting success on an unshippable tome is a harness bug, not
    an AI one: it was graded by a validator structurally blind to half the contract.
    This grades it by the commands a release is graded by.
    """
    base = _run("validate_tome.py",
                [os.path.join("tomes", tome)] + (["--strict"] if strict else []),
                timeout=900)
    ship_ok, ship_report = _shipping_report(tome, strict=strict)
    report = ((base.stdout + base.stderr).strip() + "\n\n" + ship_report).strip()
    return subprocess.CompletedProcess(
        base.args, 0 if base.returncode == 0 and ship_ok else 1, report, "")


def demo():
    """One runnable check: the amendment is measured by the gate a release is."""
    assert not plan_rel("no-such-tome"), "a tome with no plan has no contract to check"
    assert _shipping_report("no-such-tome") == (True, ""), \
        "and must not be failed for lacking one"

    tome = "homunculus"
    assert plan_rel(tome) and section_ids(tome), "the fixture tome must carry a sealed plan"
    ship_ok, report = _shipping_report(tome, strict=True)
    # Structural, not a claim about this tome's current health: the gate must actually
    # perform the two measurements validate_tome never does.
    assert "sealed-map alignment" in report, report[-2000:]
    assert "authored completion" in report, report[-2000:]

    lone = _run("validate_tome.py", [os.path.join("tomes", tome), "--strict"], timeout=900)
    combined = validate_amendment(tome, strict=True)
    assert combined.returncode == (0 if ship_ok and lone.returncode == 0 else 1), \
        combined.stdout[-2000:]
    print(f"amendment gate: OK (validate_tome exit {lone.returncode}, "
          f"shipping gate {'clean' if ship_ok else 'error(s)'})")


if __name__ == "__main__":
    demo()
