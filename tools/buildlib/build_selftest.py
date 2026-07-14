"""Ordered entry point for the focused build-harness regression suites."""
from .selftests.authoring_review import run as run_authoring_review
from .selftests.harness_runtime import run as run_harness_runtime
from .selftests.phase3_flow import run as run_phase3_flow


def run():
    run_harness_runtime()
    run_authoring_review()
    run_phase3_flow()
    from test_validation_dependencies import main as run_validation_dependencies
    run_validation_dependencies()
    print("build_tome self-test: OK")
