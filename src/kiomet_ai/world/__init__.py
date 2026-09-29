from dataclasses import dataclass, asdict
from typing import Any

@dataclass(frozen=True)
class Tower:
    id: int
    owner: str | None
    tower_type: str
    units: int
    neighbors: tuple[int, ...] = ()
    king: bool = False
    upgrade_state: str | None = None

@dataclass(frozen=True)
class Force:
    id: str
    owner: str
    source: int
    destination: int
    units: int

@dataclass(frozen=True)
class PlayerState:
    id: str
    score: int | None = None
    rank: int | None = None
    upgrade_resources: int | None = None

@dataclass(frozen=True)
class ObservableState:
    schema_version: int
    observation_id: str
    timestamp: float
    tick: int
    player: PlayerState
    towers: tuple[Tower, ...]
    forces: tuple[Force, ...]
    supply_lines: tuple[tuple[int, int], ...]
    source: str = "mock"

    def tower(self, identifier: int) -> Tower | None:
        return next((t for t in self.towers if t.id == identifier), None)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> dict[str, Any]:
        return {"observation_id": self.observation_id, "tick": self.tick,
                "source": self.source, "score": self.player.score, "rank": self.player.rank,
                "own_towers": sum(t.owner == self.player.id for t in self.towers),
                "visible_enemies": len({t.owner for t in self.towers if t.owner not in (None, self.player.id)} | {f.owner for f in self.forces if f.owner != self.player.id}),
                "moving_forces": len(self.forces)}

class WorldModel:
    """只保存最新可觀察快照；不累積不可見敵人或原始狀態。"""
    def __init__(self):
        self.current: ObservableState | None = None

    def update(self, observation: ObservableState) -> None:
        if not isinstance(observation, ObservableState):
            raise TypeError("世界模型只接受可觀察狀態")
        if self.current and observation.tick < self.current.tick:
            raise ValueError("拒絕過期觀察")
        self.current = observation
