"""User-visible contracts of the isometric/unification beta revision."""
import itertools
import math
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pytest

from chaos_kingdom.core.battlefields import Battlefield, load_battlefield
from chaos_kingdom.core.campaign import create_campaign
from chaos_kingdom.core.generation import generate_world, select_player
from chaos_kingdom.core.models import CASTLE_INDICES, World, pair
from chaos_kingdom.core.storage import digest
from chaos_kingdom.simulation.battle import Battle
from chaos_kingdom.simulation.engine import Engine
from chaos_kingdom.ui.battlefield_view import IsometricProjection


def open_battle():
    world = generate_world()
    source, target = world.locations["s20"], world.locations["s21"]
    source.troops, target.troops = 1000, 1000
    source.faction, target.faction = "f0", "f2"
    officer = world.officers["o024"]
    officer.faction, officer.location = "f0", source.id
    field = Battlefield("s21", "개방 전장", "plains", ["." * 32] * 20,
                        [[[2, y] for y in (2, 5, 9, 13, 17)], [[29, y] for y in (2, 5, 9, 13, 17)]], [16, 10])
    return world, Battle(world, source.id, target.id, officer.id, 23, interactive=True, battlefield=field)


@pytest.mark.parametrize("rect", [(24, 148, 1068, 574), (32, 185, 1024, 640)])
def test_projection_all_640_cell_centers_roundtrip_and_empty_corners_reject_input(rect):
    projection = IsometricProjection(rect)
    for y in range(20):
        for x in range(32):
            point = projection.cell_point(x + .5, y + .5)
            assert projection.cell_at(point) == (x, y)
            world = projection.world_at(point)
            assert world and abs(world[0] - (x + .5) * 100 / 32) < .15
            assert abs(world[1] - (y + .5) * 60 / 20) < .15
    assert projection.cell_at((rect[0] + 1, rect[1] + 1)) is None
    assert projection.world_at((rect[0] + rect[2] - 1, rect[1] + rect[3] - 1)) is None


def test_group_move_spreads_destinations_and_resolves_physical_crowding():
    world, battle = open_battle()
    allies = battle.active(0)
    for unit in allies:
        unit.x, unit.y = 40, 30
    battle.issue([u.id for u in allies], "move", (50, 30))
    assert len({u.destination for u in allies}) == len(allies)
    for _ in range(20):
        battle.update(.2)
    assert all(math.dist((a.x, a.y), (b.x, b.y)) > 1.9 for a, b in itertools.combinations(allies, 2))
    assert all(battle.field.walkable(battle.field.cell(u.x, u.y)) for u in battle.units)
    restored = Battle.from_data(world, battle.data())
    for _ in range(30):
        battle.update(.2)
        restored.update(.2)
    assert digest(restored.data()) == digest(battle.data())


def test_defenders_redeploy_toward_objective_while_manual_hold_is_preserved():
    _, battle = open_battle()
    allies, defenders = battle.active(0), battle.active(1)
    battle.issue([u.id for u in allies], "hold")
    objective = battle.field.point(battle.field.objective)
    initial = {u.id: math.dist((u.x, u.y), objective) for u in defenders}
    for _ in range(20):
        battle.update(1)
    assert all(u.order == "hold" for u in allies)
    assert all(math.dist((u.x, u.y), objective) < initial[u.id] - 8 for u in defenders)


def test_all_castles_have_walkable_gates_connected_to_their_interior_objective():
    for index in CASTLE_INDICES:
        field = load_battlefield(f"s{index:02}", custom=False)
        gates = [(x, y) for y, row in enumerate(field.tiles) for x, tile in enumerate(row) if tile == "g"]
        assert gates and field.objective[0] > 25 and field.revision == 3
        assert any(field.path(tuple(field.spawns[0][0]), gate) and field.path(gate, tuple(field.objective)) for gate in gates)
        assert not field.walkable((31, 2))


def test_movement_checks_the_wall_corner_crossed_between_two_walkable_endpoints():
    field = load_battlefield("s01", custom=False)
    assert field.walkable((26, 8)) and field.walkable((25, 7))
    # Both endpoints are legal, but the diagonal crosses blocked cell (25, 8).
    assert not field.traversable((81.48201058548393, 24.454556820132897), (79.6875, 22.5))
    world, original = open_battle()
    battle = Battle(world, original.source, original.destination, original.commander, 743, battlefield=field)
    for _ in range(180):
        battle.update(1)
        assert all(field.walkable(field.cell(u.x, u.y)) for u in battle.units)


def test_fifty_owned_regions_trigger_one_final_ending_even_if_faction_flags_are_stale():
    world = generate_world()
    select_player(world, "o000")
    for location in world.locations.values():
        location.faction = "f0"
    engine = Engine(world)
    engine._finish_chapter()
    assert world.victor == "f0" and world.outcome and world.unification_progress("f0") == (50, 20)
    assert world.event_counts["ending"] == 1
    engine._finish_chapter()
    assert world.event_counts["ending"] == 1
    before = digest(world.data())
    assert not engine.player_action("rest").ok
    assert digest(world.data()) == before


def test_single_active_faction_is_insufficient_if_a_region_is_neutral():
    world = generate_world()
    select_player(world, "o000")
    for location in world.locations.values():
        location.faction = "f0"
    world.locations["s49"].faction = None
    for faction in world.factions.values():
        faction.eliminated = faction.id != "f0"
    Engine(world)._finish_chapter()
    assert world.outcome is None and world.unified_by is None


def test_last_region_capture_connects_real_battle_result_to_unification():
    world = generate_world()
    select_player(world, "o000")
    for location in world.locations.values():
        location.faction = "f0"
    source, target = world.locations["s00"], world.locations["s01"]
    source.troops, target.troops, target.faction = 1000, 10, "f2"
    world.officers[world.player].location = source.id
    battle = Battle(world, source.id, target.id, world.player, 919)
    battle.auto_resolve()
    assert battle.winner == 0
    Engine(world).resolve_battle(battle, advance=False)
    assert world.victor == "f0" and world.outcome and world.unification_progress("f0") == (50, 20)
    world.validate()


def test_generated_isometric_atlases_preserve_original_hashes_and_transparent_addresses():
    import hashlib
    import pygame
    from chaos_kingdom.ui.assets import ASSET_DIR, manifest, structure_sprite, unit_sprite
    for entry in manifest()["assets"]:
        assert hashlib.sha256((ASSET_DIR / entry["file"]).read_bytes()).hexdigest() == entry["sha256"]
    for name in manifest()["structures_layout"]["names"]:
        sprite = structure_sprite(name, 64)
        assert sprite and sprite.get_width() == 64 and sprite.get_flags() & pygame.SRCALPHA
    for kind in ("infantry", "archer", "cavalry", "spear"):
        front, back = unit_sprite(kind, True, 48), unit_sprite(kind, False, 48)
        assert front and back and pygame.image.tobytes(front, "RGBA") != pygame.image.tobytes(back, "RGBA")


def test_old_personal_epilogue_migrates_without_erasing_its_prose_or_rng():
    world = generate_world()
    select_player(world, "o024")
    world.turn = world.chapter_end
    world.outcome = "96주의 첫 장이 끝났다."
    data = world.data()
    data.pop("chapter_report")
    data.pop("victor")
    restored = World.from_data(data)
    assert restored.outcome is None and restored.chapter_report == world.outcome
    assert restored.chapter_end == world.turn + 96
    assert restored.rng.getstate() == world.rng.getstate()
    assert restored.officers == world.officers and restored.locations == world.locations


def test_new_quests_do_not_auto_complete_from_an_existing_maximum_bond_or_call_a_healthy_estate_ruined():
    world = generate_world()
    officer = world.officers["o000"]
    for location in world.holdings(officer.faction):
        location.prosperity = location.morale = 100
    for other in world.officers.values():
        if other.id != officer.id:
            world.bonds[pair(officer.id, other.id)] = 100
    select_player(world, officer.id)
    engine = Engine(world)
    engine._story_progress()
    assert not any(q.complete for q in world.quests)
    assert "재건" not in world.quests[3].title
    assert world.quests[4].kind == "bond_visits"
    assert world.quests[0].kind == "bond_visits"


def test_new_companion_target_is_above_its_initial_relationship():
    world = create_campaign(742, 24)
    select_player(world, "o000")
    companion = world.quests[4]
    assert companion.kind == "companion"
    assert world.relationship(world.player, companion.reference) < companion.target
    Engine(world)._story_progress()
    assert not companion.complete
