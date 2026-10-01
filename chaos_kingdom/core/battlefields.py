"""Regional battlefields shared by simulation, the editor, and validation tools."""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import json
import math
from pathlib import Path
import random

from .storage import user_directory
from .models import CASTLE_INDICES

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "battlefields"
TILES = {
    ".": ("초원", (100, 115, 73), 1.0, 1.0),
    "f": ("숲", (47, 78, 54), .68, 1.25),
    "h": ("바위 지대", (146, 137, 99), .72, 1.20),
    "r": ("도로", (166, 151, 112), 1.18, 1.0),
    "w": ("물", (65, 117, 138), 0.0, 1.0),
    "b": ("다리", (188, 162, 108), .82, 1.0),
    "#": ("성벽", (95, 97, 88), 0.0, 1.0),
    "g": ("성문", (149, 141, 110), .90, 1.15),
}


@dataclass
class Battlefield:
    region: str
    name: str
    biome: str
    tiles: list[str]
    spawns: list[list[list[int]]]
    objective: list[int]
    revision: int = 1
    schema: int = 1
    _paths: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def width(self):
        return len(self.tiles[0])

    @property
    def height(self):
        return len(self.tiles)

    def data(self):
        return {k: v for k, v in vars(self).items() if not k.startswith("_")}

    @classmethod
    def from_data(cls, data):
        try:
            result = cls(**data)
            result.validate()
            return result
        except (TypeError, KeyError, IndexError) as exc:
            raise ValueError("전장 파일 구조가 잘못되었습니다.") from exc

    def cell(self, x, y):
        return max(0, min(self.width - 1, int(x / 100 * self.width))), max(0, min(self.height - 1, int(y / 60 * self.height)))

    def point(self, cell):
        return ((cell[0] + .5) * 100 / self.width, (cell[1] + .5) * 60 / self.height)

    def walkable(self, cell):
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height and TILES[self.tiles[y][x]][2] > 0

    def nearest(self, cell):
        if self.walkable(cell):
            return tuple(cell)
        candidates = [(x, y) for y in range(self.height) for x in range(self.width) if self.walkable((x, y))]
        return min(candidates, key=lambda p: ((p[0] - cell[0]) ** 2 + (p[1] - cell[1]) ** 2, p)) if candidates else None

    def traversable(self, start, end):
        """Check every crossed grid interval, including a tiny corner crossing."""
        if any(not (0 <= p[0] <= 100 and 0 <= p[1] <= 60) for p in (start, end)):
            return False
        times = {0.0, 1.0}
        for axis, count, extent in ((0, self.width, 100), (1, self.height, 60)):
            delta = end[axis] - start[axis]
            if abs(delta) < 1e-9:
                continue
            first = max(1, math.floor(min(start[axis], end[axis]) * count / extent) + 1)
            last = min(count, math.floor(max(start[axis], end[axis]) * count / extent) + 1)
            for boundary in range(first, last):
                t = (boundary * extent / count - start[axis]) / delta
                if 0 < t < 1:
                    times.add(t)
        ordered = sorted(times)
        for t in [0, 1] + [(a + b) / 2 for a, b in zip(ordered, ordered[1:])]:
            if not self.walkable(self.cell(start[0] + (end[0] - start[0]) * t,
                                           start[1] + (end[1] - start[1]) * t)):
                return False
        return True

    def neighbors(self, cell):
        x, y = cell
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            other = x + dx, y + dy
            if self.walkable(other):
                yield other

    def path(self, start, end):
        start, end = tuple(start), tuple(end)
        key = start, end
        if key in self._paths:
            return self._paths[key]
        if not self.walkable(start) or not self.walkable(end):
            return ()
        frontier = [(0, start)]
        cost, previous = {start: 0.0}, {}
        while frontier:
            _, current = heapq.heappop(frontier)
            if current == end:
                break
            for neighbor in self.neighbors(current):
                tile = self.tiles[neighbor[1]][neighbor[0]]
                new_cost = cost[current] + 1 / TILES[tile][2]
                if new_cost < cost.get(neighbor, math.inf):
                    cost[neighbor], previous[neighbor] = new_cost, current
                    heuristic = (abs(neighbor[0] - end[0]) + abs(neighbor[1] - end[1])) / 1.18
                    heapq.heappush(frontier, (new_cost + heuristic, neighbor))
        result = []
        if end in cost:
            current = end
            while current != start:
                result.append(current)
                current = previous[current]
            result.append(start)
            result.reverse()
        if len(self._paths) > 8192:
            self._paths.clear()
        self._paths[key] = tuple(result)
        return self._paths[key]

    def effects(self, x, y):
        cx, cy = self.cell(x, y)
        return TILES[self.tiles[cy][cx]]

    def visible(self, start, end):
        distance = math.hypot(end[0] - start[0], end[1] - start[1])
        count = max(1, math.ceil(distance))
        seen, forests = set(), 0
        start_cell, end_cell = self.cell(*start), self.cell(*end)
        for i in range(1, count):
            cell = self.cell(start[0] + (end[0] - start[0]) * i / count, start[1] + (end[1] - start[1]) * i / count)
            if cell in seen or cell in (start_cell, end_cell):
                continue
            seen.add(cell)
            tile = self.tiles[cell[1]][cell[0]]
            if tile == "#":
                return False
            forests += tile == "f"
            if forests >= 3:
                return False
        return True

    def validate(self):
        if self.schema != 1 or self.region not in {f"s{i:02}" for i in range(50)}:
            raise ValueError("지원하지 않는 전장 버전 또는 지역입니다.")
        if len(self.tiles) != 20 or any(len(row) != 32 or set(row) - TILES.keys() for row in self.tiles):
            raise ValueError("전장은 32×20칸이며 등록된 지형만 사용할 수 있습니다.")
        if len(self.spawns) != 2 or any(len(side) != 5 for side in self.spawns):
            raise ValueError("양측에 각각 5개의 출진 위치가 필요합니다.")
        cells = [c for side in self.spawns for c in side] + [self.objective]
        if any(not isinstance(c, (list, tuple)) or len(c) != 2 or any(type(n) is not int for n in c) or not self.walkable(c) for c in cells):
            raise ValueError("출진 위치와 거점은 이동 가능한 칸에 있어야 합니다.")
        if any(len({tuple(c) for c in side}) != 5 for side in self.spawns) or set(map(tuple, self.spawns[0])) & set(map(tuple, self.spawns[1])):
            raise ValueError("출진 위치가 겹칩니다.")
        origin = tuple(self.objective)
        reachable, todo = {origin}, [origin]
        while todo:
            for neighbor in self.neighbors(todo.pop()):
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    todo.append(neighbor)
        if any(tuple(c) not in reachable for c in cells):
            raise ValueError("모든 출진 위치와 거점 사이에 통행 가능한 경로가 필요합니다.")


def generate_battlefield(region, name, biome):
    index = int(region[1:])
    rng = random.Random(8200 + index)
    grid = [["." for _ in range(32)] for _ in range(20)]
    lane = 7 + index % 6
    # Broad irregular patches, rather than independent dice rolls for every cell.
    # Rock represents rough ground and cover; the map has no elevation field.
    def patches(tile, count, large):
        for _ in range(count):
            cx, cy = rng.uniform(4, 27), rng.uniform(1, 18)
            rx, ry = rng.uniform(3, 6) * large, rng.uniform(2, 4) * large
            phase = rng.uniform(0, math.tau)
            for y in range(20):
                for x in range(3, 29):
                    dx, dy = (x - cx) / rx, (y - cy) / ry
                    angle = math.atan2(dy, dx)
                    edge = 1 + .16 * math.sin(3 * angle + phase) + .09 * math.sin(5 * angle - phase)
                    if dx * dx + dy * dy < edge * edge:
                        grid[y][x] = tile
    patches("h", 5 if biome == "mountain" else 2, 1.25 if biome == "mountain" else .7)
    patches("f", 6 if biome == "forest" else 3, 1.1 if biome == "forest" else .75)
    if biome in ("river", "coast"):
        river_x = 12 + index % 7
        for y in range(20):
            offset = int(math.sin((y + index) / 4) * 2)
            for x in range(river_x + offset, river_x + offset + 2):
                grid[y][x] = "w"
        for bridge_y in (3 + (index * 3) % 14,):
            for x in range(8, 24):
                if grid[bridge_y][x] == "w":
                    grid[bridge_y][x] = "b"
        if biome == "coast":
            for x in range(32):
                grid[19][x] = "w"
    # Short built walls/ruins, not cliff bands across mountain maps.
    if index % 3 == 0:
        for x in range(22, 27):
            grid[3 + index % 3][x] = "#"
    # A gently winding road is cardinally connected, including its bridge cells.
    road = []
    for x in range(32):
        y = lane + round(math.sin((x + index) / 7) * 1.5)
        previous = road[-1] if road else y
        for joined_y in range(min(previous, y), max(previous, y) + 1):
            grid[joined_y][x] = "b" if grid[joined_y][x] == "w" else "r"
        road.append(y)
    rows = [2, 5, 9, 13, 17]
    for x in (2, 29):
        for y in range(19):
            grid[y][x] = "r"
    if index in CASTLE_INDICES:
        # Built architecture encloses the defender's ground. Gates are explicit
        # traversable cells; neither walls nor rocks imply terrain elevation.
        for y in range(1, 19):
            for x in (25, 31):
                grid[y][x] = "g" if grid[y][x] in "rb" else "#"
        for y in (1, 18):
            for x in range(25, 32):
                grid[y][x] = "g" if grid[y][x] in "rb" else "#"
        for y in (5, 13):
            grid[y][25] = "g"
            for x in range(26, 30):
                grid[y][x] = "r"
        objective_x = 27
        for y in range(min(road[25], road[27]), max(road[25], road[27]) + 1):
            for x in range(25, 30):
                grid[y][x] = "g" if x == 25 else "r"
    else:
        objective_x = 17 + index % 5
    result = Battlefield(region, name, biome, ["".join(row) for row in grid],
                         [[[2, y] for y in rows], [[29, y] for y in rows]],
                         [objective_x, road[objective_x]], revision=3)
    result.validate()
    return result


_cache = {}


def load_battlefield(region, name="", biome="plains", *, custom=True):
    custom_path = user_directory() / "battlefields" / f"{region}.json"
    path = custom_path if custom and custom_path.is_file() else DATA_DIR / f"{region}.json"
    if not path.is_file():
        return generate_battlefield(region, name or region, biome)
    key = str(path), path.stat().st_mtime_ns
    if key not in _cache:
        _cache.clear()
        _cache[key] = Battlefield.from_data(json.loads(path.read_text(encoding="utf-8")))
    return _cache[key]


def save_battlefield(battlefield, path=None):
    battlefield._paths.clear()
    battlefield.validate()
    path = Path(path) if path else user_directory() / "battlefields" / f"{battlefield.region}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(battlefield.data(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path
