#!/usr/bin/env python3
"""Negative fixtures prove the checked-in architecture policy cannot silently weaken."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.architecture.models import load_policy
from tools.architecture.rules import check_javascript, check_python


policy = load_policy(str(ROOT / "global-configs" / "architecture-policy.toml"))
assert policy["version"] == 1
assert policy["javascript"]["apiAdapters"] == ["web/app/core/api-client.js"]
assert policy["javascript"]["stateAdapters"] == ["web/app/core/store.js"]
assert {"os", "subprocess", "socket"} <= set(policy["python"]["pureForbiddenImports"])
assert "tools.buildlib" in policy["python"]["serverForbiddenImports"]
assert policy["registries"]["scenarioComposition"] == "arcanum/assessment/scenarios.py"
assert policy["registries"]["interactionComposition"] == "web/app/game/interactions/index.js"
assert policy["registries"]["cognitiveComposition"] == "web/app/mastery/cognitive.js"
assert policy["registries"]["routeComposition"] == "web/app/main.js"
assert policy["registries"]["jobComposition"] == "arcanum/jobs/registry.py"
assert policy["registries"]["aiRoleComposition"] == "arcanum/ai/roles/composition.py"

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)

    def write(relative, source):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    write("arcanum_core/impure.py", "import os\n")
    write("arcanum/server.py", "from tools.buildlib import workflow\n")
    write("arcanum/legacy.py", "import arcanum.routes_get\n")
    write("arcanum/config.py", "jobs = {}\n")
    write("runtimes/left.py", "import runtimes.right\n")
    write("runtimes/right.py", "import runtimes.left\n")
    write("web/app/core/api-client.js", "export const request = () => null;\n")
    write("web/app/core/bootstrap.js", "export const boot = () => null;\n")
    write("web/app/core/store.js", "export const state = {};\n")
    write("web/app/bad.js", "fetch('/api/state'); S.value = window.TOME;\n")
    write("web/app/left.js", "import './right.js';\n")
    write("web/app/right.js", "import './left.js';\n")
    write("web/app/domains/mastery/policy.js", "document.querySelector('#x');\n")

    python_codes = {finding.code for finding in check_python(str(root), policy)}
    assert {"python.pure-import", "python.server-authoring-import", "python.deprecated-import",
            "python.mutable-config", "python.cycle"} <= python_codes
    javascript_codes = {finding.code for finding in check_javascript(str(root), policy)}
    assert {"javascript.fetch-boundary", "javascript.ambient-state",
            "javascript.ambient-tome", "javascript.domain-dom",
            "javascript.cycle"} <= javascript_codes

print("architecture negative fixtures: OK")
