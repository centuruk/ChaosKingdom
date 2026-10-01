import json
from pathlib import Path
import zipfile

import pytest

from chaos_kingdom.core.battlefields import Battlefield, DATA_DIR, load_battlefield, save_battlefield
from chaos_kingdom.core.diagnostics import export_report
from chaos_kingdom.core.generation import generate_world, select_player
from chaos_kingdom.core.models import Memory
from chaos_kingdom.core.storage import digest, load_battle, load_world, save_world
from chaos_kingdom.simulation.battle import Battle
from chaos_kingdom.simulation.engine import Engine
from chaos_kingdom.ui.editor import MapEditor
from chaos_kingdom.ui.assets import manifest, portrait


def battlefield(**changes):
    data = json.loads(json.dumps(load_battlefield("s00", custom=False).data()))
    data.update(changes)
    return Battlefield(**data)


def battle_world():
    world = generate_world()
    a, b = world.locations["s20"], world.locations["s21"]
    a.faction, b.faction, a.troops, b.troops = "f0", "f2", 1000, 450
    commander = world.officers["o024"]
    commander.location, commander.faction = a.id, "f0"
    return world, a, b, commander


def test_all_regional_maps_are_unique_connected_and_stable():
    maps = [Battlefield.from_data(json.loads(path.read_text())) for path in sorted(DATA_DIR.glob("*.json"))]
    assert len(maps) == len({tuple(m.tiles) for m in maps}) == 50
    for m in maps:
        for side in m.spawns:
            for spawn in side:
                path = m.path(spawn, m.objective)
                assert path and all(m.walkable(cell) for cell in path)
                assert all(abs(a[0]-b[0])+abs(a[1]-b[1]) == 1 for a, b in zip(path, path[1:]))
    a, b = generate_world(1), generate_world(999)
    assert [s.terrain for s in a.locations.values()] == [s.terrain for s in b.locations.values()]


def test_river_crossing_uses_bridge_and_walls_block_sight():
    grid = ["." * 32 for _ in range(20)]
    grid = [row[:15] + "w" + row[16:] for row in grid]
    grid[10] = "." * 15 + "b" + "." * 16
    m = battlefield(tiles=grid, objective=[16, 10])
    m.validate()
    path = m.path((2, 2), (29, 2))
    assert (15, 10) in path
    grid[10] = "." * 15 + "#" + "." * 16
    broken = battlefield(tiles=grid, objective=[16, 10])
    assert not broken.visible(broken.point((14, 10)), broken.point((16, 10)))
    with pytest.raises(ValueError, match="경로"):
        broken.validate()


def test_editor_undo_redo_save_reload_and_invalid_map_protection(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOS_KINGDOM_HOME", str(tmp_path))
    editor = MapEditor(generate_world())
    before = editor.snapshot()
    editor.brush = "h"
    editor.begin((32+32*6+16, 185+32*6+16), 1)
    editor.end()
    changed = editor.snapshot()
    assert changed != before
    editor.history()
    assert editor.snapshot() == before
    editor.history(False)
    assert editor.snapshot() == changed
    editor.save()
    assert not editor.dirty
    loaded = load_battlefield(editor.field.region)
    assert loaded.tiles == editor.field.tiles
    assert loaded.revision == editor.field.revision
    editor.field.tiles = ["#" * 32 for _ in range(20)]
    with pytest.raises(ValueError):
        editor.save()
    assert load_battlefield(loaded.region).tiles == loaded.tiles


def test_mid_battle_roundtrip_continues_identically(tmp_path):
    world, source, target, officer = battle_world()
    select_player(world, officer.id)
    first = Battle(world, source.id, target.id, officer.id, 717, interactive=True)
    first.issue([0, 1, 2], "move", (62, 21))
    for _ in range(25):
        first.update(1)
    path = tmp_path / "save.json"
    save_world(world, path, battle=first)
    loaded = load_world(path)
    second = load_battle(path, loaded)
    assert digest(first.data()) == digest(second.data())
    for _ in range(35):
        first.update(.8)
        second.update(.8)
    assert digest(first.data()) == digest(second.data())
    save_world(loaded, path, battle=second)
    assert path.with_suffix(".backup.json").is_file()
    payload = json.loads(path.read_text())
    payload["battle"]["time"] += 1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="손상"):
        load_battle(path, loaded)


def test_defense_interrupts_week_without_double_advancing(tmp_path):
    world, source, target, commander = battle_world()
    defender = world.officers["o002"]
    defender.location, defender.faction, defender.rank = target.id, "f2", 3
    select_player(world, defender.id)
    world.turn = 3
    engine = Engine(world)
    # Force just this attack candidate; the battle itself uses the normal regional terrain.
    for location in world.locations.values():
        if location.id != source.id:
            location.troops = min(location.troops, 200)
    source.troops, target.troops = 1000, 120
    engine._campaigns()
    assert world.pending_battle is not None
    battle = Battle.from_data(world, world.pending_battle)
    assert battle.controlled_side == 1 and defender.id in {u.officer for u in battle.units if u.side == 1}
    before = world.turn
    engine.step()
    assert world.turn == before
    battle.issue([u.id for u in battle.active(1)], "move", (82, 30))
    assert all(u.order == "move" for u in battle.active(1))
    battle.update(1)
    path = tmp_path / "defense.json"
    save_world(world, path, battle=battle)
    restored = load_battle(path, load_world(path))
    assert digest(restored.data()) == digest(battle.data())
    battle.retreat()
    assert battle.winner == 0
    engine.resolve_battle(battle)
    assert world.turn == before and world.pending_battle is None
    world.validate()


def test_revision_one_battle_snapshot_survives_default_map_update():
    # An actual map from the previous beta archive, not regenerated by today's code.
    old_path = Path(__file__).resolve().parents[1] / "docs/examples/battlefield-v1.json"
    old = Battlefield.from_data(json.loads(old_path.read_text(encoding="utf-8")))
    assert old.revision == 1
    assert old.tiles != load_battlefield(old.region, custom=False).tiles
    world, source, target, officer = battle_world()
    first = Battle(world, source.id, target.id, officer.id, 717, battlefield=old)
    first.update(2.4)
    restored = Battle.from_data(world, first.data())
    assert restored.field.data() == old.data()
    for _ in range(20):
        first.update(.8)
        restored.update(.8)
    assert digest(first.data()) == digest(restored.data())


@pytest.mark.parametrize("region", ["s00", "s08", "s19", "s21", "s43"])
def test_tactical_units_never_enter_impassable_tiles(region):
    world, source, target, officer = battle_world()
    m = load_battlefield(region, custom=False)
    battle = Battle(world, source.id, target.id, officer.id, 72, battlefield=m)
    for _ in range(180):
        battle.update(1)
        assert all(m.walkable(m.cell(u.x, u.y)) for u in battle.units)
    assert battle.finished


def test_history_creates_personal_hooks_and_chapter_continues_toward_unification():
    world, source, target, officer = battle_world()
    officer.remember(Memory(1, "defeat", "o002", -30, f"{target.name}에서 패전했다."))
    world.log("battle", f"{target.name} 전투 — 함락.", ["o002"], target.id)
    select_player(world, officer.id)
    assert len(world.quests) == 5
    reclaim = next(q for q in world.quests if q.kind == "reclaim")
    assert reclaim.reference == target.id and reclaim.origin
    target.faction = officer.faction
    engine = Engine(world)
    engine._story_progress()
    assert reclaim.complete
    world.chapter_end = world.turn + 1
    engine.step()
    if world.pending_battle:
        battle = Battle.from_data(world, world.pending_battle)
        battle.auto_resolve()
        engine.resolve_battle(battle)
    assert world.outcome is None and world.chapter_report
    assert world.event_counts["chapter"] == 1
    assert world.chapter_end > world.turn
    before = world.turn
    assert engine.player_action("rest").ok
    assert world.turn == before + 1


def test_local_bug_bundle_contains_reproducible_state_and_all_maps(tmp_path):
    world, source, target, officer = battle_world()
    battle = Battle(world, source.id, target.id, officer.id, 77)
    path = export_report(world, [{"action": "rest"}], battle, folder=tmp_path)
    with zipfile.ZipFile(path) as bundle:
        assert len([n for n in bundle.namelist() if n.startswith("battlefields/")]) == 50
        data = json.loads(bundle.read("world.json"))
        from chaos_kingdom.core.models import World
        restored = World.from_data(data)
        restored_battle = Battle.from_data(restored, json.loads(bundle.read("battle.json")))
        assert digest(world.data()) == digest(restored.data())
        assert digest(battle.data()) == digest(restored_battle.data())
        metadata = json.loads(bundle.read("metadata.json"))
        assert "hostname" not in metadata and "environment_variables" not in metadata


def test_generated_art_has_200_addressable_portraits():
    import pygame
    pygame.font.init()
    sheets = [a for a in manifest()["assets"] if a["kind"] == "portrait-atlas"]
    assert len(sheets) == 4 and sum(a["columns"] * a["rows"] for a in sheets) == 200
    images = [portrait(f"o{i:03}", (80, 90)) for i in range(200)]
    assert all(image is not None for image in images)
    assert len({pygame.image.tobytes(image, "RGB") for image in images}) == 200
