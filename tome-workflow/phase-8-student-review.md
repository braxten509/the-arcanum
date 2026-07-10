# Phase 8 — Student review & gap-fill (mandatory)

Validation proves the tome is well-*formed*; it cannot prove it actually *teaches*.
That last question — "would a real beginner come out able to DO this?" — is the one
that keeps failing (a course that drills C++ 101 instead of the domain; two payoff
chapters left hollow; the hook taught but never how to find what to hook). So close
the loop with a fresh set of eyes.

**The review needs clean eyes** — a first-time-student reviewer who knows only what the
tome's own prerequisites assume, not what the author knows. If you authored earlier
phases in THIS same context, spawn ONE clean-context subagent to be that student. If you
are a fresh worker with no authoring context (the harness case), you already ARE the
clean eyes — do the read yourself; spawning a child just reads the tome twice at double
cost. Either way, the student lens works like this:

- **Read EVERY chapter, cover to cover, in order — no sampling, no skimming, no
  reading only titles.** Every section brief, every lesson `body`, every exercise, every
  freestyle, from `s01` to the last. A review that skipped a chapter is void; the two
  chapters most likely to be broken are the *last* ones, exactly the ones a lazy review
  skips.
- Play it straight as a learner: at each chapter, note **what you can now actually do**,
  **what was used or assumed but never taught** (an untaught prerequisite, an address
  handed to you with no method to find it, a tool named but never shown), and **where the
  prose is missing, placeholder, or hollow**.
- End with the blunt verdict: **after the final chapter, could you sit down with the real
  tools and a real target and do the thing `meta.description` promises — unaided?** If
  no, name precisely what's missing.
- **Audit the artifact, not the story.** List every file under the tome folder
  (`find tomes/<id> -type f`) and justify each against the layout contract — a nested
  folder, a backup copy, or a scratch file is a blocking finding. Verify every claim
  in the build plan against the disk: a phase that logged "registered the 6 badges"
  must have six `[[badges]]` present NOW; claims are not evidence. Confirm the engine
  contracts: the badge bank defines every engine-granted id, shop theme items point at
  real `[[themes]]`, attack starters run as given. The meta files — badges, themes,
  shop, intrusions, attacks — are content too: read them in the tome's voice, not just
  the chapters.

**The same pass (or a second clean-context reviewer) also runs the §7 human-judgement
checklist as an editor** — voice consistency, anti-template variety, balance, coverage,
learning design — over the WHOLE assembled tome. This reviewer has the authority to
FAIL the run: a blocking finding from either lens (student gap or editorial checklist)
means the tome is not done, no matter what the validator said. The validator is the
structural gate; this is the editorial one — a harness run that ends at Phase 7 has
shipped unreviewed content. write the missing lesson bodies,
add the untaught fundamentals/reconnaissance as their own lessons or chapters, repair the
hollow chapters. Re-run **Phase 7**, then send the *revised* tome back through another
student pass. Loop until the student, having read every chapter, reports no blocking gap.
(Under the harness this loop is EXTERNAL: each invocation does ONE review + fix round and
writes its verdict; the harness re-runs the phase, scoped to the findings. Do not nest
your own loop inside a harness round. The harness accepts only the exact one-line verdict
`PASS`, re-runs strict validation after every revision, and exits nonzero if the review
cap is reached without a clean pass.)

→ **Produce:** the student's per-chapter gap report + the revisions that answer it — a
tome that doesn't just validate, but actually teaches the thing it promises.
