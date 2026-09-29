"""Crash-window matrix for durable combat identity and pending verification."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kiomet_ai.app import Application
from kiomet_ai.live_controller import LiveController


def _controller(root):
    return LiveController(SimpleNamespace(root=Path(root), browser=None))


def _pending(*, status="PREPARED", sent_at=None):
    record = {
        "schema_version": 1,
        "action_id": "match-A:11->22:1000",
        "match_id": "match-A",
        "source_tower_id": 11,
        "target_tower_id": 22,
        "action_kind": "ATTACK_ENEMY",
        "cycle_id": 9,
        "status": status,
        "created_at": 1000.0,
        "attack_validation_status": "VALIDATION_PENDING",
        "attack_proof_bundle": {
            "battle_differential_evidence_id": "battle-evidence-1",
            "server_acceptance_evidence_id": "server-evidence-1",
        },
        "before": {
            "match_id": "match-A",
            "source": {"owner": "SELF", "units": {"Soldier": 20}},
            "target": {"owner": "ENEMY", "units": {"Soldier": 5}},
        },
    }
    if sent_at is not None:
        record["sent_at"] = sent_at
    return record


@pytest.mark.parametrize(("crash_point", "status", "sent_at", "unknown"), [
    ("before_dispatch", "PREPARED", None, False),
    ("during_dispatch", "PREPARED", None, False),
    ("after_dispatch_before_verify", "SENT", 1001.0, False),
    ("during_verify", "SENT", 1001.0, True),
])
def test_unresolved_crash_windows_keep_action_reservation_and_proof(
        tmp_path, crash_point, status, sent_at, unknown):
    first = _controller(tmp_path)
    record = _pending(status=status, sent_at=sent_at)
    first._set_pending_dispatch(record)
    first.journal["threat_state"] = {
        "match_id": "match-A", "cycle_id": 9, "status": "THREATENED",
        "freshness": "FRESH", "threats": [{"threat_id": "enemy-1"}],
    }
    first._save()
    if unknown:
        assert first._finish_pending_dispatch("UNKNOWN") is False
        record["status"] = "VERIFICATION_UNKNOWN"
        record["last_verdict"] = "UNKNOWN"

    restarted = _controller(tmp_path)
    pending = restarted.journal["pending_dispatch"]

    assert pending["action_id"] == "match-A:11->22:1000", crash_point
    assert pending["match_id"] == "match-A", crash_point
    assert (pending["source_tower_id"], pending["target_tower_id"]) == (11, 22)
    assert pending["status"] == record["status"]
    assert pending["attack_validation_status"] == "VALIDATION_PENDING"
    assert pending["attack_proof_bundle"] == record["attack_proof_bundle"]
    assert pending["before"] == record["before"]

    # The restored latch reserves this action's source/target until fresh,
    # same-match verification resolves it; restart cannot plan a duplicate.
    assert restarted._reconcile_pending_dispatch({}, "match-A") is True
    assert json.loads(restarted._pending_dispatch_path().read_text(
        encoding="utf-8"))["action_id"] == pending["action_id"]

    # Old threat snapshots are not reused as current decision input.
    assert restarted.journal["threat_state"]["status"] == "UNKNOWN"
    assert restarted.journal["threat_state"]["threats"] == []


def test_verified_action_is_logged_before_next_refresh_and_not_reopened(
        tmp_path):
    first = _controller(tmp_path)
    record = _pending(status="SENT", sent_at=1001.0)
    first._set_pending_dispatch(record)
    first.journal["last_action"] = {
        "origin": "LIVE_CONTROLLER", "action_kind": "ATTACK_ENEMY",
        "cycle_id": record["cycle_id"],
        "match_id": record["match_id"], "sent_at": record["sent_at"],
        "source": record["source_tower_id"],
        "target": record["target_tower_id"],
    }
    first.journal["last_verification"] = "TARGET_CONTESTED"

    assert first._finish_pending_dispatch("TARGET_CONTESTED") is True
    saved = json.loads((tmp_path / "runtime/state/live_controller.json").read_text(
        encoding="utf-8"))
    assert saved["journal"]["last_verification"] == "TARGET_CONTESTED"
    assert saved["journal"]["last_action"]["match_id"] == "match-A"
    assert "pending_dispatch" not in saved["journal"]

    # Use the production append method without constructing or starting the app.
    app = Application.__new__(Application)
    app.root = Path(tmp_path)
    (tmp_path / "runtime/logs").mkdir(parents=True, exist_ok=True)
    app.append_live_action({
        "action_id": record["action_id"], "origin": "LIVE_CONTROLLER",
        "action_kind": "ATTACK_ENEMY", "match": record["match_id"],
        "source": record["source_tower_id"], "target": record["target_tower_id"],
        "verifier": "TARGET_CONTESTED", "result": "TARGET_CONTESTED",
        "dispatch": {"sent_at": record["sent_at"]},
    })

    restarted = _controller(tmp_path)
    action_path = tmp_path / "runtime/logs/live_actions.jsonl"
    rows = [json.loads(line) for line in action_path.read_text(
        encoding="utf-8").splitlines() if line.strip()]

    assert "pending_dispatch" not in restarted.journal
    assert len(rows) == 1
    assert rows[0]["action_id"] == record["action_id"]
    assert rows[0]["verifier"] == "TARGET_CONTESTED"
    assert restarted._reconcile_pending_dispatch({}, "match-A") is False


def test_corrupt_pending_marker_fails_closed_after_restart(tmp_path):
    marker = tmp_path / "runtime/state/pending-live-dispatch.json"
    marker.parent.mkdir(parents=True)
    marker.write_text("{not-json", encoding="utf-8")

    restarted = _controller(tmp_path)

    assert restarted.journal["pending_dispatch"]["status"] == (
        "RECOVERY_MARKER_UNKNOWN")
    assert restarted._reconcile_pending_dispatch({}, "match-A") is True
