from __future__ import annotations

from dataclasses import asdict, dataclass, field
import random
import math
from typing import Any


STATS = ("command", "martial", "intellect", "politics", "charm")
STAT_NAMES = {"command": "통솔", "martial": "무력", "intellect": "지력", "politics": "정무", "charm": "매력"}
RANKS = ("수습 기사", "기사", "대장", "성주", "군주")
TERRAIN_NAMES = {"plains": "평원", "forest": "숲", "mountain": "산악", "river": "강", "coast": "해안"}
ACTION_NAMES = {"rest": "휴식", "train": "수련", "develop": "내정", "recruit": "징병", "bond": "교류", "travel": "이동", "scheme": "모략", "patrol": "순찰"}
CASTLE_INDICES = frozenset({0, 1, 3, 8, 12, 15, 18, 19, 20, 23, 26, 29, 30, 33, 36, 39, 41, 43, 46, 48})


def pair(a: str, b: str) -> str:
    return ":".join(sorted((a, b)))


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


@dataclass
class Memory:
    turn: int
    kind: str
    other: str
    weight: float
    text: str


@dataclass
class Officer:
    id: str
    name: str
    age: int
    faction: str | None
    location: str
    stats: dict[str, int]
    traits: dict[str, int]
    specialty: str
    loyalty: float = 70
    energy: float = 90
    renown: int = 0
    rank: int = 0
    gold: int = 80
    last_action: str = "rest"
    intent: str = "새로운 기회를 기다린다"
    memories: list[Memory] = field(default_factory=list)
    captor: str | None = None
    captivity: int = 0

    def remember(self, memory: Memory) -> None:
        self.memories.append(memory)
        self.memories = self.memories[-12:]


@dataclass
class Settlement:
    id: str
    name: str
    kind: str
    x: float
    y: float
    terrain: str
    faction: str | None
    neighbors: list[str] = field(default_factory=list)
    troops: int = 300
    food: float = 600
    treasury: float = 400
    prosperity: float = 40
    fortification: float = 40
    morale: float = 70
    governor: str | None = None


@dataclass
class Faction:
    id: str
    name: str
    motto: str
    color: list[int]
    capital: str
    doctrine: str
    ruler: str = ""
    ambition: float = 50
    eliminated: bool = False


@dataclass
class Chronicle:
    turn: int
    kind: str
    text: str
    actors: list[str] = field(default_factory=list)
    location: str | None = None


@dataclass
class Quest:
    id: str
    kind: str
    title: str
    description: str
    target: int
    reward: int
    progress: int = 0
    complete: bool = False
    reference: str | None = None
    origin: str = ""


@dataclass
class World:
    seed: int
    turn: int
    officers: dict[str, Officer]
    locations: dict[str, Settlement]
    factions: dict[str, Faction]
    bonds: dict[str, float] = field(default_factory=dict)
    wars: list[str] = field(default_factory=list)
    treaties: dict[str, int] = field(default_factory=dict)
    chronicles: list[Chronicle] = field(default_factory=list)
    player: str | None = None
    title: str = "왕관 없는 새벽"
    campaign_origin: int = 0
    quests: list[Quest] = field(default_factory=list)
    victories: int = 0
    outcome: str | None = None
    event_counts: dict[str, int] = field(default_factory=dict)
    chapter_end: int = 0
    chapter_report: str | None = None
    victor: str | None = None
    pending_battle: dict | None = None
    rng: random.Random = field(default_factory=random.Random, repr=False, compare=False)

    @property
    def date(self) -> str:
        seasons = ("봄", "여름", "가을", "겨울")
        return f"{742 + self.turn // 48}년 · {seasons[(self.turn % 48) // 12]} · {self.turn % 12 + 1}주"

    def relationship(self, a: str, b: str) -> float:
        return 100 if a == b else self.bonds.get(pair(a, b), 0)

    def change_bond(self, a: str, b: str, amount: float) -> float:
        if a == b:
            return 100
        key = pair(a, b)
        self.bonds[key] = clamp(self.bonds.get(key, 0) + amount, -100, 100)
        return self.bonds[key]

    def at_war(self, a: str | None, b: str | None) -> bool:
        return a is not None and b is not None and a != b and pair(a, b) in self.wars

    def log(self, kind: str, text: str, actors: list[str] | None = None, location: str | None = None) -> None:
        self.event_counts[kind] = self.event_counts.get(kind, 0) + 1
        self.chronicles.append(Chronicle(self.turn, kind, text, actors or [], location))
        self.chronicles = self.chronicles[-600:]

    def holdings(self, faction: str | None) -> list[Settlement]:
        return [s for s in self.locations.values() if s.faction == faction]

    @property
    def unified_by(self) -> str | None:
        owners = {s.faction for s in self.locations.values()}
        return next(iter(owners)) if len(owners) == 1 and None not in owners else None

    def unification_progress(self, faction):
        held = self.holdings(faction) if faction else []
        return len(held), sum(s.kind == "castle" for s in held)

    def residents(self, location: str) -> list[Officer]:
        return [o for o in self.officers.values() if o.location == location and not o.captor]

    def data(self) -> dict[str, Any]:
        result = {key: value for key, value in self.__dict__.items() if key != "rng"}
        result["officers"] = {key: asdict(value) for key, value in self.officers.items()}
        result["locations"] = {key: asdict(value) for key, value in self.locations.items()}
        result["factions"] = {key: asdict(value) for key, value in self.factions.items()}
        result["chronicles"] = [asdict(value) for value in self.chronicles]
        result["quests"] = [asdict(value) for value in self.quests]
        result["rng_state"] = self.rng.getstate()
        return result

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> World:
        content = dict(data)
        rng_state = content.pop("rng_state")
        content["officers"] = {
            key: Officer(**{**value, "memories": [Memory(**m) for m in value["memories"]]})
            for key, value in data["officers"].items()
        }
        content["locations"] = {key: Settlement(**value) for key, value in data["locations"].items()}
        content["factions"] = {key: Faction(**value) for key, value in data["factions"].items()}
        content["chronicles"] = [Chronicle(**value) for value in data["chronicles"]]
        content["quests"] = [Quest(**value) for value in data["quests"]]
        world = cls(**content)
        # Old beta saves stopped at their 96-week personal epilogue. Preserve its
        # prose, but let that campaign continue toward the new unification goal.
        if world.outcome and not world.unified_by and world.chapter_end and world.turn >= world.chapter_end:
            world.chapter_report, world.outcome = world.outcome, None
            world.chapter_end = world.turn + 96
        def tuples(value: Any) -> Any:
            return tuple(tuples(v) for v in value) if isinstance(value, (tuple, list)) else value
        world.rng.setstate(tuples(rng_state))
        world.validate()
        return world

    def validate(self) -> None:
        if type(self.turn) is not int or self.turn < 0 or type(self.chapter_end) is not int or self.chapter_end < 0:
            raise ValueError("캠페인 시간 정보가 잘못되었습니다.")
        if self.victor not in {None, *self.factions}:
            raise ValueError("천하통일 세력 정보가 잘못되었습니다.")
        if len(self.officers) != 200 or len(self.locations) != 50:
            raise ValueError("세계에는 장수 200명과 지역 50개가 필요합니다.")
        if sum(s.kind == "castle" for s in self.locations.values()) != 20:
            raise ValueError("성의 수는 20개여야 합니다.")
        for sid, s in self.locations.items():
            if s.id != sid or s.faction not in {None, *self.factions}:
                raise ValueError("지역 또는 소유 세력 정보가 잘못되었습니다.")
            if not 0 <= s.troops <= 1000 or min(s.food, s.treasury) < 0 or any(not math.isfinite(v) for v in (s.food, s.treasury, s.prosperity, s.morale, s.fortification)):
                raise ValueError("병력 또는 자원 범위가 잘못되었습니다.")
            if s.governor is not None and s.governor not in self.officers:
                raise ValueError("존재하지 않는 성주입니다.")
            for neighbor in s.neighbors:
                if neighbor not in self.locations or sid not in self.locations[neighbor].neighbors:
                    raise ValueError("도로 연결은 양방향이어야 합니다.")
        visited, todo = set(), [next(iter(self.locations))]
        while todo:
            sid = todo.pop()
            if sid not in visited:
                visited.add(sid)
                todo.extend(self.locations[sid].neighbors)
        if len(visited) != 50:
            raise ValueError("연결되지 않은 지역이 있습니다.")
        for oid, o in self.officers.items():
            if o.id != oid or o.location not in self.locations or o.faction not in {None, *self.factions}:
                raise ValueError("장수 소속 정보가 잘못되었습니다.")
            if set(o.stats) != set(STATS) or any(not 1 <= v <= 100 for v in o.stats.values()):
                raise ValueError("능력치는 1~100이어야 합니다.")
            if not 0 <= o.energy <= 100 or not 0 <= o.loyalty <= 100 or not 0 <= o.rank <= 4:
                raise ValueError("장수 상태 범위가 잘못되었습니다.")
            if not 16 <= o.age <= 90 or o.gold < 0 or o.captor not in {None, *self.factions} or o.captivity < 0:
                raise ValueError("장수 나이·자금·포로 상태가 잘못되었습니다.")
            if set(o.traits) != {"ambition", "honor", "empathy", "courage"} or any(not 0 <= v <= 100 for v in o.traits.values()):
                raise ValueError("장수 성격 값이 잘못되었습니다.")
        for f in self.factions.values():
            if f.capital not in self.locations or f.ruler not in self.officers:
                raise ValueError("군주 또는 수도가 존재하지 않습니다.")
        if self.player is not None and self.player not in self.officers:
            raise ValueError("플레이어 장수가 존재하지 않습니다.")
        for key, value in self.bonds.items():
            ids = key.split(":")
            if len(ids) != 2 or any(i not in self.officers for i in ids) or ids[0] == ids[1] or not -100 <= value <= 100:
                raise ValueError("장수 관계가 잘못되었습니다.")
        if len({q.id for q in self.quests}) != len(self.quests) or any(q.target <= 0 or q.progress < 0 or q.reward < 0 for q in self.quests):
            raise ValueError("개인 과업 정보가 잘못되었습니다.")
        if self.pending_battle:
            if self.player is None or self.pending_battle.get("source") not in self.locations or self.pending_battle.get("destination") not in self.locations or self.pending_battle.get("commander") not in self.officers:
                raise ValueError("대기 전투 정보가 잘못되었습니다.")
