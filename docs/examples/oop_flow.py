"""The runnable object-composition example from chapter 3; no GUI required."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from chaos_kingdom.core.generation import generate_world, select_player
from chaos_kingdom.core.models import World
from chaos_kingdom.core.storage import digest
from chaos_kingdom.simulation.engine import Engine

world = generate_world(742)
select_player(world, "o024")
engine = Engine(world)
assert engine.world is world
result = engine.player_action("rest")
assert result.ok
world.validate()
restored = World.from_data(world.data())
assert restored is not world
assert digest(restored.data()) == digest(world.data())
print(world.turn, result.message, len(world.officers))
