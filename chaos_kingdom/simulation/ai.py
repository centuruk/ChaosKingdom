from __future__ import annotations

from dataclasses import dataclass
from chaos_kingdom.core.models import Officer, World


@dataclass
class Decision:
    action: str
    score: float
    reason: str
    target: str | None = None


def evaluate(world: World, officer: Officer) -> list[Decision]:
    """Utility scores combine state, personality, relationships and recent memory."""
    loc = world.locations[officer.location]
    stats, traits = officer.stats, officer.traits
    tired = 100 - officer.energy
    recent = [m for m in officer.memories if world.turn - m.turn < 8]
    battle_stress = sum(abs(m.weight) for m in recent if m.kind == "defeat")
    revenge = battle_stress * traits["ambition"] / 100 * (100 - traits["empathy"]) / 100
    choices = [Decision("rest", tired * 1.5 + battle_stress * .35, "피로와 패전의 충격을 회복한다"),
               Decision("train", 22 + traits["ambition"] * .2 + (100 - stats["command"]) * .12 + revenge * .35, "패전과 야망을 헤아려 다음 지휘를 준비한다")]
    friendly = officer.faction is not None and loc.faction == officer.faction
    if friendly:
        threat = any(world.at_war(loc.faction, world.locations[n].faction) for n in loc.neighbors)
        choices.extend([
            Decision("develop", (100 - loc.prosperity) * .55 + stats["politics"] * .3 + traits["empathy"] * .12 + max(0, 450 - loc.food) * .06, "영지의 식량과 수입을 안정시킨다"),
            Decision("recruit", (1000 - loc.troops) * .06 + stats["command"] * .18 + (22 if threat else 0), "국경의 적과 부족한 수비 병력을 고려한다"),
            Decision("patrol", (100 - loc.morale) * .55 + traits["honor"] * .18 + (14 if threat else 0), "순찰로 민심과 주둔군 사기를 지킨다"),
        ])
        if loc.troops >= 1000 or loc.food < 20 or loc.treasury < 8:
            choices = [d for d in choices if d.action != "recruit"]
    peers = [o for o in world.residents(loc.id) if o.id != officer.id]
    if peers:
        def social_need(other: Officer) -> float:
            affinity = world.relationship(officer.id, other.id)
            shared = sum(m.weight for m in recent if m.other == other.id and m.kind in ("victory", "betrayal"))
            return max(0, 60 - affinity) * .35 - max(0, affinity - 70) * .6 + (10 if other.faction == officer.faction else 0) + shared * traits["empathy"] / 500
        target = max(peers, key=social_need)
        choices.append(Decision("bond", 18 + traits["empathy"] * .25 + stats["charm"] * .1 + social_need(target),
                                f"{target.name}와의 신뢰를 쌓는다", target.id))
        rival = min(peers, key=lambda o: world.relationship(officer.id, o.id))
        if world.relationship(officer.id, rival.id) < -15 and rival.faction == officer.faction and officer.rank != 4:
            choices.append(Decision("scheme", traits["ambition"] * .55 + (100 - traits["honor"]) * .3,
                                    f"경쟁자 {rival.name}의 영향력을 낮춘다", rival.id))
    if officer.rank != 4 and loc.governor != officer.id and loc.neighbors:
        destinations = [world.locations[n] for n in loc.neighbors if officer.faction is None or world.locations[n].faction in (officer.faction, None)]
        if destinations:
            def destination_need(s):
                friend = max((world.relationship(officer.id, o.id) for o in world.residents(s.id)), default=0)
                return ((1000 - s.troops) if friendly else s.prosperity * 5) + friend * traits["empathy"] / 100
            target = max(destinations, key=destination_need)
            frontier = any(world.at_war(officer.faction, world.locations[n].faction) for n in target.neighbors)
            choices.append(Decision("travel", 20 + traits["ambition"] * .2 + (22 if not friendly else 0) + (traits["courage"] * .28 if frontier else 0),
                                    f"{target.name}에서 새 기회를 찾는다", target.id))
    if officer.energy < 20:
        return [choices[0]]
    # Repeat fatigue prevents a fixed optimal action from trapping an officer forever.
    for choice in choices:
        if choice.action == officer.last_action:
            choice.score *= .73
    return sorted(choices, key=lambda d: d.score, reverse=True)


def choose(world: World, officer: Officer) -> Decision:
    choices = evaluate(world, officer)
    # Bounded noise represents incomplete information, while remaining reproducible.
    return max(choices, key=lambda d: d.score + world.rng.uniform(-12, 12))
