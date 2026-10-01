import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame
import pytest

from chaos_kingdom.core.campaign import create_campaign
from chaos_kingdom.core.generation import select_player
from chaos_kingdom.core.storage import digest
from chaos_kingdom.ui.app import App
from chaos_kingdom.ui.battlefield_view import IsometricProjection


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOS_KINGDOM_HOME", str(tmp_path))
    world = create_campaign(742, 24)
    select_player(world, "o024")
    instance = App(headless=True, world=world)
    yield instance
    pygame.quit()


@pytest.mark.parametrize("screen,tab", [("menu", "map"), ("scenarios", "map"), ("select", "map"),
                                      ("world", "map"), ("world", "officers"), ("world", "diplomacy"), ("world", "chronicle")])
def test_all_screens_draw_and_buttons_stay_inside_canvas(app, screen, tab):
    app.screen, app.tab = screen, tab
    app.draw()
    assert app.p.buttons
    bounds = app.canvas.get_rect()
    assert all(bounds.contains(rect) for rect, _, _, _ in app.p.buttons)


def test_modal_blocks_underlying_buttons(app):
    app.modal = "help"
    app.draw()
    assert {action for _, action, _, _ in app.p.buttons} == {"close"}


def test_battle_ui_and_demo_do_not_mutate_campaign(app):
    old_world = digest(app.world.data())
    app.start_demo()
    app.draw()
    app.battle.retreat()
    app.draw()
    app.dispatch("battle_done")
    assert digest(app.world.data()) == old_world
    assert app.screen == "menu"


def test_save_load_and_player_action_via_ui(app):
    app.do_action("rest")
    turn = app.world.turn
    assert app.save_path.exists()
    app.world.turn = 1000
    app.load()
    assert app.world.turn == turn
    assert app.screen == "world"


def test_editor_ui_discard_modal_and_test_return(app):
    app.dispatch("editor")
    app.draw()
    assert app.screen == "editor"
    assert all(app.canvas.get_rect().contains(rect) for rect, _, _, _ in app.p.buttons)
    app.editor.dirty = True
    app.dispatch("menu")
    app.draw()
    assert app.modal == "editor_discard"
    assert {action for _, action, _, _ in app.p.buttons} == {"close", "editor_discard"}
    app.dispatch("close")
    snapshot = app.editor.snapshot()
    original = digest(app.world.data())
    app.dispatch("editor_test")
    app.draw()
    assert app.demo and app.screen == "battle"
    app.battle.retreat()
    app.dispatch("battle_done")
    assert app.screen == "editor" and app.editor.snapshot() == snapshot
    assert digest(app.world.data()) == original


def test_ui_mid_battle_save_load(app):
    from chaos_kingdom.simulation.battle import Battle
    source, target = app.world.locations["s20"], app.world.locations["s21"]
    app.battle = Battle(app.world, source.id, target.id, app.world.player, 33, interactive=True)
    app.demo = False
    app.battle.update(1)
    before = digest(app.battle.data())
    app.save(announce=False)
    app.battle = None
    app.load()
    assert app.screen == "battle" and app.paused
    assert digest(app.battle.data()) == before


def test_quests_modal_and_chapter_continuation(app):
    app.dispatch("quests")
    app.draw()
    assert app.modal == "quests" and len(app.world.quests) == 5
    assert {action for _, action, _, _ in app.p.buttons} == {"close"}
    app.modal = None
    app.world.outcome = "첫 장의 끝"
    app.dispatch("continue_chapter")
    assert app.world.outcome is None and app.world.chapter_end == app.world.turn + 96


def test_keyboard_events_and_editor_field_label(app):
    app.dispatch("editor")
    editor = app.editor
    before = editor.snapshot()
    editor.brush = "#" if editor.field.tiles[6][6] != "#" else "."
    editor.begin(IsometricProjection(editor.rect).cell_point(6.5, 6.5), 1)
    editor.end()
    assert editor.dirty
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z))
    assert editor.snapshot() == before and not editor.dirty
    app.dispatch("editor_test")
    assert app.battle.terrain == editor.field.biome
    assert app.paused
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    assert not app.paused


def test_editor_grid_toggle_changes_only_view_and_roundtrips(app):
    app.dispatch("editor")
    app.draw()
    original = pygame.image.tobytes(app.canvas, "RGB")
    field, world = app.editor.snapshot(), digest(app.world.data())
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g))
    app.draw()
    assert app.editor.show_grid and not app.editor.dirty
    assert pygame.image.tobytes(app.canvas, "RGB") != original
    assert app.editor.snapshot() == field and digest(app.world.data()) == world
    app.dispatch("editor_grid")
    app.draw()
    assert not app.editor.show_grid
    assert pygame.image.tobytes(app.canvas, "RGB") == original


def test_terrain_render_updates_after_edit_undo_and_resize(app):
    from chaos_kingdom.ui.battlefield_view import BattlefieldRenderer
    app.dispatch("editor")
    editor = app.editor
    renderer = BattlefieldRenderer(capacity=2)
    before = editor.snapshot()
    first = renderer._surface(editor.field, (320, 200))
    first_pixels = pygame.image.tobytes(first, "RGBA")
    editor.brush = "w" if editor.field.tiles[6][6] != "w" else "."
    editor.begin(IsometricProjection(editor.rect).cell_point(6.5, 6.5), 1)
    editor.end()
    edited = renderer._surface(editor.field, (320, 200))
    assert pygame.image.tobytes(edited, "RGBA") != first_pixels
    editor.history()
    restored = renderer._surface(editor.field, (320, 200))
    assert pygame.image.tobytes(restored, "RGBA") == first_pixels
    assert editor.snapshot() == before
    resized = renderer._surface(editor.field, (640, 400))
    assert resized.get_size() == (640, 400) and len(renderer._cache) <= 2


def test_isometric_selection_and_orders_match_drawn_units_and_reject_empty_background(app):
    app.start_demo()
    unit = app.battle.active(app.battle.controlled_side)[0]
    app.selected_units = []
    app.battle_click(app.field_point(unit.x, unit.y), right=False)
    assert app.selected_units == [unit.id]
    point = IsometricProjection((24, 148, 1068, 574)).cell_point(8.5, 8.5)
    app.battle_click(point, right=True)
    assert unit.order == "move" and unit.destination
    assert app.battle.field.walkable(app.battle.field.cell(*unit.destination))
    before = digest(app.battle.data())
    app.battle_click((25, 149), right=True)
    assert digest(app.battle.data()) == before


def test_editor_isometric_gate_brush_and_empty_background_do_not_pick_wrong_cells(app):
    app.dispatch("editor")
    editor = app.editor
    before = editor.snapshot()
    editor.brush = "g"
    editor.begin((editor.rect.left + 1, editor.rect.top + 1), 1)
    editor.end()
    assert editor.snapshot() == before and not editor.dirty
    editor.begin(IsometricProjection(editor.rect).cell_point(10.5, 6.5), 1)
    editor.end()
    assert editor.field.tiles[6][10] == "g" and editor.dirty
    editor.history()
    assert editor.snapshot() == before and not editor.dirty


@pytest.mark.parametrize("view", ["menu", "battle", "editor"])
def test_transparent_art_preserves_an_opaque_frame_with_cocoa_pixel_format(tmp_path, monkeypatch, view):
    from chaos_kingdom.ui.app import WIDTH, HEIGHT

    monkeypatch.setenv("CHAOS_KINGDOM_HOME", str(tmp_path))
    original_surface = pygame.Surface

    def cocoa_surface(size, *args, **kwargs):
        # Reproduce the observed Cocoa default under SDL's dummy test driver:
        # a 32-bit alpha mask, but no per-pixel alpha blending flag.
        if tuple(size) == (WIDTH, HEIGHT) and not args and not kwargs:
            return original_surface(size, 0, 32, (0xFF0000, 0xFF00, 0xFF, 0xFF000000))
        return original_surface(size, *args, **kwargs)

    monkeypatch.setattr(pygame, "Surface", cocoa_surface)
    instance = App(headless=True)
    try:
        if view == "battle":
            instance.start_demo()
        elif view == "editor":
            instance.dispatch("editor")
        instance.draw()
        # Art and soft masks may be transparent; the completed game frame must
        # retain its opaque backdrop at every pixel, including sprite padding.
        assert set(pygame.image.tobytes(instance.canvas, "RGBA")[3::4]) == {255}
        if view == "menu":
            with_art = instance.canvas.get_at((300, 428))
            from chaos_kingdom.ui import app as app_module
            from chaos_kingdom.ui.assets import scaled_asset

            def without_ornament(name, size):
                return None if name == "ui-frame.png" else scaled_asset(name, size)

            monkeypatch.setattr(app_module, "scaled_asset", without_ornament)
            instance.draw()
            assert with_art == instance.canvas.get_at((300, 428))
    finally:
        pygame.quit()
