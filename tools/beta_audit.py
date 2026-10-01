"""Reproducible beta soak, regional combat audit, and player-role smoke runs."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaos_kingdom.core.battlefields import load_battlefield
from chaos_kingdom.core.campaign import campaign_summary, create_campaign
from chaos_kingdom.core.diagnostics import environment
from chaos_kingdom.core.generation import generate_world, select_player
from chaos_kingdom.core.storage import digest, load_world, save_world
from chaos_kingdom.simulation.battle import Battle
from chaos_kingdom.simulation.engine import Engine

ROOT = Path(__file__).resolve().parents[1]


def main():
    started = time.perf_counter()
    report = {"environment": environment(), "maps": [], "history": [], "roles": []}
    for region in range(50):
        world = generate_world()
        source, target = world.locations["s20"], world.locations["s21"]
        source.faction, target.faction = "f0", "f2"
        source.troops, target.troops = 1000, 700
        officer = world.officers["o024"]
        officer.faction, officer.location = "f0", source.id
        field = load_battlefield(f"s{region:02}", custom=False)
        battle = Battle(world, source.id, target.id, officer.id, 742 + region, battlefield=field)
        battle.auto_resolve()
        Engine(world).resolve_battle(battle, advance=False)
        world.validate()
        assert source.troops + target.troops <= 1700
        assert all(field.walkable(field.cell(u.x, u.y)) for u in battle.units)
        report["maps"].append({"region": field.region, "biome": field.biome, "winner": battle.winner,
                               "time": round(battle.time, 1), "casualties": [battle.deployed[s] - battle.totals(s) for s in (0, 1)], "control": battle.control})
    for seed in (742, 1304, 9102):
        world = create_campaign(seed, 480)
        world.validate()
        summary = campaign_summary(world)
        summary["last_actions"] = dict(Counter(o.last_action for o in world.officers.values()))
        report["history"].append(summary)
    for officer_id in ("o024", "o180", "o000"):
        world = create_campaign(742, 24)
        select_player(world, officer_id)
        engine = Engine(world)
        commands = ("develop", "train", "patrol", "recruit", "bond", "rest")
        for i in range(96):
            if world.outcome:
                break
            officer = world.officers[world.player]
            if world.pending_battle:
                battle = Battle.from_data(world, world.pending_battle)
                battle.interactive = False
                battle.auto_resolve()
                engine.resolve_battle(battle)
            if officer.faction is None:
                result = engine.player_action("enlist")
            else:
                action = commands[i % len(commands)]
                target = next((o.id for o in world.residents(officer.location) if o.id != officer.id), None) if action == "bond" else None
                result = engine.player_action(action, target)
            if not result.ok:
                result = engine.player_action("rest")
            if world.pending_battle:
                battle = Battle.from_data(world, world.pending_battle)
                battle.interactive = False
                battle.auto_resolve()
                engine.resolve_battle(battle)
            world.validate()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "campaign.json"
            save_world(world, path)
            assert digest(load_world(path).data()) == digest(world.data())
        report["roles"].append({"officer": officer_id, "turn": world.turn, "outcome": world.outcome,
                                "chapter_report": world.chapter_report,
                                "unification_progress": world.unification_progress(world.officers[officer_id].faction),
                                "quests": sum(q.complete for q in world.quests), "rank": world.officers[officer_id].rank,
                                "victories": world.victories, "valid": True})
    report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    output = ROOT / "docs/evidence/beta-audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"50 regional battles, 3 × 480-week histories, 3 player roles verified; {report['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
