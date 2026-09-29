"""Belief State（信念狀態）：部分資訊下的最後已知＋信心衰減。

- 只融合可觀察快照；絕不把預估值偽裝成真值（confidence 標示）。
- 新觀察覆寫對應塔／部隊；看不見的塔保留 last-seen，confidence 隨時間衰減。
- 敵方資訊越陳舊，呼叫方需配更高安全餘量（見 safety.py）。
"""
from __future__ import annotations

import time
from dataclasses import replace

from kiomet_ai.katakiomet.graph import ForceEdge, GameGraph, TowerNode


def decay(confidence: float, age_s: float, half_life_s: float = 8.0) -> float:
    """指數衰減信心；剛看到=1.0。"""
    if age_s <= 0:
        return min(1.0, max(0.0, confidence))
    return min(1.0, max(0.0, confidence)) * (0.5 ** (age_s / half_life_s))


class BeliefState:
    def __init__(self, player_id: str):
        self.player_id = player_id
        self.towers: dict[int, TowerNode] = {}
        self.forces: dict[str, ForceEdge] = {}
        self.updated_at: float = time.time()

    def update(self, observed: GameGraph) -> None:
        """融合一張可觀察快照。可見塔覆寫；不可見塔保留舊值只做衰減。"""
        now = observed.timestamp
        seen_ids = set()
        for tower in observed.towers.values():
            if tower.visible:
                seen_ids.add(tower.id)
                self.towers[tower.id] = replace(
                    tower, last_seen=now, confidence=1.0)
        for force in observed.forces:
            self.forces[force.id] = replace(force, last_seen=now, confidence=1.0)
        # 不可见塔：保留 last-seen，只更新信心（呼叫 get 時即時計算）。
        self.updated_at = now

    def tower(self, tower_id: int, now: float | None = None) -> TowerNode | None:
        """取塔並附上當下衰減後的 confidence；順帶回報 staleness 由呼叫方計算。"""
        tower = self.towers.get(tower_id)
        if tower is None:
            return None
        at = time.time() if now is None else now
        age = max(0.0, at - (tower.last_seen or at))
        return replace(tower, confidence=decay(tower.confidence, age))

    def staleness(self, tower_id: int, now: float | None = None) -> float | None:
        """資訊陳舊度（秒）；從未見過回 None（=完全未知）。"""
        tower = self.towers.get(tower_id)
        if tower is None or tower.last_seen is None:
            return None
        at = time.time() if now is None else now
        return max(0.0, at - tower.last_seen)

    def snapshot(self, now: float | None = None) -> GameGraph:
        """輸出當下信念快照（供風險評估，非真值）。"""
        at = time.time() if now is None else now
        towers = {}
        for tower_id, tower in self.towers.items():
            age = max(0.0, at - (tower.last_seen or at))
            towers[tower_id] = replace(tower, confidence=decay(tower.confidence, age))
        return GameGraph(timestamp=at, player_id=self.player_id,
                         towers=towers, forces=tuple(self.forces.values()))
