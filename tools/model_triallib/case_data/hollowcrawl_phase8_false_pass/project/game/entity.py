import pygame


class Entity:
    def __init__(self, x, y, width, height, speed):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.speed = speed
        self.moving = False
        self.direction = "down"

    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)

    def colliderect(self, other):
        return self.rect().colliderect(other.rect())

    def center(self):
        return (self.x + self.width / 2, self.y + self.height / 2)
