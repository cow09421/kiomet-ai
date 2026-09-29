"""Forward Simulator（前向模擬器）：簡化但確定性（deterministic）。

已確認／假設（heuristic，待 Kiomet 公開原始碼或實測校準）：
- 生產：已知產能線性累加，上限 100（heuristic 上限）。
- 移動：下令後按每跳 TRAVEL_S_PER_HOP 秒飛行，抵達才結算。
- 戰鬥：攻擊量 > 守軍 → 佔領剩餘；否則守軍扣減（同 Mock 語意）。
- UNKNOWN RULE（未知規則）：真實 Kiomet 的飛行時間、產能公式、塔類型加成
  皆未知；本模擬器只用於相對排序候選，不預測絕對戰果。

輸入 GameGraph＋行動集＋對手風格，輸出未來 GameGraph。確定性：同輸入同輸出
（RANDOM 對手用 seed 控制）。
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from kiomet_ai.actions import Action
from kiomet_ai.katakiomet.graph import ForceEdge, GameGraph
from kiomet_ai.katakiomet.opponents import opponent_actions

TRAVEL_S_PER_HOP = 3.0   # heuristic：每跳飛行秒數（UNKNOWN RULE）
UNIT_CAP = 100           # heuristic：單塔兵力上限
TICK_S = 1.0             # 模擬步長


def _apply_move(towers: dict, action: Action, now: float,
                flights: list[dict]) -> bool:
    src = towers.get(action.source or -1)
    dst = towers.get(action.destination or -1)
    if src is None or dst is None or action.amount is None:
        return False
    if src.owner != "me" and src.owner != action_owner(action, towers):
        return False
    if action.amount <= 0 or (src.units or 0) - action.amount < 0:
        return False
    keep = 15 if src.king_present else 1
    if (src.units or 0) - action.amount < keep:
        return False
    towers[src.id] = replace(src, units=(src.units or 0) - action.amount)
    flights.append({"owner": src.owner, "source": src.id, "dest": dst.id,
                    "units": action.amount, "eta": now + TRAVEL_S_PER_HOP,
                    "id": f"sim-{src.id}-{dst.id}-{now:.0f}"})
    return True


def action_owner(action: Action, towers: dict) -> str | None:
    src = towers.get(action.source or -1)
    return src.owner if src else None


def _settle(towers: dict, flight: dict) -> None:
    dst = towers.get(flight["dest"])
    if dst is None:
        return
    attack, defense = flight["units"], dst.units or 0
    if dst.owner == flight["owner"]:
        towers[dst.id] = replace(dst, units=min(UNIT_CAP, defense + attack))
    elif attack > defense:
        towers[dst.id] = replace(dst, owner=flight["owner"],
                                 units=min(UNIT_CAP, attack - defense))
    else:
        towers[dst.id] = replace(dst, units=defense - attack)


def step(graph: GameGraph, my_actions: list[Action], enemy_id: str = "enemy",
         opponent_style: str = "AGGRESSIVE", seed: int = 0,
         horizon_s: float = 5.0) -> GameGraph:
    """前進 horizon_s 秒：t=0 執行我方行動，對手每秒回應，生產累加。"""
    towers = {tid: replace(t) for tid, t in graph.towers.items()}
    flights: list[dict] = []
    now = graph.timestamp
    end = now + horizon_s
    first = True
    tick = 0
    while now < end:
        now = min(end, now + TICK_S)
        # 生產。
        for tid, tower in list(towers.items()):
            if tower.owner in ("me", enemy_id) and tower.production:
                towers[tid] = replace(
                    tower, units=min(UNIT_CAP,
                                     (tower.units or 0) + tower.production * TICK_S))
        # 抵達結算。
        arrived = [f for f in flights if f["eta"] <= now]
        flights = [f for f in flights if f["eta"] > now]
        for flight in arrived:
            _settle(towers, flight)
        # 行動：t=0 我方＋對手，之後每秒只有對手。
        if first:
            for action in my_actions:
                if action.kind == "MoveForce":
                    saved = dict(towers)
                    _apply_move(towers, action, now, flights)
                    void = towers
            for action in opponent_actions(
                    GameGraph(now, graph.player_id, towers, (), None, None),
                    enemy_id, opponent_style, seed + tick):
                if action.kind == "MoveForce":
                    attacking = action.kind == "MoveForce"
                    src = towers.get(action.source or -1)
                    if src is None or src.owner != enemy_id:
                        continue
                    tmp = Action("MoveForce", action.source, action.destination,
                                 action.amount)
                    # 借用同一移動語意（擁有者檢查放寬為敵方）。
                    if (src.units or 0) - (tmp.amount or 0) >= 1:
                        towers[src.id] = replace(src, units=(src.units or 0) - (tmp.amount or 0))
                        flights.append({"owner": enemy_id, "source": src.id,
                                        "dest": tmp.destination, "units": tmp.amount,
                                        "eta": now + TRAVEL_S_PER_HOP,
                                        "id": f"sim-foe-{tick}"})
            first = False
        else:
            tick += 1
            for action in opponent_actions(
                    GameGraph(now, graph.player_id, towers, (), None, None),
                    enemy_id, opponent_style, seed + tick):
                if action.kind == "MoveForce":
                    src = towers.get(action.source or -1)
                    if src is None or src.owner != enemy_id:
                        continue
                    if (src.units or 0) - (action.amount or 0) >= 1:
                        towers[src.id] = replace(src, units=(src.units or 0) - (action.amount or 0))
                        flights.append({"owner": enemy_id, "source": src.id,
                                        "dest": action.destination,
                                        "units": action.amount,
                                        "eta": now + TRAVEL_S_PER_HOP,
                                        "id": f"sim-foe-{tick}"})
    forces = tuple(ForceEdge(f["id"], f["owner"], f["source"], f["dest"], f["units"],
                             None, max(0.0, f["eta"] - end), end, 1.0)
                   for f in flights)
    king = next((t.id for t in towers.values()
                 if t.owner == graph.player_id and t.king_present), None)
    return GameGraph(timestamp=end, player_id=graph.player_id, towers=towers,
                     forces=forces, upgrade_resources=graph.upgrade_resources,
                     king_tower=king, score=graph.score)
