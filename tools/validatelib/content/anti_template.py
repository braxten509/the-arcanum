"""The anti-template tells: the machine-generated grid, canned per-type strings,
and mc answer positions — tallied per section as well as pooled."""
from collections import Counter

from .. import warn


def _spread_finding(answers, scope):
    """The answer-position tell for one bank of mc exercises, or "" if it is spread.

    ``answers`` is (index, choice_count) pairs; ``scope`` is "" for the whole tome and
    "sNN: " for one section, and it also selects which tells apply. An UNUSED index is a
    pattern across 142 pooled questions and ordinary luck across a section's ten, so that
    one stays tome-wide. A DOMINANT index is the exact opposite: pooling twelve balanced
    sections averages away the thirteenth sitting 70% on index 1, and that thirteenth is
    the only bank a learner actually sits in front of.
    """
    idxs = [a for a, _ in answers]
    four = [a for a, n in answers if n >= 4]
    if len(idxs) >= 4 and len(set(idxs)) == 1:
        return (f"{scope}all {len(idxs)} mc answers are index {idxs[0]} — spread "
                "correct answers across positions 0–3 (§3); a fixed index is guessable "
                "and reads as machine-authored")
    if not scope and len(four) >= 8 and (set(range(4)) - set(four)):
        miss = sorted(set(range(4)) - set(four))
        return (f"mc answers never land on index {miss} across {len(four)} "
                f"four-choice questions (they cluster on {sorted(set(four))}) — spread "
                "correct answers evenly across 0–3 (§3), don't over-correct to the middle")
    if len(idxs) >= 8 and len(set(idxs)) < 3:
        return (f"{scope}mc answers cluster on only {sorted(set(idxs))} — spread "
                "correct answers across positions 0–3 (§3)")
    counts = Counter(four)
    # Every index used, but not comparably. Tome-wide that means a position starved under
    # 10% (guessable by elimination); per section it means one position holding more than
    # half the bank (guessable outright). Same rule, sized to the sample: a 10-question
    # section cannot support a 10% floor, and 142 pooled questions hide a 70% run.
    if not scope and len(four) >= 20:
        starved = [i for i in range(4) if counts[i] / len(four) < 0.10]
        if starved:
            return (f"mc answer index(es) {starved} carry under 10% of {len(four)} "
                    f"four-choice answers (spread: {dict(sorted(counts.items()))}) — "
                    "rebalance so 0–3 are each used a comparable number of times (§3)")
    if scope and len(four) >= 8:
        top, n = counts.most_common(1)[0]
        if n * 2 > len(four):
            return (f"{scope}{n} of {len(four)} four-choice answers are index {top} "
                    f"(tally {[counts[i] for i in range(4)]}) — no index may hold half a "
                    "section's answers (§3: tally each section and rewrite until 0/1/2/3 "
                    "are comparable); guessing that index wins more often than not")
    return ""


def check_anti_template(sections_data):
    """Tome-wide Phase-3 findings for the anti-template rules structure checks miss:
    the machine-generated grid (every section the same shape) and mc answers
    stuck on one index. Direct library calls report WARN; the harness promotes them
    to ERROR at the Phase-3 owner gate so patterns cannot spread into later batches."""
    mc_answers = []
    section_mc = []  # (sid, answers) — §3 tallies answer indices per section, not just pooled
    shapes = []  # (lesson_count, tuple(exercise_counts)) per section
    lesson_types = []  # sorted type-tuple per lesson — catches "one of each type, every lesson"
    fields = {"hint": [], "prompt": [], "whyWrong": [], "explain": []}  # near-unique per §3
    for sdata in sections_data:
        lessons = sdata.get("lessons", []) or []
        here = []
        ex_counts = []
        for les in lessons:
            if not isinstance(les, dict):
                continue
            exs = les.get("exercises", []) or []
            ex_counts.append(len(exs))
            # Invalid or incomplete exercises are reported by the structural checks.
            # Keep them visible to this tome-wide shape check without asking Python to
            # order incomparable values such as ``None`` and strings.
            lesson_types.append(tuple(sorted(
                str(e["type"]) if e.get("type") is not None else "<missing>"
                for e in exs if isinstance(e, dict))))
            for ex in exs:
                if not isinstance(ex, dict):
                    continue
                if ex.get("type") == "mc" and isinstance(ex.get("answer"), int):
                    ch = ex.get("choices")
                    here.append((ex["answer"], len(ch) if isinstance(ch, list) else 0))
                    # A review variant is merged over its parent and graded as a real
                    # question (web/app/game/exercise.js), so its answer position is
                    # exactly as guessable. Tallying only exercises[] once let a tome
                    # ship with all 28 of its variants on index 0 while every pooled
                    # bank read balanced -- the variants were the only questions the
                    # spaced-review queue ever showed.
                    for var in ex.get("reviewVariants") or []:
                        if isinstance(var, dict) and isinstance(var.get("answer"), int):
                            vch = var.get("choices")
                            here.append((var["answer"],
                                         len(vch) if isinstance(vch, list) else len(ch or [])))
                for k, bucket in fields.items():
                    v = ex.get(k)
                    if isinstance(v, str) and v.strip():
                        bucket.append(v.strip())
        mc_answers.extend(here)
        section_mc.append((sdata.get("id") or "?", here))
        shapes.append((len(lessons), tuple(ex_counts)))
    # §3: hints/prompts/whyWrong/explain are exercise-specific — "180 exercises,
    # ~180 distinct hints". One canned string stamped across many exercises is the
    # content-level version of the uniform grid, and the shape checks miss it.
    for k, vals in fields.items():
        if len(vals) < 8:
            continue
        top, n = Counter(vals).most_common(1)[0]
        if n > 3:
            warn("anti-template", f"{k}: one string is reused {n}× of {len(vals)} "
                 f"({len(set(vals))} distinct) — {k} must be exercise-specific (§3), not a "
                 f"canned per-type sentence. Offender: {top[:60]!r}", phase=3)
    # mc answer spread across 0–3, measured twice. §3 says "after each section, tally its
    # mc answer indices" — the pooled tally alone cannot do that, and a tome can sit at a
    # blameless [27,62,34,19] overall while one section runs 70% on a single index. The
    # section is the bank a learner meets, so it is checked as one.
    finding = _spread_finding(mc_answers, "")
    if finding:
        warn("anti-template", finding, phase=3)
    for sid, answers in section_mc:
        finding = _spread_finding(answers, f"{sid}: ")
        if finding:
            warn("anti-template", finding, phase=3)
    if len(shapes) >= 3 and len(set(shapes)) == 1:
        lc, ec = shapes[0]
        warn("anti-template", f"every section has the same shape ({lc} lessons, exercise counts "
             f"{list(ec)}) — vary lesson counts (3–8) and exercise counts (4–6) by material (§3); "
             "a uniform grid reads as machine-generated", phase=3)
    # even when section shapes differ, every lesson carrying the identical type mix
    # (e.g. exactly one of each of mc/text/fill/type/write) is a machine tell the
    # section-level shape check misses.
    if len(lesson_types) >= 4 and len(set(lesson_types)) == 1:
        warn("anti-template", f"all {len(lesson_types)} lessons have the identical exercise-type "
             f"mix {list(lesson_types[0])} — vary the mix and order per lesson (§3), not one of "
             "each type every time", phase=3)
