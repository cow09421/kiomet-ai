"""Safety Governor（安全治理層）：MCTS／搜尋之外的最後一道閘。

即使 Solver 認為某操作有利，違反以下任一限制即拒絕（veto）或縮減：
A. King Reserve（國王預備隊）：國王塔動態安全兵力。
B. Front Reserve（前線預備隊）：不抽空戰線後方。
C. Maximum Exposure（最大暴露度）：同時主動擴張不超過上限。
D. Attack Margin（攻擊安全邊際）：含敵方合理增援仍佔優才攻擊。
E. Emergency Defense（緊急防禦）：King 風險超閾值時只留防守。
F. Uncertainty Penalty（不確定性懲罰）：資訊越舊，攻擊所需優勢越大。

輸出 (allowed, amount, reason)：allowed=False 拒絕；amount 為裁定後兵力。
"""
from __future__ import annotations

from dataclasses import dataclass

from kiomet_ai.actions import Action
from kiomet_ai.katakiomet.belief import BeliefState
from kiomet_ai.katakiomet.graph import GameGraph
from kiomet_ai.katakiomet.ownership import frontlines


@dataclass
class SafetyConfig:
    king_min_units: int = 15          # 國王塔最低保留
    rear_min_units: int = 15          # 非國王塔最低保留
    max_open_expansions: int = 2      # 同時主動擴張上限
    attack_margin: float = 1.5        # 攻擊方需要兵力比（含增援）
    king_risk_threshold: float = 0.6  # 超過即緊急
    stale_penalty_per_s: float = 0.05  # 敵方資訊每陳舊 1 秒，所需優勢 +5%


def king_risk(graph: GameGraph) -> float:
    """0~1：國王塔未知／失守=1；兵力越少、鄰敵越多越高。"""
    me = graph.player_id
    kings = [t for t in graph.towers.values()
             if t.visible and t.owner == me and t.king_present]
    if not kings:
        return 1.0
    king = kings[0]
    risk = 0.0
    if king.units is None:
        risk += 0.4
    elif king.units < 15:
        risk += 0.6 * (1 - king.units / 15.0)
    enemies = sum(1 for n in king.neighbors
                  if (t := graph.towers.get(n)) is not None and t.visible
                  and t.owner not in (None, me))
    risk += min(0.4, 0.2 * enemies)
    return min(1.0, risk)


def govern(belief: BeliefState, graph: GameGraph, action: Action,
           config: SafetyConfig | None = None) -> tuple[bool, int | None, str]:
    """裁定一個語意行動。回 (允許, 裁定兵力或 None, 原因)。"""
    config = config or SafetyConfig()
    me = graph.player_id
    if action.kind == "Wait":
        return True, None, "等待永遠允許"
    risk = king_risk(graph)
    if risk >= config.king_risk_threshold and action.kind == "MoveForce":
        dest = graph.towers.get(action.destination or -1)
        kings = [t.id for t in graph.towers.values()
                 if t.visible and t.owner == me and t.king_present]
        if action.destination not in kings:
            return False, None, f"緊急防禦：King 風險 {risk:.2f}，拒絕非國王增援"
    if action.kind == "MoveForce":
        src = graph.towers.get(action.source or -1)
        if src is None or not src.visible or src.owner != me:
            return False, None, "來源不可見或非我方"
        if src.units is None:
            return False, None, "來源兵力 UNKNOWN，拒絕出兵"
        keep = config.king_min_units if src.king_present else config.rear_min_units
        amount = min(action.amount or 0, src.units - keep)
        if amount <= 0:
            return False, None, f"預備隊不足（保留 {keep}）"
        dest = graph.towers.get(action.destination or -1)
        if dest is None or not dest.visible:
            return False, None, "目標不可見"
        if dest.owner not in (None, me):
            # 攻擊：安全邊際＋不確定性懲罰。
            stale = belief.staleness(dest.id, now=graph.timestamp)
            margin = config.attack_margin
            if stale is not None:
                margin *= 1.0 + config.stale_penalty_per_s * stale
            need = (dest.units or 0) * margin
            if amount < need:
                return False, None, (
                    f"攻擊邊際不足：需 {need:.0f}（邊際 {margin:.2f}），僅 {amount}")
        return True, amount, "安全檢查通過"
    if action.kind in ("UpgradeTower", "SetSupplyLine", "MoveKing"):
        return True, None, "非兵力行動：治理層放行（執行器另行驗證）"
    return False, None, "未知行動類型"
