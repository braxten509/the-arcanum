import pygame


ITEM_DB = {
    "health_potion": {
        "id": "health_potion",
        "name": "Health Potion",
        "type": "consumable",
        "description": "Restores 25 HP.",
        "stats": {"hp_restore": 25},
        "max_stack": 10,
    },
    "rusty_sword": {
        "id": "rusty_sword",
        "name": "Rusty Sword",
        "type": "weapon",
        "description": "A worn blade. +5 attack.",
        "stats": {"attack": 5},
        "max_stack": 1,
    },
    "mana_potion": {
        "id": "mana_potion",
        "name": "Mana Potion",
        "type": "consumable",
        "description": "Restores 15 MP.",
        "stats": {"mp_restore": 15},
        "max_stack": 5,
    },
    "steel_sword": {
        "id": "steel_sword",
        "name": "Steel Sword",
        "type": "weapon",
        "description": "A well-forged blade. +8 attack.",
        "stats": {"attack": 8},
        "max_stack": 1,
    },
    "leather_armor": {
        "id": "leather_armor",
        "name": "Leather Armor",
        "type": "armor",
        "description": "Cured hide. +3 defense.",
        "stats": {"defense": 3},
        "max_stack": 1,
    },
}


class Inventory:
    def __init__(self, max_capacity=20):
        self.slots = []
        self.max_capacity = max_capacity
        self.equipped = {"weapon": None, "armor": None}

    def add_item(self, item_id, quantity=1):
        item = ITEM_DB[item_id]
        if item["max_stack"] > 1:
            for slot in self.slots:
                if slot["item_id"] == item_id:
                    slot["quantity"] += quantity
                    return True
        if len(self.slots) >= self.max_capacity:
            return False
        self.slots.append({"item_id": item_id, "quantity": quantity})
        return True

    def remove_item(self, slot_index, quantity=1):
        if slot_index >= len(self.slots):
            return False
        slot = self.slots[slot_index]
        slot["quantity"] -= quantity
        if slot["quantity"] <= 0:
            self.slots.pop(slot_index)
        return True

    def use_item(self, slot_index, player):
        if slot_index >= len(self.slots):
            return
        slot = self.slots[slot_index]
        item = ITEM_DB[slot["item_id"]]
        if item["type"] == "consumable":
            if "hp_restore" in item["stats"]:
                player.hp = min(player.max_hp, player.hp + item["stats"]["hp_restore"])
            self.remove_item(slot_index, 1)

    def equip(self, slot_index):
        if slot_index >= len(self.slots):
            return False
        slot = self.slots[slot_index]
        item = ITEM_DB[slot["item_id"]]
        if item["type"] not in ("weapon", "armor"):
            return False
        equip_slot = item["type"]
        old_id = self.equipped[equip_slot]
        self.equipped[equip_slot] = slot["item_id"]
        self.slots.pop(slot_index)
        if old_id:
            self.add_item(old_id, 1)
        return True

    def unequip(self, slot_name):
        if self.equipped[slot_name] is None:
            return
        if len(self.slots) >= self.max_capacity:
            return False
        self.add_item(self.equipped[slot_name], 1)
        self.equipped[slot_name] = None
        return True

    def get_stat_bonuses(self):
        bonuses = {"attack": 0, "defense": 0}
        for item_id in self.equipped.values():
            if item_id is None:
                continue
            item = ITEM_DB[item_id]
            for stat, value in item["stats"].items():
                if stat in bonuses:
                    bonuses[stat] += value
        return bonuses


def draw_inventory(screen, font, inventory, selected_index, show):
    if not show:
        return
    overlay = pygame.Surface((screen.get_width(), screen.get_height()))
    overlay.set_alpha(200)
    overlay.fill((20, 20, 30))
    screen.blit(overlay, (0, 0))
    title = font.render("INVENTORY", True, (220, 180, 80))
    screen.blit(title, (40, 20))
    eq_y = 60
    for slot_name in ("weapon", "armor"):
        item_id = inventory.equipped[slot_name]
        name = ITEM_DB[item_id]["name"] if item_id else "Empty"
        label = f"{slot_name.capitalize()}: {name}"
        surf = font.render(label, True, (180, 180, 180))
        screen.blit(surf, (40, eq_y))
        eq_y += 24
    inv_y = eq_y + 16
    for i, slot in enumerate(inventory.slots):
        item = ITEM_DB[slot["item_id"]]
        color = (240, 220, 100) if i == selected_index else (200, 200, 200)
        text = f"{item['name']} x{slot['quantity']}"
        surf = font.render(text, True, color)
        screen.blit(surf, (40, inv_y))
        inv_y += 24