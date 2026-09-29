"""Heuristic Ownership（人工控制權估計）：借 KataGo Ownership 思想。

對每座可觀察塔估 control_probability_me（我方控制機率 0~1）。
不用神經網路；用距離、鄰接、兵力、產能、增援 ETA、周圍敵軍、補給方向近似。
Frontline（戰線）由控制權梯度推導，不用「旁邊有敵塔就是前線」的粗糙定義。
"""
from __future__ import annotations

from kiomet_ai.katakiomet.graph import GameGraph


def control_probability(graph: GameGraph, tower_id: int) -> float | None:
    """回傳 0~1；資訊不足回 None（UNKNOWN），不硬給 0.5 假裝知道。

    近似規則（heuristic，可被神經網路無痛替換）：
    - 我方塔：基礎 0.9，鄰接敵塔每座 -0.15，被敵軍指向每支 -0.1。
    - 敵方塔：基礎 0.1，我方鄰接每座 +0.1（可爭奪性）。
    - 中立塔：0.5，依我方鄰接兵力優勢微調。
    - 兵力未知時不調整兵力項（保持 UNKNOWN 部分）。
    """
    tower = graph.towers.get(tower_id)
    if tower is None or not tower.visible:
        return None
    me = graph.player_id
    neighbors = [graph.towers[n] for n in tower.neighbors if n in graph.towers]
    enemy_adj = sum(1 for n in neighbors if n.visible and n.owner not in (None, me))
    friendly_adj = sum(1 for n in neighbors if n.visible and n.owner == me)
    incoming = sum(1 for f in graph.forces
                   if f.destination == tower_id and f.owner not in (None, me))
    if tower.owner == me:
        prob = 0.9 - 0.15 * enemy_adj - 0.1 * incoming
        if tower.units is not None and tower.units < 10:
            prob -= 0.15
    elif tower.owner is None:
        prob = 0.5 + 0.1 * friendly_adj - 0.1 * enemy_adj
        if tower.units is not None:
            my_power = sum((graph.towers[n].units or 0) for n in tower.neighbors
                           if n in graph.towers and graph.towers[n].visible
                           and graph.towers[n].owner == me)
            if my_power > tower.units:
                prob += 0.1
    else:
        prob = 0.1 + 0.1 * friendly_adj
        if tower.units is not None and tower.units > 30:
            prob -= 0.05
    return min(0.99, max(0.01, prob))


def frontlines(graph: GameGraph) -> list[tuple[int, int]]:
    """戰線 = 控制權梯度大的相鄰對（一方 >=0.6、另一方 <=0.4），回傳塔 id 對。"""
    probs = {tid: control_probability(graph, tid) for tid in graph.towers}
    lines = []
    for tid, tower in graph.towers.items():
        mine = probs.get(tid)
        if mine is None:
            continue
        for other in tower.neighbors:
            yours = probs.get(other)
            if yours is None or other < tid:
                continue
            if (mine >= 0.6 and yours <= 0.4) or (yours >= 0.6 and mine <= 0.4):
                lines.append((tid, other))
    return lines
