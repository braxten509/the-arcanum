"""Support package for tools/build_tome.py. Module map:
- runners   runner templates/specs, harness.toml resolution, the human runner-pick pause
- config    harness.toml loading and preset resolution
- liveness  headless worker execution, hang detection, auth preflight
- agent_runtime  provider-normalized repo/web/temp access and scoped write boundaries
- prompts   phase prompt assembly, the Phase-0 gate/plan writer, verdict/findings IO
- measure   validator gate, inventory/shrinkage contract, ground-truth measuring
- gates     harness-owned between-phase validation and advance/retry decision
- sections  split-mode Phase 3 (bounded warm section batches) + per-section checkpoints
- phase3_runtime  one-worker Phase-3 resume/replacement prompt-state decisions
- skeleton  plan parser + deterministic one-placeholder-lesson Phase-2 scaffolding
- continuity  schema-checked cross-section handoffs and whole-tome continuity briefing
- review    Phase-8 repair loop plus independent fresh no-change PASS gate
- reporting  measured end-of-build plan facts and phase timings
- checkpoints  between-phase gates: Phase-1 arc gate, arc approval pause, tome rename
- workflow  phase-file parsing and the shared access-boundary prompt
- build_selftest  focused harness regression checks
Shared paths/constants live here."""
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW_DIR = os.path.join(REPO, "tome-workflow")  # one phase-N-*.md per phase
CONFIG = os.path.join(REPO, "global-configs", "harness.toml")
VALIDATOR = os.path.join(REPO, "tools", "validate_tome.py")
BUILD_DIR = os.path.join(REPO, ".tome-build")

MAX_RETRIES = 2        # per content phase on validator ERROR — paid cloud runners (retries cost money)
MAX_RETRIES_LOCAL = 4  # a free local ollama runner gets more automatic tries before it pauses to ask
MAX_STUDENT_LOOPS = 4  # includes the required fresh, no-change verification after repairs
PING_INTERVAL_DEFAULT = 30  # seconds between worker liveness checks
DEAD_PINGS_DEFAULT = 2      # consecutive idle checks before a worker is declared hung


def retries_for(runner_display):
    """Default gate-retry budget for a phase's runner: a free local/ollama worker gets more tries
    than a paid cloud one. The operator can extend either on the failure pause (see request_runner)."""
    return MAX_RETRIES_LOCAL if "ollama/" in (runner_display or "") else MAX_RETRIES
