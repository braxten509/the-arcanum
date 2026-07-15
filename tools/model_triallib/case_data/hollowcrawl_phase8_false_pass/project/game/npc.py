import pygame
from game.entity import Entity


class NPC(Entity):
    def __init__(self, x, y, name, dialog_tree):
        super().__init__(x, y, 32, 32, 0)
        self.name = name
        self.dialog_tree = dialog_tree
        self.interaction_range = 48
        self.talked_to = False
        self._current_node = None

    def start_dialog(self):
        self._current_node = "start"
        self.talked_to = True

    def current_dialog(self):
        if self._current_node is None:
            return None
        return self.dialog_tree.get(self._current_node)

    def advance_dialog(self, choice=None):
        node = self.dialog_tree.get(self._current_node)
        if node is None:
            self._current_node = None
            return
        if choice is not None and "choices" in node and choice < len(node["choices"]):
            selected = node["choices"][choice]
            if "end" in selected:
                self._current_node = None
            elif "next" in selected:
                self._current_node = selected["next"]
        elif "next" in node:
            self._current_node = node["next"]
        elif "end" in node:
            self._current_node = None

    def draw(self, screen, camera):
        if self.talked_to:
            color = (140, 200, 140)
        else:
            color = (100, 140, 200)
        screen_x = int(self.x - camera.x)
        screen_y = int(self.y - camera.y)
        pygame.draw.rect(screen, (100, 140, 200),
                         (screen_x, screen_y, self.width, self.height))
