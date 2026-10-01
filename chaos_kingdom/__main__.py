from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import platform
import sys
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from .core.campaign import SCENARIOS, campaign_summary, create_campaign
from .core.generation import select_player
from .core.storage import load_world, save_world


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="혼돈의 왕국 — 게임과 자율 역사 제작 도구")
    commands = root.add_subparsers(dest="command")
    play = commands.add_parser("play", help="게임 실행")
    play.add_argument("--headless", action="store_true")
    play.add_argument("--frames", type=int)
    play.add_argument("--screenshot", type=Path)
    play.add_argument("--view", choices=("menu", "scenarios", "select", "map", "officers", "diplomacy", "chronicle", "battle", "editor"), default="menu")
    play.add_argument("--load", type=Path)
    play.add_argument("--scenario", type=int, choices=range(3), default=0)
    play.add_argument("--quick-start", action="store_true")
    for name in ("simulate", "campaign"):
        cmd = commands.add_parser(name, help="AI 역사 생성 및 보고서 출력")
        cmd.add_argument("--seed", type=int, default=742)
        cmd.add_argument("--weeks", type=int, default=96)
        cmd.add_argument("--title", default="자율 역사")
        cmd.add_argument("--output", type=Path)
        cmd.add_argument("--report", type=Path)
    inspect = commands.add_parser("inspect", help="캠페인 저장 파일 검증 및 판세 확인")
    inspect.add_argument("path", type=Path)
    balance = commands.add_parser("balance", help="여러 시드의 AI 행동과 판세 비교")
    balance.add_argument("--seeds", type=int, default=5)
    balance.add_argument("--weeks", type=int, default=96)
    balance.add_argument("--output", type=Path)
    commands.add_parser("doctor", help="Python, Pygame, 플랫폼 진단")
    commands.add_parser("validate-maps", help="50개 지역의 전장 경로 검증")
    return root


def emit_report(data, path: Path | None = None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    command = args.command or "play"
    try:
        if command == "play":
            from .ui.app import App
            if args.command is None:
                app = App()
                app.run()
                return 0
            world = load_world(args.load) if args.load else None
            if world is None and (args.view not in ("menu", "scenarios", "battle", "editor") or args.quick_start):
                scenario = SCENARIOS[args.scenario]
                world = create_campaign(scenario["seed"], scenario["weeks"], scenario["title"])
                if args.view != "select":
                    available = [o for o in world.officers.values() if o.faction == "f0" and not o.captor and world.locations[o.location].faction == "f0"]
                    select_player(world, next((o.id for o in available if o.rank == 2), available[0].id))
            app = App(headless=args.headless, world=world)
            if args.load:
                app.save_path = args.load
                app.load()
            elif args.view == "editor":
                app.dispatch("editor")
            elif args.view in ("map", "officers", "diplomacy", "chronicle"):
                app.screen, app.tab = "world", args.view
            elif args.view == "battle":
                app.start_demo()
            elif not args.quick_start:
                app.screen = args.view
            app.run(max_frames=args.frames, screenshot=args.screenshot)
        elif command in ("campaign", "simulate"):
            started = time.perf_counter()
            world = create_campaign(args.seed, args.weeks, args.title)
            if args.output:
                save_world(world, args.output)
            summary = campaign_summary(world)
            summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            summary["recent_events"] = [event.text for event in world.chronicles[-12:]]
            emit_report(summary, args.report)
        elif command == "inspect":
            emit_report(campaign_summary(load_world(args.path)))
        elif command == "balance":
            if not 1 <= args.seeds <= 100:
                raise ValueError("시드 수는 1~100입니다.")
            reports = []
            for seed in range(742, 742 + args.seeds):
                world = create_campaign(seed, args.weeks)
                summary = campaign_summary(world)
                summary["last_actions"] = dict(Counter(o.last_action for o in world.officers.values()))
                summary["mean_loyalty"] = round(sum(o.loyalty for o in world.officers.values()) / 200, 2)
                reports.append(summary)
            emit_report({"weeks": args.weeks, "runs": reports}, args.output)
        elif command == "doctor":
            import pygame
            emit_report({"python": sys.version.split()[0], "platform": platform.platform(), "pygame": pygame.version.ver,
                         "pygame_ce": bool(getattr(pygame, "IS_CE", False)), "architecture": platform.machine(),
                         "supported_targets": ["Windows 10/11", "macOS"], "save_schema": 1})
        elif command == "validate-maps":
            from .core.battlefields import load_battlefield
            from .core.generation import generate_world
            world = generate_world()
            fields = [load_battlefield(loc.id, loc.name, loc.terrain) for loc in world.locations.values()]
            for field_map in fields:
                field_map.validate()
            emit_report({"maps": len(fields), "unique_layouts": len({tuple(f.tiles) for f in fields}), "connected": True})
    except (ValueError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        from .core.diagnostics import crash_report
        path = crash_report(exc)
        print(f"예기치 못한 오류. 진단 파일: {path}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
