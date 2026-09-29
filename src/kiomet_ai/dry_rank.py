"""Many-only 擴張乾跑排名：只回答「哪一座塔最值得攻」，不送兵。

輸入 RealTowerState（真實塔狀態）序列；輸出候選清單，每筆帶
SEND=False。安全門：STALE（陳舊）／UNKNOWN（未知）擁有者／
UNKNOWN 可派量／Single 未驗證／非鄰居一律 NO_CANDIDATE（無候選）。
不做戰略預留扣減（Planner 之後決定）；不決定實際派兵數量。
分數為 heuristic_score（啟發式分數），不是勝率。
"""
from __future__ import annotations

from kiomet_ai.observe import UNIT_NAMES, unit_capacity

_SPECIAL_UNIT_NAMES = ("Ruler", "Shell", "Emp", "Nuke")


def _special_units_clear(counts: dict | None) -> bool:
    """完整且合法的兵種向量中，四種特殊兵種都明確為 0 才可排名。"""
    return (isinstance(counts, dict)
            and set(counts) == set(UNIT_NAMES)
            and all(type(value) is int and 0 <= value <= 255
                    for value in counts.values())
            and all(type(counts.get(name)) is int and counts[name] == 0
                    for name in _SPECIAL_UNIT_NAMES))


def _target_defense(state) -> int | None:
    """目標防禦代理：護盾＋可移動兵力現量；任一未知回 UNKNOWN。"""
    counts = state.unit_counts
    if counts is None or counts.units_kind != "MANY":
        return None
    values = [counts.shield, counts.fighter, counts.chopper,
              counts.bomber, counts.tank, counts.soldier]
    if any(v is None for v in values):
        return None
    return sum(values)


def _source_power(state) -> int | None:
    force = state.deployable_force
    if force is None:
        return None
    return force.total


def rank_expansion_targets(states, current_match_id: str,
                           now: float | None = None) -> list:
    """SELF Many（DERIVED+）→ NEUTRAL 鄰居。回傳依分數排序的候選。"""
    by_id = {s.tower_id: s for s in states}
    candidates = []
    for source in states:
        if source.freshness(current_match_id, now) != "FRESH":
            continue
        if source.owner != "SELF":
            continue
        if source.unit_counts is None or source.unit_counts.units_kind != "MANY":
            continue
        if (source.deployable_force is None
                or source.deployable_force_confidence not in ("DERIVED", "VERIFIED")):
            continue
        force_counts = source.deployable_force.counts
        if not _special_units_clear(force_counts):
            continue  # PvP v0 停用特殊兵種；UNKNOWN 不得當成 0
        power = _source_power(source)
        if not power:
            continue
        for target_id in source.neighbors:
            target = by_id.get(target_id)
            if target is None:
                continue
            if target.freshness(current_match_id, now) != "FRESH":
                continue
            if target.owner != "NEUTRAL":
                continue
            defense = _target_defense(target)
            if defense is None:
                continue
            frontline = any(by_id.get(n) is not None
                            and by_id[n].owner == "SELF"
                            and by_id[n].freshness(current_match_id, now) == "FRESH"
                            for n in target.neighbors)
            frontier_gain = sum(
                1 for n in target.neighbors
                if n != source.tower_id and (by_id.get(n) is None
                   or by_id[n].owner != "SELF"))
            shield_cap = unit_capacity("Shield", target.tower_type,
                                       target.owner_ruler)
            # 啟發式分數＝可派 − 防禦 ＋ 前線加成 ＋ 新增前線收益。
            # 盾容量僅作資訊欄位（高容量塔更難長期持有），不直接加權，
            # 避免假精確。
            score = power - defense + (2 if frontline else 0) + frontier_gain
            candidates.append({
                "source": source.tower_id,
                "target": target.tower_id,
                "source_type": source.tower_type,
                "target_type": target.tower_type,
                "source_owner": source.owner,
                "target_owner": target.owner,
                "source_deployable": dict(source.deployable_force.counts),
                "source_power": power,
                "target_defense": defense,
                "source_neighbors": list(source.neighbors),
                "target_neighbors": list(target.neighbors),
                "neighbor": True,
                "frontline": frontline,
                "frontier_gain": frontier_gain,
                "target_shield_capacity": shield_cap,
                "heuristic_score": score,
                "reason": (f"SELF {source.tower_type} 可派 {power} → "
                           f"NEUTRAL {target.tower_type} 防禦 {defense}／"
                           f"盾容量 {shield_cap}／新增前線 {frontier_gain}"),
                "confidence": source.deployable_force_confidence,
                "SEND": False,
            })
    candidates.sort(key=lambda c: (-c["heuristic_score"], c["target"]))
    return candidates


def rejection_reasons(states, current_match_id: str,
                      now: float | None = None) -> list:
    """被拒候選的除錯紀錄：STALE／UNKNOWN_DEPLOYABLE／SINGLE_UNVERIFIED
    ／NON_NEIGHBOR／TARGET_NOT_NEUTRAL／SOURCE_NOT_SELF／INVALID_MATCH。"""
    by_id = {s.tower_id: s for s in states}
    rejected = []
    for source in states:
        if not source.match_id or not current_match_id:
            rejected.append({"source": source.tower_id, "target": None,
                             "reason": "INVALID_MATCH"})
            continue
        if source.freshness(current_match_id, now) != "FRESH":
            rejected.append({"source": source.tower_id, "target": None,
                             "reason": "STALE"})
            continue
        if source.owner != "SELF":
            continue  # 非己方塔不是候選來源，不記錄
        if source.unit_counts is None or source.unit_counts.units_kind != "MANY":
            rejected.append({"source": source.tower_id, "target": None,
                             "reason": "SINGLE_UNVERIFIED"})
            continue
        if (source.deployable_force is None
                or source.deployable_force_confidence not in ("DERIVED", "VERIFIED")):
            rejected.append({"source": source.tower_id, "target": None,
                             "reason": "UNKNOWN_DEPLOYABLE"})
            continue
        for target_id in source.neighbors:
            target = by_id.get(target_id)
            if target is None:
                rejected.append({"source": source.tower_id, "target": target_id,
                                 "reason": "NON_NEIGHBOR"})
                continue
            if target.owner != "NEUTRAL":
                rejected.append({"source": source.tower_id, "target": target_id,
                                 "reason": "TARGET_NOT_NEUTRAL"})
                continue
    return rejected
