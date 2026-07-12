"""Focused regression checks for the build harness wiring."""
import os

from . import BUILD_DIR, REPO
from .checkpoints import (ARC_CONTRACT, ARC_HEADING, ARC_PARTS, DAILY_DRIVERS,
                          arc_written, reset_arc)
from .liveness import _cpu_ticks, _descendants, _has_live_conn
from .prompts import GATE_QS, gate_errors, read_verdict
from .runners import _implicit_fallback, _spec_to_runner, default_runner, parse_fallbacks
from .section_security_selftest import run as section_security_selftest
from .sections import (_load_sections_done, _mark_section_done, _sections_done_path,
                       section_ids, wipe_sections)


def run():
    section_security_selftest(_spec_to_runner)
    d, cmd, im = _spec_to_runner("opencode-cli:opencode-go/deepseek-v4-flash", "--fallback")
    assert cmd[:2] == ["opencode", "run"] and "opencode-go/deepseek-v4-flash" in cmd, cmd
    assert im == "arg" and d == "opencode-cli opencode-go/deepseek-v4-flash", (im, d)
    _, ccmd, _ = _spec_to_runner("codex-cli:gpt-5.5@high", "--fallback")
    assert ccmd[-1] == "-" and "model_reasoning_effort=high" in ccmd, ccmd
    _, gcmd, gim = _spec_to_runner("antigravity-cli:gemini-3-pro", "--runner")
    assert gcmd[-1] == "--print" and gim == "arg", gcmd
    fb = parse_fallbacks(["opencode-cli:a", "codex-cli:b"])
    assert [x[0] for x in fb] == ["opencode-cli a", "codex-cli b"], fb
    cfg = {"default": "d", "runners": {"d": {"cmd": ["opencode", "run", "-m", "m"],
                                                "input": "arg"}}}
    same = ("opencode-cli m", ["opencode", "run", "-m", "m"], "arg")
    diff = ("codex-cli x", ["codex", "exec", "-"], "stdin")
    assert _implicit_fallback(cfg, {}, same) == []
    assert _implicit_fallback(cfg, {}, diff) == [default_runner(cfg, {})]
    switch = lambda died, ri, n: died and ri + 1 < n
    assert switch(True, 0, 2) and not switch(False, 0, 2) and not switch(True, 1, 2)

    me = os.getpid()
    assert me in _descendants(me)
    assert _cpu_ticks([me]) > 0
    assert isinstance(_has_live_conn([me]), bool)
    assert section_ids("no-such-tome-xyz") == []

    os.makedirs(BUILD_DIR, exist_ok=True)
    tid = "selftest-resume-xyz"
    try:
        os.remove(_sections_done_path(tid))
    except OSError:
        pass
    assert _load_sections_done(tid) == set()
    _mark_section_done(tid, "s01")
    _mark_section_done(tid, "s03")
    assert _load_sections_done(tid) == {"s01", "s03"}
    os.remove(_sections_done_path(tid))
    sec = os.path.join(REPO, "tomes", tid, "sections")
    os.makedirs(os.path.join(sec, "s01"))
    _mark_section_done(tid, "s01")
    assert wipe_sections(tid) == 1 and not os.path.exists(sec)
    assert _load_sections_done(tid) == set()
    os.rmdir(os.path.join(REPO, "tomes", tid))
    assert wipe_sections("no-such-tome-xyz") == 0

    good_gate = [(label, value) for (label, _), value in zip(
        GATE_QS, ("none", "1", "7", "6", "3", "external"))]
    assert gate_errors(good_gate) == []
    bad_gate = [(label, "") for label, _ in GATE_QS]
    assert len(gate_errors(bad_gate)) == 6

    plan = os.path.join(BUILD_DIR, f"{tid}.plan.md")
    header = "## Gate answers\n- stuff\n\n" + ARC_HEADING + ARC_CONTRACT
    drivers = "; ".join(f"{driver} = CAN" for driver in DAILY_DRIVERS)
    full = "".join(f"**{part}:** {drivers if part == 'Daily drivers' else 'hammered out in ample forge-detail'}\n"
                   for part in ARC_PARTS)
    cases = (("", False), ("\n\n", False), (full, True),
             (full.replace("**Graduate ledger:**", "ledger"), False),
             (full.replace("key-value = CAN", "key-value"), False),
             ("".join(f"**{part}:** x\n" for part in ARC_PARTS), False))
    for extra, expected in cases:
        with open(plan, "w", encoding="utf-8") as f:
            f.write(header + extra)
        assert arc_written(plan, plan)[0] is expected
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
    print("build_tome self-test: OK")
