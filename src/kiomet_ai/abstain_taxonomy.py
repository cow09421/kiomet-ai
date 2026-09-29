"""不行動原因分類（P0）。

禁止只顯示 NO_SAFE_PROPOSAL；每次 abstain 必須歸類。
提供 canonical reasons、別名對照、最近 50／100／整局的計數與比例。
未知字串保留 UNKNOWN；總數為 0 時比例為 None（不假 0）。

獨立模組（不依賴 GPT 的 reason_taxonomy.py）。
"""
from __future__ import annotations

REASONS = (
    "NO_NEUTRAL_TARGET", "NO_ENEMY_TARGET", "SOURCE_UNSAFE",
    "INSUFFICIENT_UNITS", "OWNER_UNKNOWN", "TARGET_UNKNOWN", "WORLD_STALE",
    "CAMERA_STALE", "PATH_UNKNOWN", "DEPLOYABLE_UNKNOWN",
    "BATTLE_UNSUPPORTED", "BATTLE_UNSAFE", "THREAT_UNKNOWN",
    "TOKEN_INVALID", "RESERVATION_CONFLICT", "ACTION_COOLDOWN",
    "MATCH_TRANSITION", "OTHER",
)
UNKNOWN = "UNKNOWN"

ALIASES = {
    "not_in_match": "MATCH_TRANSITION",
    "stale_world": "WORLD_STALE",
    "anchor_failed": "WORLD_STALE",
    "world_not_fresh": "WORLD_STALE",
    "observation_stale": "CAMERA_STALE",
    "anchor_stale": "CAMERA_STALE",
    "camera_stale": "CAMERA_STALE",
    "no_safe_proposal": "OTHER",
    "unknown_dispatch": "OTHER",
    "owner_unknown": "OWNER_UNKNOWN",
    "target_unknown": "TARGET_UNKNOWN",
    "path_unknown": "PATH_UNKNOWN",
    "threat_unknown": "THREAT_UNKNOWN",
    "source_unsafe": "SOURCE_UNSAFE",
    "insufficient_force": "INSUFFICIENT_UNITS",
    "insufficient_units": "INSUFFICIENT_UNITS",
    "token_stale": "TOKEN_INVALID",
    "token_invalid": "TOKEN_INVALID",
    "reservation_conflict": "RESERVATION_CONFLICT",
    "multi_threat_unresolved": "THREAT_UNKNOWN",
    "unsupported_battle": "BATTLE_UNSUPPORTED",
    "battle_unsupported": "BATTLE_UNSUPPORTED",
    "battle_unsafe": "BATTLE_UNSAFE",
    "recovery_active": "OTHER",
    "authorization_disabled": "OTHER",
    "no_enemy": "NO_ENEMY_TARGET",
    "no_enemy_target": "NO_ENEMY_TARGET",
    "no_neutral_target": "NO_NEUTRAL_TARGET",
    "deployable_unknown": "DEPLOYABLE_UNKNOWN",
    "action_cooldown": "ACTION_COOLDOWN",
    "match_transition": "MATCH_TRANSITION",
}


def classify_reason(raw) -> str:
    """把原始原因字串轉成 canonical；未知回 UNKNOWN，不猜。"""
    if raw is None:
        return UNKNOWN
    text = str(raw).strip()
    if not text:
        return UNKNOWN
    upper = text.upper()
    if upper in REASONS:
        return upper
    key = text.lower()
    if key in ALIASES:
        return ALIASES[key]
    return UNKNOWN


def summarize_window(reasons) -> dict:
    """單一窗口的計數與比例；空輸入 → 比例皆 None。"""
    counts = {reason: 0 for reason in REASONS}
    counts[UNKNOWN] = 0
    total = 0
    for raw in reasons or []:
        canonical = classify_reason(raw)
        counts[canonical] = counts.get(canonical, 0) + 1
        total += 1
    proportions = {k: (round(v / total, 4) if total else None)
                   for k, v in counts.items()}
    return {"total": total, "counts": counts, "proportions": proportions}


def window_stats(records, windows=(50, 100)) -> dict:
    """records: [{reason, ...}]（僅計入未派送者）；回傳多窗口統計。"""
    records = records if isinstance(records, list) else []
    abstain_reasons = []
    for row in records:
        if not isinstance(row, dict):
            continue
        if row.get("actions_sent"):
            continue
        abstain_reasons.append(row.get("reason"))
    out = {}
    for n in windows:
        out[f"last_{n}"] = summarize_window(abstain_reasons[-n:])
    out["match"] = summarize_window(abstain_reasons)
    return out
