"""Publish mode: alternate an independent survey with a mend turn until a tome ships.

One turn cannot both judge a tome and repair it. Asked to do both in a single pass it
grades its own homework, and the verdict is worth what that is worth. So the two jobs
run as separate processes with separate mounts: the survey may write only its report,
the mend turn may write only the tome, and neither sees the other's context except
through the report on disk.

That still leaves the same model on both sides of the desk, so the model is not the
authority. The harness re-runs the shipping gates itself after every survey, and a tome
is published only when the judgement AND the machine agree. A survey that signs off
while a gate is failing is overruled, and its own gate report becomes the next mend
turn's assignment.
"""
import os
import time

from ...ai import AiRequest
from ...config import BUILD_DIR, ROOT
from ...platform.permission_profiles import profile_paths
from . import gate, handoffs as handoff_fill, prompts
from .runner import activity_summary, failure_summary, note
from .storage import save_review_metadata, tome_has_changes

# Survey+mend pairs. Eight AI turns on a whole tome is already an expensive evening, and
# a defect that three mend turns could not clear is a defect a person should look at.
ROUNDS = 4


def verdict(report):
    """True only when the survey's own verdict line reads READY.

    Fails safe by construction: the LAST marker in the file decides, and anything that
    is not exactly READY is not ready. A report that quotes the instruction it was given
    ends on "...or PUBLISH VERDICT: NOT READY" and so costs one more round -- a report
    that hedges can never buy a publish.
    """
    _, marker, tail = report.upper().rpartition(prompts.VERDICT_LINE)
    return bool(marker) and (tail.strip().splitlines() or [""])[0].strip(" `*_.") == "READY"


def decide(ready, gate_clean, stalled, last_round):
    """What the loop does after one survey: "publish", "stop", or "mend".

    Pure, because these four lines are the whole termination contract and the loop they
    govern costs hours per pass. Two of them are the safety: no publish without the
    harness's own gate, and no round after the last one.
    """
    if ready and gate_clean:
        return "publish"
    if last_round or (stalled and not ready):
        return "stop"
    return "mend"


def _cancelled(job_manager, job_id):
    return job_manager.status(job_id).get("status") == "cancelled"


def _turn(jid, prompt, writable, *, survey, job_id, kind, model, effort, timeout,
          run_turn, ai, job_manager, processes):
    """Run one publish turn in its own process with its own mounts; return its summary."""
    role = "binder-publish-survey" if survey else "binder-publish-mend"
    invocation = ai.invocation(kind, AiRequest(
        role=role, model=model, input=prompt, timeout=timeout,
        workspace=os.path.join(ROOT, "tomes", jid),
        allowed_tools=("read", "write", "shell"), web_allowed=True,
        effort=effort, writable_paths=tuple(writable),
        trace={"jobId": job_id, "tome": jid},
        permission_paths=profile_paths("binder", build_id=job_id, tome_id=jid, phase=7),
        state_scope={"build_id": job_id, "role": role, "phase": 7, "section": ""},
        stream_events=True))
    rc, cut_short, logtail = run_turn(
        job_id, list(invocation.argv), prompt, invocation.input_mode,
        invocation.environment, invocation.cwd, kind, model, job_manager, processes)
    if cut_short:
        raise RuntimeError(f"the publish {'survey' if survey else 'mend'} turn stalled: "
                           f"{failure_summary(logtail)}")
    if rc != 0:
        raise RuntimeError(f"publish {'survey' if survey else 'mend'} exit {rc}: "
                           f"{failure_summary(logtail)}")
    return activity_summary(job_manager, job_id, f"The Binder finished its {role} turn.")


def report_path(jid):
    """A publish survey is a review, so it is filed as one and shows up in the ledger.

    The ledger keys a report by its timestamp to the second, so two reports inside one
    second would be the same file and the first verdict would be gone. Rounds take
    minutes, so this only ever waits under a test -- but a lost verdict is not a thing
    to leave to timing.
    """
    os.makedirs(os.path.join(ROOT, "reviews"), exist_ok=True)
    while True:
        rel = os.path.join("reviews", f"{jid}-{time.strftime('%Y%m%d-%H%M%S')}.md")
        absolute = os.path.join(ROOT, rel)
        try:
            open(absolute, "x", encoding="utf-8").close()
            return rel, absolute
        except FileExistsError:
            time.sleep(1)


def run(jid, req, *, job_id, kind, model, effort, timeout, rounds=ROUNDS,
        run_turn, ai, job_manager, processes, checkpoint):
    """Alternate survey and mend until the tome ships or the loop gives up.

    Returns ``(ok, summary, report_rel)``; ``ok`` is None when the operator cancelled.
    The caller holds a checkpoint of the tome, and ``checkpoint`` re-takes it after every
    completed round -- a provider fault in round four must not throw away rounds one to
    three, which is hours of paid work the tome already has on disk.
    """
    turn = dict(job_id=job_id, kind=kind, model=model, effort=effort, timeout=timeout,
                run_turn=run_turn, ai=ai, job_manager=job_manager, processes=processes)
    # A tome with no sealed plan has no shipping gate at all -- validate_phase3 never runs
    # against it -- so publish would spend four rounds grading it against half a contract.
    # The caller seals the plan; sealing creates the continuity handoffs blank, which fails
    # the gate the tome just joined, so the scoped turn that fills them runs here rather
    # than burning a whole round on a paragraph per section.
    handoff_fill.fill_blank(jid, **turn)
    plan_rel, folder = gate.plan_rel(jid), gate.handoff_dir(jid)
    writable = [os.path.join(ROOT, "tomes", jid)] + ([folder] if folder else [])
    previous, stalled, summary = "", False, ""
    for rnd in range(1, rounds + 1):
        report_rel, report_abs = report_path(jid)
        note(job_manager, job_id,
             f"round {rnd} of {rounds}: the survey measures the tome against publisher.md "
             f"and inks its verdict at {report_rel}")
        _turn(jid, prompts.publish_prompt(
            jid, req, survey=True, report_rel=report_rel, plan_rel=plan_rel,
            handoffs=folder, rnd=rnd, rounds=rounds, previous=previous),
            [report_abs], survey=True, **turn)
        if _cancelled(job_manager, job_id):
            return None, "", report_rel
        save_review_metadata(ROOT, report_rel, {
            "version": 1, "tome": jid, "path": report_rel, "completedAt": time.time(),
            "providerKind": kind, "providerModel": model, "effort": effort})
        with open(report_abs, encoding="utf-8") as handle:
            report = handle.read().strip()
        ready = verdict(report)
        checked = gate.validate_amendment(
            jid, strict=True, on_step=lambda text: note(job_manager, job_id, text))
        gate_report = "" if checked.returncode == 0 else (checked.stdout + checked.stderr).strip()
        note(job_manager, job_id,
             f"the survey says {'READY' if ready else 'NOT READY'} and the harness's own "
             f"shipping gate {'passes' if not gate_report else 'fails'}")
        step = decide(ready, not gate_report, stalled, rnd == rounds)
        if step == "publish":
            return True, (f"The tome is ready to publish. Survey {rnd} of {rounds} signed it "
                          f"off and the shipping gate agrees — the report is at {report_rel}."), report_rel
        if step == "stop":
            return False, (
                f"Publish stopped after round {rnd} of {rounds} and the tome is NOT ready. "
                + ("The last mend turn changed nothing and the survey still finds blockers, "
                   "so this one needs a person." if stalled and not ready else
                   "The rounds ran out.")
                + f" The outstanding blockers are in {report_rel}."), report_rel
        if ready:
            note(job_manager, job_id,
                 "the survey signed the tome off but the harness's own gate disagrees — the "
                 "gate wins, and its report becomes the mend turn's assignment")
        summary = _turn(jid, prompts.publish_prompt(
            jid, req, survey=False, report_rel=report_rel, plan_rel=plan_rel,
            handoffs=folder, rnd=rnd, rounds=rounds, gate_report=gate_report),
            writable, survey=False, **turn)
        if _cancelled(job_manager, job_id):
            return None, "", report_rel
        resealed, reseal_error = gate.sync_contracts(
            "reseal", jid, reason=f"Binder publish round {rnd} on {jid}")
        for line in resealed:
            note(job_manager, job_id, line)
        if reseal_error:
            note(job_manager, job_id, f"the course map could not be re-sealed: {reseal_error[:300]}")
        # Measured against the checkpoint taken at the end of the previous round, so this is
        # "did THIS mend turn change anything" -- the stalemate half of the ending rule.
        stalled = not tome_has_changes(ROOT, BUILD_DIR, jid)
        checkpoint(jid)
        previous = (f"The mend turn of round {rnd} reported:\n\n{summary[:2000]}\n\nAnything "
                    "it declined with a reason is settled — do not raise it again unless you "
                    "can say concretely why the reason is wrong.\n\n")
    return False, "Publish ran out of rounds.", ""  # unreachable: decide() stops on the last


def demo():
    """One runnable check: the verdict cannot be faked and the loop cannot run forever."""
    assert verdict("all good\n\nPUBLISH VERDICT: READY\n")
    assert verdict("**PUBLISH VERDICT: READY**")
    assert not verdict("PUBLISH VERDICT: NOT READY")
    assert not verdict("The tome is ready to publish."), "prose is not a verdict"
    assert not verdict("PUBLISH VERDICT: READY\nPUBLISH VERDICT: NOT READY"), "the last one rules"
    assert not verdict("end with `PUBLISH VERDICT: READY` or `PUBLISH VERDICT: NOT READY`"), \
        "quoting its own instructions must never buy a publish"

    assert decide(True, True, False, False) == "publish"
    assert decide(True, False, False, False) == "mend", "a failing gate overrules a sign-off"
    assert decide(False, True, True, False) == "stop", "a mend that changed nothing is a stalemate"
    assert decide(False, True, False, False) == "mend"
    assert all(decide(r, g, s, True) in ("publish", "stop")
               for r in (0, 1) for g in (0, 1) for s in (0, 1)), \
        "the last round must never ask for another one"
    print("publish loop: OK")


if __name__ == "__main__":
    demo()
