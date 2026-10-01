"""Local-only diagnostics. No telemetry, account, or network dependency."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import traceback
import zipfile

from chaos_kingdom import __version__
from .storage import digest, user_directory


def environment():
    import pygame
    return {"game": __version__, "python": sys.version.split()[0], "platform": platform.system(),
            "architecture": platform.machine(), "pygame": pygame.version.ver, "save_schema": 1}


def crash_report(exc):
    folder = user_directory() / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (datetime.now(timezone.utc).strftime("crash-%Y%m%d-%H%M%S-%f") + ".json")
    path.write_text(json.dumps({**environment(), "exception": type(exc).__name__, "traceback": traceback.format_exc()}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_report(world, journal, battle=None, *, folder=None):
    folder = Path(folder) if folder else user_directory() / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = folder / f"beta-report-{stamp}.zip"
    world_data = world.data()
    metadata = {**environment(), "seed": world.seed, "turn": world.turn, "world_checksum": digest(world_data),
                "created_utc": datetime.now(timezone.utc).isoformat(), "steps": list(journal), "battle": bool(battle)}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, value in (("metadata.json", metadata), ("world.json", world_data)):
            bundle.writestr(name, json.dumps(value, ensure_ascii=False, indent=2))
        if battle:
            bundle.writestr("battle.json", json.dumps(battle.data(), ensure_ascii=False, indent=2))
        # Include edited maps to reproduce subsequent simulation choices on another PC.
        from .battlefields import DATA_DIR
        custom = user_directory() / "battlefields"
        for default in sorted(DATA_DIR.glob("*.json")):
            candidate = custom / default.name
            bundle.write(candidate if candidate.is_file() else default, "battlefields/" + default.name)
        bundle.writestr("README.txt", "혼돈의 왕국 로컬 베타 제보 묶음\n사용자 계정·컴퓨터 이름·전체 환경변수를 수집하지 않습니다.\nworld.json은 World.from_data로, battle.json은 Battle.from_data로 복원할 수 있습니다.\n동봉된 battlefields를 별도 CHAOS_KINGDOM_HOME/battlefields에 넣어 재현하세요.\n")
    return path
