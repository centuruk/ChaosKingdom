from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import pygame

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"


@lru_cache(maxsize=16)
def asset(name):
    path = ASSET_DIR / name
    return pygame.image.load(str(path)) if path.is_file() else None


@lru_cache(maxsize=96)
def scaled_asset(name, size):
    original = asset(name)
    if original is not None and name == "ui-frame.png":
        original = original.subsurface(original.get_bounding_rect(min_alpha=16))
    return pygame.transform.smoothscale(original, size) if original is not None else None


@lru_cache(maxsize=1)
def manifest():
    return json.loads((ASSET_DIR / "manifest.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=512)
def portrait(officer_id, size):
    index = int(officer_id[1:])
    sheets = [entry for entry in manifest()["assets"] if entry["kind"] == "portrait-atlas"]
    address = manifest().get("officers", {}).get(officer_id)
    sheet_index, cell_index = (address["sheet"], address["cell"]) if address else divmod(index, 50)
    if sheet_index >= len(sheets):
        return None
    entry = sheets[sheet_index]
    original = asset(entry["file"])
    if original is None:
        return None
    usable_width = round(original.get_width() * entry.get("usable_fraction_x", 1))
    col, row = cell_index % 10, cell_index // 10
    x0, x1 = round(col * usable_width / 10), round((col + 1) * usable_width / 10)
    y0, y1 = round(row * original.get_height() / 5), round((row + 1) * original.get_height() / 5)
    # Runtime atlas addressing only; generated originals remain intact.
    cell = original.subsurface((x0 + 3, y0 + 3, x1 - x0 - 6, y1 - y0 - 6))
    return pygame.transform.smoothscale(cell, size)


@lru_cache(maxsize=128)
def terrain_tile(tile, size):
    original = asset(manifest().get("terrain_file", "terrain.png"))
    if original is None:
        return None
    index = {".": 0, "f": 1, "h": 2, "r": 3, "w": 4, "b": 5, "#": 6, "shore": 7}[tile]
    x, y = index % 4, index // 4
    width, height = original.get_width() // 4, original.get_height() // 2
    return pygame.transform.smoothscale(original.subsurface((x * width, y * height, width, height)), size)


@lru_cache(maxsize=64)
def structure_sprite(name, width):
    """Address the preserved GPT atlas at runtime, without editing its source."""
    config = manifest()
    original = asset(config.get("structures_file", "structures-isometric-v1.png"))
    if original is None:
        return None
    names = ("wall_x", "wall_y", "gate_x", "gate_y", "tower", "bridge_x", "bridge_y", "keep")
    index = names.index(name)
    x0, x1 = round(index % 4 * original.get_width() / 4), round((index % 4 + 1) * original.get_width() / 4)
    y0, y1 = round(index // 4 * original.get_height() / 2), round((index // 4 + 1) * original.get_height() / 2)
    cell = original.subsurface((x0, y0, x1 - x0, y1 - y0))
    bounds = cell.get_bounding_rect(min_alpha=16)
    if not bounds.w or not bounds.h:
        return None
    cell = cell.subsurface(bounds)
    if name in config.get("structures_layout", {}).get("mirror_x", []):
        cell = pygame.transform.flip(cell, True, False)
    return pygame.transform.smoothscale(cell, (width, max(1, round(bounds.h * width / bounds.w))))


@lru_cache(maxsize=64)
def unit_sprite(kind, facing_front, width):
    original = asset(manifest().get("units_file", "units-isometric-v1.png"))
    if original is None:
        return None
    column = ("infantry", "archer", "cavalry", "spear").index(kind)
    row = 0 if facing_front else 1
    x0, x1 = round(column * original.get_width() / 4), round((column + 1) * original.get_width() / 4)
    y0, y1 = round(row * original.get_height() / 2), round((row + 1) * original.get_height() / 2)
    cell = original.subsurface((x0, y0, x1 - x0, y1 - y0))
    bounds = cell.get_bounding_rect(min_alpha=16)
    cell = cell.subsurface(bounds)
    return pygame.transform.smoothscale(cell, (width, max(1, round(bounds.h * width / bounds.w))))
