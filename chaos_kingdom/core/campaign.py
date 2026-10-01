from __future__ import annotations

from .generation import generate_world
from .models import World
from chaos_kingdom.simulation.engine import Engine


SCENARIOS = [
    {"title": "왕관 없는 새벽", "subtitle": "여섯 깃발, 아직 쓰이지 않은 역사", "seed": 742, "weeks": 24, "description": "황제의 죽음 뒤 24주. 국경이 흔들리기 시작한 왕국에서 자신의 길을 찾는다."},
    {"title": "칼과 겨울", "subtitle": "굶주린 국경에서 피어나는 야망", "seed": 1304, "weeks": 72, "description": "AI가 72주 동안 진행한 전쟁과 외교. 승자와 패자의 인연 위에서 새로운 기사가 등장한다."},
    {"title": "배신의 연대기", "subtitle": "오래된 맹세는 누구의 편인가", "seed": 9102, "weeks": 120, "description": "120주의 자율 역사. 높아진 명성과 누적된 원한이 다음 전쟁의 이유가 된다."},
]


def create_campaign(seed: int, weeks: int, title: str = "자율 역사") -> World:
    if not 0 <= weeks <= 2400:
        raise ValueError("역사 생성 기간은 0~2400주입니다.")
    world = generate_world(seed)
    engine = Engine(world)
    for _ in range(weeks):
        engine.step()
    world.title, world.campaign_origin = title, world.turn
    world.validate()
    return world


def campaign_summary(world: World) -> dict:
    return {
        "title": world.title, "seed": world.seed, "turn": world.turn, "date": world.date,
        "castles": sum(s.kind == "castle" for s in world.locations.values()),
        "outposts": sum(s.kind == "outpost" for s in world.locations.values()),
        "officers": len(world.officers), "battles": sum(e.kind == "battle" for e in world.chronicles),
        "total_battles": world.event_counts.get("battle", 0), "event_totals": dict(world.event_counts),
        "bonds": sum(value >= 60 for value in world.bonds.values()),
        "factions": [{"name": f.name, "holdings": len(world.holdings(f.id)), "soldiers": sum(s.troops for s in world.holdings(f.id)), "eliminated": f.eliminated} for f in world.factions.values()],
    }
