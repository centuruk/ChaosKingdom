from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
import random

from chaos_kingdom.core.models import Officer, World, clamp
from chaos_kingdom.core.battlefields import Battlefield, load_battlefield


UNIT_NAMES = {"infantry": "보병", "archer": "궁병", "cavalry": "기병", "spear": "창병"}
PROFILES = {
    "infantry": (3.2, 3.2, 0.92, 1.05),
    "archer": (2.6, 19.0, 0.66, 0.75),
    "cavalry": (5.1, 3.8, 1.22, 0.9),
    "spear": (2.8, 3.5, 0.84, 1.2),
}


@dataclass
class Unit:
    id: int
    side: int
    officer: str
    name: str
    kind: str
    x: float
    y: float
    soldiers: float
    initial: int
    morale: float
    skill: float
    cohesion: float
    order: str = "advance"
    target: int | None = None
    destination: tuple[float, float] | None = None
    facing: float = 0
    routed: bool = False
    route: list = field(default_factory=list)
    route_goal: tuple | None = None
    courage: float = 50
    tactic_at: float = 0

    @property
    def alive(self) -> bool:
        return self.soldiers >= 1 and not self.routed


class Battle:
    """A bounded 0.2-second simulation; the UI never determines combat results."""

    def __init__(self, world: World, source: str, destination: str, commander: str, seed: int,
                 *, interactive: bool = False, battlefield: Battlefield | None = None, controlled_side: int = 0):
        self.source, self.destination, self.commander = source, destination, commander
        self.attacker = world.locations[source].faction
        self.defender = world.locations[destination].faction
        self.terrain = world.locations[destination].terrain
        loc = world.locations[destination]
        self.field = battlefield or load_battlefield(destination, loc.name, loc.terrain)
        self.field.validate()
        self.terrain = self.field.biome
        self.control = [0.0, 0.0]
        self.rng = random.Random(seed)
        self.interactive = interactive
        self.controlled_side = controlled_side
        self.time = 0.0
        self.accumulator = 0.0
        self.finished = False
        self.resolved = False
        self.winner: int | None = None
        self.reason = ""
        self.rally_ready = [0.0, 0.0]
        self.units: list[Unit] = []
        self.deployed = [min(1000, int(world.locations[source].troops * .82)), world.locations[destination].troops]
        for side, location in enumerate((source, destination)):
            faction = self.attacker if side == 0 else self.defender
            local = sorted((o for o in world.residents(location) if o.faction == faction), key=lambda o: o.stats["command"], reverse=True)
            governor = world.officers.get(world.locations[location].governor)
            reserves = [o for o in world.officers.values() if o.faction == faction and not o.captor]
            leader = world.officers[commander] if side == 0 else (
                governor if governor and governor.faction == faction else (local[0] if local else max(reserves, key=lambda o: o.stats["command"]) if reserves else world.officers[commander]))
            if interactive and controlled_side == side == 1 and world.player:
                leader = world.officers[world.player]
            local = [leader] + [o for o in local if o.id != leader.id]
            kinds = ["infantry", "archer", "cavalry", "spear", "infantry"]
            count = min(5, max(1, self.deployed[side] // 35))
            for index in range(count):
                officer = local[index % len(local)]
                n = self.deployed[side] // count + (index < self.deployed[side] % count)
                cohesion = clamp(70 + world.relationship(leader.id, officer.id) * .15, 45, 95)
                morale = clamp(world.locations[location].morale + leader.stats["command"] * .15 + self.rng.uniform(-2, 2), 30, 100)
                skill = (officer.stats["command"] * .55 + officer.stats["martial"] * .25 + officer.stats["intellect"] * .2) / 100
                if officer.specialty == kinds[index]:
                    skill += .12
                x, y = self.field.point(self.field.spawns[side][index])
                self.units.append(Unit(len(self.units), side, officer.id, officer.name, kinds[index],
                                       x, y, n, n, morale, skill, cohesion,
                                       order="advance" if side == 0 else "hold", facing=0 if side == 0 else math.pi, courage=officer.traits["courage"]))
        self.defense_bonus = 1 + world.locations[destination].fortification / 600

    def totals(self, side: int) -> int:
        return sum(max(0, int(u.soldiers)) for u in self.units if u.side == side)

    def data(self):
        keys = ("source", "destination", "commander", "attacker", "defender", "terrain", "interactive", "time", "accumulator",
                "finished", "resolved", "winner", "reason", "rally_ready", "deployed", "defense_bonus", "control", "controlled_side")
        return {"schema": 1, **{k: getattr(self, k) for k in keys}, "field": self.field.data(), "units": [asdict(u) for u in self.units]}

    @classmethod
    def from_data(cls, world, data):
        if data.get("schema") != 1 or data.get("resolved"):
            raise ValueError("지원하지 않거나 이미 결산된 전투입니다.")
        field_map = Battlefield.from_data(data["field"])
        result = cls(world, data["source"], data["destination"], data["commander"], 0, interactive=True, battlefield=field_map)
        for key in result.data():
            if key not in ("schema", "field", "units"):
                setattr(result, key, data[key])
        if result.controlled_side not in (0, 1) or not 0 <= result.time <= 180.21 or not 0 <= result.accumulator <= 1.01:
            raise ValueError("전투 시간 또는 지휘 편이 잘못되었습니다.")
        result.units = [Unit(**{**u, "route_goal": tuple(u["route_goal"]) if u.get("route_goal") else None}) for u in data["units"]]
        if len(result.units) not in range(2, 11) or len({u.id for u in result.units}) != len(result.units):
            raise ValueError("전투 부대 정보가 잘못되었습니다.")
        if any(u.side not in (0, 1) or u.officer not in world.officers or u.kind not in PROFILES or not 0 <= u.soldiers <= u.initial <= 1000 or not 0 <= u.morale <= 100 or not 0 <= u.x <= 100 or not 0 <= u.y <= 60 or not field_map.walkable(field_map.cell(u.x, u.y)) for u in result.units):
            raise ValueError("전투 병력 또는 위치가 잘못되었습니다.")
        if any(sum(u.initial for u in result.units if u.side == side) != result.deployed[side] or result.deployed[side] > 1000 for side in (0, 1)):
            raise ValueError("출진 병력 합계가 잘못되었습니다.")
        return result

    def active(self, side: int) -> list[Unit]:
        return [u for u in self.units if u.side == side and u.alive]

    def issue(self, ids: list[int], order: str, point: tuple[float, float] | None = None, target: int | None = None) -> None:
        if self.finished or order not in {"advance", "charge", "hold", "flank", "move"}:
            return
        chosen = [u for u in self.units if u.id in ids and u.side == self.controlled_side and u.alive]
        destinations = {}
        if order == "move" and point and chosen:
            center = self.field.nearest(self.field.cell(*point))
            frontier, slots = [center], []
            seen = {center}
            while frontier and len(slots) < len(chosen):
                cell = frontier.pop(0)
                slots.append(cell)
                for cell in self.field.neighbors(cell):
                    if cell not in seen:
                        seen.add(cell)
                        frontier.append(cell)
            destinations = {u.id: self.field.point(cell) for u, cell in zip(chosen, slots)}
        for unit in self.units:
            if unit.id in ids and unit.side == self.controlled_side and unit.alive:
                unit.order, unit.destination, unit.target = order, destinations.get(unit.id, point), target
                unit.route, unit.route_goal = [], None
                unit.tactic_at = self.time + 8

    def _tactics(self, unit, target, distance, reach):
        """Coordinate a defensible objective, then react to nearby threats."""
        unit.tactic_at = self.time + 4
        if unit.kind == "archer" and distance < 8:
            unit.order, unit.destination = "move", (clamp(unit.x + (-9 if unit.side == 0 else 9), 3, 97), unit.y)
        elif unit.side == 1 and distance > (reach if unit.kind == "archer" else 12):
            # Defensive deployment is a formation around the contested objective,
            # rather than five independent units waiting at their starting edge.
            index = [u.id for u in self.units if u.side == unit.side].index(unit.id)
            offset = ((2, -2), (4, 1), (1, 3), (0, -1), (2, 2))[index]
            goal = self.field.nearest((self.field.objective[0] + offset[0], self.field.objective[1] + offset[1]))
            destination = self.field.point(goal)
            unit.order = "move" if math.dist((unit.x, unit.y), destination) > 1 else "hold"
            unit.destination = destination if unit.order == "move" else None
        elif unit.kind == "archer":
            unit.order, unit.destination = ("advance" if distance > reach else "hold"), None
        elif unit.kind == "cavalry" and target.kind == "archer" and unit.courage > 55 and distance < 32:
            unit.order, unit.destination = "flank", None
        elif target.kind == "cavalry" and unit.kind == "spear" and distance < 8:
            unit.order, unit.destination = "hold", None
        elif distance < 10 and unit.courage > 65 and target.kind != "spear" and unit.morale > 55:
            unit.order, unit.destination = "charge", None
        else:
            unit.order, unit.destination = "advance", None

    def _separate_units(self):
        """Resolve crowding on traversable ground without crossing a wall/river.

        This is local steering, not a second pathfinder. Stable unit order and
        bounded passes make midpoint saves resume identically.
        """
        living = [u for u in self.units if u.alive]
        def nudge(unit, dx, dy):
            x, y = unit.x + dx, unit.y + dy
            if self.field.traversable((unit.x, unit.y), (x, y)):
                unit.x, unit.y = x, y
        for _ in range(4):
            for i, first in enumerate(living):
                for second in living[i + 1:]:
                    dx, dy = second.x - first.x, second.y - first.y
                    distance = math.hypot(dx, dy)
                    minimum = 2.4 if first.side == second.side else 1.8
                    if distance >= minimum:
                        continue
                    if distance < .001:
                        angle = (first.id * 7 + second.id * 11) * .73
                        dx, dy, distance = math.cos(angle), math.sin(angle), 1
                        overlap = minimum / 2
                    else:
                        overlap = (minimum - distance) / 2
                    nudge(first, -dx / distance * overlap, -dy / distance * overlap)
                    nudge(second, dx / distance * overlap, dy / distance * overlap)

    def rally(self, side: int | None = None) -> bool:
        side = self.controlled_side if side is None else side
        if self.finished or self.time < self.rally_ready[side]:
            return False
        for unit in self.active(side):
            unit.morale = clamp(unit.morale + 16)
        self.rally_ready[side] = self.time + 35
        return True

    def retreat(self, side: int | None = None) -> None:
        side = self.controlled_side if side is None else side
        if not self.finished:
            self.finished, self.winner, self.reason = True, 1 - side, "철수 명령"

    def update(self, dt: float) -> None:
        self.accumulator += min(dt, 1.0)
        while self.accumulator >= .2 and not self.finished:
            self.accumulator -= .2
            self._step(.2)

    def auto_resolve(self) -> None:
        while not self.finished:
            self.update(1.0)

    def _step(self, dt: float) -> None:
        self.time += dt
        for side in (0, 1):
            if not self.active(side):
                self.finished, self.winner, self.reason = True, 1 - side, "적 부대 와해"
                return
        damage = {u.id: 0.0 for u in self.units}
        pressure = {u.id: 0.0 for u in self.units}
        for unit in self.units:
            if not unit.alive:
                continue
            enemies = self.active(1 - unit.side)
            target = next((e for e in enemies if e.id == unit.target), None)
            if target is None:
                target = min(enemies, key=lambda e: math.hypot(e.x - unit.x, e.y - unit.y) * (.8 + e.soldiers / max(1, e.initial) * .2))
                unit.target = target.id
            speed, reach, attack, armor = PROFILES[unit.kind]
            distance = math.hypot(target.x - unit.x, target.y - unit.y)
            if unit.kind == "archer" and distance < 6:
                attack *= .4
            ai_controls = unit.side != self.controlled_side or not self.interactive
            if ai_controls and self.time >= unit.tactic_at:
                self._tactics(unit, target, distance, reach)
            if ai_controls and unit.morale < 55 and self.time >= self.rally_ready[unit.side]:
                self.rally(unit.side)
            point = None
            if unit.order == "move" and unit.destination:
                point = unit.destination
            elif unit.order == "flank":
                lane = 5 if unit.y < 30 else 56
                if unit.destination is None:
                    unit.destination = (clamp(target.x + (8 if unit.side == 0 else -8), 4, 96), lane)
                if math.hypot(unit.destination[0] - unit.x, unit.destination[1] - unit.y) > 1:
                    point = unit.destination
                else:
                    unit.order, unit.destination = "advance", None
                    point = (target.x, target.y)
            elif unit.order in ("advance", "charge", "flank") and (distance > reach * .9 or not self.field.visible((unit.x, unit.y), (target.x, target.y))):
                point = (target.x, target.y)
            if point:
                end = self.field.nearest(self.field.cell(*point))
                if end != unit.route_goal or not unit.route:
                    path = self.field.path(self.field.cell(unit.x, unit.y), end)
                    if not path:
                        unit.order, unit.destination = "hold", None
                        continue
                    unit.route = [self.field.point(c) for c in path]
                    unit.route_goal = end
                while unit.route and math.hypot(unit.route[0][0] - unit.x, unit.route[0][1] - unit.y) < .3:
                    unit.route.pop(0)
                waypoint = unit.route[0] if unit.route else self.field.point(end)
                dx, dy = waypoint[0] - unit.x, waypoint[1] - unit.y
                travel = math.hypot(dx, dy)
                if travel > .05:
                    terrain_speed = self.field.effects(unit.x, unit.y)[2]
                    step = min(travel, dt * speed * terrain_speed * (.8 + unit.cohesion / 250))
                    proposed = (unit.x + dx / travel * step, unit.y + dy / travel * step)
                    if not self.field.traversable((unit.x, unit.y), proposed):
                        # Steering can leave a unit off the path's cell center.
                        # Recenter before following the next cardinal edge.
                        center = self.field.point(self.field.cell(unit.x, unit.y))
                        dx, dy = center[0] - unit.x, center[1] - unit.y
                        travel = math.hypot(dx, dy)
                        if travel > .001:
                            step = min(step, travel)
                            proposed = unit.x + dx / travel * step, unit.y + dy / travel * step
                        else:
                            proposed = unit.x, unit.y
                        unit.route, unit.route_goal = [], None
                    unit.x, unit.y = proposed
                    unit.facing = math.atan2(dy, dx)
                elif unit.order == "move" and not unit.route:
                    unit.order, unit.destination = "hold", None
            distance = math.hypot(target.x - unit.x, target.y - unit.y)
            if distance > reach:
                continue
            if not self.field.visible((unit.x, unit.y), (target.x, target.y)):
                continue
            angle = math.atan2(unit.y - target.y, unit.x - target.x)
            rear = abs(math.atan2(math.sin(angle - target.facing), math.cos(angle - target.facing))) > 2.1
            modifier = 1.30 if rear and unit.kind != "archer" else 1.0
            if unit.kind == "cavalry" and target.kind == "spear":
                modifier *= .48
            if unit.kind == "spear" and target.kind == "cavalry":
                modifier *= 1.6
            if unit.order == "charge":
                modifier *= 1.28
                unit.morale = clamp(unit.morale - dt * .6)
            if target.order == "hold":
                modifier *= .8
            if self.field.effects(unit.x, unit.y)[0] == "숲" and unit.kind == "cavalry":
                modifier *= .65
            defense = PROFILES[target.kind][3] * (self.defense_bonus if target.side == 1 else 1)
            defense *= self.field.effects(target.x, target.y)[3]
            dealt = dt * (unit.soldiers ** .65 / 8) * attack * (.65 + unit.skill) * (.45 + unit.morale / 100) * modifier / defense
            damage[target.id] += dealt
            pressure[target.id] += dealt * (.5 + (1 if rear else 0))
        for unit in self.units:
            if not unit.alive:
                continue
            unit.soldiers = max(0, unit.soldiers - damage[unit.id])
            unit.morale = clamp(unit.morale - pressure[unit.id] / max(30, unit.initial) * 65)
            if unit.morale < 13 or unit.soldiers < unit.initial * .13:
                unit.routed = True
                for ally in self.active(unit.side):
                    ally.morale = clamp(ally.morale - 8)
        self._separate_units()
        objective = self.field.point(self.field.objective)
        controlling = [any(math.hypot(u.x - objective[0], u.y - objective[1]) < 8 for u in self.active(side)) for side in (0, 1)]
        if controlling[0] != controlling[1]:
            self.control[int(controlling[1])] += dt
        if self.time >= 180:
            strength = [sum(u.soldiers * (.4 + u.morale / 100) for u in self.active(side)) + self.control[side] * 2 for side in (0, 1)]
            self.finished, self.winner, self.reason = True, int(strength[1] >= strength[0]), "해질녘의 전황 판정"
