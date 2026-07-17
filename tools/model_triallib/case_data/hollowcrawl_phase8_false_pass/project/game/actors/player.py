import pygame
from game.world.settings import SCREEN_WIDTH, SCREEN_HEIGHT, PLAYER_MAX_HP, PLAYER_ATTACK, PLAYER_DEFENSE, PLAYER_ATTACK_COOLDOWN
from game.actors.entity import Entity


class Player(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, 32, 32, 200)
        self.hp = PLAYER_MAX_HP
        self.attack = PLAYER_ATTACK
        self.defense = PLAYER_DEFENSE
        self.attack_cooldown = 0.0
        self.anim_timer = 0.0
        self.anim_frame = 0

    def update(self, dt, keys, world_width=None, world_height=None, tilemap=None):
        self.moving = False
        bw = world_width if world_width is not None else SCREEN_WIDTH
        bh = world_height if world_height is not None else SCREEN_HEIGHT

        dx = 0.0
        dy = 0.0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx -= self.speed * dt
            self.moving = True
            self.direction = "left"
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx += self.speed * dt
            self.moving = True
            self.direction = "right"
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            dy -= self.speed * dt
            self.moving = True
            self.direction = "up"
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            dy += self.speed * dt
            self.moving = True
            self.direction = "down"

        if tilemap is not None:
            self.x += dx
            if tilemap.check_collision(pygame.Rect(int(self.x), int(self.y), self.width, self.height)):
                self.x -= dx
            self.y += dy
            if tilemap.check_collision(pygame.Rect(int(self.x), int(self.y), self.width, self.height)):
                self.y -= dy
        else:
            self.x += dx
            self.y += dy

        self.x = max(0, min(self.x, bw - self.width))
        self.y = max(0, min(self.y, bh - self.height))

        if self.attack_cooldown > 0:
            self.attack_cooldown = max(0, self.attack_cooldown - dt)

        self.anim_timer += dt
        if self.anim_timer >= 0.15:
            self.anim_timer -= 0.15
            self.anim_frame = (self.anim_frame + 1) % 4

    def draw(self, screen, camera):
        direction_colors = {
            "right": [(200, 160, 120), (210, 170, 130), (200, 160, 120), (190, 150, 110)],
            "left": [(200, 160, 120), (190, 150, 110), (200, 160, 120), (210, 170, 130)],
            "up": [(180, 170, 160), (190, 180, 170), (180, 170, 160), (170, 160, 150)],
            "down": [(180, 170, 160), (170, 160, 150), (180, 170, 160), (190, 180, 170)],
        }
        if self.moving:
            color = direction_colors[self.direction][self.anim_frame]
        else:
            color = (200, 180, 140)
        if self.direction == "down":
            color = (200, 180, 140)
        screen_x = self.x - camera.x
        screen_y = self.y - camera.y
        pygame.draw.rect(screen, color, (int(screen_x), int(screen_y), self.width, self.height))
