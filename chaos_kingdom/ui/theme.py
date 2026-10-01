from __future__ import annotations

import math
import os
from pathlib import Path
import random

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame
from .assets import portrait as generated_portrait


BG = (15, 23, 25)
PANEL = (24, 34, 36)
PANEL_LIGHT = (31, 45, 46)
LINE = (53, 68, 68)
TEXT = (230, 228, 212)
MUTED = (143, 158, 152)
GOLD = (210, 178, 112)
TEAL = (92, 176, 157)
RED = (209, 115, 98)
INK = (48, 55, 49)


class Painter:
    def __init__(self, surface: pygame.Surface):
        self.surface = surface
        candidates = [os.environ.get("CHAOS_KINGDOM_FONT", ""),
                      "C:/Windows/Fonts/malgun.ttf", "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                      "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
        self.font_path = next((p for p in candidates if p and Path(p).is_file()), None)
        if not self.font_path:
            self.font_path = pygame.font.match_font("malgungothic,applesdgothicneo,notosanscjkkr,nanumgothic")
        self.fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        self.mouse = (-1, -1)
        self.buttons: list[tuple[pygame.Rect, str, object, bool]] = []
        self.tooltip = ""

    def font(self, size: int, bold: bool = False) -> pygame.font.Font:
        key = (size, bold)
        if key not in self.fonts:
            font = pygame.font.Font(self.font_path, size)
            font.set_bold(bold)
            self.fonts[key] = font
        return self.fonts[key]

    def text(self, value: str, x: float, y: float, size: int = 18, color=TEXT, bold: bool = False,
             width: int | None = None, align: str = "left") -> pygame.Rect:
        font = self.font(size, bold)
        if width is not None:
            original = value
            while value and font.size(value)[0] > width:
                value = value[:-1]
            if value != original and len(value) > 1:
                value = value[:-1] + "…"
        image = font.render(value, True, color)
        rect = image.get_rect()
        if align == "center":
            rect.midtop = (int(x), int(y))
        elif align == "right":
            rect.topright = (int(x), int(y))
        else:
            rect.topleft = (int(x), int(y))
        self.surface.blit(image, rect)
        return rect

    def paragraph(self, value: str, x: int, y: int, width: int, size: int = 17, color=MUTED,
                  max_lines: int = 8, line_height: int | None = None) -> int:
        font, lines, current = self.font(size), [], ""
        for char in value:
            if char == "\n" or font.size(current + char)[0] > width:
                lines.append(current)
                current = "" if char == "\n" else char
            else:
                current += char
        if current:
            lines.append(current)
        for index, line in enumerate(lines[:max_lines]):
            self.text(line, x, y + index * (line_height or size + 8), size, color)
        return y + min(max_lines, len(lines)) * (line_height or size + 8)

    def panel(self, rect, color=PANEL, border=LINE, radius=8):
        rect = pygame.Rect(rect)
        pygame.draw.rect(self.surface, color, rect, border_radius=radius)
        pygame.draw.rect(self.surface, border, rect, 1, border_radius=radius)
        return rect

    def button(self, rect, label: str, action: str, payload=None, *, primary=False, enabled=True,
               tooltip="", size=17):
        rect = pygame.Rect(rect)
        hovered = rect.collidepoint(self.mouse)
        hover = hovered and enabled
        color = TEAL if primary else PANEL_LIGHT
        if hover:
            color = tuple(min(255, c + 15) for c in color)
        if not enabled:
            color = PANEL
        pygame.draw.rect(self.surface, color, rect, border_radius=5)
        pygame.draw.rect(self.surface, GOLD if hover else LINE, rect, 1, border_radius=5)
        self.text(label, rect.centerx, rect.y + (rect.h - size) / 2 - 3, size,
                  BG if primary and enabled else TEXT if enabled else MUTED, primary, width=rect.w - 14, align="center")
        self.buttons.append((rect, action, payload, enabled))
        if hovered and tooltip:
            self.tooltip = tooltip

    def bar(self, rect, value: float, maximum: float = 100, color=TEAL):
        rect = pygame.Rect(rect)
        pygame.draw.rect(self.surface, BG, rect, border_radius=3)
        fill = rect.copy()
        fill.width = max(0, round(rect.width * min(1, max(0, value / maximum))))
        if fill.width:
            pygame.draw.rect(self.surface, color, fill, border_radius=3)

    def portrait(self, rect, officer, color=TEAL):
        rect = pygame.Rect(rect)
        image = generated_portrait(officer.id, rect.size)
        if image is not None:
            self.surface.blit(image, rect)
            pygame.draw.rect(self.surface, color, rect, 2, border_radius=3)
            return
        seed = int(officer.id[1:])
        rng = random.Random(seed + 98)
        self.panel(rect, PANEL_LIGHT)
        cx, cy = rect.centerx, rect.y + rect.h * .41
        scale = min(rect.w / 140, rect.h / 170)
        skin = rng.choice([(186, 151, 118), (198, 170, 135), (156, 119, 91), (213, 181, 145)])
        hair = rng.choice([(62, 51, 43), (125, 97, 62), (154, 141, 118), (31, 32, 32)])
        # Heraldic portraits are generated locally; no copyrighted character art is used.
        for r in range(5):
            pygame.draw.circle(self.surface, LINE, (cx, cy), int((55 + r * 5) * scale), 1)
        pygame.draw.polygon(self.surface, color, [(cx - 55 * scale, rect.bottom - 5), (cx - 36 * scale, cy + 42 * scale),
                                                (cx + 36 * scale, cy + 42 * scale), (cx + 55 * scale, rect.bottom - 5)])
        pygame.draw.polygon(self.surface, (83, 90, 83), [(cx - 34 * scale, cy + 42 * scale), (cx, rect.bottom - 14), (cx + 34 * scale, cy + 42 * scale)])
        pygame.draw.rect(self.surface, skin, (cx - 10 * scale, cy + 25 * scale, 20 * scale, 23 * scale))
        pygame.draw.ellipse(self.surface, hair, (cx - 31 * scale, cy - 39 * scale, 62 * scale, 75 * scale))
        pygame.draw.ellipse(self.surface, skin, (cx - 26 * scale, cy - 30 * scale, 52 * scale, 68 * scale))
        pygame.draw.polygon(self.surface, hair, [(cx - 30 * scale, cy - 6 * scale), (cx - 26 * scale, cy - 37 * scale),
                                               (cx + 20 * scale, cy - 36 * scale), (cx + 30 * scale, cy - 10 * scale), (cx + 5 * scale, cy - 23 * scale)])
        for direction in (-1, 1):
            pygame.draw.line(self.surface, hair, (cx + direction * 8 * scale, cy), (cx + direction * 18 * scale, cy - 2 * scale), max(1, int(2 * scale)))
            pygame.draw.circle(self.surface, INK, (cx + direction * 12 * scale, cy + 5 * scale), max(1, int(2 * scale)))
        pygame.draw.line(self.surface, INK, (cx - 7 * scale, cy + 23 * scale), (cx + 8 * scale, cy + 23 * scale), max(1, int(scale)))
        if seed % 3 == 0:
            pygame.draw.polygon(self.surface, hair, [(cx - 21 * scale, cy + 20 * scale), (cx, cy + 46 * scale), (cx + 21 * scale, cy + 20 * scale), (cx, cy + 29 * scale)])
        if officer.rank == 4:
            pygame.draw.polygon(self.surface, GOLD, [(cx - 26 * scale, cy - 30 * scale), (cx - 30 * scale, cy - 50 * scale),
                                                   (cx - 9 * scale, cy - 39 * scale), (cx, cy - 57 * scale), (cx + 11 * scale, cy - 39 * scale), (cx + 28 * scale, cy - 49 * scale), (cx + 25 * scale, cy - 30 * scale)])

    def compass(self, x: int, y: int, color=GOLD):
        for angle in range(8):
            a = angle * math.pi / 4
            length = 25 if angle % 2 == 0 else 13
            pygame.draw.line(self.surface, color, (x, y), (x + math.sin(a) * length, y + math.cos(a) * length), 1)
        self.text("N", x, y - 46, 14, color, align="center")
