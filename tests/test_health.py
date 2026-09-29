"""Supervisor 健康模型回歸（P0 §5）。

區分 process-only alive 與真正活著；world stale 與 controller 卡死不同；
UNKNOWN 不視為健康；暫停與恢復可辨識。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.health import evaluate_health, summarize

NOW = 1000.0


def _sig(**over):
    base = {"process_alive": True, "browser_connected": True,
            "gate_state": "RUNNING", "controller_running": True,
            "last_cycle_at": NOW - 1, "last_observation_at": NOW - 2,
            "last_world_at": NOW - 2, "world_fresh": True,
            "planner_active": True, "executor_reachable": True,
            "verifier_reachable": True}
    base.update(over)
    return base


def test_healthy_all_green():
    assert evaluate_health(_sig(), NOW)["state"] == "HEALTHY"


def test_process_dead_is_failed():
    result = evaluate_health(_sig(process_alive=False), NOW)
    assert result["state"] == "FAILED"
    assert "process_dead" in result["reasons"]


def test_browser_disconnected_is_failed():
    result = evaluate_health(_sig(browser_connected=False), NOW)
    assert result["state"] == "FAILED"
    assert "browser_disconnected" in result["reasons"]


def test_recovering_when_gate_error():
    result = evaluate_health(_sig(gate_state="ERROR"), NOW)
    assert result["state"] == "RECOVERING"
    assert "gate_error" in result["reasons"]


def test_recovering_flag():
    assert evaluate_health(_sig(recovering=True), NOW)["state"] == "RECOVERING"


def test_paused_and_stopped():
    assert evaluate_health(_sig(gate_state="PAUSED"), NOW)["state"] == "PAUSED"
    assert evaluate_health(_sig(gate_state="STOPPED"), NOW)["state"] == "PAUSED"


def test_process_alive_but_controller_stuck_is_degraded():
    """核心區分：程序活著但 controller 卡死，不是 HEALTHY。"""
    result = evaluate_health(_sig(controller_running=False), NOW)
    assert result["state"] == "DEGRADED"
    assert "controller_not_cycling" in result["reasons"]


def test_controller_cycle_stale_is_degraded():
    result = evaluate_health(_sig(last_cycle_at=NOW - 60), NOW)
    assert result["state"] == "DEGRADED"
    assert "controller_cycle_stale" in result["reasons"]


def test_controller_running_but_world_stale_is_stale():
    """核心區分：controller 有跑但 world 過期 → STALE，非 DEGRADED。"""
    result = evaluate_health(_sig(world_fresh=False), NOW)
    assert result["state"] == "STALE"
    assert "world_not_fresh" in result["reasons"]


def test_observation_stale_is_stale():
    result = evaluate_health(_sig(last_observation_at=NOW - 100), NOW)
    assert result["state"] == "STALE"
    assert "observation_stale" in result["reasons"]


def test_subsystem_unreachable_is_degraded():
    result = evaluate_health(_sig(executor_reachable=False), NOW)
    assert result["state"] == "DEGRADED"
    assert "executor_unreachable" in result["reasons"]


def test_unknown_signals_never_healthy():
    assert evaluate_health({"process_alive": None,
                            "browser_connected": None,
                            "gate_state": "RUNNING"}, NOW)["state"] == "UNKNOWN"
    assert evaluate_health(None, NOW)["state"] == "UNKNOWN"


def test_failed_takes_priority_over_recovering():
    result = evaluate_health(_sig(process_alive=False, gate_state="ERROR"),
                             NOW)
    assert result["state"] == "FAILED"


def test_summarize():
    result = evaluate_health(_sig(world_fresh=False), NOW)
    assert summarize(result).startswith("STALE ::")
    assert summarize(evaluate_health(_sig(), NOW)) == "HEALTHY"


def test_current_blocker_scenario():
    """目前 GPU blocker 情境：process 活、browser 斷、gate ERROR。"""
    result = evaluate_health(_sig(browser_connected=False,
                                  gate_state="ERROR"), NOW)
    assert result["state"] == "FAILED"
