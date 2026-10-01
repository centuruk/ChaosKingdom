"""Ground personal campaign hooks in simulated events and current relationships."""
from .models import Quest


def personal_quests(world, officer):
    historical = [e for e in world.chronicles if e.kind == "battle" and e.location and "함락" in e.text
                  and world.locations[e.location].faction != officer.faction
                  and (officer.id in e.actors or any(m.kind == "defeat" and world.locations[e.location].name in m.text for m in officer.memories))]
    if historical and officer.faction:
        event = historical[-1]
        name = world.locations[event.location].name
        strategic = Quest("q3", "reclaim", "빼앗긴 깃발", f"{event.turn}주의 {name} 함락 기록을 바탕으로, 이 영지를 현재 소속 세력의 손에 되돌리세요.", 1, 150, reference=event.location, origin=event.text)
    else:
        event = next((e for e in reversed(world.chronicles) if e.kind == "incident" and e.location
                      and officer.faction and world.locations[e.location].faction == officer.faction
                      and (world.locations[e.location].morale < 60 or world.locations[e.location].prosperity < 60)), None)
        owned = world.holdings(officer.faction) if officer.faction else []
        loc = world.locations[event.location] if event else min(owned, key=lambda s: (s.prosperity + s.morale, s.id)) if owned else world.locations[officer.location]
        damaged = loc.prosperity < 60 or loc.morale < 60
        strategic = Quest("q3", "steward", "흔들린 영지의 재건" if damaged else "번영을 지키는 책무", f"{loc.name}에서 내정·순찰을 6회 수행하세요. 현재 번영 {loc.prosperity:.0f}, 사기 {loc.morale:.0f}인 영지를 돌봅니다.", 6, 110, reference=loc.id, origin=event.text if event else f"출발 당시 {loc.name}의 번영 {loc.prosperity:.0f}, 사기 {loc.morale:.0f}")
    candidates = [o for o in world.officers.values() if o.id != officer.id and not o.captor
                  and world.relationship(officer.id, o.id) < 80]
    related = [m for m in officer.memories if any(o.id == m.other for o in candidates)
               and world.officers[m.other].faction == officer.faction]
    if candidates:
        companion = world.officers[related[-1].other] if related else max(candidates, key=lambda o: (o.location == officer.location, o.faction == officer.faction, world.relationship(officer.id, o.id), o.id))
        current = max(0, int(world.relationship(officer.id, companion.id)))
        target = min(100, max(60, current + 20))
        social = Quest("q4", "companion", "기억에서 이어진 인연", f"{companion.name}와 친밀도 {current}에서 {target}을 목표로 인연을 가꾸세요. 현재 위치: {world.locations[companion.location].name}.", target, 90, progress=current, reference=companion.id, origin=related[-1].text if related else "출발 시점에서 아직 성장할 수 있는 인연")
    else:
        social = Quest("q4", "bond_visits", "맹우들과 함께한 시간", "모든 인연이 이미 깊습니다. 직접 교류를 3회 수행해 함께한 시간을 남기세요.", 3, 90, origin="출발 시점의 모든 장수와 친밀도 80 이상")
    return [strategic, social]
