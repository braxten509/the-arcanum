"""Ordered entry point for the focused build-harness regression suites."""
import os

from .selftests.authoring_review import run as run_authoring_review
from .selftests.harness_runtime import run as run_harness_runtime
from .selftests.phase3_flow import run as run_phase3_flow


def run():
    old = os.environ.get("ARCANUM_REQUIRE_PROOF_V1")
    os.environ["ARCANUM_REQUIRE_PROOF_V1"] = "1"
    try:
        run_harness_runtime()
        run_authoring_review()
        run_phase3_flow()
        from test_validation_dependencies import main as run_validation_dependencies
        from test_tome_proof import main as run_tome_proof
        from test_smoke_tome import main as run_smoke_tome
        run_validation_dependencies()
        run_tome_proof()
        run_smoke_tome()
    finally:
        if old is None:
            os.environ.pop("ARCANUM_REQUIRE_PROOF_V1", None)
        else:
            os.environ["ARCANUM_REQUIRE_PROOF_V1"] = old
    print("build_tome self-test: OK")
