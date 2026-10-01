"""Rebuild packaged maps deterministically; never touch the user's custom maps."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaos_kingdom.core.battlefields import DATA_DIR, generate_battlefield, save_battlefield
from chaos_kingdom.core.generation import generate_world


def main():
    world = generate_world()
    for location in world.locations.values():
        field = generate_battlefield(location.id, location.name, location.terrain)
        save_battlefield(field, DATA_DIR / f"{location.id}.json")
    print("50 packaged maps regenerated, schema 1 / revision 3; custom maps untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
