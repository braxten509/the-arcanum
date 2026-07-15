import pygame
from game.entity import Entity


class Enemy(Entity):
    def __init__(self, x, y, hp, attack, defense, speed, patrol_path):
        super().__init__(x, y, 32, 32, speed)
        self.hp = hp
        self.max_hp = hp
        self.attack = attack
        self.defense = defense
        self.patrol_path = patrol_path
        self.patrol_index = 0
        self.state = "patrol"
        self.aggro_range = 150
        self.attack_cooldown = 0.0
        self.attack_range = 40

    def update(self, dt, player, tilemap):
        if self.attack_cooldown > 0:
            self.attack_cooldown = max(0, self.attack_cooldown - dt)
        if self.hp <= 0:
            return

        px, py = player.center()
        ex, ey = self.center()
        dist = ((px - ex) ** 2 + (py - ey) ** 2) ** 0.5
        self.state = "chase" if dist <= self.aggro_range else "patrol"

        if self.state == "patrol":
            target = self.patrol_path[self.patrol_index]
            tx, ty = target
            if ((self.x - tx) ** 2 + (self.y - ty) ** 2) ** 0.5 < 4:
                self.patrol_index = (self.patrol_index + 1) % len(self.patrol_path)
        else:
            target = (px, py)

        dx = target[0] - self.x
        dy = target[1] - self.y
        length = max(0.001, (dx ** 2 + dy ** 2) ** 0.5)
        dx = dx / length * self.speed * dt
        dy = dy / length * self.speed * dt

        self.x += dx
        if tilemap.check_collision(self.rect()):
            self.x -= dx
        self.y += dy
        if tilemap.check_collision(self.rect()):
            self.y -= dy

    def draw(self, screen, camera):
        if self.hp <= 0:
            return
        screen_x = int(self.x - camera.x)
        screen_y = int(self.y - camera.y)
        pygame.draw.rect(screen, (200, 80, 60),
                         (screen_x, screen_y, self.width, self.height))
        bar_w = 24
        bar_h = 4
        bar_x = screen_x + (self.width - bar_w) // 2
        bar_y = screen_y - 6
        ratio = self.hp / self.max_hp
        if ratio > 0.5:
            bar_color = (60, 200, 80)
        elif ratio > 0.25:
            bar_color = (200, 200, 60)
        else:
            bar_color = (200, 60, 60)
        pygame.draw.rect(screen, (40, 40, 40), (bar_x - 1, bar_y - 1, bar_w + 2, bar_h + 2))
        pygame.draw.rect(screen, bar_color, (bar_x, bar_y, int(bar_w * ratio), bar_h))
        if self.hp <= 0:
            return
        screen_x = int(self.x - camera.x)
        screen_y = int(self.y - camera.y)
        pygame.draw.rect(screen, (200, 80, 60),
                         (screen_x, screen_y, self.width, self.height))
