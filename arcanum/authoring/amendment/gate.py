"""Grade an amended tome against the gates that actually decide whether it ships.

Everything here crosses into ``tools/`` by subprocess. That is not indirection for its
own sake: ``architecture-policy.toml`` forbids the server package from importing
buildlib, and the sealed-map and continuity gates live there.
"""
import json
import os
import subprocess
import sys
import tomllib

from ...config import BUILD_DIR, ROOT

GATE_TIMEOUT = 1800
# How ``sync_contracts.py plan`` reports that a tome's own content blocks the plan it
# would otherwise be given. Matched, not parsed: the cause after it goes to the Binder
# verbatim as work it can do. See tools/tests/binder/test_adopt_build.py.
PLAN_REFUSED = "cannot be put under the full shipping gate yet"


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


def blank_handoffs(tome):
    """Section ids whose handoff exists but carries no ``artifact_state`` the gate takes.

    Twenty characters is ``validate_phase3``'s own floor, not a threshold invented here:
    below it the file is present and still fails, which is exactly the state adoption
    leaves behind on purpose rather than inventing an author's prose.
    """
    folder = handoff_dir(tome)
    blank = []
    for name in sorted(os.listdir(folder)) if folder else []:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue  # unreadable is a validator finding, not a thing to fill
        if len(str(data.get("artifact_state") or "").strip()) < 20:
            blank.append(str(data.get("section") or name[:-len(".json")]))
    return blank


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
    notes = []
    for line in done.stdout.splitlines():
        if not line.strip():
            continue
        # A note may carry its own detail list — the plan refusal names its first blockers.
        # Those belong TO the note: split apart they reach the feed as eight near-identical
        # cards, and the prompt as "First blockers:" with nothing after it.
        if line.startswith(("-", " ", "\t")) and notes:
            notes[-1] += "\n" + line
        else:
            notes.append(line)
    return notes, ""


def _shipping_report(tome, *, strict=False, on_step=None):
    """Run the release gate and the per-section sweep; return (ok, report).

    ``validate_tome`` is not the gate a tome ships against. It does no sealed-map
    alignment even when handed the plan, and its tome-wide pooling averages away
    per-section defects -- answer-position clustering inside one section reads as
    balanced once nine other sections are mixed in. So the whole-tome gate runs first
    and every section is then measured on its own, which is the only way those two
    classes of finding ever reach the Binder.

    ``on_step`` receives one line per gate before it runs. This sweep takes minutes,
    and without it the Binder goes dark between the survey's verdict and the harness's
    -- which reads exactly like a hang.
    """
    plan = plan_rel(tome)
    if not plan:
        return True, ""
    tome_rel = os.path.join("tomes", tome)
    lines, ok = [], True
    step = on_step or (lambda _text: None)
    step("re-checking the whole tome against the Phase 3 release gate")
    phase3 = _run("validate_phase3.py",
                  [tome_rel, "--plan", plan] + (["--strict"] if strict else []))
    lines.append((phase3.stdout + phase3.stderr).strip())
    ok = phase3.returncode == 0
    sids = section_ids(tome)
    for index, sid in enumerate(sids, 1):
        step(f"re-checking section {index} of {len(sids)} ({sid})")
        # --no-run, not --source-only: the whole-tome gate above already executed this
        # tome end to end, so re-running each section buys nothing it does not have.
        # What this sweep is actually for is the per-section analysis that whole-tome
        # pooling hides, and that is authored content, not execution. --source-only
        # only defers the package build and still ran source acceptance -- 20+ seconds
        # a section on a compiled tome, where this is a third of a second.
        one = _run("validate_section.py",
                   [tome_rel, sid, "--plan", plan, "--no-run"])
        if one.returncode != 0:
            ok = False
            lines.append(f"===== section gate {sid} =====\n"
                         + (one.stdout + one.stderr).strip())
    return ok, "\n".join(line for line in lines if line)


def validate_amendment(tome, *, strict=False, on_step=None):
    """Independently re-check an amended tome, as a ``CompletedProcess``.

    The Binder honestly reporting success on an unshippable tome is a harness bug, not
    an AI one: it was graded by a validator structurally blind to half the contract.
    This grades it by the commands a release is graded by.
    """
    if on_step:
        on_step("re-checking the whole tome against the full validator")
    base = _run("validate_tome.py",
                [os.path.join("tomes", tome)] + (["--strict"] if strict else []),
                timeout=900)
    ship_ok, ship_report = _shipping_report(tome, strict=strict, on_step=on_step)
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
