import json


class SaveManager:
    def __init__(self, player, inventory, npcs, enemies):
        self.player = player
        self.inventory = inventory
        self.npcs = npcs
        self.enemies = enemies
        self.quest_complete = False

    def save(self, path):
        state = {
            "version": 1,
            "player": {
                "x": self.player.x,
                "y": self.player.y,
                "hp": self.player.hp,
                "direction": self.player.direction,
            },
            "inventory": {
                "slots": self.inventory.slots,
                "equipped": self.inventory.equipped,
            },
            "npcs": [],
            "quest_complete": self.quest_complete,
            "enemies": [],
        }
        for npc in self.npcs:
            state["npcs"].append({
                "name": npc.name,
                "talked_to": npc.talked_to,
                "quest_given": getattr(npc, "quest_given", False),
            })
        for enemy in self.enemies:
            state["enemies"].append({
                "x": enemy.x,
                "y": enemy.y,
                "hp": enemy.hp,
                "max_hp": enemy.max_hp,
                "defeated": enemy.hp <= 0,
            })
        try:
            with open(path, "w") as f:
                json.dump(state, f, indent=2)
        except OSError:
            print("Could not write save file.")
            return False
        return True

    def load(self, path):
        try:
            with open(path, "r") as f:
                state = json.load(f)
        except FileNotFoundError:
            print("No save file found.")
            return False
        except json.JSONDecodeError:
            print("Save file is corrupted.")
            return False
        if state.get("version") != 1:
            return False
        pd = state["player"]
        self.player.x = pd["x"]
        self.player.y = pd["y"]
        self.player.hp = pd["hp"]
        self.player.direction = pd.get("direction", "down")
        self.quest_complete = state.get("quest_complete", False)
        inv = state["inventory"]
        self.inventory.slots = inv.get("slots", [])
        self.inventory.equipped = inv.get("equipped", {"weapon": None, "armor": None})
        for npc_data in state.get("npcs", []):
            for npc in self.npcs:
                if npc.name == npc_data["name"]:
                    npc.talked_to = npc_data.get("talked_to", False)
                    if "quest_given" in npc_data:
                        npc.quest_given = npc_data["quest_given"]
        saved_enemy_ids = set()
        for ed in state.get("enemies", []):
            if not ed.get("defeated", False):
                for enemy in self.enemies:
                    if abs(enemy.x - ed["x"]) < 1 and abs(enemy.y - ed["y"]) < 1:
                        enemy.hp = ed.get("hp", enemy.max_hp)
                        saved_enemy_ids.add(id(enemy))
                        break
        for enemy in self.enemies:
            if enemy.hp <= 0:
                continue
            if id(enemy) not in saved_enemy_ids:
                enemy.hp = 0
        return True
