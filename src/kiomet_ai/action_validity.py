"""行動有效性權杖＋原子資源保留（GPT Round 11 契約工程化）。

規則：
- 每個可執行提案綁定 token：match／cycle／世界快照／來源狀態版本／
  目標狀態版本／相機版本／建立時間／來源／目標／保留的可派快照。
- 派送前重驗：任一版本或核心狀態不同 → STALE_PROPOSAL。
- 同一來源同一時間只屬一個行動；VERIFYING 期間同源同目標鎖定。
- 世界快照 ID＝錨點檔 mtime＋探測時間；相機版本＝相機參數取整。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionValidityToken:
    match_id: str | None = None
    cycle_id: int | None = None
    world_snapshot_id: str | None = None
    source_state_version: str | None = None
    target_state_version: str | None = None
    camera_version: str | None = None
    created_at: float | None = None
    source_tower_id: int | None = None
    target_tower_id: int | None = None
    reserved_deployable: tuple | None = None  # 排序後的 (兵種, 數量) 元組


def _counts_dict(counts):
    """TowerUnitCounts dataclass 或純 dict 皆接受；其他回 None。"""
    if counts is None:
        return None
    if isinstance(counts, dict):
        values = counts
    else:
        try:
            values = vars(counts)
        except TypeError:
            return None
    if not isinstance(values, dict):
        return None
    names = ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier")
    normalized = {
        name: values.get(name, values.get(name.lower(), "?"))
        for name in names
    }
    normalized["SingleUnitType"] = values.get(
        "SingleUnitType", values.get("single_unit_type", "?"))
    normalized["SingleCount"] = values.get(
        "SingleCount", values.get("single_count", "?"))
    return normalized


def _deployable_snapshot(counts: dict | None) -> tuple | None:
    """正規化可派兵力；缺值、空值、非整數或負數都視為 UNKNOWN。"""
    if not isinstance(counts, dict) or not counts:
        return None
    if (any(not isinstance(name, str) or not name for name in counts)
            or any(type(value) is not int or value < 0
                   for value in counts.values())):
        return None
    return tuple(sorted(counts.items()))


def _token_deployable_snapshot(snapshot: tuple | None) -> tuple | None:
    """驗證權杖內不可變的兵力快照，拒絕重複欄位或錯誤值。"""
    if not isinstance(snapshot, tuple) or not snapshot:
        return None
    try:
        counts = dict(snapshot)
    except (TypeError, ValueError):
        return None
    if len(counts) != len(snapshot):
        return None
    return _deployable_snapshot(counts)


def tower_state_version(tower_ref, units_kind: str | None,
                        counts: dict | None, owner,
                        owner_ruler=None) -> str:
    """塔狀態版本：ref＋種類＋組成＋擁有者＋國王光環。任一未知以 ? 標記。"""
    parts = [str(tower_ref), str(units_kind), str(owner),
             str(owner_ruler)]
    if isinstance(counts, dict):
        parts.extend(f"{name}={counts.get(name, '?')}" for name in
                     ("Shield", "Fighter", "Chopper", "Bomber",
                      "Tank", "Soldier", "SingleUnitType",
                      "SingleCount"))
    else:
        parts.append("counts=?")
    return "|".join(parts)


def camera_version(camera) -> str:
    """相機版本：參數取整；未知回 ?。"""
    try:
        return ",".join(str(round(float(v), 1)) for v in camera[1:])
    except (TypeError, ValueError, IndexError):
        return "?"


def build_token(match_id, cycle_id, anchor_mtime: float | None,
                probe_time: float | None, source_state, target_state,
                camera, deployable_counts: dict | None = None,
                now: float | None = None) -> ActionValidityToken:
    """由新鮮觀察建立權杖。"""
    world_snapshot = f"{anchor_mtime or '?'}@{probe_time or '?'}"
    reserved = _deployable_snapshot(deployable_counts)
    return ActionValidityToken(
        match_id=match_id, cycle_id=cycle_id,
        world_snapshot_id=str(world_snapshot),
        source_state_version=tower_state_version(
            source_state.tower_ref if source_state else None,
            source_state.units_kind if source_state else None,
            _counts_dict(source_state.unit_counts) if source_state else None,
            source_state.owner if source_state else None,
            source_state.owner_ruler if source_state else None),
        target_state_version=tower_state_version(
            target_state.tower_ref if target_state else None,
            target_state.units_kind if target_state else None,
            _counts_dict(target_state.unit_counts) if target_state else None,
            target_state.owner if target_state else None,
            target_state.owner_ruler if target_state else None),
        camera_version=camera_version(camera),
        created_at=time.time() if now is None else now,
        source_tower_id=source_state.tower_id if source_state else None,
        target_tower_id=target_state.tower_id if target_state else None,
        reserved_deployable=reserved)


def validate_token(token: ActionValidityToken, match_id,
                   anchor_mtime: float | None, probe_time: float | None,
                   source_state, target_state, camera,
                   current_cycle_id: int | None = None,
                   current_deployable_counts: dict | None = None) -> str:
    """重驗：OK 或 STALE_PROPOSAL＋原因；必須仍在建立權杖的週期。"""
    if token is None:
        return "STALE_PROPOSAL:missing-token"
    if token.match_id != match_id:
        return "STALE_PROPOSAL:match-changed"
    if type(token.cycle_id) is not int or type(current_cycle_id) is not int:
        return "STALE_PROPOSAL:cycle-unknown"
    if token.cycle_id != current_cycle_id:
        return "STALE_PROPOSAL:cycle-changed"
    token_deployable = _token_deployable_snapshot(token.reserved_deployable)
    current_deployable = _deployable_snapshot(current_deployable_counts)
    if token_deployable is None or current_deployable is None:
        return "STALE_PROPOSAL:deployable-unknown"
    if token_deployable != current_deployable:
        return "STALE_PROPOSAL:deployable-changed"
    world_snapshot = f"{anchor_mtime or '?'}@{probe_time or '?'}"
    if token.world_snapshot_id != world_snapshot:
        return "STALE_PROPOSAL:world-changed"
    if token.camera_version != camera_version(camera):
        return "STALE_PROPOSAL:camera-changed"
    if token.source_state_version != tower_state_version(
            source_state.tower_ref if source_state else None,
            source_state.units_kind if source_state else None,
            _counts_dict(source_state.unit_counts) if source_state else None,
            source_state.owner if source_state else None,
            source_state.owner_ruler if source_state else None):
        return "STALE_PROPOSAL:source-changed"
    if token.target_state_version != tower_state_version(
            target_state.tower_ref if target_state else None,
            target_state.units_kind if target_state else None,
            _counts_dict(target_state.unit_counts) if target_state else None,
            target_state.owner if target_state else None,
            target_state.owner_ruler if target_state else None):
        return "STALE_PROPOSAL:target-changed"
    return "OK"


class ReservationBoard:
    """原子保留板：同源／同目標單一行動；VERIFYING 鎖定。

    單進程內使用；換局清空。key 皆為 tower_id。
    """

    def __init__(self):
        self._sources: dict = {}
        self._targets: dict = {}

    def clear_match(self):
        self._sources.clear()
        self._targets.clear()

    def reserve(self, action_id: str, source_id: int,
                target_id: int) -> str | None:
        """成功回 None；被佔用回原因。"""
        if source_id in self._sources:
            return "RESOURCE_RESERVED:source"
        if target_id in self._targets:
            return "RESOURCE_RESERVED:target"
        self._sources[source_id] = action_id
        self._targets[target_id] = action_id
        return None

    def release(self, action_id: str):
        for table in (self._sources, self._targets):
            for key, value in list(table.items()):
                if value == action_id:
                    del table[key]

    def holder(self, tower_id: int) -> str | None:
        return self._sources.get(tower_id, self._targets.get(tower_id))
