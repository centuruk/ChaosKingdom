from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import shutil
import tempfile

from .models import World


SAVE_VERSION = 1


def user_directory() -> Path:
    if override := os.environ.get("CHAOS_KINGDOM_HOME"):
        return Path(override)
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parents[2] / "saves"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ChaosKingdom"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ChaosKingdom"
    return Path.home() / ".local" / "share" / "ChaosKingdom"


def digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save_world(world: World, path: Path, *, battle=None) -> None:
    world.validate()
    data = world.data()
    payload = {"version": SAVE_VERSION, "checksum": digest(data), "world": data}
    if battle is not None:
        payload["battle"] = battle.data()
        payload["battle_checksum"] = digest(payload["battle"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".save-", delete=False) as stream:
            temp_path = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_file():
            try:
                load_world(path)
                shutil.copy2(path, path.with_suffix(".backup.json"))
            except ValueError:
                pass
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_world(path: Path) -> World:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("version") != SAVE_VERSION:
            raise ValueError("지원하지 않는 저장 파일 버전입니다.")
        data = payload["world"]
        if payload.get("checksum") != digest(data):
            raise ValueError("저장 파일이 손상되었거나 외부에서 변경되었습니다.")
        return World.from_data(data)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("저장 파일 구조가 잘못되었습니다.") from exc


def load_battle(path: Path, world: World):
    from chaos_kingdom.simulation.battle import Battle
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        data = payload.get("battle")
        if data is None:
            return None
        if payload.get("battle_checksum") != digest(data):
            raise ValueError("전투 저장 정보가 손상되었습니다.")
        return Battle.from_data(world, data)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("전투 저장 파일 구조가 잘못되었습니다.") from exc
