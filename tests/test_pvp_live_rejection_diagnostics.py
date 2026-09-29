"""即時循環要保留原始 no-action 原因與有界候選拒絕摘要。"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.live_controller import LiveController
from kiomet_ai import live_controller as live_controller_module


def controller_for_cycle():
    controller = LiveController.__new__(LiveController)
    controller.app = SimpleNamespace(
        gate=SimpleNamespace(authorized=True, state="RUNNING"))
    controller.running = True
    controller.cycle_count = 3
    controller.last_cycle_at = 12.0
    controller.phase = "NO_SAFE_PROPOSAL"
    controller.journal = {"recent_cycles": []}
    return controller


def test_cycle_keeps_raw_reason_and_rejection_summary():
    controller = controller_for_cycle()
    info = {
        "match_id": "m1",
        "reason": "no_candidate",
        "candidate_count": 0,
        "rejection_count": 2,
        "rejection_counts": {"TARGET_NOT_NEUTRAL": 2},
        "rejection_examples": [
            {"source": 10, "target": 11, "reason": "TARGET_NOT_NEUTRAL"},
            {"source": 10, "target": 12, "reason": "TARGET_NOT_NEUTRAL"},
        ],
    }

    controller._record_cycle(3, 12.0, "NO_SAFE_PROPOSAL", info)

    record = controller.journal["last_cycle"]
    assert record["no_action_reason"] == "NO_SAFE_PROPOSAL"
    assert record["raw_reason"] == "no_candidate"
    assert record["candidate_count"] == 0
    assert record["rejection_counts"] == {"TARGET_NOT_NEUTRAL": 2}
    assert controller.journal["last_info"]["raw_reason"] == "no_candidate"
    assert controller.heartbeat()["candidates"] == 0


def test_live_safety_blockers_get_stable_categories_and_keep_raw_reason():
    controller = controller_for_cycle()
    raw = "SOURCE_SAFETY_source-defender-composition-unknown"

    controller._record_cycle(
        4, 13.0, "NO_SAFE_PROPOSAL", {"reason": raw})

    record = controller.journal["last_cycle"]
    assert record["no_action_reason"] == "SOURCE_SAFETY_BLOCKED"
    assert record["raw_reason"] == raw


def test_stale_and_reserved_dispatch_reasons_get_stable_categories():
    normalize = LiveController.normalize_reason

    assert normalize("STALE_PROPOSAL:tower-state-changed") == "STALE_PROPOSAL"
    assert normalize("RESOURCE_RESERVED:source") == "RESOURCE_RESERVED"
    assert normalize({"reason": "malformed"}) == "OTHER_EXPLICIT_REASON"


def test_rejection_summary_counts_all_but_keeps_only_twenty_examples():
    rows = [{"source": index, "reason": "TARGET_NOT_NEUTRAL"}
            for index in range(25)]

    summary = LiveController.summarize_rejections(rows)

    assert summary["rejection_count"] == 25
    assert summary["rejection_counts"] == {"TARGET_NOT_NEUTRAL": 25}
    assert len(summary["rejection_examples"]) == 20


def test_empty_rank_returns_rejection_diagnostics(tmp_path, monkeypatch):
    controller = LiveController.__new__(LiveController)
    controller.root = tmp_path
    controller.app = SimpleNamespace(
        browser=SimpleNamespace(game={
            "state": "IN_MATCH", "match": {"id": "m1"}}))

    async def ensure_anchor(match_id):
        return {"match_id": match_id, "towers": []}

    controller.ensure_anchor = ensure_anchor
    controller.build_states = lambda anchor, rows, now: [
        SimpleNamespace(tower_id=10)]
    controller._check_pending_captures = lambda by_id, match_id, now: None
    probe_path = (tmp_path / "runtime/research/units"
                  / "unit-struct-probe-m1.json")
    probe_path.parent.mkdir(parents=True)
    probe_path.write_text(json.dumps({"rows": []}), encoding="utf-8")
    rejected = [{"source": 10, "target": 11,
                 "reason": "TARGET_NOT_NEUTRAL"}]
    monkeypatch.setattr(live_controller_module, "rank_expansion_targets",
                        lambda states, match_id, now: [])
    monkeypatch.setattr(live_controller_module, "rejection_reasons",
                        lambda states, match_id, now: rejected)

    phase, info = asyncio.run(controller.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert info["reason"] == "no_candidate"
    assert info["candidate_count"] == 0
    assert info["rejection_counts"] == {"TARGET_NOT_NEUTRAL": 1}
    assert info["rejection_examples"] == rejected
