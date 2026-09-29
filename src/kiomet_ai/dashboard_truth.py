"""儀表板欄位真實性分類（P1 §8）。

每個欄位必須是 LIVE / STALE / LAST_MATCH / UNKNOWN / OFFLINE 之一；
NEXT ACTION 只有「目前 match + 新鮮 cycle」才 READY，否則
NO_ACTIVE_MATCH / NO_SAFE_PROPOSAL / STALE / LAST_MATCH / UNKNOWN。

純函式；上一局資料不得冒充目前局。不觸碰 index.html。
"""
from __future__ import annotations

FIELD_STATUSES = ("LIVE", "STALE", "LAST_MATCH", "UNKNOWN", "OFFLINE")
NEXT_ACTION_STATUSES = ("READY", "NO_ACTIVE_MATCH", "NO_SAFE_PROPOSAL",
                        "STALE", "LAST_MATCH", "UNKNOWN", "OFFLINE")

IN_MATCH_STATES = ("IN_MATCH",)


def _age_ok(age_s, stale_after_s):
    return isinstance(age_s, (int, float)) and age_s <= stale_after_s


def classify_field(*, browser_connected=True, game_state=None,
                   current_match_id=None, data_match_id=None,
                   data_age_s=None, stale_after_s=15.0,
                   has_data=True) -> str:
    """分類單一欄位。"""
    if browser_connected is False:
        return "OFFLINE"
    if has_data is False:
        return "UNKNOWN"
    if current_match_id is None:
        # 沒有目前對局：資料若不是本局，只能算上一局或未知
        if data_match_id is not None:
            return "LAST_MATCH"
        return "UNKNOWN"
    if data_match_id is not None and data_match_id != current_match_id:
        return "LAST_MATCH"
    if data_match_id is None:
        return "UNKNOWN"
    if game_state not in IN_MATCH_STATES:
        return "LAST_MATCH"
    if data_age_s is not None and not _age_ok(data_age_s, stale_after_s):
        return "STALE"
    return "LIVE"


def next_action_status(*, browser_connected=True, game_state=None,
                       current_match_id=None, proposal=None,
                       proposal_match_id=None, proposal_cycle=None,
                       current_cycle=None, proposal_age_s=None,
                       stale_after_s=15.0) -> str:
    """NEXT ACTION 專屬狀態。"""
    if browser_connected is False:
        return "OFFLINE"
    if game_state not in IN_MATCH_STATES or current_match_id is None:
        return "NO_ACTIVE_MATCH"
    if proposal is None and proposal_match_id is None:
        return "NO_SAFE_PROPOSAL"
    if proposal_match_id is None:
        # 有提案但缺 match 綁定 → 無法確認目前局，回 UNKNOWN（不得 READY）。
        return "UNKNOWN"
    if proposal_match_id != current_match_id:
        return "LAST_MATCH"
    if proposal_cycle is None or current_cycle is None:
        # 缺 cycle 綁定 → 無法確認新鮮度，回 UNKNOWN。
        return "UNKNOWN"
    if proposal_cycle != current_cycle:
        return "STALE"
    if proposal_age_s is not None and not _age_ok(proposal_age_s,
                                                  stale_after_s):
        return "STALE"
    return "READY"


def label_snapshot(snapshot: dict | None) -> dict:
    """對常見欄位批次標籤；缺欄位一律 UNKNOWN，不假裝。"""
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    common = {
        "browser_connected": snapshot.get("browser_connected", False),
        "game_state": snapshot.get("game_state"),
        "current_match_id": snapshot.get("current_match_id"),
        "stale_after_s": snapshot.get("stale_after_s", 15.0),
    }
    fields = {}
    for name in ("proposal", "score", "source", "target",
                 "world_counts", "threats"):
        entry = snapshot.get(name)
        if isinstance(entry, dict):
            fields[name] = classify_field(
                data_match_id=entry.get("match_id"),
                data_age_s=entry.get("age_s"),
                has_data=entry.get("has_data", True), **common)
        else:
            fields[name] = classify_field(has_data=entry is not None,
                                          **common)
    fields["next_action"] = next_action_status(
        proposal=snapshot.get("proposal"),
        proposal_match_id=snapshot.get("proposal_match_id"),
        proposal_cycle=snapshot.get("proposal_cycle"),
        current_cycle=snapshot.get("current_cycle"),
        proposal_age_s=snapshot.get("proposal_age_s"),
        **{k: v for k, v in common.items() if k != "stale_after_s"},
        stale_after_s=snapshot.get("stale_after_s", 15.0))
    return fields


def truth_from_snapshot(snapshot: dict | None, now: float) -> dict:
    """把 app.snapshot() 轉成欄位真實性標籤；缺欄位一律 UNKNOWN。"""
    snap = snapshot if isinstance(snapshot, dict) else {}
    if not snap:
        offline = {name: "OFFLINE"
                   for name in ("proposal", "score", "source", "target",
                                "world_counts", "threats", "next_action")}
        offline.update({"game_state": "UNKNOWN", "match_id": None,
                        "world_match_id": None, "observation_age_s": None,
                        "source_of_truth": "app.snapshot()"})
        return offline
    browser = snap.get("browser") if isinstance(snap.get("browser"), dict) \
        else {}
    game = snap.get("game") if isinstance(snap.get("game"), dict) else {}
    live = snap.get("live") if isinstance(snap.get("live"), dict) else {}
    anchor = snap.get("anchor_summary") \
        if isinstance(snap.get("anchor_summary"), dict) else {}
    controller = snap.get("live_controller") \
        if isinstance(snap.get("live_controller"), dict) else {}

    match = game.get("match") if isinstance(game.get("match"), dict) else {}
    current_match_id = match.get("id")
    game_state = game.get("state")
    connected = browser.get("connected")

    def age_of(ts):
        if isinstance(ts, (int, float)):
            return max(0.0, float(now) - float(ts))
        return None

    proposal = snap.get("next_action") \
        if isinstance(snap.get("next_action"), dict) else None
    proposal_match_id = None
    if isinstance(proposal, dict):
        proposal_match_id = proposal.get("match_id")
    core = {
        "browser_connected": connected,
        "game_state": game_state,
        "current_match_id": current_match_id,
        "current_cycle": controller.get("cycles"),
        "proposal": proposal,
        "proposal_match_id": proposal_match_id,
        "proposal_cycle": proposal.get("cycle_id")
        if isinstance(proposal, dict) else None,
        "proposal_age_s": None,
        "stale_after_s": 15.0,
        "score": None,
        "source": ({"match_id": proposal_match_id,
                    "age_s": None} if proposal_match_id else None),
        "target": ({"match_id": proposal_match_id,
                    "age_s": None} if proposal_match_id else None),
        "world_counts": ({"match_id": anchor.get("match_id"),
                          "age_s": None}
                         if anchor.get("match_id") else None),
        "threats": None,
    }
    labels = label_snapshot(core)
    labels["game_state"] = game_state or "UNKNOWN"
    labels["match_id"] = current_match_id
    labels["world_match_id"] = anchor.get("match_id")
    labels["observation_age_s"] = age_of(live.get("captured_at"))
    labels["source_of_truth"] = "app.snapshot()"
    return labels
