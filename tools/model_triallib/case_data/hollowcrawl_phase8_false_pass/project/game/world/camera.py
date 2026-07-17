class Camera:
    def __init__(self, width, height, world_width, world_height):
        self.x = 0
        self.y = 0
        self.width = width
        self.height = height
        self.world_width = world_width
        self.world_height = world_height

    def follow(self, target):
        self.x = target.x + target.width // 2 - self.width // 2
        self.y = target.y + target.height // 2 - self.height // 2
        self.x = max(0, min(self.x, self.world_width - self.width))
        self.y = max(0, min(self.y, self.world_height - self.height))

    def apply(self, world_x, world_y):
        return (world_x - self.x, world_y - self.y)
