from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from chaos_kingdom.core.models import ACTION_NAMES, Memory, Officer, World, clamp, pair
from chaos_kingdom.core.korean import as_role, subject, together
from .ai import choose
from .battle import Battle


@dataclass
class ActionResult:
    ok: bool
    message: str
    battle: Battle | None = None


class Engine:
    def __init__(self, world: World):
        self.world = world
        self.action_counts: Counter = Counter()

    def player_action(self, action: str, target: str | None = None) -> ActionResult:
        world = self.world
        if world.player is None:
            return ActionResult(False, "먼저 플레이할 장수를 선택하세요.")
        if world.pending_battle:
            return ActionResult(False, "먼저 진행 중인 방어전을 마쳐야 합니다.", Battle.from_data(world, world.pending_battle))
        if world.outcome:
            return ActionResult(False, "캠페인이 종료되었습니다. 새 캠페인을 시작하세요.")
        officer = world.officers[world.player]
        if officer.captor:
            if action != "rest":
                return ActionResult(False, "포로 상태입니다. 휴식으로 석방을 기다리세요.")
            self.step()
            return ActionResult(True, "포로 교섭을 기다린다.")
        if action == "attack":
            error = self.attack_error(officer, target)
            if error:
                return ActionResult(False, error)
            battle = Battle(world, officer.location, target, officer.id, world.rng.randrange(2**31), interactive=True)
            return ActionResult(True, "전투가 시작됩니다.", battle)
        if action == "policy":
            if not officer.faction or officer.rank != 4:
                return ActionResult(False, "군주만 세력의 통치 방침을 바꿀 수 있습니다.")
            faction = world.factions[officer.faction]
            doctrines = ("balanced", "aggressive", "defensive", "mercantile")
            faction.doctrine = doctrines[(doctrines.index(faction.doctrine) + 1) % len(doctrines)]
            names = {"balanced": "균형", "aggressive": "공격", "defensive": "방어", "mercantile": "상업"}
            world.log("policy", f"{subject(officer.name)} {faction.name}의 방침을 {as_role(names[faction.doctrine])} 변경했다.", [officer.id])
            self.step()
            return ActionResult(True, f"통치 방침: {names[faction.doctrine]}")
        if action == "petition_war":
            if not officer.faction or officer.rank < 2 or target not in world.factions:
                return ActionResult(False, "대장 이상이 개전을 건의할 수 있습니다.")
            key = pair(officer.faction, target)
            if target == officer.faction or world.factions[target].eliminated or key in world.wars:
                return ActionResult(False, "평화 상태인 다른 세력을 선택하세요.")
            if key in world.treaties:
                return ActionResult(False, "불가침 조약이 만료될 때까지 기다리세요.")
            if officer.gold < 25:
                return ActionResult(False, "군사 회의 경비 25금이 필요합니다.")
            officer.gold -= 25
            accepted = officer.rank == 4 or world.rng.random() < .3 + officer.stats["command"] / 200
            if accepted:
                world.wars.append(key)
                world.log("war", f"{officer.name}의 군사 회의로 {subject(world.factions[officer.faction].name)} {world.factions[target].name}에 선전포고했다.", [officer.id])
            self.step()
            return ActionResult(True, "개전 건의가 받아들여졌다." if accepted else "군사 회의에서 개전이 보류되었다.")
        if action == "enlist":
            loc = world.locations[officer.location]
            if loc.faction is None or officer.faction == loc.faction:
                return ActionResult(False, "다른 세력이 통치하는 지역에서 임관할 수 있습니다.")
            if world.factions[loc.faction].eliminated:
                return ActionResult(False, "이 세력은 더 이상 존재하지 않습니다.")
            self._change_faction(officer, loc.faction, "스스로 새로운 주군을 택했다")
            self.step()
            return ActionResult(True, f"{world.factions[loc.faction].name}에 임관했다.")
        if action == "negotiate":
            if officer.faction is None or officer.rank < 2 or target not in world.factions:
                return ActionResult(False, "대장 이상의 장수만 외교를 제안할 수 있습니다.")
            if target == officer.faction or world.factions[target].eliminated:
                return ActionResult(False, "살아 있는 다른 세력을 선택하세요.")
            if officer.gold < 40:
                return ActionResult(False, "사절단 경비 40금이 필요합니다.")
            officer.gold -= 40
            chance = .25 + officer.stats["charm"] / 200 + officer.stats["intellect"] / 500
            success = world.rng.random() < chance
            if success:
                key = pair(officer.faction, target)
                if key in world.wars:
                    world.wars.remove(key)
                world.treaties[key] = world.turn + 12
                world.log("diplomacy", f"{officer.name}의 교섭으로 {together(world.factions[target].name)} 12주 불가침 조약을 맺었다.", [officer.id])
                officer.renown += 24
            self.step()
            return ActionResult(True, "12주 불가침 조약이 성립했다." if success else "사절단이 돌아왔다. 이번 교섭은 결렬되었다.")
        error = self.action_error(officer, action, target)
        if error:
            return ActionResult(False, error)
        message = self.perform(officer, action, target, player=True)
        self.step()
        return ActionResult(True, message)

    def action_error(self, officer: Officer, action: str, target: str | None) -> str | None:
        world, loc = self.world, self.world.locations[officer.location]
        if action not in ACTION_NAMES:
            return "알 수 없는 행동입니다."
        if action != "rest" and officer.energy < 15:
            return "기력이 부족합니다. 먼저 휴식하세요."
        if action in ("develop", "recruit", "patrol", "scheme") and (officer.faction is None or loc.faction != officer.faction):
            return "소속 세력의 지역에서 수행할 수 있습니다."
        if action in ("bond", "scheme"):
            other = world.officers.get(target or "")
            if not other or other.id == officer.id or other.location != officer.location or other.captor:
                return "같은 지역에 있는 다른 장수를 선택하세요."
        if action == "travel":
            if target not in loc.neighbors:
                return "도로로 직접 연결된 지역으로 이동할 수 있습니다."
            if world.at_war(officer.faction, world.locations[target].faction):
                return "교전 세력의 지역으로는 진군해야 합니다."
        if action == "recruit" and (loc.treasury < 8 or loc.food < 20 or loc.troops >= 1000):
            return "징병할 여력이나 병력의 빈자리가 없습니다."
        return None

    def attack_error(self, officer: Officer, target: str | None) -> str | None:
        world, loc = self.world, self.world.locations[officer.location]
        if not officer.faction or loc.faction != officer.faction:
            return "소속 세력의 지역에서 진군할 수 있습니다."
        if officer.rank < 1:
            return "기사 이상의 계급이 필요합니다. 내정과 수련으로 명성을 얻으세요."
        if officer.energy < 20 or loc.troops < 100 or loc.food < 150:
            return "기력 20, 주둔군 100명, 군량 150이 필요합니다."
        if target not in loc.neighbors:
            return "도로로 연결된 적 지역을 선택하세요."
        if not world.at_war(officer.faction, world.locations[target].faction):
            return "교전 중인 세력의 지역만 공격할 수 있습니다."
        return None

    def perform(self, officer: Officer, action: str, target: str | None = None, *, player: bool = False) -> str:
        world, loc = self.world, self.world.locations[officer.location]
        self.action_counts[action] += 1
        officer.last_action = action
        if action == "rest":
            officer.energy = clamp(officer.energy + 32)
            text = "충분히 쉬어 기력을 회복했다."
        else:
            officer.energy = clamp(officer.energy - (20 if action in ("recruit", "travel") else 15))
            officer.renown += 3 if action == "bond" else 6
            if action == "train":
                key = min(officer.stats, key=officer.stats.get)
                if world.rng.random() < .65:
                    officer.stats[key] = min(100, officer.stats[key] + 1)
                text = "전술과 검술을 수련했다. 능력과 명성이 성장한다."
            elif action == "develop":
                gain = 1.2 + officer.stats["politics"] / 50
                loc.prosperity = clamp(loc.prosperity + gain)
                loc.food = min(8000, loc.food + officer.stats["politics"] * .8)
                text = f"{loc.name}의 번영이 {gain:.1f} 증가했다."
            elif action == "recruit":
                amount = min(1000 - loc.troops, 16 + officer.stats["command"] // 3, int(loc.treasury / .5), int(loc.food / 1.2))
                loc.troops += amount
                loc.treasury -= amount * .5
                loc.food -= amount * 1.2
                text = f"{amount}명의 병사를 모집했다."
            elif action == "patrol":
                loc.morale = clamp(loc.morale + 6 + officer.stats["martial"] / 25)
                loc.fortification = clamp(loc.fortification + .8)
                text = f"{loc.name}의 치안과 수비 태세를 개선했다."
            elif action == "travel":
                officer.location = target
                text = f"{world.locations[target].name}에 도착했다."
                self._reassign_governors()
            elif action == "bond":
                other = world.officers[target]
                gain = 5 + officer.stats["charm"] / 18 + other.traits["empathy"] / 30
                previous = world.relationship(officer.id, other.id)
                current = world.change_bond(officer.id, other.id, gain)
                officer.remember(Memory(world.turn, "friendship", other.id, gain, f"{together(other.name)} 오래 이야기를 나누었다."))
                other.remember(Memory(world.turn, "friendship", officer.id, gain, f"{officer.name}의 방문을 기억한다."))
                if previous < 60 <= current:
                    world.log("bond", f"{together(officer.name)} {subject(other.name)} 맹우가 되었다.", [officer.id, other.id], loc.id)
                    officer.renown += 12
                text = f"{together(other.name)} 친밀도가 {gain:.0f} 증가했다. 현재 {current:.0f}."
                if player:
                    self._quest("bond", int(current), absolute=True)
                    self._quest("bond_visits", 1)
            elif action == "scheme":
                other = world.officers[target]
                world.change_bond(officer.id, other.id, -12)
                success = world.rng.random() < officer.stats["intellect"] / 120
                if success:
                    other.loyalty = clamp(other.loyalty - 6)
                    other.renown = max(0, other.renown - 12)
                else:
                    officer.loyalty = clamp(officer.loyalty - 8)
                other.remember(Memory(world.turn, "betrayal", officer.id, -20, f"{officer.name}의 모략을 의심한다."))
                text = "경쟁자의 평판을 흔들었다." if success else "모략이 발각되어 주군의 신뢰를 잃었다."
            else:
                raise ValueError(action)
        if player:
            world.log("action", f"{officer.name}: {text}", [officer.id], officer.location)
            if action in ("develop", "patrol"):
                self._quest("develop", 1)
                for quest in world.quests:
                    if quest.kind == "steward" and quest.reference == officer.location:
                        self._quest("steward", 1)
        return text

    def _quest(self, kind: str, progress: int, *, absolute: bool = False) -> None:
        world = self.world
        for quest in world.quests:
            if quest.kind == kind and not quest.complete:
                quest.progress = max(quest.progress, progress) if absolute else quest.progress + progress
                if quest.progress >= quest.target:
                    quest.complete = True
                    officer = world.officers[world.player]
                    officer.renown += quest.reward
                    officer.gold += quest.reward
                    world.log("quest", f"{officer.name}: 과업 ‘{quest.title}’ 완료. 명성 {quest.reward} 획득.", [officer.id])

    def step(self) -> None:
        world = self.world
        if world.outcome or world.pending_battle:
            return
        world.turn += 1
        self._economy()
        for officer in world.officers.values():
            officer.energy = clamp(officer.energy + 7)
            if officer.captor:
                officer.captivity -= 1
                if officer.captivity <= 0:
                    officer.captor = None
                    holdings = world.holdings(officer.faction)
                    if holdings:
                        officer.location = holdings[0].id
                    world.log("release", f"{subject(officer.name)} 포로 교섭으로 석방되었다.", [officer.id])
                continue
            if officer.id != world.player:
                decision = choose(world, officer)
                officer.intent = decision.reason
                if not self.action_error(officer, decision.action, decision.target):
                    self.perform(officer, decision.action, decision.target)
            self._career(officer)
            self._loyalty(officer)
        self._diplomacy()
        if world.turn % 3 == 0:
            self._campaigns()
        self._reassign_governors()
        self._incidents()
        if world.turn % 8 == 0:
            for key in world.bonds:
                world.bonds[key] *= .97
        if world.player:
            self._story_progress()
            if not world.pending_battle:
                self._finish_chapter()

    def _finish_chapter(self):
        world = self.world
        if world.outcome:
            return
        victor = world.unified_by
        if world.player and victor:
            world.victor = victor
            world.outcome = f"{subject(world.factions[victor].name)} 성 20개와 거점 30개를 모두 다스리며 엘드라스를 통일했다."
            world.log("ending", world.outcome)
        elif world.player and world.chapter_end and world.turn >= world.chapter_end:
            officer = world.officers[world.player]
            completed = sum(q.complete for q in world.quests)
            epithet = "왕국의 영웅" if world.victories >= 3 else "영지의 수호자" if completed >= 3 else "새 시대의 증인"
            world.chapter_report = f"{officer.name}, {epithet}. 명성 {officer.renown}, 승전 {world.victories}회, 과업 {completed}/{len(world.quests)}. 천하통일을 향한 다음 96주가 시작된다."
            world.chapter_end += 96
            world.log("chapter", world.chapter_report, [officer.id])

    def _story_progress(self):
        world = self.world
        officer = world.officers[world.player]
        for quest in world.quests:
            if quest.kind == "companion" and quest.reference in world.officers:
                self._quest("companion", max(0, int(world.relationship(officer.id, quest.reference))), absolute=True)
            elif quest.kind == "reclaim" and quest.reference in world.locations and officer.faction and world.locations[quest.reference].faction == officer.faction:
                self._quest("reclaim", 1, absolute=True)

    def _economy(self) -> None:
        world = self.world
        winter = world.turn % 48 >= 36
        for loc in world.locations.values():
            income = 12 + loc.prosperity * .5
            harvest = (24 + loc.prosperity * 1.0) * (.5 if winter else 1.3)
            loc.treasury = clamp(loc.treasury + income - loc.troops * .025, 0, 5000)
            loc.food = clamp(loc.food + harvest - loc.troops * (.08 if winter else .06), 0, 8000)
            if loc.food < 30:
                loc.troops = max(0, loc.troops - 10)
                loc.morale = clamp(loc.morale - 5)
            else:
                loc.morale = clamp(loc.morale + .5)
            if loc.treasury < 10:
                loc.morale = clamp(loc.morale - 3)
        if world.turn % 4 == 0:
            for officer in world.officers.values():
                if officer.faction:
                    officer.gold += 8 + officer.rank * 4

    def _career(self, officer: Officer) -> None:
        if not officer.faction or officer.rank >= 3:
            return
        thresholds = (35, 120, 260)
        if officer.renown >= thresholds[officer.rank]:
            officer.rank += 1
            officer.loyalty = clamp(officer.loyalty + 7)
            rank_name = ("수습 기사", "기사", "대장", "성주")[officer.rank]
            self.world.log("promotion", f"{subject(officer.name)} {as_role(rank_name)} 승진했다.", [officer.id], officer.location)

    def _loyalty(self, officer: Officer) -> None:
        world = self.world
        if not officer.faction or officer.rank == 4 or officer.captor:
            return
        ruler = world.factions[officer.faction].ruler
        affinity = world.relationship(officer.id, ruler)
        drift = (officer.traits["honor"] - officer.traits["ambition"]) / 160 + affinity / 200
        officer.loyalty = clamp(officer.loyalty + drift)
        if officer.id == world.player or officer.loyalty >= 30 or world.rng.random() > .12:
            return
        friends = sorted(world.officers.values(), key=lambda other: world.relationship(officer.id, other.id), reverse=True)
        candidate = next((o for o in friends if o.faction and o.faction != officer.faction and not world.factions[o.faction].eliminated and world.relationship(officer.id, o.id) > 22), None)
        if candidate:
            self._change_faction(officer, candidate.faction, f"{together(candidate.name)}의 인연을 따라 귀순했다")

    def _change_faction(self, officer: Officer, faction: str, reason: str) -> None:
        world = self.world
        previous = officer.faction
        # A player ruler's resignation also triggers a real succession.
        if previous and world.factions[previous].ruler == officer.id:
            successors = [o for o in world.officers.values() if o.faction == previous and o.id != officer.id and not o.captor]
            if successors:
                successor = max(successors, key=lambda o: o.renown + o.stats["command"])
                world.factions[previous].ruler = successor.id
                successor.rank, successor.loyalty = 4, 100
                world.log("succession", f"{subject(successor.name)} {world.factions[previous].name}의 새 군주가 되었다.", [successor.id])
        officer.faction, officer.loyalty, officer.rank = faction, 65, 1
        officer.location = world.factions[faction].capital
        officer.remember(Memory(world.turn, "defection", world.factions[faction].ruler, 20, reason))
        world.log("defection", f"{officer.name}: {reason}. 새 소속은 {world.factions[faction].name}.", [officer.id], officer.location)
        self._reassign_governors()

    def _diplomacy(self) -> None:
        world = self.world
        world.treaties = {key: until for key, until in world.treaties.items() if until > world.turn}
        if world.turn % 6:
            return
        for faction in world.factions.values():
            if faction.eliminated:
                continue
            holdings = world.holdings(faction.id)
            bordering = sorted({world.locations[n].faction for s in holdings for n in s.neighbors if world.locations[n].faction != faction.id and world.locations[n].faction})
            for other in bordering:
                key = pair(faction.id, other)
                if world.factions[other].eliminated or key in world.treaties:
                    continue
                ours = sum(s.troops for s in holdings)
                theirs = sum(s.troops for s in world.holdings(other))
                rulers_bond = world.relationship(faction.ruler, world.factions[other].ruler)
                if key in world.wars:
                    if (ours < theirs * .45 or rulers_bond > 55) and world.rng.random() < .6:
                        world.wars.remove(key)
                        world.treaties[key] = world.turn + 12
                        world.log("diplomacy", f"{together(faction.name)} {subject(world.factions[other].name)} 휴전을 맺었다.")
                elif world.rng.random() < (.38 if faction.doctrine == "aggressive" else .18) and rulers_bond < 35:
                    world.wars.append(key)
                    world.log("war", f"{subject(faction.name)} {world.factions[other].name}에 선전포고했다.")

    def _campaigns(self) -> None:
        world = self.world
        choices = []
        for source in world.locations.values():
            if source.troops < 280 or source.food < 160 or source.faction is None:
                continue
            commanders = [o for o in world.residents(source.id) if o.faction == source.faction and o.id != world.player and o.energy >= 25]
            if not commanders:
                continue
            commander = max(commanders, key=lambda o: o.stats["command"])
            for sid in source.neighbors:
                target = world.locations[sid]
                if not world.at_war(source.faction, target.faction):
                    continue
                ratio = source.troops * .82 / max(50, target.troops)
                bravery = commander.traits["courage"] / 300
                doctrine = world.factions[source.faction].doctrine
                threshold = 1.01 - bravery + (.12 if doctrine == "defensive" else -.1 if doctrine == "aggressive" else 0)
                if ratio > threshold:
                    score = ratio * 20 + (25 if target.kind == "castle" else 8) + world.rng.uniform(0, 12)
                    choices.append((score, source.id, target.id, commander.id))
        # The order is recalculated every turn, and only two campaigns can consume resources.
        used = set()
        count = 0
        for _, source, target, commander in sorted(choices, reverse=True):
            if source in used or target in used or self.attack_error(world.officers[commander], target):
                continue
            player = world.officers.get(world.player)
            defense = bool(player and player.location == target and player.faction == world.locations[target].faction and player.rank >= 1 and not player.captor)
            battle = Battle(world, source, target, commander, world.rng.randrange(2**31), interactive=defense, controlled_side=1 if defense else 0)
            if defense:
                world.pending_battle = battle.data()
                world.log("defense", f"{world.locations[target].name}에 적군이 접근한다. {player.name}에게 수비 지휘권이 주어졌다.", [player.id], target)
            else:
                battle.auto_resolve()
                self.resolve_battle(battle, advance=False)
            used.update((source, target))
            count += 1
            if count == 2:
                break

    def resolve_battle(self, battle: Battle, *, advance: bool = True) -> None:
        if not battle.finished:
            raise ValueError("아직 끝나지 않은 전투입니다.")
        if battle.resolved:
            raise ValueError("이미 반영한 전투입니다.")
        battle.resolved = True
        world = self.world
        was_pending = bool(world.pending_battle and world.pending_battle["source"] == battle.source and world.pending_battle["destination"] == battle.destination)
        if was_pending:
            world.pending_battle = None
        source, target = world.locations[battle.source], world.locations[battle.destination]
        commander = world.officers[battle.commander]
        survivors = [battle.totals(0), battle.totals(1)]
        reserves = source.troops - battle.deployed[0]
        source.troops = max(0, reserves + survivors[0])
        target.troops = max(0, survivors[1])
        source.food = max(0, source.food - 150)
        commander.energy = clamp(commander.energy - 25)
        previous = target.faction
        won = battle.winner == 0
        if won:
            target.faction = battle.attacker
            occupation = min(survivors[0], max(40, int(survivors[0] * .7)))
            target.troops = occupation
            source.troops = max(0, source.troops - occupation)
            target.morale, target.prosperity = 50, max(0, target.prosperity - 8)
            target.fortification = max(5, target.fortification - 15)
            commander.location = target.id
            commander.renown += 42 if target.kind == "castle" else 25
            commander.remember(Memory(world.turn, "victory", "", 20, f"{target.name}의 전투에서 승리했다."))
            for resident in world.residents(target.id):
                if resident.faction == previous:
                    holdings = world.holdings(previous)
                    if holdings:
                        resident.location = holdings[0].id
                    resident.loyalty = clamp(resident.loyalty - 8)
                    resident.remember(Memory(world.turn, "defeat", commander.id, -18, f"{target.name}에서 패전했다."))
                    world.change_bond(resident.id, commander.id, -10)
            if commander.id == world.player:
                world.victories += 1
                self._quest("battle", 1)
        else:
            commander.renown += 4
            commander.remember(Memory(world.turn, "defeat", "", -24, f"{target.name}의 전투에서 패전했다."))
            target.morale = clamp(target.morale + 5)
            if survivors[0] < battle.deployed[0] * .25 and world.rng.random() < .35:
                commander.captor, commander.captivity = previous, 4
                world.log("capture", f"{subject(commander.name)} 포로로 붙잡혔다.", [commander.id], target.id)
        for side in (0, 1):
            allies = sorted({u.officer for u in battle.units if u.side == side})
            for a, b in zip(allies, allies[1:]):
                world.change_bond(a, b, 7 if battle.winner == side else -3)
            for oid in allies:
                if oid != commander.id:
                    world.officers[oid].remember(Memory(world.turn, "victory" if battle.winner == side else "defeat", commander.id, 15 if battle.winner == side else -18, f"{target.name}의 {'승전' if battle.winner == side else '패전'}에 참가했다."))
        if was_pending and battle.winner == 1 and world.player:
            world.victories += 1
            world.officers[world.player].renown += 35
            self._quest("battle", 1)
        result = "함락" if won else "방어 성공"
        world.log("battle", f"{target.name} 전투 — {result}. {commander.name} 지휘, {battle.deployed[0]} 대 {battle.deployed[1]}명. 손실 {battle.deployed[0] - survivors[0]} / {battle.deployed[1] - survivors[1]}명.", [commander.id], target.id)
        self._eliminations()
        self._reassign_governors()
        if not world.pending_battle:
            if world.player:
                self._story_progress()
            self._finish_chapter()
        if advance and not was_pending:
            self.step()
        elif was_pending:
            self._story_progress()
            self._finish_chapter()

    def _eliminations(self) -> None:
        world = self.world
        for faction in world.factions.values():
            holdings = world.holdings(faction.id)
            if not holdings and not faction.eliminated:
                faction.eliminated = True
                world.log("fall", f"{subject(faction.name)} 마지막 영지를 잃고 붕괴했다.")
                world.wars = [key for key in world.wars if faction.id not in key.split(":")]
                for officer in world.officers.values():
                    if officer.faction == faction.id:
                        officer.faction, officer.rank = None, 0
                        officer.captor = None
                        officer.remember(Memory(world.turn, "fall", faction.ruler, -30, "섬기던 세력이 무너졌다."))
            elif holdings and world.locations[faction.capital].faction != faction.id:
                faction.capital = max(holdings, key=lambda s: (s.kind == "castle", s.troops)).id

    def _reassign_governors(self) -> None:
        world = self.world
        for loc in world.locations.values():
            residents = [o for o in world.residents(loc.id) if o.faction == loc.faction]
            loc.governor = max(residents, key=lambda o: o.rank * 20 + o.stats["politics"]).id if residents else None

    def _incidents(self) -> None:
        world = self.world
        if world.turn % 5 == 0:
            loc = world.rng.choice(list(world.locations.values()))
            if world.rng.random() < .45:
                loc.food = max(0, loc.food - 140)
                loc.morale = clamp(loc.morale - 7)
                world.log("incident", f"{loc.name}에서 흉작이 발생했다. 군량과 민심이 줄었다.", location=loc.id)
            else:
                loc.treasury = min(5000, loc.treasury + 120)
                world.log("incident", f"{loc.name}의 시장에 대상단이 도착했다. 세입이 늘었다.", location=loc.id)
        if world.turn % 9 == 0:
            free = [o for o in world.officers.values() if o.faction is None and not o.captor and o.id != world.player]
            if free:
                officer = world.rng.choice(free)
                faction = world.locations[officer.location].faction
                if faction:
                    self._change_faction(officer, faction, "새로운 주군에게 발탁되었다")
