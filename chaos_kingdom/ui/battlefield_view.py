from __future__ import annotations

from collections import OrderedDict
import math
import pygame

from chaos_kingdom.core.battlefields import TILES
from .theme import GOLD, RED, TEAL, TEXT
from .assets import terrain_tile, structure_sprite


class IsometricProjection:
    """One reversible 2:1 projection for drawing, orders and map editing.

    There is no height coordinate. Architecture may be tall; the ground is flat.
    """

    def __init__(self, rect, width=32, height=20):
        self.rect = pygame.Rect(rect)
        self.width, self.height = width, height
        self.tile_width = min((self.rect.w - 32) * 2 / (width + height),
                              (self.rect.h - 56) * 4 / (width + height))
        self.tile_height = self.tile_width / 2
        self.ground_size = (round((width + height) * self.tile_width / 2),
                            round((width + height) * self.tile_height / 2))
        self.left = self.rect.centerx - self.ground_size[0] / 2
        self.top = self.rect.y + 44 + (self.rect.h - 56 - self.ground_size[1]) / 2
        self.origin = (self.left + height * self.tile_width / 2, self.top)

    def cell_point(self, x, y):
        return (round(self.origin[0] + (x - y) * self.tile_width / 2),
                round(self.origin[1] + (x + y) * self.tile_height / 2))

    def world_point(self, x, y):
        return self.cell_point(x * self.width / 100, y * self.height / 60)

    def coordinates(self, point):
        dx = (point[0] - self.origin[0]) / (self.tile_width / 2)
        dy = (point[1] - self.origin[1]) / (self.tile_height / 2)
        x, y = (dx + dy) / 2, (dy - dx) / 2
        return (x, y) if 0 <= x < self.width and 0 <= y < self.height else None

    def world_at(self, point):
        cell = self.coordinates(point)
        return (cell[0] * 100 / self.width, cell[1] * 60 / self.height) if cell else None

    def cell_at(self, point):
        cell = self.coordinates(point)
        return (math.floor(cell[0]), math.floor(cell[1])) if cell else None


class BattlefieldRenderer:
    """Continuous flat materials; movement and cover rules remain in the model."""

    def __init__(self, capacity=12):
        self.capacity = capacity
        self._cache = OrderedDict()
        self._iso_cache = OrderedDict()

    def _material(self, tile, size):
        layer = pygame.Surface(size, pygame.SRCALPHA)
        layer.fill(TILES[tile][1] if tile in TILES else (164, 150, 118))
        # Repeat over world coordinates, not separately inside each gameplay cell.
        texture = terrain_tile(tile, (144, 144))
        if texture is not None:
            for y in range(0, size[1], 144):
                for x in range(0, size[0], 144):
                    layer.blit(texture, (x, y))
        return layer

    def _coverage(self, rows, group):
        width, height, scale = len(rows[0]), len(rows), 8
        mask = pygame.Surface((width * scale, height * scale), pygame.SRCALPHA)
        mask.fill((255, 255, 255, 0))
        white = (255, 255, 255, 255)
        def matching(x, y):
            return not (0 <= x < width and 0 <= y < height) or rows[y][x] in group
        for y, row in enumerate(rows):
            for x, tile in enumerate(row):
                if tile not in group:
                    continue
                cell = pygame.Rect(x * scale, y * scale, scale, scale)
                radius = 2 if group == {"w", "b"} else 3
                pygame.draw.rect(mask, white, cell, border_radius=radius)
                for dx, dy, edge in ((0, -1, (cell.x, cell.y, scale, radius)),
                                     (0, 1, (cell.x, cell.bottom - radius, scale, radius)),
                                     (-1, 0, (cell.x, cell.y, radius, scale)),
                                     (1, 0, (cell.right - radius, cell.y, radius, scale))):
                    if matching(x + dx, y + dy):
                        pygame.draw.rect(mask, white, edge)
        if group in ({"b"}, {"#"}):
            return mask
        # Filter the shared coverage as a whole so corners blend into a contour.
        # Only the drawing mask is softened; gameplay still uses exact cells.
        return pygame.transform.smoothscale(
            pygame.transform.smoothscale(mask, (width * 2, height * 2)), mask.get_size())

    def _composite(self, output, tile, mask):
        layer = self._material(tile, output.get_size())
        layer.blit(pygame.transform.smoothscale(mask, output.get_size()), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        output.blit(layer, (0, 0))

    def _surface(self, battlefield, size):
        key = tuple(battlefield.tiles), tuple(size)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        rows = key[0]
        output = self._material(".", size)
        for tile in ("h", "f", "r"):
            self._composite(output, tile, self._coverage(rows, {tile, "g"} if tile == "r" else {tile}))
        water = self._coverage(rows, {"w", "b"})
        # Pebble banks follow the river beneath bridges; they add no height rules.
        bank = pygame.Surface(water.get_size(), pygame.SRCALPHA)
        bank.fill((255, 255, 255, 0))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                bank.blit(water, (dx, dy), special_flags=pygame.BLEND_RGBA_MAX)
        self._composite(output, "shore", bank)
        self._composite(output, "w", water)
        for tile in ("b", "#"):
            self._composite(output, tile, self._coverage(rows, {tile}))
        self._cache[key] = output
        while len(self._cache) > self.capacity:
            self._cache.popitem(last=False)
        return output

    def draw(self, surface, battlefield, rect):
        projection = IsometricProjection(rect, battlefield.width, battlefield.height)
        key = tuple(battlefield.tiles), projection.ground_size
        if key not in self._iso_cache:
            flat = self._surface(battlefield, (1024, 640))
            diamond = pygame.transform.rotate(flat, -45)
            self._iso_cache[key] = pygame.transform.smoothscale(diamond, projection.ground_size)
            while len(self._iso_cache) > self.capacity:
                self._iso_cache.popitem(last=False)
        self._iso_cache.move_to_end(key)
        surface.fill((29, 39, 35), rect)
        surface.blit(self._iso_cache[key], (round(projection.left), round(projection.top)))
        return projection

    def structures(self, surface, battlefield, projection):
        def neighbor(x, y, tile):
            return 0 <= x < battlefield.width and 0 <= y < battlefield.height and battlefield.tiles[y][x] == tile
        objects = []
        for y, row in enumerate(battlefield.tiles):
            for x, tile in enumerate(row):
                if tile not in "#bg":
                    continue
                along_x = neighbor(x - 1, y, tile) or neighbor(x + 1, y, tile)
                along_y = neighbor(x, y - 1, tile) or neighbor(x, y + 1, tile)
                if tile == "#":
                    name = "tower" if along_x and along_y else "wall_x" if along_x else "wall_y"
                    if name == "tower" and x == battlefield.width - 1 and y == battlefield.height - 2:
                        name = "keep"
                elif tile == "g":
                    name = "gate_x" if neighbor(x - 1, y, "#") or neighbor(x + 1, y, "#") else "gate_y"
                else:
                    name = "bridge_x" if along_x or neighbor(x - 1, y, "r") or neighbor(x + 1, y, "r") else "bridge_y"
                objects.append((x + y, x, y, name))
        return objects

    def draw_structure(self, surface, projection, item):
        _, x, y, name = item
        sprite = structure_sprite(name, round(projection.tile_width * (1.6 if name == "keep" else 1.18)))
        if sprite:
            point = projection.cell_point(x + .5, y + .5)
            surface.blit(sprite, (point[0] - sprite.get_width() // 2,
                                  point[1] - sprite.get_height() + round(projection.tile_height * .5)))


_renderer = BattlefieldRenderer()


def draw_field(painter, battlefield, rect, *, grid=False, deployment=False, structures=True):
    rect = pygame.Rect(rect)
    surface = painter.surface
    projection = _renderer.draw(surface, battlefield, rect)
    if grid:
        for x in range(battlefield.width + 1):
            pygame.draw.line(surface, (65, 73, 57), projection.cell_point(x, 0), projection.cell_point(x, battlefield.height))
        for y in range(battlefield.height + 1):
            pygame.draw.line(surface, (65, 73, 57), projection.cell_point(0, y), projection.cell_point(battlefield.width, y))
    if structures:
        for item in sorted(_renderer.structures(surface, battlefield, projection)):
            _renderer.draw_structure(surface, projection, item)
    if deployment:
        for side, cells in enumerate(battlefield.spawns):
            for i, (x, y) in enumerate(cells):
                cx, cy = projection.cell_point(x + .5, y + .5)
                pygame.draw.circle(surface, TEAL if side == 0 else RED, (int(cx), int(cy)), 12)
                painter.text(str(i + 1), cx, cy - 9, 15, TEXT, True, align="center")
    x, y = battlefield.objective
    cx, cy = projection.cell_point(x + .5, y + .5)
    pygame.draw.circle(surface, GOLD, (cx, cy), 17, 2)
    pygame.draw.line(surface, GOLD, (cx, cy - 11), (cx, cy + 11), 2)
    pygame.draw.polygon(surface, GOLD, [(cx, cy - 11), (cx + 10, cy - 8), (cx, cy - 3)])
    return projection


def structure_items(battlefield, projection):
    return _renderer.structures(None, battlefield, projection)


def draw_structure(surface, projection, item):
    _renderer.draw_structure(surface, projection, item)
