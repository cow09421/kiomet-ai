"""Repeated controller restarts must not replay or re-reserve an action."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kiomet_ai.action_validity import ReservationBoard
from kiomet_ai.live_controller import LiveController


MATCH_ID = "restart-match"
ACTION_ID = "restart-match:10->11:1000"


def _pending(status: str) -> dict:
    record = {
        "schema_version": 1,
        "action_id": ACTION_ID,
        "match_id": MATCH_ID,
        "source_tower_id": 10,
        "target_tower_id": 11,
        "action_kind": "ATTACK_ENEMY",
        "cycle_id": 7,
        "status": status,
        "created_at": 1_000.0,
        "browser_session_id": "isolated-session",
        "join_clicks": 1,
        "attack_validation_status": "VALIDATION_PENDING",
        "attack_proof_bundle": {
            "action_id": ACTION_ID,
            "match_id": MATCH_ID,
            "battle_differential_evidence_id": "battle-proof-1",
        },
        "before": {
            "match_id": MATCH_ID,
            "source": {"owner": "SELF", "units": {"Soldier": 12}},
            "target": {"owner": "ENEMY", "units": {"Soldier": 4}},
        },
    }
    if status in ("SENT", "VERIFICATION_UNKNOWN"):
        record["sent_at"] = 1_001.0
    if status == "VERIFICATION_UNKNOWN":
        record["last_verdict"] = "UNKNOWN"
    return record


class _App:
    def __init__(self, root: Path, browser):
        self.root = root
        self.browser = browser
        self.autonomy_paused = False
        self.execute_calls = []

    async def execute_move(self, payload):
        self.execute_calls.append(payload)
        return {"sent": True}


def _controller(root: Path, *, cycle: int = 0):
    browser = SimpleNamespace(
        game={"state": "IN_MATCH", "match": {"id": MATCH_ID},
              "join_clicks": 1},
        session_id="isolated-session",
    )
    app = _App(root, browser)
    controller = LiveController(app)
    controller.cycle_seq = cycle

    probe_dir = root / "runtime/research/units"
    probe_dir.mkdir(parents=True, exist_ok=True)
    (probe_dir / f"unit-struct-probe-{MATCH_ID}.json").write_text(
        json.dumps({"match_id": MATCH_ID, "rows": []}), encoding="utf-8")

    async def ensure_anchor(match_id):
        return {"match_id": match_id, "towers": [], "edges": []}

    async def no_op(*_args):
        return None

    controller.ensure_anchor = ensure_anchor
    controller.build_states = lambda *_args: [
        SimpleNamespace(
            tower_id=tower_id,
            freshness=lambda _match_id, _now: "STALE",
        )
        for tower_id in (10, 11)
    ]
    controller._observe_cycle_threat_state = no_op
    controller._evaluate_cycle_multi_threat = lambda *_args: None
    controller._evaluate_cycle_defense = no_op
    controller._evaluate_cycle_attack_candidates = no_op
    controller._check_pending_captures = lambda *_args: None
    return controller


@pytest.mark.parametrize("restart_count", (1, 2, 5))
@pytest.mark.parametrize("status", (
    "PREPARED", "SENT", "VERIFICATION_UNKNOWN",
))
def test_unresolved_action_is_never_redispatched_or_rereserved(
        tmp_path, monkeypatch, restart_count, status):
    reserve_calls = []
    original_reserve = ReservationBoard.reserve

    def count_reserve(board, action_id, source_id, target_id):
        reserve_calls.append((action_id, source_id, target_id))
        return original_reserve(board, action_id, source_id, target_id)

    monkeypatch.setattr(ReservationBoard, "reserve", count_reserve)

    original = _controller(tmp_path)
    original._select_reservation_match(MATCH_ID)
    assert original._reservations.reserve(ACTION_ID, 10, 11) is None
    original._set_pending_dispatch(_pending(status))
    marker = original._pending_dispatch_path()
    durable_record = json.loads(marker.read_text(encoding="utf-8"))
    assert reserve_calls == [(ACTION_ID, 10, 11)]

    execute_calls = []
    for restart in range(restart_count):
        recovered = _controller(tmp_path, cycle=restart + 100)
        assert recovered.journal["pending_dispatch"] == durable_record

        phase, info = asyncio.run(recovered.cycle_once())

        assert phase == "NO_SAFE_PROPOSAL"
        assert info["reason"] == "ACTION_VERIFICATION_PENDING"
        assert info["action_id"] == ACTION_ID
        assert recovered.journal["pending_dispatch"] == durable_record
        assert recovered._reservations.holder(10) is None
        assert recovered._reservations.holder(11) is None
        execute_calls.extend(recovered.app.execute_calls)

    assert execute_calls == []
    assert reserve_calls == [(ACTION_ID, 10, 11)]
    assert json.loads(marker.read_text(encoding="utf-8")) == durable_record


@pytest.mark.parametrize("restart_count", (1, 2, 5))
def test_verified_action_stays_final_across_restarts(
        tmp_path, restart_count):
    original = _controller(tmp_path)
    original._select_reservation_match(MATCH_ID)
    assert original._reservations.reserve(ACTION_ID, 10, 11) is None
    original._set_pending_dispatch(_pending("SENT"))

    assert original._finish_pending_dispatch("TARGET_CAPTURED") is True
    assert not original._pending_dispatch_path().exists()

    for restart in range(restart_count):
        recovered = _controller(tmp_path, cycle=restart + 200)
        assert "pending_dispatch" not in recovered.journal
        assert recovered._reconcile_pending_dispatch({}, MATCH_ID) is False
        assert recovered.app.execute_calls == []
        assert recovered._reservations.holder(10) is None
        assert recovered._reservations.holder(11) is None
        assert not recovered._pending_dispatch_path().exists()
