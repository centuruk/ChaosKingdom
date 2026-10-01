"""Restore a beta report into an isolated folder, never into the live campaign."""
import argparse
import json
from pathlib import Path
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chaos_kingdom.core.battlefields import Battlefield, save_battlefield
from chaos_kingdom.core.models import World
from chaos_kingdom.core.storage import digest, save_world
from chaos_kingdom.simulation.battle import Battle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, default=Path("exports/reproduction"))
    args = parser.parse_args()
    with zipfile.ZipFile(args.report) as bundle:
        world = World.from_data(json.loads(bundle.read("world.json")))
        metadata = json.loads(bundle.read("metadata.json"))
        if digest(world.data()) != metadata["world_checksum"]:
            raise ValueError("제보 묶음의 세계 체크섬이 맞지 않습니다.")
        battle = Battle.from_data(world, json.loads(bundle.read("battle.json"))) if "battle.json" in bundle.namelist() else None
        maps = [Battlefield.from_data(json.loads(bundle.read(f"battlefields/s{i:02}.json"))) for i in range(50)]
        args.output.mkdir(parents=True, exist_ok=True)
        for m in maps:
            save_battlefield(m, args.output / "battlefields" / f"{m.region}.json")
        save_world(world, args.output / "campaign.json", battle=battle)
        (args.output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"복원 완료: {args.output.resolve()}\nCHAOS_KINGDOM_HOME을 이 경로로 지정하고 저장한 이야기를 불러오세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
