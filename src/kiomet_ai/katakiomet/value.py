"""Heuristic Value（人工局面價值）：多目標評分，極度偏向穩定而非搶分。

優先級：King 活著 >> 戰線不崩 >> 核心生產區 >> 預備隊 >> 合理擴張 >> 分數。
輸出 breakdown（分項）供 Dashboard「AI 思考監視器」顯示。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kiomet_ai.katakiomet.graph import GameGraph
from kiomet_ai.katakiomet.ownership import frontlines


@dataclass(frozen=True)
class ValueBreakdown:
    total: float
    parts: dict[str, float] = field(default_factory=dict)


# 預設權重（可被 Self-Play 調參覆寫）。
DEFAULT_WEIGHTS = {
    "king_safety": 100.0,
    "frontline": 20.0,
    "territory": 5.0,
    "production": 4.0,
    "reserve": 6.0,
    "exposure": -8.0,
    "overextension": -6.0,
}


def evaluate(graph: GameGraph, weights: dict[str, float] | None = None) -> ValueBreakdown:
    """未知欄位不計分（不把 UNKNOWN 當 0 懲罰，也不當滿分獎勵）。"""
    weights = weights or DEFAULT_WEIGHTS
    me = graph.player_id
    own = [t for t in graph.towers.values() if t.visible and t.owner == me]
    parts: dict[str, float] = {}

    # King Safety：國王塔存在且兵力充足為滿分；找不到國王為重罰。
    king = next((t for t in own if t.king_present), None)
    if king is None:
        parts["king_safety"] = -1.0 if graph.king_tower is None else 0.0
    elif king.units is None:
        parts["king_safety"] = 0.5
    else:
        parts["king_safety"] = min(1.0, king.units / 30.0)

    # Frontline：戰線數量適中為佳（0 條可能代表資訊缺失，不獎勵）。
    lines = frontlines(graph)
    parts["frontline"] = 0.5 if not lines else max(0.0, 1.0 - 0.2 * (len(lines) - 1))

    # Territory／Production：我方塔數與已知產能。
    parts["territory"] = min(1.0, len(own) / 10.0)
    known_prod = [t.production or 0 for t in own if t.production is not None]
    parts["production"] = min(1.0, sum(known_prod) / 10.0) if known_prod else 0.5

    # Reserve：後方（非戰線端點）閒置兵力比例。
    line_towers = {i for pair in lines for i in pair}
    rear_units = sum(t.units or 0 for t in own
                     if t.id not in line_towers and t.units is not None)
    total_units = sum(t.units or 0 for t in own if t.units is not None)
    parts["reserve"] = (rear_units / total_units) if total_units else 0.5

    # Exposure：與敵接壤的我方塔比例（越低越好，取負向）。
    exposed = sum(1 for t in own
                  if any(graph.towers.get(n) is not None
                         and graph.towers[n].visible
                         and graph.towers[n].owner not in (None, me)
                         for n in t.neighbors))
    parts["exposure"] = -(exposed / len(own)) if own else 0.0

    # Overextension：孤立我方塔（無我方鄰接）比例，取負向。
    isolated = sum(1 for t in own
                   if not any(graph.towers.get(n) is not None
                              and graph.towers[n].visible
                              and graph.towers[n].owner == me
                              for n in t.neighbors))
    parts["overextension"] = -(isolated / len(own)) if own else 0.0

    total = sum(weights.get(k, 0.0) * v for k, v in parts.items())
    return ValueBreakdown(total=total, parts=parts)
