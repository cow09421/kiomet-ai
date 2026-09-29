"""Heuristic Policy（人工策略先驗）：輸出語意行動（Semantic Action），不輸出滑鼠。

- Amount（兵力）離散化：25%／50%／75%／MAX_SAFE，降低行動空間。
- 只產生當前已確認可可靠操作語意（MoveForce／UpgradeTower／SetSupplyLine／
  MoveKing／Wait）；ATTACK／REINFORCE／RETREAT 意圖映射到 MoveForce 上。
- 回傳 [(prior, action)]，prior 為策略先驗分數（排序用，非機率歸一）。
"""
from __future__ import annotations

from kiomet_ai.actions import Action
from kiomet_ai.katakiomet.graph import GameGraph
from kiomet_ai.katakiomet.ownership import control_probability, frontlines

AMOUNTS = (0.25, 0.5, 0.75, 1.0)  # 佔可動兵力的比例；MAX_SAFE 由 safety 層裁定


def safe_sendable(units: int | None, keep: int) -> int:
    """可動兵力 = 已知兵力 - 保留；未知回 0（不對 UNKNOWN 出兵）。"""
    if units is None:
        return 0
    return max(0, units - keep)


class PolicyProvider:
    def candidates(self, graph: GameGraph, intent: str = "CONSOLIDATE"
                   ) -> list[tuple[float, Action]]:
        raise NotImplementedError


class HeuristicPolicy(PolicyProvider):
    def candidates(self, graph: GameGraph, intent: str = "CONSOLIDATE"
                   ) -> list[tuple[float, Action]]:
        me = graph.player_id
        out: list[tuple[float, Action]] = []
        own = {t.id: t for t in graph.towers.values()
               if t.visible and t.owner == me}
        lines = frontlines(graph)
        line_towers = {i for pair in lines for i in pair}

        def push(prior: float, action: Action) -> None:
            out.append((prior, action))

        # 1. 國王增援（King Safety 最高優先）。
        kings = [t for t in own.values() if t.king_present]
        if kings:
            king = kings[0]
            if king.units is not None and king.units < 15:
                for nid in king.neighbors:
                    donor = own.get(nid)
                    if donor and (donor.units or 0) > 25:
                        push(1.0, Action("MoveForce", donor.id, king.id, 10,
                                         reason="國王安全：增援國王所在塔"))
                        break

        # 2. 前線缺口：戰線端點中我方弱塔，向強鄰接要兵。
        for tid in sorted(line_towers):
            tower = own.get(tid)
            if tower is None or tower.units is None or tower.units >= 15:
                continue
            helpers = [own[n] for n in tower.neighbors
                       if n in own and (own[n].units or 0) > 20]
            if helpers:
                donor = max(helpers, key=lambda t: t.units or 0)
                amount = min(10, safe_sendable(donor.units, 15))
                if amount > 0:
                    push(0.9, Action("MoveForce", donor.id, tid, amount,
                                     reason="前線缺口：增援弱側"))

        # 3. 後方閒置兵力前送（非戰線塔兵力超過 25 即為閒置）。
        fronts = [t for t in own.values() if t.id in line_towers]
        for tower in sorted(own.values(), key=lambda t: t.id):
            if tower.id in line_towers or (tower.units or 0) <= 25:
                continue
            target = next((t for t in fronts
                           if t.id in tower.neighbors and (t.units or 0) < 20), None)
            if target is None:
                target = next((t for t in own.values()
                               if t.id in tower.neighbors and t.id in line_towers), None)
            if target is not None:
                amount = min(10, safe_sendable(tower.units, 15))
                if amount > 0:
                    push(0.6, Action("MoveForce", tower.id, target.id, amount,
                                     reason="後方閒置兵力前送"))

        # 4. 明顯優勢才擴張：中立弱塔＋意圖允許＋控制權 >= 0.6。
        if intent in ("EXPAND", "CONSOLIDATE"):
            for tower in sorted(own.values(), key=lambda t: t.id):
                if (tower.units or 0) < 25:
                    continue
                for nid in tower.neighbors:
                    target = graph.towers.get(nid)
                    if target is None or not target.visible or target.owner is not None:
                        continue
                    if (target.units or 99) >= 10:
                        continue
                    prob = control_probability(graph, nid)
                    if prob is not None and prob >= 0.6:
                        push(0.5 if intent == "EXPAND" else 0.35,
                             Action("MoveForce", tower.id, nid, 10,
                                    reason="優勢擴張：佔領中立弱塔"))
                        break

        # 5. 緊急時不擴張：EMERGENCY 只保留前兩類＋等待。
        if intent == "EMERGENCY_KING_DEFENSE":
            out = [c for c in out if c[1].reason.startswith(("國王安全", "前線缺口"))]

        push(0.1, Action("Wait", reason="保留兵力，等待新的可觀察局面"))
        out.sort(key=lambda c: -c[0])
        return out
