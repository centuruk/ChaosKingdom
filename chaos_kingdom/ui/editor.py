"""A reversible, file-backed regional map editor embedded in the game."""
from __future__ import annotations

import json
import pygame

from chaos_kingdom.core.battlefields import Battlefield, TILES, load_battlefield, save_battlefield
from chaos_kingdom.core.models import TERRAIN_NAMES
from .battlefield_view import draw_field, IsometricProjection
from .theme import GOLD, LINE, MUTED, PANEL, RED, TEAL, TEXT


class MapEditor:
    rect = pygame.Rect(32, 185, 1024, 640)

    def __init__(self, world, region="s01"):
        self.world = world
        self.brush = "f"
        self.undo, self.redo = [], []
        self.stroke = None
        self.dragging = False
        self.selected_spawn = [0, 0]
        self.dirty = False
        self.show_grid = False
        self.message = "좌클릭·드래그로 칠하기 / 우클릭으로 지형 선택"
        self.open(region)

    def snapshot(self):
        return json.dumps(self.field.data(), ensure_ascii=False)

    def restore(self, snapshot):
        # Intermediate editor states may be disconnected; validation occurs on save/test.
        self.field = Battlefield(**json.loads(snapshot))
        self.field._paths.clear()

    def open(self, region, *, original=False):
        loc = self.world.locations[region]
        self.field = Battlefield(**json.loads(json.dumps(load_battlefield(region, loc.name, loc.terrain, custom=not original).data())))
        self.undo, self.redo, self.stroke = [], [], None
        self.dirty = original
        self.saved_snapshot = None if original else self.snapshot()
        self.dragging = False
        self.message = "원본을 불러왔습니다. 저장하면 사용자 전장을 덮어씁니다." if original else "지형을 칠하고 출진 경로를 확인하세요."

    def begin(self, point, button):
        cell = self.cell(point)
        if cell is None:
            return
        if button == 3:
            x, y = cell
            self.brush = self.field.tiles[y][x]
            return
        if button != 1:
            return
        self.stroke, self.dragging = self.snapshot(), True
        self.paint(point)

    def cell(self, point):
        return IsometricProjection(self.rect, self.field.width, self.field.height).cell_at(point)

    def paint(self, point):
        cell = self.cell(point)
        if not self.dragging or cell is None:
            return
        x, y = cell
        if self.brush == "objective":
            self.field.objective = [x, y]
        elif self.brush == "spawn":
            side, index = self.selected_spawn
            self.field.spawns[side][index] = [x, y]
        else:
            rows = list(self.field.tiles)
            rows[y] = rows[y][:x] + self.brush + rows[y][x + 1:]
            self.field.tiles = rows
        self.field._paths.clear()

    def end(self):
        if self.stroke is not None and self.snapshot() != self.stroke:
            self.undo.append(self.stroke)
            self.undo = self.undo[-64:]
            self.redo.clear()
            self.dirty = self.saved_snapshot is None or self.snapshot() != self.saved_snapshot
        self.stroke, self.dragging = None, False

    def history(self, backwards=True):
        self.end()
        source, target = (self.undo, self.redo) if backwards else (self.redo, self.undo)
        if source:
            target.append(self.snapshot())
            self.restore(source.pop())
            self.dirty = self.saved_snapshot is None or self.snapshot() != self.saved_snapshot

    def validate(self):
        self.field._paths.clear()
        self.field.validate()
        self.message = "검증 통과: 양측 10부대와 거점이 연결되어 있습니다."

    def save(self):
        self.end()
        self.validate()
        self.field.revision += 1
        path = save_battlefield(self.field)
        self.dirty = False
        self.saved_snapshot = self.snapshot()
        self.message = f"{path.name} 저장 완료 · 다음 지역 전투부터 적용됩니다."

    def draw(self, app):
        p = app.p
        app.heading("BATTLEFIELD WORKSHOP", "전장 편집기", "50개 지역의 이동·시야·엄폐·출진 위치를 직접 설계합니다.")
        p.button((1030, 35, 218, 39), "격자 숨기기 G" if self.show_grid else "격자 표시 G", "editor_grid")
        region_index = int(self.field.region[1:])
        p.button((32, 139, 51, 34), "◀", "editor_region", (region_index - 1) % 50)
        p.button((1005, 139, 51, 34), "▶", "editor_region", (region_index + 1) % 50)
        p.text(f"{region_index + 1:02}/50  {self.field.name}  ·  {TERRAIN_NAMES.get(self.field.biome, self.field.biome)}  ·  수정 {self.field.revision}" + ("  *미저장" if self.dirty else ""), 95, 143, 20, GOLD)
        draw_field(p, self.field, self.rect, grid=self.show_grid, deployment=True)
        pygame.draw.rect(p.surface, LINE, self.rect, 1)
        p.panel((1080, 139, 328, 686))
        p.text("지형 브러시", 1100, 158, 22, TEXT, True)
        for i, (tile, (label, color, speed, cover)) in enumerate(TILES.items()):
            x, y = 1100 + (i % 2) * 145, 199 + (i // 2) * 42
            p.button((x, y, 136, 34), label, "editor_brush", tile, primary=self.brush == tile)
        p.button((1100, 367, 281, 30), "중앙 거점", "editor_brush", "objective", primary=self.brush == "objective")
        p.text("출진 위치 옮기기", 1100, 402, 15, GOLD)
        for side in (0, 1):
            for i in range(5):
                p.button((1100 + i * 56, 430 + side * 36, 49, 30), f"{'아' if side == 0 else '적'}{i+1}", "editor_spawn", (side, i), primary=self.brush == "spawn" and self.selected_spawn == [side, i], size=14)
        p.button((1100, 511, 136, 35), "되돌리기 Z", "editor_undo", enabled=bool(self.undo))
        p.button((1245, 511, 136, 35), "다시 하기 Y", "editor_redo", enabled=bool(self.redo))
        p.button((1100, 562, 281, 38), "경로·출진 검증", "editor_validate")
        p.button((1100, 610, 281, 38), "이 전장에서 시험 전투", "editor_test", primary=True)
        p.button((1100, 658, 281, 38), "지역 전장 저장 S", "editor_save", primary=True)
        p.button((1100, 706, 136, 35), "원본 복원", "editor_reset")
        p.button((1245, 706, 136, 35), "저장본 읽기", "editor_reload")
        p.paragraph("도로 이동 +18% · 숲 엄폐 +25%\n물·성벽 통행 불가 · 성문·다리 통행\n아이소 시점 · 지형 높이·단차 없음", 1100, 761, 280, 14, MUTED, max_lines=3, line_height=18)
        p.text(self.message, 32, 851, 16, MUTED, width=1376)
