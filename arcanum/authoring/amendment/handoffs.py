"""Fill the continuity handoffs that a first-time plan seals into existence, blank.

A tome authored before build plans existed earns its plan by being repaired, so the
harness can only seal one on the way OUT of the run that did the repairing -- and the
sealing is what creates the handoff files. That ordering is deliberate (a plan written
earlier would be a promise about a tome still eligible for rollback), but it strands
the handoffs: they appear one second after the sandbox that could have written them
ended, and `course_map.adopt` will not invent an `artifact_state` for them. Left alone
the tome lands on the full gate owing one blocker per section, and the only cure is a
second whole run costing hours to write a paragraph each.

So the run that earned the plan takes one more scoped turn, mounted on the handoff
folder alone, and writes them.
"""
import os

from ...ai import AiRequest
from ...config import ROOT
from ...platform.permission_profiles import profile_paths
from . import gate, prompts
from .runner import failure_summary, note


def fill_blank(jid, *, job_id, kind, model, effort, timeout, run_turn,
               ai, job_manager, processes):
    """Write every blank ``artifact_state``; return True if the turn ran and succeeded.

    ``run_turn`` is the caller's own turn runner, so this inherits the same continuation
    behaviour every other Binder turn has instead of quietly getting a flimsier one.

    Never raises. The tome itself already passed its validator before this point, so a
    failure here costs the operator a second run -- it must not cost them the amendment.
    """
    blank = gate.blank_handoffs(jid)
    plan_rel = gate.plan_rel(jid)
    folder = gate.handoff_dir(jid)
    if not (blank and plan_rel and folder):
        return False
    note(job_manager, job_id,
         f"the sealed plan created {len(blank)} blank continuity handoff(s) "
         f"({', '.join(blank)}); one scoped turn now writes them")
    prompt = prompts.fill_handoffs(jid, folder, blank, plan_rel)
    try:
        invocation = ai.invocation(kind, AiRequest(
            role="binder-handoffs", model=model, input=prompt,
            timeout=timeout, workspace=os.path.join(ROOT, "tomes", jid),
            allowed_tools=("read", "write", "shell"), web_allowed=False,
            effort=effort, writable_paths=(folder,),
            trace={"jobId": job_id, "tome": jid},
            permission_paths=profile_paths(
                "binder", build_id=job_id, tome_id=jid, phase=7),
            state_scope={"build_id": job_id, "role": "binder-handoffs",
                         "phase": 7, "section": ""},
            stream_events=True))
        rc, cut_short, logtail = run_turn(
            job_id, list(invocation.argv), prompt,
            invocation.input_mode, invocation.environment, invocation.cwd,
            kind, model, job_manager, processes)
    except Exception as error:  # a provider fault here is news, not a failed amendment
        note(job_manager, job_id, f"the continuity handoffs could not be written: {error}")
        return False
    if rc != 0 or cut_short:
        note(job_manager, job_id,
             f"the continuity handoffs were not finished: {failure_summary(logtail)}")
        return False
    still_blank = gate.blank_handoffs(jid)
    note(job_manager, job_id,
         "every continuity handoff now describes its section's artifact"
         if not still_blank else
         f"{len(still_blank)} continuity handoff(s) are still blank: {', '.join(still_blank)}")
    return not still_blank
