#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Regression checks that role trials start red and require complete real repairs."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.model_triallib.fixtures import ROLE_ORDER, create_workspace  # noqa: E402
from tools.model_triallib.grading import baseline_hashes, grade_workspace  # noqa: E402
from tools.model_triallib.reviewer_fixture import (HOLLOW_COMMANDS,  # noqa: E402
                                                   SAVE_COMMANDS)


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def line_of(path, needle):
    for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if needle in text:
            return number
    raise AssertionError(f"{needle!r} not found in {path}")


def command_rows(commands, observations):
    return [{"command": command, "exitCode": 0, "observation": observation}
            for command, observation in zip(commands, observations)]


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    protected = create_workspace(root, ROLE_ORDER)
    baseline = baseline_hashes(protected)
    compiled = subprocess.run([sys.executable, "-m", "py_compile", str(root / "check.py")],
                              capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    initial = grade_workspace(root, ROLE_ORDER, baseline)
    assert not any(item["passed"] for item in initial.values()), initial
    initial_failures = set(initial["reviewer"]["criticalFailures"])
    assert {"hollow ordinary cold launch", "hollow three negative controls",
            "ashen ordinary save round trip", "ashen acceptance anti-counterfeit"}.issubset(
                initial_failures), initial["reviewer"]

    brief = json.loads((root / "drafter/brief.json").read_text())
    dump(root / "drafter/plan.json", {
        "audienceAssumption": "No prior programming knowledge is assumed.",
        "tooling": "external", "teachingOrder": brief["requiredConcepts"],
        "acceptance": brief["acceptance"],
        "verification": ["python3 main.py", "python3 -m pytest -q"],
    })
    concepts = ["variables", "conditions", "loops", "functions", "classes",
                "dictionaries", "json-files", "game-loop"]
    scenarios = ["launch-window", "move-player", "save-reload"]
    lessons = []
    for index, concept in enumerate(concepts):
        lessons.append({"id": f"l{index + 1}", "teaches": [concept],
                        "uses": concepts[:index],
                        "scenarios": [scenarios[index]] if index < len(scenarios) else [],
                        "why": "This introduces one concrete building block before later code depends on it.",
                        "observable": "The learner can run a visible, inspectable behavior."})
    dump(root / "writer/arc.json", {"lessons": lessons})
    (root / "sections/game.py").write_text('''import os
SCENARIOS = ("launch-window", "inventory-opens")
def visible_columns(viewport_width, tile_size):
    return list(range(0, viewport_width // tile_size + 2))
def inventory_lines(items):
    return [f"{i}. {item}" for i, item in enumerate(items, 1)]
def acceptance():
    challenge = os.environ.get("ARCANUM_ACCEPTANCE_CHALLENGE")
    width = -32 if challenge == "launch-window" else 65
    items = [] if challenge == "inventory-opens" else ["key"]
    results = {"launch-window": len(visible_columns(width, 16)) > 0,
               "inventory-opens": inventory_lines(items) == ["1. key"]}
    return {"version": 1, "status": "PASS" if all(results.values()) else "FAIL",
            "scenarios": results}
''', encoding="utf-8")
    dump(root / "sections/lesson.json", {
        "integerDivision": "Floor division produces a whole tile count, which range requires; ordinary slash division produces a float even when the arithmetic looks exact.",
        "functionDefinition": "Python must execute a function definition before code can call that name, so define the inventory formatter before the frame path invokes it.",
        "negativeControls": "A trustworthy acceptance check changes one controlled input and derives failure from the same behavior instead of printing a prepared failure receipt.",
    })

    candidates = root / "reviewer/candidates"
    hollow = candidates / "hollow-crawl/authored"
    tilemap = hollow / "game/tilemap.py"
    tilemap.write_text(tilemap.read_text(encoding="utf-8")
                       .replace("start_col = max(0, camera.x // self.tile_size)",
                                "start_col = max(0, int(camera.x // self.tile_size))")
                       .replace("end_col = min(self.columns, (camera.x + camera.width) // self.tile_size + 1)",
                                "end_col = min(self.columns, int((camera.x + camera.width) // self.tile_size + 1))")
                       .replace("start_row = max(0, camera.y // self.tile_size)",
                                "start_row = max(0, int(camera.y // self.tile_size))")
                       .replace("end_row = min(self.rows, (camera.y + camera.height) // self.tile_size + 1)",
                                "end_row = min(self.rows, int((camera.y + camera.height) // self.tile_size + 1))"),
                       encoding="utf-8")
    hollow_main = hollow / "main.py"
    hollow_main.write_text(hollow_main.read_text(encoding="utf-8").replace(
        "from game.hud import Inventory", "from game.hud import Inventory, draw_inventory"),
        encoding="utf-8")
    (hollow / "game/acceptance.py").write_text('''import os

from .scenarios import inventory_scenario, launch_scenario, movement_scenario


def acceptance_report():
    challenge = os.environ.get("ARCANUM_ACCEPTANCE_CHALLENGE")
    results = {
        "launch": launch_scenario(rows=0 if challenge == "launch" else 30),
        "move-player": movement_scenario(
            target_x=0 if challenge == "move-player" else 180,
            target_y=0 if challenge == "move-player" else 140),
        "open-inventory": inventory_scenario(
            items=() if challenge == "open-inventory" else ("rusty key",)),
    }
    return {"version": 1, "status": "PASS" if all(results.values()) else "FAIL",
            "scenarios": results}
''', encoding="utf-8")

    ashen = candidates / "ashen-ledger/authored"
    manager = ashen / "game/save_manager.py"
    manager.write_text(manager.read_text(encoding="utf-8")
                       + '        self.inventory.equipped = dict(data["equipped"])\n',
                       encoding="utf-8")
    correct_save_acceptance = '''import json
import os

from .inventory import Inventory
from .save_manager import SaveManager


def acceptance_report():
    original = Inventory()
    original.add("rusty-sword", 1)
    original.equip("rusty-sword")
    payload = SaveManager(original).dump()
    if os.environ.get("ARCANUM_ACCEPTANCE_CHALLENGE") == "save-reload":
        damaged = json.loads(payload)
        damaged["equipped"]["weapon"] = None
        payload = json.dumps(damaged)
    restored = Inventory()
    SaveManager(restored).load(payload)
    results = {"save-reload": restored.snapshot() == original.snapshot()}
    return {"version": 1, "status": "PASS" if all(results.values()) else "FAIL",
            "scenarios": results}
'''
    (ashen / "game/acceptance.py").write_text(correct_save_acceptance, encoding="utf-8")

    hollow_rows = command_rows(HOLLOW_COMMANDS, (
        "Replay rebuilt the learner project from authored files.",
        "Two protected unit tests ran and passed OK.",
        "Public scenario acceptance derived PASS.",
        "Changed launch input derived FAIL only for launch.",
        "Changed movement input derived FAIL only for move-player.",
        "Changed inventory input derived FAIL only for open-inventory.",
        "Ordinary launch rendered nonempty tiles and the inventory overlay.",
    ))
    save_rows = command_rows(SAVE_COMMANDS, (
        "Replay rebuilt the learner project from authored files.",
        "One protected unit test ran and passed OK.",
        "Save and load behavior derived acceptance PASS.",
        "Corrupted serialized input derived challenge FAIL.",
        "Ordinary round trip preserved quantities and equipped weapon.",
    ))
    dump(root / "reviewer/findings.json", {
        "version": 3,
        "candidates": [
            {"id": "hollow-crawl", "outcome": "REPAIRED", "commandsRun": hollow_rows,
             "repairs": [
                 {"id": "integer-visible-bounds", "file": "authored/game/tilemap.py",
                  "line": line_of(tilemap, "start_col ="),
                  "evidence": "Converted float camera-derived range bounds to int so the ordinary frame renders."},
                 {"id": "import-inventory-drawer", "file": "authored/main.py",
                  "line": line_of(hollow_main, "draw_inventory"),
                  "evidence": "Imported draw_inventory so the public frame path no longer raises NameError."},
                 {"id": "derive-acceptance-scenarios", "file": "authored/game/acceptance.py",
                  "line": line_of(hollow / "game/acceptance.py", "def acceptance_report"),
                  "evidence": "Removed the hardcoded literal receipt; public scenario calls now exercise behavior and each challenge changes input to derive failure."},
             ]},
            {"id": "ashen-ledger", "outcome": "REPAIRED", "commandsRun": save_rows,
             "repairs": [
                 {"id": "restore-equipped-state", "file": "authored/game/save_manager.py",
                  "line": line_of(manager, "self.inventory.equipped"),
                  "evidence": "Added missing equipped restoration during load so the round trip now preserves the weapon."},
                 {"id": "remove-positive-state-forgery", "file": "authored/game/acceptance.py",
                  "line": line_of(ashen / "game/acceptance.py", "SaveManager(restored).load"),
                  "evidence": "Removed the manual equipped assignment; acceptance now derives restored equipment through load."},
                 {"id": "derive-negative-control", "file": "authored/game/acceptance.py",
                  "line": line_of(ashen / "game/acceptance.py", "damaged ="),
                  "evidence": "The negative challenge now corrupts serialized payload input and derives FAIL through save/load instead of forcing False."},
             ]},
            {"id": "lantern-archive", "outcome": "CLEAN", "commandsRun": save_rows,
             "repairs": []},
        ],
    })
    final = grade_workspace(root, ROLE_ORDER, baseline)
    assert all(item["passed"] for item in final.values()), final
    reference = json.loads((root / "reviewer/findings.json").read_text())

    noisy = json.loads(json.dumps(reference))
    noisy["candidates"][2]["outcome"] = "REPAIRED"
    noisy["candidates"][2]["repairs"].append({
        "id": "invented-clean-fix", "file": "authored/main.py", "line": 1,
        "evidence": "Invented a repair against a project whose behavior was already clean."})
    dump(root / "reviewer/findings.json", noisy)
    noisy_grade = grade_workspace(root, ("reviewer",), baseline)["reviewer"]
    assert not noisy_grade["passed"]
    assert "clean-control report precision" in noisy_grade["criticalFailures"]

    # A receipt that still forces the negative outcome can make every visible
    # command green; the hidden production gate must nevertheless reject it.
    (ashen / "game/acceptance.py").write_text('''import os
from .inventory import Inventory
from .save_manager import SaveManager
def acceptance_report():
    original = Inventory(); original.add("rusty-sword", 1); original.equip("rusty-sword")
    restored = Inventory(); SaveManager(restored).load(SaveManager(original).dump())
    results = {"save-reload": restored.snapshot() == original.snapshot()}
    if os.environ.get("ARCANUM_ACCEPTANCE_CHALLENGE") == "save-reload":
        results["save-reload"] = False
    return {"version": 1, "status": "PASS" if all(results.values()) else "FAIL", "scenarios": results}
''', encoding="utf-8")
    dump(root / "reviewer/findings.json", reference)
    fake_grade = grade_workspace(root, ("reviewer",), baseline)["reviewer"]
    assert not fake_grade["passed"], fake_grade
    assert "ashen acceptance anti-counterfeit" in fake_grade["criticalFailures"]

print("model role trial scorer: OK (repair/replay red, complete green, counterfeit red)")
