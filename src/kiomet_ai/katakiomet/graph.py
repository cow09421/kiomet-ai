"""KataKiomet 圖結構世界模型：把 Kiomet 變成「棋盤」，不是像素。

核心規則：
- 所有未知值用 None 表示 UNKNOWN，絕不能用 0 代替。
- Tower（塔）= 節點（Node）；移動部隊 = 邊（Edge）。
- 不可變（frozen）快照；Belief（信念）層負責時間融合。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TowerNode:
    """單座塔的圖節點。units 等為 None 代表 UNKNOWN（未知）。"""
    id: int
    owner: str | None = None          # None＝中立或未知（配合 visible 判斷）
    tower_type: str | None = None
    position: tuple[float, float] | None = None
    visible: bool = False
    units: int | None = None
    production: float | None = None   # 每秒產兵（未知規則先 None）
    upgrade_state: str | None = None
    king_present: bool | None = None
    neighbors: tuple[int, ...] = ()
    supply: tuple[int, ...] = ()
    last_seen: float | None = None
    confidence: float = 0.0           # 0~1
    strategic_value: float | None = None


@dataclass(frozen=True)
class ForceEdge:
    """移動中的部隊。progress 0~1，eta_s 秒；未知為 None。"""
    id: str
    owner: str | None = None
    source: int = 0
    destination: int = 0
    units: int | None = None
    progress: float | None = None
    eta_s: float | None = None
    last_seen: float | None = None
    confidence: float = 0.0


@dataclass(frozen=True)
class GameGraph:
    """一張時間戳快照。只含當下可觀察資訊（Observation Contract 上游保證）。"""
    timestamp: float
    player_id: str
    towers: dict[int, TowerNode] = field(default_factory=dict)
    forces: tuple[ForceEdge, ...] = ()
    upgrade_resources: int | None = None
    king_tower: int | None = None
    score: int | None = None

    def own_towers(self) -> list[TowerNode]:
        return [t for t in self.towers.values()
                if t.visible and t.owner == self.player_id]

    def visible_enemies(self) -> list[TowerNode]:
        return [t for t in self.towers.values()
                if t.visible and t.owner not in (None, self.player_id)]
