"""Export factual campaign material for designers and writers."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chaos_kingdom.core.campaign import campaign_summary, create_campaign
from chaos_kingdom.core.models import RANKS
from chaos_kingdom.core.storage import save_world


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 캠페인을 저장·CSV·연대기·판세로 내보냅니다.")
    parser.add_argument("--seed", type=int, default=742)
    parser.add_argument("--weeks", type=int, default=96)
    parser.add_argument("--title", default="엘드라스의 기록")
    parser.add_argument("--output", type=Path, default=Path("exports/realm"))
    args = parser.parse_args()
    world = create_campaign(args.seed, args.weeks, args.title)
    args.output.mkdir(parents=True, exist_ok=True)
    save_world(world, args.output / "campaign.json")
    (args.output / "summary.json").write_text(json.dumps(campaign_summary(world), ensure_ascii=False, indent=2), encoding="utf-8")
    with (args.output / "officers.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["ID", "이름", "세력", "지역", "계급", "통솔", "무력", "지력", "정무", "매력", "명성", "충성", "생각"])
        for o in world.officers.values():
            writer.writerow([o.id, o.name, world.factions[o.faction].name if o.faction else "재야", world.locations[o.location].name,
                             RANKS[o.rank], *o.stats.values(), o.renown, round(o.loyalty), o.intent])
    lines = [f"# {world.title}", "", f"시드 {world.seed} · {args.weeks}주 생성 · {world.date}", "", "## 판세", ""]
    for f in world.factions.values():
        lines.append(f"- {f.name}: 영지 {len(world.holdings(f.id))}곳, 군주 {world.officers[f.ruler].name}")
    lines.extend(["", "## 실제 사건", "", "최근 최대 600개 사건을 생성 순서대로 기록합니다.", ""])
    for event in world.chronicles:
        lines.append(f"- [{event.turn}주 · {event.kind}] {event.text}")
    (args.output / "chronicle.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"캠페인·장수 CSV·판세·연대기 생성: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
