"""Tower::force_units 的只讀離線鏡像；不呼叫瀏覽器、WASM 或遊戲 API。"""
from __future__ import annotations

from dataclasses import dataclass

from kiomet_ai.observe import TOWER_TYPES, TowerUnitCounts, UNIT_NAMES


@dataclass(frozen=True)
class DeployableForce:
    """正式函式回傳的逐兵種組成；與策略預留或路徑合法性分開。"""

    counts: dict[str, int]
    total: int
    tower_type: str
    production_rule: str
    input_evidence: str
    trace: tuple[str, ...]


def _u8(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255


def mirror_force_units(unit_counts: TowerUnitCounts | None,
                       tower_type: str | None) -> DeployableForce | None:
    """從已觀察的塔狀態推導逐兵種可派組成；資料不完整時回 UNKNOWN（None）。

    正式函式 2031 只排除非 Projector 塔的 Shield；所有其他非零兵種
    原量加入。這裡不把所有權、路徑、國王拖曳延遲或策略預留混入結果。
    """
    if unit_counts is None or tower_type not in TOWER_TYPES or not _u8(unit_counts.shield):
        return None
    composition = {name: 0 for name in UNIT_NAMES}
    trace = []
    if unit_counts.units_kind == "MANY":
        values = [unit_counts.fighter, unit_counts.chopper, unit_counts.bomber,
                  unit_counts.tank, unit_counts.soldier]
        if not all(_u8(value) for value in values):
            return None
        composition.update(zip(UNIT_NAMES[1:6], values))
        evidence = "RUNTIME_VALIDATED"
        trace.append("Many：Fighter、Chopper、Bomber、Tank、Soldier 的目前數量原量納入")
    elif unit_counts.units_kind == "SINGLE":
        name, count = unit_counts.single_unit_type, unit_counts.single_count
        if name not in UNIT_NAMES[6:] or not _u8(count) or count == 0:
            return None
        composition[name] = count
        evidence = "INFERRED"  # Single 只有 Ruler 自然樣本，缺正式介面數字。
        trace.append(f"Single：{name} 的目前數量 {count} 納入")
    else:
        return None
    if tower_type == "Projector":
        composition["Shield"] = unit_counts.shield
        trace.append("Projector：Shield 可移動，原量納入")
    else:
        trace.append("非 Projector：Shield 不可移動，保留在塔內")
    return DeployableForce(counts=composition,total=sum(composition.values()),
                           tower_type=tower_type,production_rule="PRODUCTION_PROVEN",
                           input_evidence=evidence,trace=tuple(trace))
