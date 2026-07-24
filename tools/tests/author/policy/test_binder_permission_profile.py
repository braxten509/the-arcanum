#!/usr/bin/env python3
"""Binder tome work uses a declared role profile and isolated provider state."""
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from arcanum.ai import AiRequest
from arcanum.ai.contracts import ProviderConfigurationError
from arcanum.ai.providers import CodexCliProvider
from arcanum.platform.agent_scratch import remove as remove_agent_scratch
from tools.buildlib.access import profile_paths


workspace = str(ROOT / "tomes" / "binder-policy-test")
base = dict(
    role="binder-amend", model="gpt-test", input="fortify", timeout=10,
    workspace=workspace, writable_paths=(workspace,),
)
provider = CodexCliProvider()

try:
    provider.invocation(AiRequest(**base))
except ProviderConfigurationError as exc:
    assert "no declared permission profile" in str(exc)
else:
    raise AssertionError("generic tome invocation bypassed the declared-profile requirement")

permissions = profile_paths(
    "binder", build_id="binder-policy-test", tome_id="binder-policy-test", phase=7)
reads = set(permissions["read"])
assert str(ROOT / "course-improvement-guide.md") in reads
assert str(ROOT / "tools") in reads
assert str(ROOT / "tomes") in reads
assert ["python3", "tools/validate_tome.py",
        "tomes/binder-policy-test", "--strict"] in permissions["execute_commands"]

scope = {
    "build_id": "binder-policy-test",
    "role": "binder-amend",
    "phase": 7,
    "section": "",
}
calls = []
with patch(
        "arcanum.ai.providers.cli.scoped_runner_command",
        lambda *args, **kwargs: calls.append((args, kwargs)) or list(args[1])), \
        patch("arcanum.ai.providers.cli.ensure_cli_access", lambda *_args: None):
    invocation = provider.invocation(AiRequest(
        **base, permission_paths=permissions, state_scope=scope))

assert invocation.cwd == workspace
assert calls[0][1]["permission_paths"] is permissions
assert calls[0][1]["state_scope"] is scope

remove_agent_scratch("binder-policy-test")
print("Binder permission profile and isolated CLI state: OK")
