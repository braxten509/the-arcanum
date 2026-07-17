import pygame


class TileMap:
    def __init__(self, rows, cols, tile_size=32):
        self.tile_size = tile_size
        self.rows = rows
        self.cols = cols
        self.width = cols * tile_size
        self.height = rows * tile_size
        self.data = []
        for r in range(rows):
            row = []
            for c in range(cols):
                if r == 0 or r == rows - 1 or c == 0 or c == cols - 1:
                    row.append(1)
                else:
                    row.append(0)
            self.data.append(row)

        self.rooms = {}
        self.current_room = "main"

    def is_solid(self, tile_id):
        return tile_id == 1

    def tile_at_pixel(self, x, y):
        col = x // self.tile_size
        row = y // self.tile_size
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return self.data[row][col]
        return 1

    def check_collision(self, rect):
        corners = [
            (rect.left, rect.top),
            (rect.right, rect.top),
            (rect.left, rect.bottom),
            (rect.right, rect.bottom),
        ]
        for cx, cy in corners:
            tile_id = self.tile_at_pixel(cx, cy)
            if self.is_solid(tile_id):
                return True
        return False

    def add_room(self, name, grid):
        self.rooms[name] = grid

    def load_room(self, name):
        if name in self.rooms:
            self.current_room = name
            self.data = self.rooms[name]
            self.rows = len(self.data)
            self.cols = len(self.data[0])
            self.width = self.cols * self.tile_size
            self.height = self.rows * self.tile_size
            return True
        return False

    def tile_is_transition(self, tile_id):
        return tile_id == 3

    def draw(self, screen, camera):
        start_col = max(0, camera.x // self.tile_size)
        end_col = min(self.cols, (camera.x + camera.width) // self.tile_size + 1)
        start_row = max(0, camera.y // self.tile_size)
        end_row = min(self.rows, (camera.y + camera.height) // self.tile_size + 1)

        tile_colors = {
            0: (40, 35, 30),
            1: (80, 70, 60),
        }

        for row in range(start_row, end_row):
            for col in range(start_col, end_col):
                tile_id = self.data[row][col]
                color = tile_colors.get(tile_id, (255, 0, 255))
                x = col * self.tile_size - camera.x
                y = row * self.tile_size - camera.y
                pygame.draw.rect(screen, color, (x, y, self.tile_size, self.tile_size))
