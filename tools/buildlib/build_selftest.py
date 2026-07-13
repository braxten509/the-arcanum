"""Ordered entry point for the focused build-harness regression suites."""
from .selftests.authoring_review import run as run_authoring_review
from .selftests.harness_runtime import run as run_harness_runtime


def run():
    run_harness_runtime()
    run_authoring_review()
    print("build_tome self-test: OK")
