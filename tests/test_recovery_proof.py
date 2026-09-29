"""恢復證據包回歸（P0 §6）。

完整鏈才 COMPLETE；缺階段 PARTIAL；stage FAILED 回 FAILED；
時間倒流可偵測；不推測。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.recovery_proof import RecoveryProof


def _full():
    p = RecoveryProof()
    p.note_crash(100.0)
    p.note_stage("DETECTED", 100.0)
    p.note_stage("RECOVERING_PAGE", 101.0)
    p.note_stage("RECOVERING_CHROMIUM", 102.0)
    p.note_stage("REACQUIRING_MATCH", 103.0)
    p.note_new_page(222)
    p.note_new_browser(111)
    p.note_match("m1-new")
    p.note_first_fresh_observation(110.0)
    p.note_stage("READY", 110.0)
    p.note_first_cycle(1, 111.0)
    p.note_first_decision("EXPAND", 112.0)
    p.note_first_action({"kind": "EXPAND_NEUTRAL"})
    return p


def test_full_chain_complete():
    result = _full().verify_chain()
    assert result["status"] == "COMPLETE"
    assert result["missing"] == []


def test_missing_stages_is_partial():
    p = RecoveryProof()
    p.note_crash(100.0)
    p.note_match("m1")
    result = p.verify_chain()
    assert result["status"] == "PARTIAL"
    assert "first_fresh_observation_at" in result["missing"]
    assert "first_cycle_at" in result["missing"]


def test_stage_failed_is_failed():
    p = RecoveryProof()
    p.note_crash(100.0)
    p.note_stage("FAILED", 101.0)
    assert p.verify_chain()["status"] == "FAILED"


def test_abstain_counts_as_first_post_recovery_outcome():
    p = RecoveryProof()
    p.note_crash(100.0)
    p.note_match("m1")
    p.note_first_fresh_observation(110.0)
    p.note_first_cycle(1, 111.0)
    p.note_first_decision("none", 112.0)
    p.note_first_abstain("STALE_WORLD")
    result = p.verify_chain()
    assert "first_action_or_abstain" not in result["missing"]
    assert result["status"] == "COMPLETE"


def test_time_reversal_detected():
    p = _full()
    p.note_first_decision("LATE", 50.0)  # 不改 first，但為觀察用
    p._timeline.append((1.0, "event"))
    assert p.time_ordered() is False
    p2 = _full()
    p2._timeline = [(200.0, "x"), (100.0, "y")]
    result = p2.verify_chain()
    assert result["status"] == "PARTIAL"
    assert result["reason"] == "time_reversal"


def test_bad_stage_rejected():
    try:
        RecoveryProof().note_stage("WAT")
        assert False, "should reject"
    except ValueError:
        pass


def test_first_values_not_overwritten():
    p = _full()
    p.note_first_cycle(99, 500.0)
    p.note_first_fresh_observation(999.0)
    bundle = p.bundle()
    assert bundle["first_cycle_id"] == 1
    assert bundle["first_fresh_observation_at"] == 110.0


def test_bundle_shape():
    bundle = _full().bundle()
    for key in ("crash_at", "stage", "new_page_pid", "new_browser_pid",
                "new_match_id", "first_fresh_observation_at",
                "first_cycle_at", "first_decision_at", "verification"):
        assert key in bundle
    assert bundle["new_browser_pid"] == 111


def test_reset_clears():
    p = _full()
    p.reset()
    assert p.crash_at is None
    assert p.verify_chain()["status"] == "PARTIAL"
