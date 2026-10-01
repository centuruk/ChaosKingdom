from __future__ import annotations

import math
import random
import pygame

from chaos_kingdom.core.models import World
from .theme import GOLD, INK, LINE, TEAL, TEXT, Painter
from .assets import scaled_asset


LAND = [(6, 9), (18, 4), (33, 7), (50, 3), (66, 7), (82, 3), (101, 7), (109, 21), (104, 34),
        (109, 44), (102, 58), (106, 72), (87, 77), (66, 72), (52, 78), (36, 73), (20, 78), (6, 66), (3, 47), (7, 32), (2, 18)]


class MapView:
    def __init__(self):
        self.background = None
        self.key = None
        self.points: dict[str, tuple[int, int]] = {}

    def project(self, rect: pygame.Rect, x: float, y: float) -> tuple[int, int]:
        return int(rect.x + x / 112 * rect.w), int(rect.y + y / 82 * rect.h)

    def draw(self, painter: Painter, world: World, rect, selected: str | None = None,
             player_location: str | None = None, *, labels: bool = True):
        rect = pygame.Rect(rect)
        key = (world.seed, rect.size, tuple(s.faction for s in world.locations.values()))
        if key != self.key:
            self.key = key
            self.background = self._background(world, rect.size)
        painter.surface.blit(self.background, rect)
        self.points = {s.id: self.project(rect, s.x, s.y) for s in world.locations.values()}
        for loc in world.locations.values():
            a = self.points[loc.id]
            for neighbor in loc.neighbors:
                if neighbor < loc.id:
                    continue
                b = self.points[neighbor]
                color = (123, 118, 98) if not world.at_war(loc.faction, world.locations[neighbor].faction) else (170, 104, 80)
                pygame.draw.line(painter.surface, color, a, b, 1)
        for loc in world.locations.values():
            x, y = self.points[loc.id]
            color = world.factions[loc.faction].color if loc.faction else (160, 154, 137)
            if selected == loc.id:
                pygame.draw.circle(painter.surface, GOLD, (x, y), 17, 2)
            if player_location == loc.id:
                pygame.draw.circle(painter.surface, TEXT, (x, y), 21, 2)
                pygame.draw.polygon(painter.surface, TEXT, [(x, y - 29), (x - 5, y - 36), (x + 5, y - 36)])
            if loc.kind == "castle":
                pygame.draw.rect(painter.surface, INK, (x - 7, y - 7, 15, 15), border_radius=2)
                pygame.draw.rect(painter.surface, color, (x - 5, y - 5, 11, 11), border_radius=1)
                for offset in (-5, 0, 5):
                    pygame.draw.rect(painter.surface, color, (x + offset - 1, y - 10, 3, 5))
            else:
                pygame.draw.circle(painter.surface, INK, (x, y), 5)
                pygame.draw.circle(painter.surface, color, (x, y), 3)
            if labels:
                painter.text(loc.name, x, y + 12, 13 if loc.kind == "outpost" else 14, INK, loc.kind == "castle", width=78, align="center")
            hitbox = pygame.Rect(x - 22, y - 14, 44, 40)
            painter.buttons.append((hitbox, "location", loc.id, True))
        painter.compass(rect.right - 47, rect.bottom - 50, INK)

    def _background(self, world: World, size) -> pygame.Surface:
        surface = pygame.Surface(size)
        illustration = scaled_asset("world-map.png", size)
        if illustration is not None:
            surface.blit(illustration, (0, 0))
            ownership = pygame.Surface(size, pygame.SRCALPHA)
            for y in range(0, size[1], 12):
                for x in range(0, size[0], 12):
                    wx, wy = x / size[0] * 112, y / size[1] * 82
                    nearest = min(world.locations.values(), key=lambda s: (s.x - wx) ** 2 + (s.y - wy) ** 2)
                    color = world.factions[nearest.faction].color if nearest.faction else (160, 150, 130)
                    pygame.draw.rect(ownership, (*color, 32), (x, y, 12, 12))
            surface.blit(ownership, (0, 0))
            return surface
        surface.fill((38, 61, 63))
        rect = surface.get_rect()
        land = pygame.Surface(size, pygame.SRCALPHA)
        polygon = [self.project(rect, x, y) for x, y in LAND]
        pygame.draw.polygon(land, (191, 181, 147), polygon)
        # A low-resolution Voronoi tint shows ownership independently of location icons.
        for y in range(0, size[1], 9):
            for x in range(0, size[0], 9):
                if land.get_at((x, y)).a:
                    wx, wy = x / size[0] * 112, y / size[1] * 82
                    nearest = min(world.locations.values(), key=lambda s: (s.x - wx) ** 2 + (s.y - wy) ** 2)
                    fc = world.factions[nearest.faction].color if nearest.faction else (160, 150, 130)
                    color = tuple(int(a * .83 + b * .17) for a, b in zip((191, 181, 147), fc))
                    pygame.draw.rect(land, color, (x, y, 9, 9))
        # Reapply the coast mask after drawing rectangular territory tiles.
        mask = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), polygon)
        land.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(land, (0, 0))
        pygame.draw.lines(surface, (113, 113, 91), True, polygon, 2)
        rng = random.Random(world.seed)
        for _ in range(500):
            x, y = rng.randrange(size[0]), rng.randrange(size[1])
            if mask.get_at((x, y)).a:
                surface.set_at((x, y), (159, 152, 123))
        for loc in world.locations.values():
            x, y = self.project(rect, loc.x, loc.y)
            if loc.terrain == "mountain":
                for i in range(3):
                    xx, yy = x + (i - 1) * 11, y - 18 - (i % 2) * 5
                    pygame.draw.lines(surface, (128, 126, 102), False, [(xx - 8, yy + 7), (xx, yy - 8), (xx + 8, yy + 7)], 1)
            elif loc.terrain == "forest":
                for i in range(4):
                    xx, yy = x - 19 + i * 10, y - 22 + (i % 2) * 4
                    pygame.draw.polygon(surface, (123, 136, 102), [(xx, yy - 7), (xx - 5, yy + 4), (xx + 5, yy + 4)], 1)
        river = [(22, 1), (26, 12), (24, 24), (38, 34), (43, 46), (40, 59), (52, 81)]
        pygame.draw.lines(surface, (106, 140, 141), False, [self.project(rect, x, y) for x, y in river], 4)
        for y in range(16, size[1], 40):
            pygame.draw.line(surface, (46, 70, 72), (size[0] - 15, y), (size[0] - 2, y), 1)
        return surface
