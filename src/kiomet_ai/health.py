"""Supervisor 可觀測健康模型（P0 §5）。

區分「程序存在」與「AI 真的活著」：
- process alive 但 controller 卡死 → DEGRADED（controller_not_cycling）
- controller running 但 world 過期   → STALE（world_stale）
- browser 斷線 / process 死         → FAILED
- gate ERROR / recovering           → RECOVERING
- gate PAUSED/STOPPED               → PAUSED
- 全綠                              → HEALTHY

純函式：輸入 signals dict，輸出狀態＋原因；不觸碰任何 GPT 檔案。
UNKNOWN 訊號不被視為健康。
"""
from __future__ import annotations

HEALTH_STATES = ("HEALTHY", "DEGRADED", "RECOVERING", "PAUSED",
                 "STALE", "FAILED", "UNKNOWN")

# 預設過期門檻（秒）
DEFAULT_THRESHOLDS = {
    "cycle_stale_after_s": 10.0,
    "observation_stale_after_s": 15.0,
    "world_stale_after_s": 30.0,
}


def _age(now, ts):
    if not isinstance(ts, (int, float)):
        return None
    return max(0.0, float(now) - float(ts))


def _is_fresh(now, ts, limit):
    age = _age(now, ts)
    return age is not None and age <= limit


def evaluate_health(signals: dict | None, now: float,
                    thresholds: dict | None = None) -> dict:
    """由訊號判定健康狀態與原因。"""
    signals = signals if isinstance(signals, dict) else {}
    limits = dict(DEFAULT_THRESHOLDS)
    if isinstance(thresholds, dict):
        limits.update(thresholds)
    reasons: list[str] = []

    process_alive = signals.get("process_alive")
    gate_state = str(signals.get("gate_state") or "UNKNOWN").upper()
    browser_connected = signals.get("browser_connected")
    recovering = bool(signals.get("recovering"))

    # 1) 硬失敗：程序死 / 瀏覽器斷線
    if process_alive is False:
        return _result("FAILED", ["process_dead"], signals)
    if browser_connected is False:
        return _result("FAILED", ["browser_disconnected"], signals)

    # 2) 恢復中
    if recovering or gate_state == "ERROR":
        reasons.append("recovery_active" if recovering else "gate_error")
        return _result("RECOVERING", reasons, signals)

    # 3) 刻意暫停
    if gate_state in ("PAUSED", "STOPPED"):
        return _result("PAUSED", [f"gate_{gate_state.lower()}"], signals)

    # 4) 關鍵訊號未知 → 不得視為健康
    if process_alive is None or browser_connected is None:
        return _result("UNKNOWN", ["signals_unknown"], signals)

    # 5) controller 沒有在跑（程序/瀏覽器仍活）→ DEGRADED
    controller_running = signals.get("controller_running")
    if controller_running is False:
        return _result("DEGRADED", ["controller_not_cycling"], signals)
    cycle_age = _age(now, signals.get("last_cycle_at"))
    if controller_running is None and cycle_age is None:
        return _result("UNKNOWN", ["controller_state_unknown"], signals)
    if cycle_age is not None and cycle_age > limits["cycle_stale_after_s"]:
        return _result("DEGRADED", ["controller_cycle_stale"], signals)

    # 6) 子系統不可達 → DEGRADED
    for key, reason in (("planner_active", "planner_inactive"),
                        ("executor_reachable", "executor_unreachable"),
                        ("verifier_reachable", "verifier_unreachable")):
        if signals.get(key) is False:
            reasons.append(reason)
    if reasons:
        return _result("DEGRADED", reasons, signals)

    # 7) world / observation 過期 → STALE
    if signals.get("world_fresh") is False:
        return _result("STALE", ["world_not_fresh"], signals)
    obs_age = _age(now, signals.get("last_observation_at"))
    world_age = _age(now, signals.get("last_world_at"))
    if obs_age is not None and obs_age > limits["observation_stale_after_s"]:
        return _result("STALE", ["observation_stale"], signals)
    if world_age is not None and world_age > limits["world_stale_after_s"]:
        return _result("STALE", ["world_stale"], signals)
    if obs_age is None and signals.get("world_fresh") is None:
        return _result("UNKNOWN", ["observation_unknown"], signals)

    return _result("HEALTHY", [], signals)


def _result(state: str, reasons: list, signals: dict) -> dict:
    return {
        "state": state,
        "reasons": list(reasons),
        "process_alive": signals.get("process_alive"),
        "browser_connected": signals.get("browser_connected"),
        "gate_state": signals.get("gate_state"),
        "controller_running": signals.get("controller_running"),
    }


def summarize(health: dict) -> str:
    state = (health or {}).get("state", "UNKNOWN")
    reasons = (health or {}).get("reasons") or []
    return state + (f" :: {', '.join(reasons)}" if reasons else "")


def health_from_snapshot(snapshot: dict | None, now: float) -> dict:
    """把 app.snapshot() 轉成健康訊號並判定。缺欄位一律 UNKNOWN。"""
    snap = snapshot if isinstance(snapshot, dict) else {}
    browser = (snap.get("browser")
               if isinstance(snap.get("browser"), dict) else {})
    controller = (snap.get("live_controller")
                  if isinstance(snap.get("live_controller"), dict) else {})
    game = snap.get("game") if isinstance(snap.get("game"), dict) else {}
    live = snap.get("live") if isinstance(snap.get("live"), dict) else {}
    game_state = game.get("state")
    world_fresh = None
    if game_state is not None:
        world_fresh = game_state == "IN_MATCH"
    signals = {
        "process_alive": snap.get("state") is not None,
        "browser_connected": browser.get("connected"),
        "gate_state": snap.get("state"),
        "controller_running": None,
        "last_cycle_at": controller.get("updated_at"),
        "last_observation_at": live.get("captured_at"),
        "world_fresh": world_fresh,
        "planner_active": None,
        "executor_reachable": None,
        "verifier_reachable": None,
    }
    result = evaluate_health(signals, now)
    result["source"] = "app.snapshot()"
    return result
