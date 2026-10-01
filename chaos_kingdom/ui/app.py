from __future__ import annotations

import math
import os
from pathlib import Path
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from chaos_kingdom.core.campaign import SCENARIOS, create_campaign
from chaos_kingdom import __version__
from chaos_kingdom.core.generation import generate_world, select_player
from chaos_kingdom.core.models import ACTION_NAMES, RANKS, STAT_NAMES, TERRAIN_NAMES, World, pair
from chaos_kingdom.core.storage import digest, load_battle, load_world, save_world, user_directory
from chaos_kingdom.core.diagnostics import export_report
from chaos_kingdom.simulation.ai import evaluate
from chaos_kingdom.simulation.battle import Battle, UNIT_NAMES
from chaos_kingdom.simulation.engine import Engine
from .map_view import MapView
from .editor import MapEditor
from .battlefield_view import draw_field, IsometricProjection, structure_items, draw_structure
from .assets import scaled_asset, unit_sprite
from .theme import BG, GOLD, INK, LINE, MUTED, PANEL, PANEL_LIGHT, RED, TEAL, TEXT, Painter


WIDTH, HEIGHT = 1440, 900


class App:
    def __init__(self, *, headless: bool = False, world: World | None = None):
        if headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        pygame.display.init()
        pygame.font.init()
        self.window = pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
        pygame.display.set_caption("혼돈의 왕국 · Chaos Kingdom")
        # Cocoa's display format has an alpha mask. Inheriting that format
        # without SRCALPHA can replace the backdrop with transparent PNG pixels.
        # Start each frame opaque in draw(), then blend every overlay explicitly.
        self.canvas = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA, 32)
        self.p = Painter(self.canvas)
        self.map_view = MapView()
        self.world = world or generate_world(742)
        self.engine = Engine(self.world)
        self.screen = "world" if self.world.player else "menu"
        self.tab = "map"
        self.running = True
        self.selected_location = self.world.officers[self.world.player].location if self.world.player else "s01"
        self.selected_officer = self.world.player or "o024"
        self.roster_page = 0
        self.roster_filter: str | None = "all"
        self.roster_sort = "renown"
        self.log_page = 0
        self.modal: str | None = None
        self.modal_page = 0
        self.pending_action = "bond"
        self.toast = ""
        self.toast_until = 0.0
        self.battle: Battle | None = None
        self.demo = False
        self.paused = True
        self.speed = 1
        self.selected_units: list[int] = [0]
        self.save_path = user_directory() / "campaign.json"
        self.offset = (0, 0)
        self.scale = 1.0
        self.editor = None
        self.demo_return = "menu"
        self.pending_editor = None
        self.journal = []
        self.last_battle_save = 0.0

    def notify(self, message: str, duration: float = 5) -> None:
        self.toast, self.toast_until = message, time.monotonic() + duration

    def save(self, *, announce: bool = True) -> None:
        if self.demo:
            return
        if not self.world.player:
            return
        try:
            save_world(self.world, self.save_path, battle=self.battle)
            if announce:
                self.notify("현재 캠페인을 저장했습니다.")
        except (OSError, ValueError) as exc:
            self.notify(f"저장 실패: {exc}", 9)

    def load(self) -> None:
        try:
            loaded = load_world(self.save_path)
            battle = load_battle(self.save_path, loaded)
            if not loaded.player:
                raise ValueError("플레이어가 선택되지 않은 캠페인입니다.")
            self.world, self.engine = loaded, Engine(loaded)
            self.selected_officer = loaded.player
            self.selected_location = loaded.officers[loaded.player].location
            self.screen, self.tab, self.modal = "world", "map", None
            self.battle = battle
            self.demo, self.paused = False, True
            if battle:
                self.screen = "battle"
                self.selected_units = [u.id for u in battle.active(battle.controlled_side)][:1]
                self.last_battle_save = battle.time
            self.notify("저장한 이야기를 이어갑니다.")
            self.enter_pending()
        except (OSError, ValueError) as exc:
            self.notify(f"불러오기 실패: {exc}", 9)

    def run(self, *, max_frames: int | None = None, screenshot: Path | None = None) -> None:
        clock = pygame.time.Clock()
        frames = 0
        while self.running:
            dt = min(.05, clock.tick(60) / 1000)
            self.draw()
            self.present()
            for event in pygame.event.get():
                self.handle_event(event)
            if self.battle and not self.paused and not self.battle.finished:
                # Keep fixed simulation steps even when running at four times speed.
                self.battle.update(dt * self.speed)
                if not self.demo and self.battle.time - self.last_battle_save >= 10:
                    self.save(announce=False)
                    self.last_battle_save = self.battle.time
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        if screenshot:
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(self.canvas, str(screenshot))
        if max_frames is None:
            self.save(announce=False)
        pygame.quit()

    def present(self) -> None:
        w, h = self.window.get_size()
        self.scale = min(w / WIDTH, h / HEIGHT)
        scaled = (max(1, int(WIDTH * self.scale)), max(1, int(HEIGHT * self.scale)))
        self.offset = ((w - scaled[0]) // 2, (h - scaled[1]) // 2)
        self.window.fill(BG)
        self.window.blit(pygame.transform.smoothscale(self.canvas, scaled), self.offset)
        pygame.display.flip()

    def logical_mouse(self, pos) -> tuple[int, int]:
        return (int((pos[0] - self.offset[0]) / self.scale), int((pos[1] - self.offset[1]) / self.scale))

    def handle_event(self, event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.MOUSEMOTION:
            self.p.mouse = self.logical_mouse(event.pos)
            if self.screen == "editor" and self.editor and not self.modal:
                self.editor.paint(self.p.mouse)
        elif event.type == pygame.MOUSEBUTTONUP:
            if self.editor:
                self.editor.end()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            point = self.logical_mouse(event.pos)
            self.p.mouse = point
            if event.button == 1:
                for rect, action, payload, enabled in reversed(self.p.buttons):
                    if rect.collidepoint(point) and enabled:
                        self.dispatch(action, payload)
                        return
                if self.screen == "battle" and not self.modal:
                    self.battle_click(point, right=False)
                elif self.screen == "editor" and self.editor and not self.modal:
                    self.editor.begin(point, event.button)
            elif event.button == 3 and self.screen == "battle" and not self.modal:
                self.battle_click(point, right=True)
            elif event.button == 3 and self.screen == "editor" and not self.modal:
                self.editor.begin(point, event.button)
        elif event.type == pygame.MOUSEWHEEL and not self.modal:
            if self.screen == "select" or (self.screen == "world" and self.tab == "officers"):
                self.roster_page = max(0, self.roster_page - event.y)
            elif self.screen == "world" and self.tab == "chronicle":
                self.log_page = max(0, self.log_page - event.y)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.modal:
                    self.modal = None
                elif self.screen == "battle":
                    self.paused, self.modal = True, "retreat"
                elif self.screen == "world":
                    self.save(announce=False)
                    self.screen = "menu"
                elif self.screen == "editor" and self.editor and self.editor.dirty:
                    self.pending_editor, self.modal = ("menu", None), "editor_discard"
                else:
                    self.screen = "menu"
            elif self.modal:
                return
            elif self.screen == "editor" and self.editor:
                if event.key == pygame.K_z:
                    self.editor.history()
                elif event.key == pygame.K_y:
                    self.editor.history(False)
                elif event.key in (pygame.K_s, pygame.K_F5):
                    self.dispatch("editor_save")
                elif event.key == pygame.K_g:
                    self.dispatch("editor_grid")
            elif event.key == pygame.K_h:
                self.modal = "help"
            elif event.key == pygame.K_r:
                self.dispatch("report")
            elif event.key == pygame.K_F5:
                self.save()
            elif event.key == pygame.K_F9 and self.screen != "battle":
                self.load()
            elif event.key == pygame.K_SPACE:
                if self.screen == "battle" and self.battle and not self.battle.finished:
                    self.paused = not self.paused
                elif self.screen == "world":
                    self.do_action("rest")
            elif event.key == pygame.K_TAB and self.screen == "world":
                tabs = ["map", "officers", "diplomacy", "chronicle"]
                self.tab = tabs[(tabs.index(self.tab) + 1) % len(tabs)]
            elif event.key == pygame.K_a and self.screen == "battle" and self.battle:
                self.selected_units = [u.id for u in self.battle.active(self.battle.controlled_side)]
            elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5) and self.screen == "battle" and self.battle:
                index = event.key - pygame.K_1
                ours = [u for u in self.battle.units if u.side == self.battle.controlled_side]
                if index < len(ours):
                    self.selected_units = [ours[index].id]

    def dispatch(self, action: str, payload=None) -> None:
        if action == "new":
            self.screen = "scenarios"
        elif action == "menu":
            if self.screen == "editor" and self.editor and self.editor.dirty:
                self.pending_editor, self.modal = ("menu", None), "editor_discard"
                return
            self.screen = "menu"
        elif action == "editor":
            self.editor = MapEditor(self.world)
            self.screen = "editor"
        elif action.startswith("editor_"):
            self.editor_action(action, payload)
        elif action == "help":
            self.modal = "help"
        elif action == "quests":
            self.modal = "quests"
        elif action == "continue_chapter":
            if not self.world.victor and not self.world.unified_by:
                self.world.chapter_report, self.world.outcome = self.world.outcome, None
                self.world.chapter_end = self.world.turn + 96
                self.world.log("chapter", "장수의 다음 96주 연대기가 시작된다.", [self.world.player])
                self.save(announce=False)
        elif action == "close":
            self.modal = None
        elif action == "memories":
            self.modal = "memories"
        elif action == "load":
            self.load()
        elif action == "save":
            self.save()
        elif action == "report":
            try:
                path = export_report(self.world, self.journal, self.battle if not self.demo else None)
                self.notify(f"로컬 제보 저장: reports/{path.name}", 12)
            except (OSError, ValueError) as exc:
                self.notify(f"제보 저장 실패: {exc}", 9)
        elif action == "quit":
            self.running = False
        elif action == "scenario":
            scenario = SCENARIOS[payload]
            self.notify("장수들이 역사를 만들고 있습니다…", 30)
            self.draw()
            self.present()
            self.world = create_campaign(scenario["seed"], scenario["weeks"], scenario["title"])
            self.engine = Engine(self.world)
            candidates = [o for o in self.world.officers.values() if o.faction == "f0" and not o.captor and self.world.locations[o.location].faction == o.faction]
            candidates.sort(key=lambda o: (any(self.world.at_war(o.faction, self.world.locations[n].faction) for n in self.world.locations[o.location].neighbors), o.rank < 3, o.energy), reverse=True)
            self.selected_officer = candidates[0].id if candidates else next(o.id for o in self.world.officers.values() if not o.captor)
            self.roster_page, self.roster_filter, self.screen = 0, "all", "select"
            self.notify(f"{scenario['weeks']}주의 자율 역사가 완성되었습니다. 장수를 선택하세요.")
        elif action == "filter":
            self.roster_filter, self.roster_page = payload, 0
        elif action == "sort":
            self.roster_sort, self.roster_page = payload, 0
        elif action == "roster_page":
            self.roster_page = max(0, self.roster_page + payload)
        elif action == "officer":
            self.selected_officer = payload
        elif action == "begin":
            try:
                select_player(self.world, self.selected_officer)
            except ValueError as exc:
                self.notify(str(exc))
                return
            self.screen, self.tab = "world", "map"
            self.selected_location = self.world.officers[self.world.player].location
            self.save(announce=False)
            self.notify("당신의 이야기가 시작됩니다. H키로 지휘 안내를 확인하세요.", 8)
        elif action == "tab":
            self.tab = payload
        elif action == "location":
            if self.screen == "world":
                self.selected_location = payload
        elif action == "home":
            self.selected_location = self.world.officers[self.world.player].location
        elif action == "do":
            self.do_action(payload)
        elif action == "bond_modal":
            self.modal, self.pending_action, self.modal_page = "residents", payload, 0
        elif action == "resident_page":
            self.modal_page = max(0, self.modal_page + payload)
        elif action == "target_action":
            self.modal = None
            self.do_action(self.pending_action, payload)
        elif action == "negotiate":
            self.do_action("negotiate", payload)
        elif action == "petition_war":
            self.do_action("petition_war", payload)
        elif action == "log_page":
            self.log_page = max(0, self.log_page + payload)
        elif action == "demo":
            self.start_demo()
        elif action == "pause":
            self.paused = not self.paused
        elif action == "speed":
            self.speed = {1: 2, 2: 4, 4: 1}[self.speed]
        elif action == "order" and self.battle:
            self.battle.issue(self.selected_units, payload)
            self.record("battle_order", {"units": self.selected_units, "order": payload, "time": self.battle.time})
            self.save(announce=False)
        elif action == "all" and self.battle:
            self.selected_units = [u.id for u in self.battle.active(self.battle.controlled_side)]
        elif action == "rally" and self.battle:
            if not self.battle.rally():
                self.notify("격려는 35초마다 사용할 수 있습니다.")
        elif action == "retreat":
            self.paused, self.modal = True, "retreat"
        elif action == "confirm_retreat" and self.battle:
            self.battle.retreat()
            self.modal = None
        elif action == "battle_done" and self.battle:
            if not self.demo:
                self.engine.resolve_battle(self.battle)
                self.selected_location = self.world.officers[self.world.player].location
                self.screen, self.tab = "world", "map"
            else:
                self.screen = self.demo_return
            self.battle = None
            self.demo = False
            self.enter_pending()
            self.save(announce=False)
        elif action == "unit":
            self.selected_units = [payload]

    def do_action(self, action: str, target: str | None = None) -> None:
        if action in ("travel", "attack"):
            target = self.selected_location
        before = digest(self.world.data())
        try:
            result = self.engine.player_action(action, target)
        except (ValueError, OSError) as exc:
            self.notify(f"행동을 진행할 수 없습니다: {exc}", 9)
            return
        self.record("strategy", {"action": action, "target": target, "ok": result.ok, "before": before, "after": digest(self.world.data())})
        self.notify(result.message, 7)
        if result.battle:
            self.battle, self.screen, self.paused = result.battle, "battle", True
            self.selected_units, self.speed, self.demo = [u.id for u in self.battle.active(self.battle.controlled_side)][:1], 1, False
            self.last_battle_save = 0.0
            self.save(announce=False)
        elif result.ok:
            self.enter_pending()
            self.save(announce=False)
            self.selected_officer = self.world.player
            if action in ("travel", "enlist"):
                self.selected_location = self.world.officers[self.world.player].location

    def record(self, kind, data):
        self.journal.append({"turn": self.world.turn, "kind": kind, **data})
        self.journal = self.journal[-200:]

    def enter_pending(self):
        if self.world.pending_battle and self.battle is None:
            self.battle = Battle.from_data(self.world, self.world.pending_battle)
            self.screen, self.paused, self.demo = "battle", True, False
            self.selected_units = [u.id for u in self.battle.active(self.battle.controlled_side)][:1]
            self.last_battle_save = 0.0
            self.notify("적군이 현재 영지를 공격합니다. 방어전을 지휘하세요.", 9)

    def start_demo(self, battlefield=None) -> None:
        demo = generate_world(742)
        source, target = demo.locations["s20"], demo.locations["s21"]
        source.faction, target.faction = "f0", "f2"
        source.troops, target.troops = 1000, 780
        target.terrain, target.fortification = "river", 25
        commander = demo.officers["o024"]
        commander.location, commander.faction = source.id, "f0"
        for index in (6, 12, 18, 30):
            ally = demo.officers[f"o{index:03}"]
            ally.location, ally.faction = source.id, "f0"
            demo.change_bond(commander.id, ally.id, 45)
        for index in (2, 8, 14, 26, 32):
            enemy = demo.officers[f"o{index:03}"]
            enemy.location, enemy.faction = target.id, "f2"
        target.governor = "o002"
        self.battle = Battle(demo, source.id, target.id, commander.id, 12, interactive=True, battlefield=battlefield)
        self.demo_return = "editor" if battlefield is not None else "menu"
        self.screen, self.paused, self.speed, self.demo = "battle", True, 1, True
        self.selected_units = [0]

    def editor_action(self, action, payload):
        editor = self.editor
        if not editor:
            return
        try:
            if action in ("editor_region", "editor_reset", "editor_reload") and editor.dirty:
                self.pending_editor, self.modal = (action, payload), "editor_discard"
                return
            if action == "editor_discard":
                editor.dirty = False
                self.modal = None
                action, payload = self.pending_editor
                self.dispatch(action, payload)
            elif action == "editor_brush":
                editor.brush = payload
            elif action == "editor_spawn":
                editor.brush, editor.selected_spawn = "spawn", list(payload)
            elif action == "editor_undo":
                editor.history()
            elif action == "editor_redo":
                editor.history(False)
            elif action == "editor_grid":
                editor.show_grid = not editor.show_grid
            elif action == "editor_region":
                editor.open(f"s{payload:02}")
            elif action == "editor_reset":
                editor.open(editor.field.region, original=True)
            elif action == "editor_reload":
                editor.open(editor.field.region)
            elif action == "editor_validate":
                editor.validate()
            elif action == "editor_save":
                editor.save()
            elif action == "editor_test":
                editor.validate()
                self.start_demo(battlefield=editor.field)
        except (ValueError, OSError) as exc:
            editor.message = f"검증 실패: {exc}"
            self.notify(str(exc), 8)

    def draw(self) -> None:
        p = self.p
        p.buttons, p.tooltip = [], ""
        self.canvas.fill(BG)
        if self.screen == "menu":
            self.draw_menu()
        elif self.screen == "scenarios":
            self.draw_scenarios()
        elif self.screen == "select":
            self.draw_selection()
        elif self.screen == "world":
            self.draw_world()
        elif self.screen == "battle":
            self.draw_battle()
        elif self.screen == "editor" and self.editor:
            self.editor.draw(self)
        if self.modal:
            self.draw_modal()
        if time.monotonic() < self.toast_until:
            rect = pygame.Rect(310, 839, 820, 42)
            p.panel(rect, PANEL_LIGHT, GOLD)
            p.text(self.toast, rect.centerx, rect.y + 9, 16, TEXT, width=790, align="center")
        elif p.tooltip:
            p.panel((310, 842, 820, 37), PANEL_LIGHT)
            p.text(p.tooltip, 720, 850, 15, MUTED, width=790, align="center")

    def draw_menu(self) -> None:
        p = self.p
        background = scaled_asset("title.png", (WIDTH, HEIGHT))
        if background is not None:
            self.canvas.blit(background, (0, 0))
        else:
            self.map_view.draw(p, self.world, (603, 125, 805, 597), labels=False)
        # Map buttons are intentionally inactive on the title screen.
        p.buttons.clear()
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(veil, (15, 23, 25, 155), (0, 0, 570, HEIGHT))
        pygame.draw.rect(veil, (15, 23, 25, 105), (590, 674, 810, 119))
        self.canvas.blit(veil, (0, 0))
        p.text("ELDRAS  /  THE FRACTURED CROWN", 64, 80, 16, GOLD)
        p.text("CHAOS", 60, 151, 90, TEXT, True)
        p.text("KINGDOM", 60, 240, 90, TEXT, True)
        p.text("혼돈의 왕국", 66, 357, 34, GOLD, True)
        frame = scaled_asset("ui-frame.png", (465, 24))
        if frame is not None:
            self.canvas.blit(frame, (56, 416))
        else:
            pygame.draw.line(self.canvas, LINE, (66, 420), (510, 420))
        p.paragraph("왕은 죽었다.\n200명의 의지는 멈추지 않는다.\n한 장수의 선택으로 왕국의 역사를 바꾸세요.", 66, 445, 450, 21, MUTED, line_height=34)
        p.button((66, 576, 365, 56), "새로운 이야기 시작", "new", primary=True, size=21)
        p.button((66, 646, 176, 45), "저장한 이야기", "load", enabled=self.save_path.exists())
        p.button((255, 646, 176, 45), "전투 연습", "demo")
        p.button((66, 705, 176, 43), "전장 편집기", "editor")
        p.button((255, 705, 176, 43), "지휘 안내  H", "help")
        p.button((66, 761, 176, 36), "게임 종료", "quit")
        p.button((255, 761, 176, 36), "문제 제보 저장  R", "report", size=14)
        for i, faction in enumerate(self.world.factions.values()):
            x, y = 673 + (i % 3) * 232, 691 + (i // 3) * 48
            pygame.draw.circle(self.canvas, faction.color, (x, y + 10), 5)
            p.text(faction.name, x + 15, y, 17, TEXT)
        p.text("장수 200명   /   성 20개   /   거점 30개   /   최대 1,000명 지휘", 66, 816, 17, MUTED)
        p.text(f"v{__version__}  ·  클로즈드 베타", 1376, 855, 14, MUTED, align="right")

    def heading(self, kicker: str, title: str, subtitle: str = "") -> None:
        p = self.p
        frame = scaled_asset("ui-frame.png", (820, 17))
        if frame is not None:
            self.canvas.blit(frame, (24, 82))
        p.text(kicker, 32, 27, 14, GOLD)
        p.text(title, 32, 51, 32, TEXT, True)
        if subtitle:
            p.text(subtitle, 34, 103, 17, MUTED)
        p.button((1266, 35, 142, 39), "돌아가기", "menu")

    def draw_scenarios(self) -> None:
        p = self.p
        self.heading("CAMPAIGN ARCHIVES", "역사의 시작을 고르세요", "미리 정해진 승자는 없습니다. 장수들의 행동이 출발 시점의 판세와 인연을 만듭니다.")
        for i, scenario in enumerate(SCENARIOS):
            x = 32 + i * 465
            p.panel((x, 172, 440, 571))
            p.text(f"0{i + 1}", x + 28, 199, 44, GOLD)
            p.text(f"{scenario['weeks']}주의 자율 역사", x + 28, 259, 16, TEAL)
            # Campaign imagery is a heraldic crest, drawn directly by pygame.
            cx, cy = x + 220, 382
            color = (TEAL, RED, (170, 134, 191))[i]
            pygame.draw.polygon(self.canvas, color, [(cx - 65, cy - 60), (cx + 65, cy - 60), (cx + 53, cy + 35), (cx, cy + 76), (cx - 53, cy + 35)], 2)
            for offset in (-25, 0, 25):
                pygame.draw.line(self.canvas, GOLD, (cx + offset, cy - 26), (cx + offset, cy + 23), 4)
            pygame.draw.line(self.canvas, GOLD, (cx - 45, cy - 5), (cx + 45, cy - 5), 3)
            p.text(scenario["title"], x + 28, 491, 30, TEXT, True)
            p.text(scenario["subtitle"], x + 28, 537, 17, GOLD)
            p.paragraph(scenario["description"], x + 28, 572, 382, 18, MUTED, max_lines=3)
            p.button((x + 28, 670, 384, 47), "역사 생성 · 장수 선택", "scenario", i, primary=True)
        p.text("같은 역사 시드에서는 같은 출발점이 만들어집니다. 플레이를 시작한 순간부터 선택이 역사를 바꿉니다.", 33, 783, 18, MUTED)

    def officer_list(self):
        officers = list(self.world.officers.values())
        if self.roster_filter != "all":
            officers = [o for o in officers if o.faction == self.roster_filter]
        return sorted(officers, key=lambda o: (o.stats[self.roster_sort] if self.roster_sort in o.stats else o.renown, o.id), reverse=True)

    def filters(self, x: int, y: int, width: int) -> None:
        p = self.p
        entries = [("all", "전체"), *[(f.id, f.name.split()[0]) for f in self.world.factions.values()], (None, "재야")]
        button_width = (width - 7 * 6) // 8
        for i, (value, label) in enumerate(entries):
            p.button((x + i * (button_width + 6), y, button_width, 33), label, "filter", value, primary=self.roster_filter == value, size=14)

    def draw_selection(self) -> None:
        p = self.p
        self.heading("CHOOSE YOUR OFFICER", "누구의 이야기로 시작할까요?", f"{self.world.title}  ·  {self.world.date}  ·  시드 {self.world.seed}")
        p.panel((32, 151, 903, 650))
        self.filters(52, 171, 863)
        self.draw_roster(52, 221, 863, 11)
        p.panel((955, 151, 453, 650))
        self.officer_detail(self.selected_officer, 977, 171, 410, large=True)
        officer = self.world.officers[self.selected_officer]
        p.button((977, 728, 410, 50), "이 장수로 시작", "begin", primary=True, enabled=not officer.captor, size=20)

    def draw_roster(self, x: int, y: int, width: int, rows: int) -> None:
        p = self.p
        officers = self.officer_list()
        pages = max(1, math.ceil(len(officers) / rows))
        self.roster_page = min(pages - 1, self.roster_page)
        p.text("장수 / 소속", x + 10, y, 15, MUTED)
        p.text("계급", x + 320, y, 15, MUTED)
        for i, key in enumerate(("command", "martial", "intellect", "politics", "charm")):
            p.button((x + 430 + i * 62, y - 4, 57, 27), STAT_NAMES[key], "sort", key, primary=self.roster_sort == key, size=13)
        for row, officer in enumerate(officers[self.roster_page * rows:(self.roster_page + 1) * rows]):
            yy = y + 36 + row * 43
            selected = officer.id == self.selected_officer
            rect = pygame.Rect(x, yy, width, 39)
            p.panel(rect, PANEL_LIGHT if selected else PANEL, GOLD if selected else LINE, 3)
            color = self.world.factions[officer.faction].color if officer.faction else MUTED
            pygame.draw.circle(self.canvas, color, (x + 15, yy + 18), 4)
            p.text(officer.name, x + 29, yy + 4, 17, TEXT, selected, width=260)
            p.text(self.world.factions[officer.faction].name if officer.faction else "재야", x + 29, yy + 22, 11, MUTED)
            p.text("포로" if officer.captor else RANKS[officer.rank], x + 320, yy + 9, 15, MUTED)
            for i, key in enumerate(("command", "martial", "intellect", "politics", "charm")):
                p.text(str(officer.stats[key]), x + 458 + i * 62, yy + 8, 17, GOLD if officer.stats[key] >= 85 else TEXT, align="center")
            p.buttons.append((rect, "officer", officer.id, True))
        bottom = y + 36 + rows * 43 + 14
        p.button((x, bottom, 86, 32), "이전", "roster_page", -1, enabled=self.roster_page > 0)
        p.text(f"{self.roster_page + 1} / {pages}  ·  {len(officers)}명", x + width / 2, bottom + 5, 15, MUTED, align="center")
        p.button((x + width - 86, bottom, 86, 32), "다음", "roster_page", 1, enabled=self.roster_page < pages - 1)

    def officer_detail(self, oid: str, x: int, y: int, width: int, *, large: bool = False, compact: bool = False) -> None:
        p, o = self.p, self.world.officers[oid]
        color = self.world.factions[o.faction].color if o.faction else MUTED
        size = 142 if large else 112
        p.portrait((x + (width - size) // 2, y, size, size + 18), o, color)
        yy = y + size + 35
        p.text(o.name, x, yy, 24 if large else 21, TEXT, True, width=width)
        p.text(f"{RANKS[o.rank]}  ·  {o.age}세  ·  {self.world.locations[o.location].name}", x, yy + 36, 16, GOLD, width=width)
        p.text(self.world.factions[o.faction].name if o.faction else "재야 장수", x, yy + 65, 16, color)
        yy += 107
        for key, label in STAT_NAMES.items():
            p.text(label, x, yy, 16, MUTED)
            p.bar((x + 50, yy + 7, width - 97, 8), o.stats[key], color=color)
            p.text(str(o.stats[key]), x + width, yy, 17, TEXT, align="right")
            yy += 29
        p.text(f"명성 {o.renown}   충성 {o.loyalty:.0f}   기력 {o.energy:.0f}", x, yy + 10, 15, MUTED, width=width)
        traits = o.traits
        temperament = "명예를 지키는" if traits["honor"] > 65 else "야망이 강한" if traits["ambition"] > 65 else "신중한"
        if not compact:
            p.paragraph(f"{temperament} {UNIT_NAMES.get(o.specialty, '책략')} 지휘관.\n생각: {o.intent}", x, yy + 45, width, 16, MUTED, max_lines=2 if large else 3)
        if large and o.memories:
            p.text("기억: " + o.memories[-1].text, x, yy + 96, 14, GOLD, width=width)

    def draw_world(self) -> None:
        p, world = self.p, self.world
        player = world.officers[world.player]
        p.text("CHAOS KINGDOM", 24, 22, 20, GOLD, True)
        p.text(world.title, 24, 55, 16, MUTED)
        tabs = [("map", "왕국 지도"), ("officers", "장수 열전"), ("diplomacy", "세력과 외교"), ("chronicle", "역사의 기록")]
        for i, (key, label) in enumerate(tabs):
            p.button((273 + i * 151, 28, 142, 42), label, "tab", key, primary=self.tab == key)
        p.text(world.date, 932, 22, 17, TEXT)
        p.text(f"자금 {player.gold}금  ·  승전 {world.victories}회", 932, 52, 14, MUTED)
        holdings, castles = world.unification_progress(player.faction)
        p.text(f"천하통일 {holdings}/50  ·  성 {castles}/20  ·  거점 {holdings-castles}/30", 932, 76, 12, GOLD)
        p.button((1155, 28, 74, 42), "저장", "save")
        p.button((1238, 28, 84, 42), "안내", "help")
        p.button((1330, 28, 86, 42), "1주 휴식", "do", "rest", primary=True)
        pygame.draw.line(self.canvas, LINE, (24, 92), (1416, 92))
        p.panel((24, 113, 220, 765))
        p.text("당신의 장수", 43, 132, 14, MUTED)
        self.officer_detail(player.id, 43, 164, 182, compact=True)
        p.bar((43, 620, 182, 8), player.energy)
        p.text(f"기력 {player.energy:.0f} / 100", 43, 636, 15, MUTED)
        p.text("가까운 인연", 43, 679, 17, GOLD)
        related = sorted((o for o in world.officers.values() if o.id != player.id), key=lambda o: world.relationship(player.id, o.id), reverse=True)[:4]
        for i, other in enumerate(related):
            yy = 718 + i * 30
            p.text(other.name, 43, yy, 14, TEXT, width=135)
            p.text(f"{world.relationship(player.id, other.id):.0f}", 224, yy, 14, TEAL, align="right")
        p.button((43, 841, 182, 25), "현재 위치로", "home", size=14)
        if self.tab == "map":
            self.draw_world_map()
        elif self.tab == "officers":
            self.draw_world_roster()
        elif self.tab == "diplomacy":
            self.draw_diplomacy()
        else:
            self.draw_chronicle()
        if world.outcome:
            p.buttons.clear()
            p.panel((280, 355, 860, 200), PANEL_LIGHT, GOLD)
            p.text("천하통일 달성" if world.unified_by == player.faction else "천하통일 · 왕국의 마지막 페이지", 710, 382, 24, GOLD, True, align="center")
            p.text(world.outcome, 710, 433, 17, TEXT, width=820, align="center")
            p.button((405, 490, 280, 37), "메인 메뉴", "menu")
            p.button((715, 490, 280, 37), "새로운 이야기", "new", primary=True)

    def draw_world_map(self) -> None:
        p, world = self.p, self.world
        player = world.officers[world.player]
        p.text("엘드라스 대륙", 267, 111, 23, TEXT, True)
        p.text("성 ■  /  거점 ●  /  붉은 도로: 교전 국경", 1118, 118, 14, MUTED, align="right")
        p.panel((264, 151, 854, 501))
        self.map_view.draw(p, world, (265, 152, 852, 499), self.selected_location, player.location)
        p.panel((264, 671, 854, 207))
        p.text("전령의 보고", 284, 687, 19, GOLD)
        for i, event in enumerate(reversed(world.chronicles[-5:])):
            color = RED if event.kind in ("battle", "war", "fall") else MUTED
            p.text(f"{event.turn}주", 284, 725 + i * 27, 14, GOLD)
            p.text(event.text, 339, 723 + i * 27, 15, color, width=757)
        self.draw_location_panel()

    def draw_location_panel(self) -> None:
        p, world = self.p, self.world
        player = world.officers[world.player]
        loc = world.locations[self.selected_location]
        p.panel((1138, 113, 278, 765))
        p.text("선택한 영지", 1158, 132, 14, MUTED)
        p.text(loc.name, 1158, 161, 26, TEXT, True, width=239)
        p.text(f"{'성' if loc.kind == 'castle' else '거점'}  ·  {TERRAIN_NAMES[loc.terrain]}", 1158, 204, 16, GOLD)
        faction = world.factions.get(loc.faction)
        p.text(faction.name if faction else "무주지", 1158, 234, 17, faction.color if faction else MUTED, width=238)
        governor = world.officers.get(loc.governor)
        p.text(f"성주  {governor.name if governor else '공석'}", 1158, 269, 15, MUTED, width=237)
        for i, (label, value) in enumerate((("병력", f"{loc.troops}명"), ("군량", f"{loc.food:.0f}"), ("세입금", f"{loc.treasury:.0f}"), ("번영 / 사기", f"{loc.prosperity:.0f} / {loc.morale:.0f}"))):
            p.text(label, 1158, 310 + i * 30, 16, MUTED)
            p.text(value, 1396, 310 + i * 30, 17, TEXT, align="right")
        here = player.location == loc.id
        p.text("장수의 행동", 1158, 452, 18, GOLD)
        p.text("각 행동은 1주를 사용합니다", 1158, 482, 14, MUTED)
        actions = [("수련", "train", "통솔·무력·지력·정무·매력 중 가장 낮은 능력을 수련합니다."),
                   ("내정", "develop", "현재 소속 영지의 번영과 군량을 늘립니다."),
                   ("징병", "recruit", "현재 영지에서 최대 1,000명까지 병사를 모집합니다."),
                   ("순찰", "patrol", "현재 영지의 민심과 요새 수비를 개선합니다.")]
        for i, (label, action, tip) in enumerate(actions):
            x, y = 1158 + (i % 2) * 122, 513 + (i // 2) * 43
            p.button((x, y, 116, 36), label, "do", action, tooltip=tip)
        p.button((1158, 603, 116, 36), "장수 교류", "bond_modal", "bond", tooltip="현재 위치의 장수와 인연을 쌓습니다.")
        p.button((1280, 603, 116, 36), "모략", "bond_modal", "scheme")
        p.button((1158, 647, 116, 38), "이동", "do", "travel", enabled=not here and loc.id in world.locations[player.location].neighbors,
                 tooltip="직접 연결된 비교전 지역을 선택하고 이동하세요.")
        p.button((1280, 647, 116, 38), "진군", "do", "attack", primary=True, enabled=self.engine.attack_error(player, loc.id) is None,
                 tooltip=self.engine.attack_error(player, loc.id) or "선택한 적 영지로 진군합니다.")
        p.button((1158, 693, 238, 33), "현재 영지의 세력에 임관", "do", "enlist", enabled=world.locations[player.location].faction != player.faction)
        p.button((1158, 738, 238, 33), "과업과 역사적 배경", "quests", size=15)
        for i, quest in enumerate(sorted(world.quests, key=lambda q: q.complete)[:3]):
            label = "완료" if quest.complete else f"{min(quest.progress, quest.target)}/{quest.target}"
            p.text(quest.title, 1158, 782 + i * 28, 14, TEXT)
            p.text(label, 1396, 782 + i * 28, 14, TEAL if quest.complete else MUTED, align="right")

    def draw_world_roster(self) -> None:
        p = self.p
        p.panel((264, 113, 854, 765))
        p.text("200명의 의지", 284, 135, 24, TEXT, True)
        self.filters(284, 181, 814)
        self.draw_roster(284, 233, 814, 12)
        p.panel((1138, 113, 278, 765))
        self.officer_detail(self.selected_officer, 1158, 140, 238, compact=True)
        officer = self.world.officers[self.selected_officer]
        p.text(f"야망 {officer.traits['ambition']} · 명예 {officer.traits['honor']} · 공감 {officer.traits['empathy']}", 1158, 583, 14, MUTED, width=238)
        p.text("판단의 이유", 1158, 607, 19, GOLD)
        for i, decision in enumerate(evaluate(self.world, officer)[:3]):
            p.text(f"{i + 1}. {ACTION_NAMES[decision.action]}", 1158, 643 + i * 60, 16, TEAL)
            p.paragraph(decision.reason, 1158, 668 + i * 60, 238, 14, MUTED, max_lines=2, line_height=19)
        p.button((1158, 833, 238, 31), "이 장수의 기억 읽기", "memories", size=15)

    def draw_diplomacy(self) -> None:
        p, world = self.p, self.world
        player = world.officers[world.player]
        p.text("깃발 아래의 약속", 267, 116, 24, TEXT, True)
        p.text("대장 이상은 40금을 사용해 12주 불가침 조약을 제안할 수 있습니다.", 267, 159, 17, MUTED)
        for i, faction in enumerate(world.factions.values()):
            x, y = 264 + (i % 3) * 390, 213 + (i // 3) * 286
            p.panel((x, y, 374, 265))
            pygame.draw.rect(self.canvas, faction.color, (x + 1, y + 1, 6, 263), border_radius=4)
            holdings = world.holdings(faction.id)
            p.text(faction.name, x + 24, y + 23, 25, TEXT, True, width=326)
            p.text(faction.motto, x + 24, y + 64, 16, faction.color)
            p.text(f"군주  {world.officers[faction.ruler].name}", x + 24, y + 99, 17, MUTED, width=325)
            p.text(f"영지 {len(holdings)}곳  /  병력 {sum(s.troops for s in holdings):,}명", x + 24, y + 133, 18, TEXT)
            relation = "소속 세력" if faction.id == player.faction else "교전 중" if world.at_war(player.faction, faction.id) else "평화"
            treaty = world.treaties.get(pair(player.faction, faction.id), 0) if player.faction else 0
            if treaty > world.turn:
                relation = f"불가침 · {treaty - world.turn}주 남음"
            if faction.eliminated:
                relation = "붕괴한 세력"
            p.text(relation, x + 24, y + 171, 17, RED if relation == "교전 중" else GOLD)
            if faction.id == player.faction:
                names = {"balanced": "균형", "aggressive": "공격", "defensive": "방어", "mercantile": "상업"}
                p.button((x + 24, y + 211, 326, 34), f"통치 방침: {names[faction.doctrine]} · 변경", "do", "policy", enabled=player.rank == 4)
            else:
                p.button((x + 24, y + 211, 200, 34), "외교 사절 · 40금", "negotiate", faction.id,
                         enabled=bool(player.faction and player.rank >= 2 and player.gold >= 40 and not faction.eliminated))
                p.button((x + 234, y + 211, 116, 34), "개전 건의", "petition_war", faction.id, size=15,
                         enabled=bool(player.faction and player.rank >= 2 and player.gold >= 25 and not faction.eliminated and not world.at_war(player.faction, faction.id) and treaty <= world.turn), tooltip="25금으로 군사 회의를 엽니다. 군주의 결정은 항상 수락됩니다.")
        p.text("세력 전체의 병력은 여러 영지의 합계입니다. 한 전장에서 지휘하는 병력은 각 측 최대 1,000명입니다.", 267, 824, 16, MUTED)

    def draw_chronicle(self) -> None:
        p, world = self.p, self.world
        p.panel((264, 113, 1152, 765))
        p.text("왕국의 연대기", 287, 134, 26, TEXT, True)
        p.text("당신이 오기 전에도, 장수들은 살고 싸우고 기억했습니다.", 287, 177, 17, MUTED)
        events = list(reversed(world.chronicles))
        pages = max(1, math.ceil(len(events) / 17))
        self.log_page = min(self.log_page, pages - 1)
        for i, event in enumerate(events[self.log_page * 17:(self.log_page + 1) * 17]):
            y = 223 + i * 34
            if i % 2 == 0:
                pygame.draw.rect(self.canvas, PANEL_LIGHT, (283, y - 2, 1112, 31), border_radius=3)
            color = RED if event.kind in ("battle", "war", "fall", "capture") else TEAL if event.kind in ("bond", "quest", "promotion") else MUTED
            p.text(f"{742 + event.turn // 48}년 {event.turn % 48 + 1:02}주", 296, y + 2, 14, GOLD)
            p.text(event.text, 435, y + 1, 16, color, width=938)
        p.button((287, 825, 106, 33), "더 최근", "log_page", -1, enabled=self.log_page > 0)
        p.text(f"{self.log_page + 1} / {pages}  ·  최근 {len(events)}개 사건", 840, 832, 15, MUTED, align="center")
        p.button((1288, 825, 106, 33), "더 과거", "log_page", 1, enabled=self.log_page < pages - 1)

    def field_point(self, x: float, y: float) -> tuple[int, int]:
        return IsometricProjection((24, 148, 1068, 574)).world_point(x, y)

    def battle_click(self, point, *, right: bool) -> None:
        if not self.battle or self.battle.finished or not pygame.Rect(24, 148, 1068, 574).collidepoint(point):
            return
        coordinates = IsometricProjection((24, 148, 1068, 574)).world_at(point)
        if coordinates is None:
            return
        x, y = coordinates
        nearby = min((u for u in self.battle.units if u.alive), key=lambda u: math.dist(self.field_point(u.x, u.y), point), default=None)
        if right:
            if nearby and nearby.side != self.battle.controlled_side and math.dist(self.field_point(nearby.x, nearby.y), point) < 20:
                self.battle.issue(self.selected_units, "advance", target=nearby.id)
            else:
                self.battle.issue(self.selected_units, "move", (x, y))
            self.record("battle_point", {"point": [x, y], "units": list(self.selected_units), "time": self.battle.time})
            self.save(announce=False)
        elif nearby and nearby.side == self.battle.controlled_side and math.dist(self.field_point(nearby.x, nearby.y), point) < 20:
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                if nearby.id in self.selected_units:
                    self.selected_units.remove(nearby.id)
                else:
                    self.selected_units.append(nearby.id)
            else:
                self.selected_units = [nearby.id]

    def draw_battle(self) -> None:
        p, battle = self.p, self.battle
        if battle is None:
            return
        p.text("ISOMETRIC FIELD COMMAND", 24, 24, 15, GOLD)
        title = battle.field.name + (" · 전술 연습" if self.demo else " 전투")
        p.text(title, 24, 51, 31, TEXT, True)
        p.text(f"경과 {int(battle.time)}초  ·  {TERRAIN_NAMES[battle.terrain]}", 665, 36, 19, MUTED)
        p.button((960, 29, 113, 42), "계속" if self.paused else "일시정지", "pause", primary=True, enabled=not battle.finished)
        p.button((1084, 29, 89, 42), f"속도 {self.speed}×", "speed", enabled=not battle.finished)
        p.button((1184, 29, 106, 42), "지휘 안내", "help")
        p.button((1301, 29, 115, 42), "철수", "retreat", enabled=not battle.finished)
        p.text("좌클릭 선택  ·  Shift 다중 선택  ·  우클릭 이동 / 적 공격  ·  Space 일시정지  ·  A 전체 선택", 24, 106, 17, MUTED)
        field = pygame.Rect(24, 148, 1068, 574)
        projection = draw_field(p, battle.field, field, structures=False)
        labels = []
        numbers = {u.id: i + 1 for side in (0, 1) for i, u in enumerate(u for u in battle.units if u.side == side)}
        layers = [(item[0], "structure", item) for item in structure_items(battle.field, projection)]
        layers.extend((u.x * battle.field.width / 100 + u.y * battle.field.height / 60, "unit", u) for u in battle.units if u.alive)
        for _, kind, item in sorted(layers, key=lambda entry: (entry[0], entry[1])):
            if kind == "structure":
                draw_structure(self.canvas, projection, item)
                continue
            unit = item
            x, y = self.field_point(unit.x, unit.y)
            color = TEAL if unit.side == battle.controlled_side else RED
            pygame.draw.ellipse(self.canvas, color, (x - 16, y - 7, 32, 14), 1)
            if unit.id in self.selected_units:
                pygame.draw.ellipse(self.canvas, GOLD, (x - 20, y - 9, 40, 18), 2)
                if unit.destination:
                    pygame.draw.line(self.canvas, GOLD, (x, y), self.field_point(*unit.destination), 1)
                elif unit.target is not None and unit.order in ("advance", "charge", "flank"):
                    target = next((u for u in battle.units if u.id == unit.target and u.alive), None)
                    if target:
                        endpoint = self.field_point(target.x, target.y)
                        pygame.draw.line(self.canvas, (148, 91, 64), (x, y), endpoint, 1)
                        pygame.draw.circle(self.canvas, RED, endpoint, 7, 1)
            sprite = unit_sprite(unit.kind, math.cos(unit.facing) + math.sin(unit.facing) >= 0, 34 if unit.kind == "cavalry" else 28)
            if sprite:
                self.canvas.blit(sprite, (x - sprite.get_width() // 2, y - sprite.get_height() + 5))
            else:
                for i in range(6):
                    xx, yy = x - 9 + i % 3 * 7, y - 4 + i // 3 * 5
                    pygame.draw.line(self.canvas, color, (xx, yy - 8), (xx, yy), 3)
                    pygame.draw.circle(self.canvas, (205, 205, 182), (xx, yy - 10), 2)
            side_label = "아" if unit.side == battle.controlled_side else "적"
            labels.append((f"{side_label}{numbers[unit.id]} {UNIT_NAMES[unit.kind]} {int(unit.soldiers)}", x, y, color))
            p.bar((x - 25, y + 18, 50, 4), unit.morale, color=color)
        # Labels stay separate from depth-sorted bodies and never intercept orders.
        placed = []
        for label, x, y, color in labels:
            width = p.font(13, True).size(label)[0] + 12
            rect = pygame.Rect(0, 0, width, 22)
            for offset in [-36 - i * 26 for i in range(10)] + [32 + i * 26 for i in range(10)]:
                rect.midtop = (x, y + offset)
                rect.clamp_ip(field.inflate(-8, -8))
                if not any(rect.inflate(6, 4).colliderect(other) for other in placed):
                    break
            placed.append(rect.copy())
            pygame.draw.line(self.canvas, color, (x, y - 10), rect.center, 1)
            p.panel(rect, PANEL, color, radius=3)
            p.text(label, rect.centerx, rect.y + 2, 13, TEXT, True, align="center")
        pygame.draw.rect(self.canvas, LINE, field, 1, border_radius=6)
        if self.paused and not battle.finished:
            p.panel((433, 156, 250, 37), PANEL, GOLD)
            p.text("작전 지시 중 · 일시정지", 558, 165, 16, GOLD, align="center")
        p.panel((1112, 148, 304, 574))
        p.text("전황", 1132, 169, 23, TEXT, True)
        for index, (side, label, color) in enumerate(((battle.controlled_side, "아군", TEAL), (1 - battle.controlled_side, "적군", RED))):
            y = 215 + index * 64
            p.text(label, 1132, y, 17, color)
            p.text(f"{battle.totals(side)} / {battle.deployed[side]}명", 1396, y, 18, TEXT, align="right")
            p.bar((1132, y + 30, 264, 8), battle.totals(side), max(1, battle.deployed[side]), color)
        p.text("선택한 부대", 1132, 365, 18, GOLD)
        selected = [u for u in battle.units if u.id in self.selected_units]
        if selected:
            unit = selected[0]
            p.text(unit.name if len(selected) == 1 else f"{len(selected)}개 부대 동시 지휘", 1132, 399, 19, TEXT, width=264)
            p.text(f"{UNIT_NAMES[unit.kind]}  ·  사기 {unit.morale:.0f}  ·  결속 {unit.cohesion:.0f}", 1132, 432, 16, MUTED)
            orders = {"advance": "전진", "charge": "돌격", "hold": "방어", "flank": "우회", "move": "이동"}
            target = next((u for u in battle.units if u.id == unit.target and u.alive), None)
            detail = "지정 지점" if unit.destination else target.name if target and unit.order != "hold" else "현재 진형"
            p.text(f"명령: {orders[unit.order]} · {detail}", 1132, 456, 13, GOLD, width=264)
        for i, (label, order) in enumerate((("전진", "advance"), ("돌격", "charge"), ("방어", "hold"), ("우회", "flank"))):
            p.button((1132 + (i % 2) * 136, 478 + (i // 2) * 46, 128, 38), label, "order", order, enabled=not battle.finished, primary=bool(selected and all(u.order == order for u in selected)))
        p.button((1132, 585, 264, 39), "지휘관 격려 · 사기 회복", "rally", enabled=not battle.finished and battle.time >= battle.rally_ready[battle.controlled_side])
        p.button((1132, 636, 264, 37), "전 부대 선택  A", "all", enabled=not battle.finished)
        p.text(f"거점 확보  아군 {battle.control[battle.controlled_side]:.0f}초 / 적군 {battle.control[1-battle.controlled_side]:.0f}초", 1132, 682, 14, GOLD)
        p.text("적 와해 또는 180초 병력·사기·거점 판정", 1132, 704, 12, MUTED)
        p.text("거점 단독 확보 1초마다 판정 점수 +2", 24, 863, 15, GOLD)
        ours = [u for u in battle.units if u.side == battle.controlled_side]
        for i, unit in enumerate(ours):
            x, y = 24 + i * 218, 744
            rect = p.panel((x, y, 207, 104), PANEL_LIGHT if unit.id in self.selected_units else PANEL, GOLD if unit.id in self.selected_units else LINE)
            p.text(f"{i + 1}  {UNIT_NAMES[unit.kind]}  {int(unit.soldiers)}명", x + 13, y + 12, 17, TEAL if unit.alive else MUTED)
            p.text(unit.name, x + 13, y + 40, 14, TEXT, width=183)
            p.bar((x + 13, y + 75, 182, 7), unit.morale, color=TEAL)
            p.buttons.append((rect, "unit", unit.id, unit.alive))
        if battle.finished:
            p.panel((337, 304, 470, 240), PANEL_LIGHT, GOLD)
            p.text("승전" if battle.winner == battle.controlled_side else "패전", 572, 327, 46, GOLD if battle.winner == battle.controlled_side else RED, True, align="center")
            p.text(battle.reason, 572, 390, 20, TEXT, align="center")
            p.text(f"아군 손실 {battle.deployed[battle.controlled_side] - battle.totals(battle.controlled_side)}명  ·  적군 손실 {battle.deployed[1-battle.controlled_side] - battle.totals(1-battle.controlled_side)}명", 572, 430, 17, MUTED, align="center")
            p.button((386, 483, 372, 42), "전투 연습 마치기" if self.demo else "전투 결과 반영 · 왕국으로", "battle_done", primary=True)

    def draw_modal(self) -> None:
        p = self.p
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 180))
        self.canvas.blit(veil, (0, 0))
        # A modal blocks every underlying click, including empty parts of the veil.
        p.buttons.clear()
        p.panel((298, 123, 844, 650), PANEL, GOLD)
        p.button((1012, 144, 106, 35), "닫기  Esc", "close")
        if self.modal == "quests":
            p.text("나의 과업 · 다음 연대기까지 " + str(max(0, self.world.chapter_end - self.world.turn)) + "주", 330, 157, 27, GOLD, True)
            for i, quest in enumerate(self.world.quests):
                y = 218 + i * 100
                label = "완료" if quest.complete else f"{min(quest.progress, quest.target)}/{quest.target}"
                p.text(quest.title, 330, y, 20, TEXT, True)
                p.text(f"{label}  ·  보상 {quest.reward}", 1095, y + 3, 16, TEAL, align="right")
                p.paragraph(quest.description, 330, y + 28, 768, 16, MUTED, max_lines=2, line_height=22)
                if quest.origin:
                    p.text("역사 근거: " + quest.origin, 330, y + 74, 13, GOLD, width=766)
        elif self.modal == "editor_discard":
            p.text("저장하지 않은 전장", 330, 188, 30, GOLD, True)
            p.paragraph("편집 내용을 저장하거나 현재 작업을 버리고 이동할 수 있습니다.", 330, 245, 770, 20, TEXT)
            p.button((330, 345, 370, 48), "작업 버리고 이동", "editor_discard")
            p.button((725, 345, 370, 48), "편집 계속", "close", primary=True)
        elif self.modal == "help":
            p.text("왕국을 살아가는 법", 330, 156, 30, TEXT, True)
            sections = [
                ("01  한 장수의 삶", "장수를 선택하고 수련·내정·순찰·징병·교류를 수행하세요. 행동마다 1주가 흐르고 다른 199명도 행동합니다. 재야 장수는 평화로운 영지로 이동해 임관할 수 있습니다."),
                ("02  명성과 인연", "기사 35, 대장 120, 성주 260의 명성을 모아 승진합니다. 친밀도 60 이상은 맹우입니다. 함께 싸운 경험과 모략은 인연과 기억에 남아 AI의 판단과 부대 결속에 영향을 줍니다."),
                ("03  지도와 진군", "영지를 클릭해 소유 세력·주둔군·군량을 확인하세요. 도로가 연결된 지역으로 이동합니다. 현재 영지가 아군이며 기사 이상일 때 인접한 교전 세력의 영지로 진군할 수 있습니다."),
                ("04  전장 지휘", "전투는 일시정지 상태로 시작합니다. 좌클릭으로 부대를 선택하고 우클릭으로 이동하거나 적을 공격하세요. A는 전체 선택, 1~5는 개별 선택, Space는 정지/재개입니다. 전진·돌격·방어·우회와 격려를 활용하세요."),
                ("05  천하통일과 저장", "최종 목표는 소속 세력으로 성 20개와 거점 30개를 모두 다스리는 천하통일입니다. 96주마다 연대기를 기록하며 캠페인은 계속됩니다. 전투는 적 와해 또는 180초의 병력·사기·거점 판정으로 끝납니다. F5 저장, F9 복구, R 문제 제보. 공격받으면 방어전을 지휘합니다."),
            ]
            y = 217
            for title, text in sections:
                p.text(title, 330, y, 19, GOLD, True)
                y = p.paragraph(text, 330, y + 30, 780, 17, MUTED, max_lines=3, line_height=25) + 20
        elif self.modal == "residents":
            player = self.world.officers[self.world.player]
            residents = [o for o in self.world.residents(player.location) if o.id != player.id]
            p.text("인연을 쌓을 장수" if self.pending_action == "bond" else "모략의 대상", 330, 157, 29, TEXT, True)
            p.text(f"현재 위치: {self.world.locations[player.location].name}  ·  {len(residents)}명", 330, 202, 17, MUTED)
            pages = max(1, math.ceil(len(residents) / 8))
            self.modal_page = min(self.modal_page, pages - 1)
            for i, officer in enumerate(residents[self.modal_page * 8:(self.modal_page + 1) * 8]):
                y = 256 + i * 49
                p.text(officer.name, 344, y + 6, 19, TEXT)
                p.text(f"친밀도 {self.world.relationship(player.id, officer.id):.0f}", 748, y + 8, 17, GOLD)
                p.button((963, y, 140, 37), "교류" if self.pending_action == "bond" else "모략", "target_action", officer.id)
            if not residents:
                p.paragraph("현재 지역에 만날 장수가 없습니다. 다른 아군 영지로 이동하면 새로운 인연을 찾을 수 있습니다.", 330, 275, 740, 20, MUTED)
            p.button((330, 709, 110, 34), "이전", "resident_page", -1, enabled=self.modal_page > 0)
            p.text(f"{self.modal_page + 1} / {pages}", 720, 716, 16, MUTED, align="center")
            p.button((1002, 709, 110, 34), "다음", "resident_page", 1, enabled=self.modal_page < pages - 1)
        elif self.modal == "memories":
            officer = self.world.officers[self.selected_officer]
            p.text(f"{officer.name}의 기억", 330, 157, 28, TEXT, True)
            p.text("승전과 패전, 신뢰와 배신은 이후의 선택에 남습니다.", 330, 204, 17, MUTED)
            for i, memory in enumerate(reversed(officer.memories[-8:])):
                yy = 260 + i * 55
                p.text(f"{memory.turn}주", 330, yy, 15, GOLD)
                p.paragraph(memory.text, 410, yy, 680, 17, TEAL if memory.weight > 0 else RED, max_lines=2, line_height=22)
            if not officer.memories:
                p.text("아직 특별한 기억이 없습니다.", 330, 270, 20, MUTED)
        elif self.modal == "retreat":
            p.text("철수 명령", 330, 172, 32, GOLD, True)
            p.paragraph("철수하면 이번 전투에서 패배합니다. 살아남은 병력은 복귀하며 전장 경험은 장수의 기억에 남습니다.", 330, 258, 740, 24, TEXT)
            p.button((330, 457, 360, 53), "전투로 돌아가기", "close", primary=True)
            p.button((750, 457, 360, 53), "철수 확정", "confirm_retreat")
