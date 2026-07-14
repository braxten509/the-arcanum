"""Workflow phase discovery and the access contract appended to every build prompt."""
import glob
import os
import re

from . import BUILD_DIR, REPO, WORKFLOW_DIR


PHASE_H1 = re.compile(r"#\s*Phase (\d+)\s*—\s*(.*)")
RUNTIME_CONFIG_DIR = os.path.join(REPO, "global-configs", "runtimes")
NARROW_TOME_WRITES = {
    4: ("intrusions.toml", "attacks_src.toml", "generated"),
    5: ("tome.toml",),
    6: ("themes.toml", "shop.toml", "badges.toml"),
}


def parse_phases():
    """Return ordered `(number, title, body)` tuples from tome-workflow phase files."""
    phases = []
    for path in glob.glob(os.path.join(WORKFLOW_DIR, "phase-*.md")):
        head, _, body = open(path, encoding="utf-8").read().partition("\n")
        match = PHASE_H1.fullmatch(head.strip())
        if not match:
            raise SystemExit(
                f"{path}: first line must be '# Phase N — Title', got {head.strip()!r}"
            )
        phases.append((int(match.group(1)), match.group(2).strip(), body.strip()))
    if not phases:
        raise SystemExit(f"parsed 0 phases from {WORKFLOW_DIR}/ — where did they go?")
    return sorted(phases)


def support_prompt(name):
    """Load one progressively disclosed worker/reconciliation prompt."""
    if not re.fullmatch(r"[a-z0-9-]+", name):
        raise ValueError(f"invalid support prompt name {name!r}")
    path = os.path.join(WORKFLOW_DIR, "support", name + ".md")
    try:
        return open(path, encoding="utf-8").read().strip()
    except OSError as exc:
        raise SystemExit(f"missing workflow support prompt {path}: {exc}") from exc


def phase_writable_paths(num, tome_scope, sidecars=()):
    """Project paths a whole-phase worker may mutate.

    Phase 2 may establish a reusable language runtime; Phase 8 may repair a mismatch
    between that selected runtime and the completed tome.  Both are post-audited so
    only the runtime named by the tome may actually change.
    """
    if num == 1:
        paths = [*sidecars]
    elif num in NARROW_TOME_WRITES:
        paths = [os.path.join(tome_scope, relative)
                 for relative in NARROW_TOME_WRITES[num]] + [*sidecars]
    else:
        paths = [tome_scope, *sidecars]
    if num in (2, 8):
        paths.append(RUNTIME_CONFIG_DIR)
    return paths


def prepare_phase_writable_paths(num, tome_scope, sidecars=(), phase3_sections=()):
    """Create only expected narrow outputs, then return the real worker write mounts."""
    if num == 3 and phase3_sections:
        section_paths = [os.path.join(tome_scope, "sections", sid) for sid in phase3_sections]
        for path in section_paths:
            os.makedirs(path, exist_ok=True)
        return section_paths + [*sidecars]
    if num in NARROW_TOME_WRITES:
        for relative in NARROW_TOME_WRITES[num]:
            path = os.path.join(tome_scope, relative)
            if relative == "generated":
                os.makedirs(path, exist_ok=True)
            elif not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "a", encoding="utf-8").close()
    return phase_writable_paths(num, tome_scope, sidecars)


def phase_sidecars(num, plan_path, verdict_path, findings_path, shrink_path, tid=None):
    """Exact harness files exposed writable to one whole-phase worker."""
    paths = []
    if num == 1:
        paths.append(plan_path)
    if num >= 2:
        paths.append(shrink_path)
    if num == 8:
        paths.extend((verdict_path, findings_path))
    handoffs = os.path.join(BUILD_DIR, f"{tid}.handoffs") if tid else ""
    if num in (7, 8) and os.path.isdir(handoffs):
        paths.append(handoffs)
    return paths


def access_boundary(tid, num):
    extra = (" This phase may also create or repair only the selected language definition "
             "under global-configs/runtimes/; the harness rejects changes to every other "
             "runtime file." if num in (2, 8) else "")
    if num == 1:
        write_scope = "Write only the Phase 1 build-plan sidecar; the scaffolded tome is read-only."
    elif num == 3:
        write_scope = ("Write only the assigned Phase-3 section directories and exact continuity/"
                       "harness sidecars named in the prompt. The rest of the tome is read-only.")
    elif num in NARROW_TOME_WRITES:
        exact = ", ".join(f"tomes/{tid}/{path}" for path in NARROW_TOME_WRITES[num])
        write_scope = (f"Write only these phase outputs: {exact}, plus the exact harness "
                       "sidecars named in the prompt. The rest of the tome is read-only.")
    else:
        write_scope = f"Write only tomes/{tid}/ and the exact phase sidecars named in the prompt."
    return (f"\n\n===== WRITE BOUNDARY =====\nRepository root: {REPO}. Read the whole "
            "repository, execute trusted repository Python, use web search/fetch, and use /tmp. "
            f"{write_scope}{extra} Engine code, other "
            "tomes, and unrelated build state are read-only. Resolve relative paths from the "
            "repository root.")
