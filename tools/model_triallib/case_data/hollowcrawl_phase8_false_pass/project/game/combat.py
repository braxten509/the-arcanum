import pygame
from game.settings import PLAYER_ATTACK_COOLDOWN


class CombatManager:
    def __init__(self, player, enemies):
        self.player = player
        self.enemies = enemies

    def update(self, dt, keys_just_pressed):
        if pygame.K_SPACE in keys_just_pressed and self.player.attack_cooldown <= 0:
            self.player.attack_cooldown = PLAYER_ATTACK_COOLDOWN
            for enemy in self.enemies:
                if enemy.hp <= 0:
                    continue
                dist = self._distance(self.player, enemy)
                if dist <= enemy.attack_range + 16:
                    damage = max(1, self.player.attack - enemy.defense)
                    enemy.hp -= damage

        for enemy in self.enemies:
            if enemy.hp <= 0:
                continue
            dist = self._distance(self.player, enemy)
            if dist <= enemy.attack_range and enemy.attack_cooldown <= 0:
                enemy.attack_cooldown = 1.0
                damage = max(1, enemy.attack - self.player.defense)
                self.player.hp -= damage

        self.enemies[:] = [e for e in self.enemies if e.hp > 0]

    def _distance(self, a, b):
        ax, ay = a.center()
        bx, by = b.center()
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
