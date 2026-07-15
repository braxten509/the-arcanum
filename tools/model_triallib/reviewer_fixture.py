"""Production-shaped repair/replay fixture for the independent Reviewer hand."""
import hashlib
import json
import shutil
from pathlib import Path


CANDIDATE_IDS = ("hollow-crawl", "ashen-ledger", "lantern-archive")
HOLLOW_COMMANDS = (
    "python3 replay.py",
    "PYTHONPATH=learner-project python3 -m unittest discover -s tests -q",
    "python3 learner-project/main.py --acceptance",
    "ARCANUM_ACCEPTANCE_CHALLENGE=launch python3 learner-project/main.py --acceptance",
    "ARCANUM_ACCEPTANCE_CHALLENGE=move-player python3 learner-project/main.py --acceptance",
    "ARCANUM_ACCEPTANCE_CHALLENGE=open-inventory python3 learner-project/main.py --acceptance",
    "python3 learner-project/main.py",
)
SAVE_COMMANDS = (
    "python3 replay.py",
    "PYTHONPATH=learner-project python3 -m unittest discover -s tests -q",
    "python3 learner-project/main.py --acceptance",
    "ARCANUM_ACCEPTANCE_CHALLENGE=save-reload python3 learner-project/main.py --acceptance",
    "python3 learner-project/main.py",
)
EDITABLE = {
    "hollow-crawl": {
        "authored/game/tilemap.py", "authored/game/acceptance.py", "authored/main.py"},
    "ashen-ledger": {
        "authored/game/save_manager.py", "authored/game/acceptance.py"},
    "lantern-archive": set(),
}


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(path, value):
    _write(path, json.dumps(value, indent=2) + "\n")


def _evidence(path, candidate, rows):
    _json(path, {
        "version": 3,
        "candidate": candidate,
        "fingerprint": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
        "summary": "PASS",
        "rows": [{"id": row, "status": "PASS", "exitCode": 0,
                  "output": "verified"} for row in rows],
    })


def _replay_script(root):
    _write(root / "replay.py", '''from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
target = ROOT / "learner-project"
if target.exists():
    shutil.rmtree(target)
shutil.copytree(ROOT / "authored", target)
print("REPLAY OK")
''')


def _materialize(root):
    target = root / "learner-project"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(root / "authored", target)


def _candidate(root, candidate, promise, commands, rows):
    _json(root / "review-contract.json", {
        "id": candidate,
        "promise": promise,
        "sourceOfTruth": "authored",
        "derivedProject": "learner-project",
        "commands": list(commands),
        "repairRule": "Repair authored causes, run replay.py, then rerun every command. Never edit replay.py, tests, prior evidence, or learner-project directly.",
    })
    _evidence(root / "review-evidence.json", candidate, rows)
    _replay_script(root)


def _hollow(root):
    _candidate(
        root, "hollow-crawl",
        "After replay, cold launch must render a nonempty dungeon frame and inventory overlay. Acceptance must derive launch, movement, and inventory results from game.scenarios; each challenge must alter its input and derive only that scenario as false.",
        HOLLOW_COMMANDS,
        [f"checkpoint:s{section:02d}/proof:s{proof:02d}"
         for section in range(1, 9) for proof in range(1, section + 1)]
        + ["acceptance:launch", "acceptance:movement", "acceptance:inventory",
           "delivery:ordinary-launch"],
    )
    authored = root / "authored"
    _write(authored / "game/__init__.py", "")
    _write(authored / "game/camera.py", '''class Camera:
    def __init__(self, width, height, world_width, world_height):
        self.width = width
        self.height = height
        self.world_width = world_width
        self.world_height = world_height
        self.x = 0.0
        self.y = 0.0

    def follow(self, target_x, target_y):
        self.x = max(0.0, min(float(target_x - self.width / 2),
                              float(self.world_width - self.width)))
        self.y = max(0.0, min(float(target_y - self.height / 2),
                              float(self.world_height - self.height)))
''')
    _write(authored / "game/tilemap.py", '''class TileMap:
    def __init__(self, rows, columns, tile_size):
        self.rows = rows
        self.columns = columns
        self.tile_size = tile_size
        self.data = [[1 if row in (0, rows - 1) or col in (0, columns - 1) else 0
                      for col in range(columns)] for row in range(rows)]

    @property
    def width(self):
        return self.columns * self.tile_size

    @property
    def height(self):
        return self.rows * self.tile_size

    def visible_cells(self, camera):
        start_col = max(0, camera.x // self.tile_size)
        end_col = min(self.columns, (camera.x + camera.width) // self.tile_size + 1)
        start_row = max(0, camera.y // self.tile_size)
        end_row = min(self.rows, (camera.y + camera.height) // self.tile_size + 1)
        cells = []
        for row in range(start_row, end_row):
            for column in range(start_col, end_col):
                cells.append((row, column, self.data[row][column]))
        return cells

    def draw(self, camera):
        return [f"{row}:{column}:{tile}" for row, column, tile
                in self.visible_cells(camera)]
''')
    _write(authored / "game/hud.py", '''class Inventory:
    def __init__(self):
        self.items = []

    def add(self, item):
        self.items.append(item)


def draw_inventory(inventory):
    return [f"{index}. {item}" for index, item in enumerate(inventory.items, 1)]
''')
    _write(authored / "game/scenarios.py", '''from .camera import Camera
from .hud import Inventory, draw_inventory
from .tilemap import TileMap


def launch_scenario(rows=30, columns=40):
    tilemap = TileMap(rows, columns, 16)
    camera = Camera(65, 49, tilemap.width, tilemap.height)
    camera.follow(180, 140)
    return len(tilemap.draw(camera)) > 0


def movement_scenario(target_x=180, target_y=140):
    camera = Camera(65, 49, 640, 480)
    before = (camera.x, camera.y)
    camera.follow(target_x, target_y)
    return (camera.x, camera.y) != before


def inventory_scenario(items=("rusty key",)):
    inventory = Inventory()
    for item in items:
        inventory.add(item)
    return draw_inventory(inventory) == ["1. rusty key"]
''')
    _write(authored / "game/acceptance.py", '''def acceptance_report():
    return {"version": 1, "status": "PASS", "scenarios": {
        "launch": True, "move-player": True, "open-inventory": True}}
''')
    _write(authored / "main.py", '''import json
import sys

from game.acceptance import acceptance_report
from game.camera import Camera
from game.hud import Inventory
from game.tilemap import TileMap


def run_frame():
    tilemap = TileMap(30, 40, 16)
    camera = Camera(65, 49, tilemap.width, tilemap.height)
    camera.follow(180, 140)
    inventory = Inventory()
    inventory.add("rusty key")
    print(json.dumps({"tiles": tilemap.draw(camera),
                      "inventory": draw_inventory(inventory)}, sort_keys=True))


if __name__ == "__main__":
    if "--acceptance" in sys.argv:
        print(json.dumps(acceptance_report(), sort_keys=True))
    else:
        run_frame()
''')
    _write(root / "tests/test_models.py", '''import unittest

from game.camera import Camera
from game.hud import Inventory


class ModelTests(unittest.TestCase):
    def test_camera_clamps(self):
        camera = Camera(65, 49, 640, 480)
        camera.follow(-100, -100)
        self.assertGreaterEqual(camera.x, 0)

    def test_inventory_adds(self):
        inventory = Inventory()
        inventory.add("key")
        self.assertEqual(inventory.items, ["key"])


if __name__ == "__main__":
    unittest.main()
''')
    _materialize(root)


def _save_case(root, candidate, correct):
    _candidate(
        root, candidate,
        "After replay, saving and loading must preserve item quantities and equipped weapon. The negative control must corrupt serialized input and derive failure through the same save/load behavior.",
        SAVE_COMMANDS,
        ["checkpoint:inventory", "checkpoint:equip", "checkpoint:save",
         "checkpoint:reload", "acceptance:save-reload", "negative:save-reload",
         "delivery:ordinary-launch"],
    )
    authored = root / "authored"
    _write(authored / "game/__init__.py", "")
    _write(authored / "game/inventory.py", '''class Inventory:
    def __init__(self):
        self.slots = []
        self.equipped = {"weapon": None}

    def add(self, item_id, quantity=1):
        self.slots.append({"item_id": item_id, "quantity": quantity})

    def equip(self, item_id):
        if any(slot["item_id"] == item_id for slot in self.slots):
            self.equipped["weapon"] = item_id

    def snapshot(self):
        return {"slots": [dict(slot) for slot in self.slots],
                "equipped": dict(self.equipped)}
''')
    equipment = ('        self.inventory.equipped = dict(data["equipped"])\n'
                 if correct else "")
    _write(authored / "game/save_manager.py", '''import json


class SaveManager:
    def __init__(self, inventory):
        self.inventory = inventory

    def dump(self):
        return json.dumps(self.inventory.snapshot(), sort_keys=True)

    def load(self, payload):
        data = json.loads(payload)
        self.inventory.slots = [dict(slot) for slot in data["slots"]]
''' + equipment)
    if correct:
        acceptance = '''import json
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
    else:
        acceptance = '''import os

from .inventory import Inventory
from .save_manager import SaveManager


def acceptance_report():
    original = Inventory()
    original.add("rusty-sword", 1)
    original.equip("rusty-sword")
    payload = SaveManager(original).dump()
    restored = Inventory()
    SaveManager(restored).load(payload)
    restored.equipped["weapon"] = "rusty-sword"
    results = {"save-reload": restored.snapshot() == original.snapshot()}
    if os.environ.get("ARCANUM_ACCEPTANCE_CHALLENGE") == "save-reload":
        results["save-reload"] = False
    return {"version": 1, "status": "PASS" if all(results.values()) else "FAIL",
            "scenarios": results}
'''
    _write(authored / "game/acceptance.py", acceptance)
    _write(authored / "main.py", '''import json
import sys

from game.acceptance import acceptance_report
from game.inventory import Inventory
from game.save_manager import SaveManager


def ordinary_demo():
    inventory = Inventory()
    inventory.add("rusty-sword", 2)
    inventory.equip("rusty-sword")
    payload = SaveManager(inventory).dump()
    restored = Inventory()
    SaveManager(restored).load(payload)
    print(json.dumps(restored.snapshot(), sort_keys=True))


if __name__ == "__main__":
    if "--acceptance" in sys.argv:
        print(json.dumps(acceptance_report(), sort_keys=True))
    else:
        ordinary_demo()
''')
    _write(root / "tests/test_storage.py", '''import unittest

from game.inventory import Inventory
from game.save_manager import SaveManager


class StorageTests(unittest.TestCase):
    def test_slots_round_trip(self):
        source = Inventory()
        source.add("rusty-sword", 2)
        payload = SaveManager(source).dump()
        restored = Inventory()
        SaveManager(restored).load(payload)
        self.assertEqual(restored.slots, source.slots)


if __name__ == "__main__":
    unittest.main()
''')
    _materialize(root)


def create_reviewer_fixture(root):
    """Create two authored-source repair targets and one clean precision control."""
    candidates = Path(root) / "reviewer/candidates"
    _hollow(candidates / "hollow-crawl")
    _save_case(candidates / "ashen-ledger", "ashen-ledger", correct=False)
    _save_case(candidates / "lantern-archive", "lantern-archive", correct=True)
    _json(Path(root) / "reviewer/findings.json", {
        "version": 3,
        "candidates": [{"id": candidate, "outcome": "UNREVIEWED",
                        "commandsRun": [], "repairs": []}
                       for candidate in CANDIDATE_IDS],
    })


def reviewer_protected_paths(root):
    """Everything except the five authored files a correct Reviewer must repair."""
    candidates = Path(root) / "reviewer/candidates"
    protected = []
    for candidate in CANDIDATE_IDS:
        candidate_root = candidates / candidate
        editable = EDITABLE[candidate]
        for path in candidate_root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(candidate_root).as_posix()
            if rel.startswith("learner-project/") or rel in editable:
                continue
            protected.append(path)
    return sorted(protected)
