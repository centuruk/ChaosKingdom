from __future__ import annotations

import json
import random
from importlib.resources import files
from .models import CASTLE_INDICES, Faction, Memory, Officer, Quest, Settlement, World, pair
from .korean import together


def content() -> dict:
    return json.loads(files("chaos_kingdom").joinpath("data/realm.json").read_text(encoding="utf-8"))


def generate_world(seed: int = 742) -> World:
    config = content()
    portrait_catalog = json.loads(files("chaos_kingdom").joinpath("assets/manifest.json").read_text(encoding="utf-8")).get("officers", {})
    rng = random.Random(seed)
    locations = {}
    terrains = ("plains", "forest", "mountain", "river", "coast")
    for index, name in enumerate(config["names"]):
        row, col = divmod(index, 10)
        kind = "castle" if index in CASTLE_INDICES else "outpost"
        sid = f"s{index:02}"
        locations[sid] = Settlement(sid, name, kind, 12 + col * 9.2 + rng.uniform(-2.2, 2.2),
                                   10 + row * 14 + rng.uniform(-3.2, 3.2),
                                   rng.choice(terrains[:-1]) if col < 9 else "coast", None,
                                   troops=rng.randint(380, 740) if kind == "castle" else rng.randint(130, 310),
                                   food=rng.randint(700, 1300), treasury=rng.randint(300, 750),
                                   prosperity=rng.randint(30, 68), fortification=65 if kind == "castle" else 22)
        locations[sid].terrain = config["battlefield_biomes"][index]
    # A connected road network, with sparse diagonals that enable flank campaigns.
    for index in range(50):
        neighbors = []
        if index % 10 != 9:
            neighbors.append(index + 1)
        if index < 40:
            neighbors.append(index + 10)
            if index % 10 != 9 and index % 3 == 0:
                neighbors.append(index + 11)
        for other in neighbors:
            a, b = f"s{index:02}", f"s{other:02}"
            locations[a].neighbors.append(b)
            locations[b].neighbors.append(a)
    factions = {}
    for entry in config["factions"]:
        factions[entry["id"]] = Faction(**{**entry, "capital": f"s{entry['capital']:02}"}, ambition=rng.randint(38, 85))
    for loc in locations.values():
        owner = min(factions.values(), key=lambda f: (loc.x - locations[f.capital].x) ** 2 + (loc.y - locations[f.capital].y) ** 2)
        loc.faction = owner.id
    officers = {}
    specialties = ("infantry", "archer", "cavalry", "spear", "tactician")
    for index in range(200):
        house, given = divmod(index, 20)
        name = f"{config['given_names'][given]} {config['houses'][house]}"
        faction = None if index >= 180 else f"f{index % 6}"
        owned = [s for s in locations.values() if s.faction == faction] or list(locations.values())
        stats = {key: rng.randint(35, 88) for key in ("command", "martial", "intellect", "politics", "charm")}
        stats[rng.choice(list(stats))] = rng.randint(80, 97)
        officers[f"o{index:03}"] = Officer(
            f"o{index:03}", name, rng.randint(19, 57), faction, rng.choice(owned).id, stats,
            {key: rng.randint(10, 95) for key in ("ambition", "honor", "empathy", "courage")},
            specialties[index % len(specialties)], loyalty=rng.randint(48, 96), rank=0 if faction is None else 1,
            renown=rng.randint(10, 70), gold=rng.randint(50, 180))
        if portrait := portrait_catalog.get(f"o{index:03}"):
            officers[f"o{index:03}"].age = portrait["age"]
    world = World(seed, 0, officers, locations, factions, rng=rng)
    for index, faction in enumerate(factions.values()):
        ruler = officers[f"o{index:03}"]
        ruler.rank, ruler.renown, ruler.location, ruler.loyalty = 4, 420, faction.capital, 100
        faction.ruler = ruler.id
        for loc in world.holdings(faction.id):
            available = [o for o in officers.values() if o.faction == faction.id and o.rank < 3]
            governor = max(available, key=lambda o: o.stats["politics"] + o.stats["command"])
            governor.rank, governor.location, governor.renown = 3, loc.id, 230
            loc.governor = governor.id
    for o in officers.values():
        peers = [other for other in world.residents(o.location) if other.id != o.id]
        for other in rng.sample(peers, min(3, len(peers))):
            world.change_bond(o.id, other.id, rng.randint(-14, 28))
        if peers:
            other = rng.choice(peers)
            o.remember(Memory(0, "origin", other.id, 12, f"{together(other.name)} 같은 지역에서 기사 생활을 시작했다."))
    world.wars = [pair("f0", "f2"), pair("f1", "f3"), pair("f4", "f5")]
    world.log("origin", "엘드라스의 마지막 황제가 후계자 없이 죽었다. 여섯 세력이 흩어진 왕관을 노린다.")
    world.validate()
    return world


def select_player(world: World, officer_id: str) -> None:
    officer = world.officers[officer_id]
    if officer.captor:
        raise ValueError("포로인 장수는 선택할 수 없습니다.")
    world.player = officer_id
    world.campaign_origin = world.turn
    world.chapter_end = world.turn + 96
    officer.energy = 100
    world.quests = [
        Quest("q0", "bond_visits", "인연을 가꾸는 시간", "같은 지역 장수와 직접 교류를 2회 수행하세요. 이미 가까운 사이도 함께한 시간이 필요합니다.", 2, 45),
        Quest("q1", "develop", "영지의 등불", "내정 또는 순찰을 4회 수행하세요.", 4, 70),
        Quest("q2", "battle", "첫 승전", "직접 지휘한 전투에서 승리하세요.", 1, 100),
    ]
    from .story import personal_quests
    world.quests.extend(personal_quests(world, officer))
    world.log("player", f"{officer.name}의 이야기가 시작된다.", [officer_id], officer.location)
