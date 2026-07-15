"""Shared authoring and validation support.

- runners   command templates for the freely chosen persistent author
- single_author  pause/message/resume control for the one author session
- liveness  generic CLI authentication probes used outside tome construction
- agent_runtime  provider-normalized repo/web/temp access and scoped write boundaries
- prompts   Phase-0 gate and calibrated build-plan writer
- measure   canonical validator command and final shipping checks
- skeleton  plan parser + deterministic one-placeholder-lesson Phase-2 scaffolding
- continuity  schema-checked cross-section evidence used by validators
- review_evidence  proof-v1 evidence derived from execution
- checkpoints  Phase-1 arc gate and deterministic tome rename
- phase_reset  durable phase-start snapshots and transactional Binder rewinds
Shared paths/constants live here."""
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW_DIR = os.path.join(REPO, "tome-workflow")  # one phase-N-*.md per phase
VALIDATOR = os.path.join(REPO, "tools", "validate_tome.py")
BUILD_DIR = os.path.join(REPO, ".tome-build")

# Generic CLI health checks still use these; tome construction no longer monitors,
# kills, retries, or replaces an author based on liveness heuristics.
PING_INTERVAL_DEFAULT = 30
DEAD_PINGS_DEFAULT = 2
