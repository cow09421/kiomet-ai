from dataclasses import dataclass, replace
import time
from uuid import uuid4
from kiomet_ai.world import ObservableState, Tower, Force, PlayerState

@dataclass
class RawMockState:
    """僅用於本機模擬。包含刻意不可見的測試資料，禁止傳給規劃器。"""
    towers: dict[int, Tower]
    visible_ids: set[int]
    forces: list[Force]
    supply_lines: list[tuple[int, int]]
    tick: int = 0
    resources: int = 30

class MockGame:
    def __init__(self):
        self.raw = RawMockState(
            towers={
                1: Tower(1, "self", "Outpost", 40, (2, 3, 99), True),
                2: Tower(2, None, "Outpost", 4, (1, 3)),
                3: Tower(3, "enemy", "Outpost", 8, (1, 2)),
                99: Tower(99, "hidden_enemy", "Radar", 999, (1,)),
            }, visible_ids={1, 2, 3}, forces=[], supply_lines=[])

    def advance(self):
        self.raw.tick += 1
        self.raw.forces.clear()
        # 此為測試規則，不代表 Kiomet 真實遊戲規則。
        for identifier, tower in list(self.raw.towers.items()):
            if tower.owner == "self":
                self.raw.towers[identifier] = replace(tower, units=min(100, tower.units + 1))

class MockObserver:
    def __init__(self, game: MockGame):
        self._game = game
        self.count = 0

    async def observe(self) -> ObservableState:
        self.count += 1
        raw = self._game.raw
        visible = raw.visible_ids
        towers = tuple(replace(t, neighbors=tuple(n for n in t.neighbors if n in visible))
                       for identifier, t in sorted(raw.towers.items()) if identifier in visible)
        forces = tuple(f for f in raw.forces if f.source in visible and f.destination in visible)
        lines = tuple((a, b) for a, b in raw.supply_lines if a in visible and b in visible)
        return ObservableState(1, str(uuid4()), time.time(), raw.tick,
            PlayerState("self", sum(t.owner == "self" for t in towers) * 100, None, raw.resources),
            towers, forces, lines)
