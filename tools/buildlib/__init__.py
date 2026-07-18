"""Shared authoring and validation support.

- runtime   provider runners, access boundaries, liveness, and validation environments
- single_author  author controls, phase gates, scope, sessions, and optional full review
- workflow  prompts, checkpoints, progress markers, and phase resets
- measure   canonical validator command and final shipping checks
- skeleton  Phase-2 scaffolding plus artifact-integrity contracts
- course_map  Phase-1 seed, graph schema, codecs, locations, digest, and seal
- course  alignment, amendment, control, dependencies, limits, and derived state
- language_mastery  capability planning, map validation, and authored evidence
- continuity  handoff-v3 discoveries and typed fulfillment evidence
- prerequisites  mandatory cached post-section Validator AI gate and prompt
- review_evidence  proof-v1 evidence derived from execution
Shared paths/constants live here."""
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW_DIR = os.path.join(REPO, "tome-workflow")  # one phase-N-*.md per phase
VALIDATOR = os.path.join(REPO, "tools", "validate_tome.py")
BUILD_DIR = os.path.join(REPO, ".tome-build")
VALIDATOR_FAILURE_DIR = os.path.join(REPO, "validator-failures")

# Generic CLI health checks still use these; tome construction no longer monitors,
# kills, retries, or replaces an author based on liveness heuristics.
PING_INTERVAL_DEFAULT = 30
DEAD_PINGS_DEFAULT = 2
