import json
from pathlib import Path

import pytest

from chaos_kingdom.core.campaign import create_campaign
from chaos_kingdom.core.generation import generate_world, select_player
from chaos_kingdom.core.models import Memory, pair
from chaos_kingdom.core.storage import digest, load_world, save_world
from chaos_kingdom.simulation.ai import evaluate
from chaos_kingdom.simulation.battle import Battle
from chaos_kingdom.simulation.engine import Engine


@pytest.mark.parametrize("seed", [0, 742, 1304, 9102])
def test_world_contract(seed):
    world = generate_world(seed)
    world.validate()
    assert len({o.name for o in world.officers.values()}) == 200
    assert len(world.holdings(None)) == 0
    assert sum(s.kind == "outpost" for s in world.locations.values()) == 30


def test_history_reproduces_and_seed_changes_history():
    first = create_campaign(742, 72)
    second = create_campaign(742, 72)
    different = create_campaign(743, 72)
    assert digest(first.data()) == digest(second.data())
    assert digest(first.data()) != digest(different.data())
    assert any(e.kind == "battle" for e in first.chronicles)
    assert any(e.kind == "promotion" for e in first.chronicles)


def test_save_roundtrip_preserves_future_randomness(tmp_path):
    original = create_campaign(742, 24)
    path = tmp_path / "save.json"
    save_world(original, path)
    loaded = load_world(path)
    assert digest(original.data()) == digest(loaded.data())
    a, b = Engine(original), Engine(loaded)
    for _ in range(12):
        a.step()
        b.step()
    assert digest(original.data()) == digest(loaded.data())


def test_corrupt_and_future_saves_are_rejected(tmp_path):
    path = tmp_path / "save.json"
    save_world(generate_world(), path)
    data = json.loads(path.read_text())
    data["world"]["turn"] += 1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="손상"):
        load_world(path)
    data["version"] = 99
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="버전"):
        load_world(path)


def test_invalid_actions_have_no_side_effects():
    world = generate_world()
    select_player(world, "o024")
    engine = Engine(world)
    before = digest(world.data())
    assert not engine.player_action("travel", "missing").ok
    assert not engine.player_action("bond", world.player).ok
    assert not engine.player_action("attack", world.officers[world.player].location).ok
    assert not engine.player_action("fake").ok
    assert digest(world.data()) == before


def test_player_action_advances_everyone_and_quest():
    world = generate_world()
    select_player(world, "o024")
    engine = Engine(world)
    officer = world.officers[world.player]
    before = officer.renown
    assert engine.player_action("develop").ok
    assert world.turn == 1
    assert officer.renown >= before + 6
    assert world.quests[1].progress == 1
    assert sum(engine.action_counts.values()) >= 190


def test_personality_state_and_memories_change_decisions():
    world = generate_world()
    officer = world.officers["o024"]
    officer.energy = 4
    assert evaluate(world, officer)[0].action == "rest"
    officer.energy = 100
    before = next(d.score for d in evaluate(world, officer) if d.action == "rest")
    officer.remember(Memory(0, "defeat", "", -40, "패전을 기억한다"))
    after = next(d.score for d in evaluate(world, officer) if d.action == "rest")
    assert after > before


def setup_battle():
    world = generate_world()
    source, target = world.locations["s20"], world.locations["s21"]
    source.faction, target.faction = "f0", "f2"
    source.troops, target.troops, target.fortification = 1000, 450, 10
    officer = world.officers["o024"]
    officer.location, officer.faction = source.id, "f0"
    return world, Battle(world, source.id, target.id, officer.id, 13)


def test_tactical_cap_termination_and_determinism():
    world, first = setup_battle()
    _, second = setup_battle()
    for side in (0, 1):
        assert sum(u.initial for u in first.units if u.side == side) == first.deployed[side] <= 1000
    first.auto_resolve()
    second.auto_resolve()
    assert first.finished and first.time <= 180.21
    assert first.winner == second.winner
    assert first.totals(0) == second.totals(0)
    assert first.totals(1) == second.totals(1)
    assert first.totals(0) < first.deployed[0]


def test_battle_orders_rally_and_retreat():
    _, battle = setup_battle()
    battle.issue([0], "move", (30, 10))
    before = battle.units[0].x
    battle.update(1)
    assert battle.units[0].x > before
    assert battle.rally(0)
    assert not battle.rally(0)
    battle.retreat()
    assert battle.finished and battle.winner == 1


def test_battle_result_preserves_troops_and_connects_to_history():
    world, battle = setup_battle()
    before = world.locations[battle.source].troops + world.locations[battle.destination].troops
    battle.auto_resolve()
    engine = Engine(world)
    engine.resolve_battle(battle, advance=False)
    after = world.locations[battle.source].troops + world.locations[battle.destination].troops
    assert 0 <= after <= before
    assert any(e.kind == "battle" for e in world.chronicles)
    assert any(m.kind in ("victory", "defeat") for m in world.officers[battle.commander].memories)
    world.validate()


@pytest.mark.parametrize("seed", [742, 743, 744, 1304, 9102])
def test_long_simulation_invariants(seed):
    world = create_campaign(seed, 240)
    world.validate()
    assert len(world.chronicles) <= 600
    assert all(len(o.memories) <= 12 for o in world.officers.values())
    assert all(-100 <= value <= 100 for value in world.bonds.values())


def test_free_officer_can_enlist_and_ruler_resignation_has_successor():
    world = generate_world()
    select_player(world, "o180")
    officer = world.officers[world.player]
    faction = world.locations[officer.location].faction
    assert Engine(world).player_action("enlist").ok
    assert officer.faction == faction
    old_ruler = world.factions["f0"].ruler
    select_player(world, old_ruler)
    ruler = world.officers[old_ruler]
    ruler.location = world.factions["f1"].capital
    assert Engine(world).player_action("enlist").ok
    assert world.factions["f0"].ruler != old_ruler
    world.validate()


def test_relationship_saturation_reduces_need_for_more_socializing():
    world = generate_world()
    officer = world.officers["o024"]
    peers = [o for o in world.residents(officer.location) if o.id != officer.id]
    assert peers
    for other in peers:
        world.bonds[pair(officer.id, other.id)] = 0
    before = next(d.score for d in evaluate(world, officer) if d.action == "bond")
    for other in peers:
        world.bonds[pair(officer.id, other.id)] = 100
    after = next(d.score for d in evaluate(world, officer) if d.action == "bond")
    assert after < before


def test_battle_result_cannot_be_applied_twice():
    world, battle = setup_battle()
    battle.auto_resolve()
    engine = Engine(world)
    engine.resolve_battle(battle, advance=False)
    before = digest(world.data())
    with pytest.raises(ValueError, match="이미"):
        engine.resolve_battle(battle, advance=False)
    assert digest(world.data()) == before


def test_event_totals_survive_chronicle_trimming():
    world = generate_world()
    for _ in range(650):
        world.log("example", "검증 사건")
    assert len(world.chronicles) == 600
    assert world.event_counts["example"] == 650


def test_ruler_policy_and_war_petition_respect_treaty():
    world = generate_world()
    select_player(world, world.factions["f0"].ruler)
    engine = Engine(world)
    assert engine.player_action("policy").ok
    assert world.factions["f0"].doctrine == "aggressive"
    world.treaties[pair("f0", "f1")] = world.turn + 12
    before = digest(world.data())
    assert not engine.player_action("petition_war", "f1").ok
    assert digest(world.data()) == before
    assert engine.player_action("petition_war", "f3").ok
    assert world.at_war("f0", "f3")


def test_flank_order_plans_a_waypoint_behind_enemy():
    _, battle = setup_battle()
    enemy = next(u for u in battle.units if u.side == 1)
    battle.issue([0], "flank", target=enemy.id)
    battle.update(.2)
    assert battle.units[0].destination[0] > enemy.x


def test_player_battle_updates_quest_and_returns_to_valid_world():
    world, _ = setup_battle()
    select_player(world, "o024")
    world.locations["s21"].troops = 120
    engine = Engine(world)
    result = engine.player_action("attack", "s21")
    assert result.ok and result.battle
    result.battle.auto_resolve()
    assert result.battle.winner == 0
    engine.resolve_battle(result.battle)
    assert world.turn == 1
    assert world.quests[2].complete
    assert world.victories == 1
    assert world.locations["s21"].faction == "f0"
    world.validate()
