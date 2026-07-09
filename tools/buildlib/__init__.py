"""Support package for tools/build_tome.py. Module map:
- runners   runner templates/specs, harness.toml resolution, the human runner-pick pause
- liveness  headless worker execution, hang detection, auth preflight
- prompts   phase prompt assembly, the Phase-0 gate/plan writer, verdict/findings IO
- measure   validator gate, inventory/shrinkage contract, ground-truth measuring
- sections  split-mode Phase 3 (one worker per section) + its resume bookkeeping
Shared paths/constants live here."""
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW = os.path.join(REPO, "TOME-WORKFLOW.md")
CONFIG = os.path.join(REPO, "harness.toml")
VALIDATOR = os.path.join(REPO, "tools", "validate_tome.py")
BUILD_DIR = os.path.join(REPO, ".tome-build")

MAX_RETRIES = 2        # per content phase on validator ERROR — paid cloud runners (retries cost money)
MAX_RETRIES_LOCAL = 4  # a free local ollama runner gets more automatic tries before it pauses to ask
MAX_STUDENT_LOOPS = 3  # phase 8 review -> fill loops before giving up
PING_INTERVAL_DEFAULT = 30  # seconds between worker liveness checks
DEAD_PINGS_DEFAULT = 2      # consecutive idle checks before a worker is declared hung


def retries_for(runner_display):
    """Default gate-retry budget for a phase's runner: a free local/ollama worker gets more tries
    than a paid cloud one. The operator can extend either on the failure pause (see request_runner)."""
    return MAX_RETRIES_LOCAL if "ollama/" in (runner_display or "") else MAX_RETRIES
