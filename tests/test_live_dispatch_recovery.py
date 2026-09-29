"""An uncertain live dispatch must survive controller process replacement."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from kiomet_ai.live_controller import LiveController


def controller(root, browser=None):
    return LiveController(SimpleNamespace(root=Path(root), browser=browser))


def pending_record(*, match_id="m1", session_id="browser-old",
                   join_clicks=1, status="SENT"):
    return {
        "schema_version": 1,
        "action_id": "m1:10->11:1000",
        "match_id": match_id,
        "source_tower_id": 10,
        "target_tower_id": 11,
        "status": status,
        "created_at": 1000.0,
        "browser_session_id": session_id,
        "join_clicks": join_clicks,
        "before": {
            "match_id": match_id,
            "source": {"owner": "SELF", "units": {
                "Shield": 0, "Fighter": 0, "Chopper": 0,
                "Bomber": 0, "Tank": 0, "Soldier": 10}},
            "target": {"owner": "NEUTRAL", "units": {
                "Shield": 0, "Fighter": 0, "Chopper": 0,
                "Bomber": 0, "Tank": 0, "Soldier": 2}},
        },
    }


def tower(owner, soldier):
    counts = SimpleNamespace(
        units_kind="MANY", shield=0, fighter=0, chopper=0,
        bomber=0, tank=0, soldier=soldier)
    return SimpleNamespace(owner=owner, unit_counts=counts,
                           freshness=lambda _match, _now: "FRESH")


def test_pending_dispatch_is_persisted_and_reloaded_after_restart(tmp_path):
    first = controller(tmp_path)
    record = pending_record()

    first._set_pending_dispatch(record)
    restarted = controller(tmp_path)

    assert restarted.journal["pending_dispatch"] == record
    assert (tmp_path / "runtime/state/live_controller.json").exists()


def test_unresolved_same_match_dispatch_blocks_new_action_after_restart(tmp_path):
    first = controller(tmp_path)
    first._set_pending_dispatch(pending_record())
    restarted = controller(tmp_path)

    blocked = restarted._reconcile_pending_dispatch(
        {10: tower("SELF", 10), 11: tower("NEUTRAL", 2)}, "m1")

    assert blocked is True
    assert restarted.journal["pending_dispatch"]["status"] == "SENT"


def test_reconcile_restores_marker_when_memory_journal_is_missing(tmp_path):
    live = LiveController.__new__(LiveController)
    live.root = Path(tmp_path)
    marker = tmp_path / "runtime/state/pending-live-dispatch.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps(pending_record()), encoding="utf-8")

    assert live._reconcile_pending_dispatch({}, "m1") is True
    assert live.journal["pending_dispatch"]["action_id"] == "m1:10->11:1000"


def test_cycle_once_does_not_plan_while_same_match_dispatch_is_unresolved(
        tmp_path):
    browser = SimpleNamespace(game={
        "state": "IN_MATCH", "match": {"id": "m1"}, "join_clicks": 1,
    }, session_id="browser-old")
    live = controller(tmp_path, browser)
    live._set_pending_dispatch(pending_record())
    probe_dir = tmp_path / "runtime/research/units"
    probe_dir.mkdir(parents=True, exist_ok=True)
    (probe_dir / "unit-struct-probe-m1.json").write_text(
        json.dumps({"match_id": "m1", "rows": []}), encoding="utf-8")
    async def ensure_anchor(_match_id):
        return {"match_id": "m1", "towers": [], "edges": []}

    live.ensure_anchor = ensure_anchor
    live.build_states = lambda *_args: [
        SimpleNamespace(tower_id=10, freshness=lambda *_: "FRESH",
                        owner="SELF", unit_counts=SimpleNamespace(
                            units_kind="MANY", shield=0, fighter=0,
                            chopper=0, bomber=0, tank=0, soldier=10)),
        SimpleNamespace(tower_id=11, freshness=lambda *_: "FRESH",
                        owner="NEUTRAL", unit_counts=SimpleNamespace(
                            units_kind="MANY", shield=0, fighter=0,
                            chopper=0, bomber=0, tank=0, soldier=2)),
    ]

    phase, info = asyncio.run(live.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert info["reason"] == "ACTION_VERIFICATION_PENDING"
    assert info["action_id"] == "m1:10->11:1000"


def test_fresh_post_action_proof_resolves_pending_dispatch(tmp_path):
    live = controller(tmp_path)
    live._set_pending_dispatch(pending_record())

    blocked = live._reconcile_pending_dispatch(
        {10: tower("SELF", 8), 11: tower("SELF", 5)}, "m1")

    assert blocked is False
    assert "pending_dispatch" not in live.journal


def test_unknown_verification_keeps_pending_latch_but_verified_result_clears(
        tmp_path):
    live = controller(tmp_path)
    live._set_pending_dispatch(pending_record())

    assert live._finish_pending_dispatch("UNKNOWN") is False
    assert live.journal["pending_dispatch"]["status"] == "VERIFICATION_UNKNOWN"
    assert live._finish_pending_dispatch("TARGET_CONTESTED") is True
    assert "pending_dispatch" not in live.journal


def test_unknown_verification_latch_survives_a_second_controller_restart(
        tmp_path):
    live = controller(tmp_path)
    live._set_pending_dispatch(pending_record())
    live._finish_pending_dispatch("UNKNOWN")

    restarted = controller(tmp_path)

    assert restarted.journal["pending_dispatch"]["status"] == (
        "VERIFICATION_UNKNOWN")


def test_attack_proof_pending_status_survives_restart_and_unknown_verification(
        tmp_path):
    record = pending_record()
    record.update({
        "action_kind": "ATTACK_ENEMY",
        "attack_validation_status": "VALIDATION_PENDING",
    })
    first = controller(tmp_path)
    first._set_pending_dispatch(record)

    restarted = controller(tmp_path)
    assert restarted.journal["pending_dispatch"] == record
    assert "attack_proof_bundle" not in restarted.journal["pending_dispatch"]
    assert restarted._reconcile_pending_dispatch({}, "m1") is True
    assert restarted.journal["pending_dispatch"][
        "attack_validation_status"] == "VALIDATION_PENDING"

    assert restarted._finish_pending_dispatch("UNKNOWN") is False
    second_restart = controller(tmp_path)
    pending = second_restart.journal["pending_dispatch"]
    assert pending["status"] == "VERIFICATION_UNKNOWN"
    assert pending["action_kind"] == "ATTACK_ENEMY"
    assert pending["attack_validation_status"] == "VALIDATION_PENDING"
    assert "attack_proof_bundle" not in pending


def test_only_explicit_new_match_entry_clears_old_match_latch(tmp_path):
    browser = SimpleNamespace(
        session_id="browser-new",
        game={"join_clicks": 1, "match": {"id": "m2"}},
    )
    live = controller(tmp_path, browser)
    live._set_pending_dispatch(pending_record())

    blocked = live._reconcile_pending_dispatch({}, "m2")

    assert blocked is False
    assert "pending_dispatch" not in live.journal


def test_same_session_new_match_without_a_new_join_click_stays_blocked(
        tmp_path):
    browser = SimpleNamespace(
        session_id="browser-old",
        game={"join_clicks": 1, "match": {"id": "m2"}},
    )
    live = controller(tmp_path, browser)
    live._set_pending_dispatch(pending_record(
        session_id="browser-old", join_clicks=1))

    assert live._reconcile_pending_dispatch({}, "m2") is True


def test_match_change_without_explicit_new_entry_stays_blocked(tmp_path):
    browser = SimpleNamespace(
        session_id="browser-new",
        game={"join_clicks": 0, "match": {"id": "m2"}},
    )
    live = controller(tmp_path, browser)
    live._set_pending_dispatch(pending_record())

    assert live._reconcile_pending_dispatch({}, "m2") is True
