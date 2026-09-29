"""PvP 無行動原因碼的明確分類與穩定序列化。

此模組只描述原因，不會修改控制器決策。未列出的字串與非字串輸入
一律分類為 UNKNOWN；不使用子字串、前綴或大小寫猜測。
"""
from __future__ import annotations

import json
from types import MappingProxyType
from typing import Mapping


SCHEMA_VERSION = 1

REASON_CODES = (
    "NO_ENEMY",
    "NO_THREAT",
    "STALE_WORLD",
    "UNKNOWN_OWNER",
    "UNSUPPORTED_BATTLE",
    "SOURCE_UNSAFE",
    "INSUFFICIENT_FORCE",
    "ETA_UNKNOWN",
    "MULTI_THREAT_UNRESOLVED",
    "TOKEN_STALE",
    "RESERVATION_CONFLICT",
    "RECOVERY_ACTIVE",
    "NOT_IN_MATCH",
    "AUTHORIZATION_DISABLED",
)

UNKNOWN = "UNKNOWN"

REASON_METADATA: Mapping[str, str] = MappingProxyType({
    "NO_ENEMY": "沒有明確敵方目標可供評估",
    "NO_THREAT": "目前沒有已確認的入侵威脅",
    "STALE_WORLD": "世界或觀察資料已過期",
    "UNKNOWN_OWNER": "必要的所有者身分未知",
    "UNSUPPORTED_BATTLE": "戰鬥情境超出支援範圍",
    "SOURCE_UNSAFE": "行動來源未通過安全檢查",
    "INSUFFICIENT_FORCE": "已知可派兵力不足",
    "ETA_UNKNOWN": "抵達時間未知",
    "MULTI_THREAT_UNRESOLVED": "多威脅評估尚未解決",
    "TOKEN_STALE": "行動有效性權杖已過期或與目前狀態不符",
    "RESERVATION_CONFLICT": "行動資源已由其他行動保留",
    "RECOVERY_ACTIVE": "前一行動仍在驗證或恢復",
    "NOT_IN_MATCH": "目前不在對局中",
    "AUTHORIZATION_DISABLED": "自主行動授權已關閉",
    UNKNOWN: "來源原因未列入明確對照，保留未知",
})


_EXPLICIT_ALIASES = {
    "NO_ENEMY": ("NO_ENEMY",),
    "NO_THREAT": (
        "NO_THREAT",
        "no-known-threats",
        "no-enemy-inbound-threats",
    ),
    "STALE_WORLD": (
        "STALE_WORLD", "MATCH_STALE", "OBSERVATION_STALE", "ANCHOR_STALE",
        "PROBE_STALE", "CAMERA_STALE", "FORCE_STALE", "CONTROLLER_STALE",
        "RECOVERY_STALE", "UNKNOWN_STALE", "STALE_CAMERA",
        "anchor_unavailable", "anchor_failed", "anchor_unstable",
        "anchor_quality", "probe_failed", "probe_unavailable", "tower_gone",
        "camera_failed", "STALE_PROPOSAL:tower-id-unknown",
        "STALE_PROPOSAL:refresh-probe-failed",
        "STALE_PROPOSAL:refresh-probe-unknown",
        "STALE_PROPOSAL:tower-gone",
    ),
    "UNKNOWN_OWNER": (
        "UNKNOWN_OWNER", "adjacent-tower-owner-relation-unknown",
        "enemy-owner-id-unknown", "attacker owner is unknown",
        "enemy tower owner is unknown or conflicts with attacker",
        "the controlled player's owner id is unknown",
    ),
    "UNSUPPORTED_BATTLE": (
        "UNSUPPORTED_BATTLE", "UNSUPPORTED_TEMPORAL_CASE", "mirror-unsupported",
        "same-tick order is not validated",
    ),
    "SOURCE_UNSAFE": (
        "SOURCE_UNSAFE", "SOURCE_WOULD_BECOME_UNSAFE",
        "SOURCE_SAFETY_SOURCE_WOULD_BECOME_UNSAFE",
    ),
    "INSUFFICIENT_FORCE": ("INSUFFICIENT_FORCE", "NO_DEPLOYABLE_FORCE"),
    "ETA_UNKNOWN": (
        "ETA_UNKNOWN", "ABSTAIN_ETA_UNKNOWN", "threat-eta-unknown",
        "reinforcement ETA unknown", "enemy ETA is unknown",
        "SOURCE_SAFETY_threat-eta-unknown",
    ),
    "MULTI_THREAT_UNRESOLVED": (
        "MULTI_THREAT_UNRESOLVED",
        "an unresolved incoming threat prevents a safe next action",
        "defense-assessment-stale-or-unresolved",
    ),
    "TOKEN_STALE": (
        "TOKEN_STALE", "STALE_PROPOSAL:missing-token",
        "STALE_PROPOSAL:match-changed", "STALE_PROPOSAL:cycle-unknown",
        "STALE_PROPOSAL:cycle-changed", "STALE_PROPOSAL:deployable-unknown",
        "STALE_PROPOSAL:deployable-changed", "STALE_PROPOSAL:world-changed",
        "STALE_PROPOSAL:camera-changed", "STALE_PROPOSAL:source-changed",
        "STALE_PROPOSAL:target-changed", "STALE_PROPOSAL:screen-map-unknown",
        "STALE_PROPOSAL:tower-state-changed",
        "STALE_PROPOSAL:action-cycle-changed",
    ),
    "RESERVATION_CONFLICT": (
        "RESERVATION_CONFLICT", "RESOURCE_RESERVED:source",
        "RESOURCE_RESERVED:target",
    ),
    "RECOVERY_ACTIVE": (
        "RECOVERY_ACTIVE", "ACTION_VERIFICATION_PENDING",
        "VERIFICATION_PENDING",
    ),
    "NOT_IN_MATCH": ("NOT_IN_MATCH", "not_in_match"),
    "AUTHORIZATION_DISABLED": (
        "AUTHORIZATION_DISABLED", "autonomy_paused",
    ),
}


def _build_aliases() -> Mapping[str, str]:
    aliases: dict[str, str] = {}
    for code, values in _EXPLICIT_ALIASES.items():
        for value in values:
            if value in aliases:
                raise RuntimeError(f"duplicate reason alias: {value}")
            aliases[value] = code
    return MappingProxyType(aliases)


REASON_ALIASES = _build_aliases()


def classify_no_action_reason(raw_reason: object) -> str:
    """以精確對照分類原因；未知或格式錯誤輸入都回傳 UNKNOWN。"""
    if type(raw_reason) is not str or not raw_reason:
        return UNKNOWN
    return REASON_ALIASES.get(raw_reason, UNKNOWN)


def build_reason_record(raw_reason: object) -> dict[str, object]:
    """建立欄位固定且可 JSON 編碼的無行動原因紀錄。"""
    code = classify_no_action_reason(raw_reason)
    return {
        "schema_version": SCHEMA_VERSION,
        "code": code,
        "known": code != UNKNOWN,
        "raw_reason": raw_reason if type(raw_reason) is str else None,
        "description": REASON_METADATA[code],
    }


def serialize_reason_record(raw_reason: object) -> str:
    """輸出固定鍵排序、無多餘空白的 UTF-8 JSON 字串。"""
    return json.dumps(
        build_reason_record(raw_reason),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
