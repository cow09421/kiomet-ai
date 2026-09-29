"""授權＋單次派送＋模式分離測試。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.app import Application, parse_args
from kiomet_ai.control import ActionGate


def test_gate_default_unauthorized():
    gate = ActionGate()
    assert gate.authorized is False
    assert gate.authorization_provenance is None


def test_gate_provenance_recorded():
    gate = ActionGate()
    gate.set_authorized(True, "explicit_user_authorization:test")
    assert gate.authorized is True
    assert gate.authorization_provenance == "explicit_user_authorization:test"
    assert gate.authorization_granted_at is not None
    gate.set_authorized(False)
    assert gate.authorized is False
    assert gate.authorization_provenance is None


def test_dispatch_exec_blocked_without_authorization():
    async def run():
        gate = ActionGate()
        gate.state = "RUNNING"
        calls = []
        async def op():
            calls.append(1)
            return True
        assert await gate.dispatch_exec(op) is None  # 未授權擋下
        assert calls == []
        gate.set_authorized(True, "test")
        assert await gate.dispatch_exec(op) is True  # 授權＋RUNNING 放行一次
        assert calls == [1]
        gate.state = "PAUSED"
        assert await gate.dispatch_exec(op) is None  # 暫停擋下
        assert calls == [1]
    asyncio.run(run())


def test_live_authorize_flag():
    assert parse_args([]).live_authorize is False
    assert parse_args(["--live-authorize"]).live_authorize is True


def test_execute_move_requires_authorization(tmp_path):
    (tmp_path / "runtime" / "logs").mkdir(parents=True)
    (tmp_path / "runtime" / "audio").mkdir(parents=True)
    app = Application(tmp_path, {"log_max_bytes": 65536, "log_backups": 1},
                      no_browser=True)
    app.gate.state = "RUNNING"  # 運行中但無授權
    result = asyncio.run(app.execute_move({"source": [1, 2], "target": [3, 4],
                                           "match_id": "m1"}))
    assert result["ok"] is False
    assert result["result"] == "NOT_AUTHORIZED"
    assert app._read_live_journal()["sent_actions"] == 0


def test_publish_carries_live_keys(tmp_path):
    (tmp_path / "runtime" / "logs").mkdir(parents=True)
    (tmp_path / "runtime" / "audio").mkdir(parents=True)
    app = Application(tmp_path, {"log_max_bytes": 65536, "log_backups": 1},
                      no_browser=True)
    app.publish()
    snap = app.snapshot()
    assert "live_gameplay" in snap
    assert "live_sent_actions" in snap
    assert "live_authorization" in snap
    assert snap["live_authorization"]["enabled"] is False
    assert "next_action" in snap

def _make_app(tmp_path, mode):
    (tmp_path / "runtime" / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "audio").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "state").mkdir(parents=True, exist_ok=True)
    import json as _json
    (tmp_path / "runtime" / "state" / "control.json").write_text(
        _json.dumps({"url": "http://127.0.0.1:8765", "token": "t"}), encoding="utf-8")
    config = {"log_max_bytes": 65536, "log_backups": 1, "mode": mode}
    return Application(tmp_path, config, no_browser=True)


def test_live_mode_separates_mock_loop(tmp_path):
    live = _make_app(tmp_path, "live")
    assert live.live_mode is True
    assert live.game is None and live.observer is None
    assert live.planner is None and live.executor is None and live.verifier is None
    assert live.live_controller is not None
    mock = _make_app(tmp_path, "mock")
    assert mock.live_mode is False
    assert mock.live_controller is None
    assert mock.game is not None and mock.observer is not None


def test_live_publish_without_mocks(tmp_path):
    live = _make_app(tmp_path, "live")
    live.publish()  # 不得因 mock 為 None 而崩潰
    snap = live.snapshot()
    assert snap["observation_count"] == 0
    assert snap["sent_actions"] == 0
    assert snap["controller"]["running"] is False
    assert snap["live_authorization"]["enabled"] is False
    assert "anchor_summary" in snap


def test_origin_split_counts(tmp_path):
    live = _make_app(tmp_path, "live")

    class StubBrowser:
        status = {"connected": False}
        game = {"state": "UNKNOWN", "match": {}}
        move_probe = {"last": None}
        directed_moves = [
            {"origin": "LIVE_CONTROLLER"}, {"origin": "LIVE_CONTROLLER"},
            {"origin": "API_MANUAL"}]
    live.browser = StubBrowser()
    live.publish()
    snap = live.snapshot()
    assert snap["live_sent_actions"] == 3
    assert snap["autonomous_sent_actions"] == 2
    assert snap["manual_probe_sent_actions"] == 1

def test_record_verification_counts(tmp_path):
    live = _make_app(tmp_path, "live")
    journal = live.record_verification("TARGET_CONTESTED", "m1")
    assert journal["verified_moves"] == 1
    assert journal["verified_expansions"] == 0
    assert journal["last_verification"] == "TARGET_CONTESTED"
    journal = live.record_verification("TARGET_CAPTURED", "m1")
    assert journal["verified_moves"] == 2
    assert journal["verified_expansions"] == 1
    journal = live.record_verification("UNKNOWN_RESULT", "m1")
    assert journal["verified_moves"] == 2
    assert live.snapshot()["live_gameplay"]["verified_moves"] == 2


def test_cycle_reason_taxonomy():
    from kiomet_ai.live_controller import LiveController
    assert LiveController.normalize_reason("pair_cooldown") == "COOLDOWN"
    assert LiveController.normalize_reason("anchor_failed") == "STALE_WORLD"
    assert LiveController.normalize_reason("camera_failed") == "STALE_CAMERA"
    assert LiveController.normalize_reason("not_in_match") == "NOT_IN_MATCH"
    assert LiveController.normalize_reason("NO_SAFE_PROPOSAL") == "NO_SAFE_PROPOSAL"
    assert LiveController.normalize_reason("whatever-unknown") == "OTHER_EXPLICIT_REASON"
    assert LiveController.normalize_reason(None) == "OTHER_EXPLICIT_REASON"


def test_cycle_reason_taxonomy_covers_known_runtime_outcomes_and_is_idempotent():
    from kiomet_ai.live_controller import LiveController

    expected = {
        "anchor_unavailable": "STALE_WORLD",
        "probe_unavailable": "STALE_WORLD",
        "tower_gone": "STALE_WORLD",
        "ACTION_VERIFICATION_PENDING": "WAITING_VERIFICATION",
        "PVP_DEFENSE_DECISION_STALE": "ACTION_GATE_BLOCKED",
        "PVP_ATTACK_DECISION_STALE_OR_UNRESOLVED": "ACTION_GATE_BLOCKED",
        "attack-dispatch-evidence-incomplete": "ACTION_GATE_BLOCKED",
        "PVP_ATTACK_FORCE_MISMATCH": "ACTION_GATE_BLOCKED",
        "PVP_ARBITRATION_ABSTAIN": "ACTION_GATE_BLOCKED",
        "PVP_REINFORCEMENT_PROPOSAL_rejected": "NO_SAFE_PROPOSAL",
        "PVP_ATTACK_PROPOSAL_rejected": "NO_SAFE_PROPOSAL",
        "static-robust-pvp-enemy-attack-pending-runtime-verification":
            "VALIDATION_PENDING",
        "not_in_match": "NOT_IN_MATCH",
    }

    for raw_reason, category in expected.items():
        assert LiveController.normalize_reason(raw_reason) == category
        assert LiveController.normalize_reason(category) == category


def test_controller_heartbeat_shape():
    from kiomet_ai.live_controller import LiveController
    controller = LiveController.__new__(LiveController)
    controller.running = True
    controller.cycle_count = 7
    controller.last_cycle_at = 123.0
    controller.phase = "NO_SAFE_PROPOSAL"
    controller.journal = {"sent_actions": 1, "verified_moves": 1,
                          "verified_expansions": 0}
    heart = controller.heartbeat()
    assert heart["cycle_count"] == 7
    assert heart["journal"]["sent_actions"] == 1
