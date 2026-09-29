"""待確認目標終結回歸。

Finalize 規則（以現行正式行為為準）：
- 對局結束前無 after 框 → 待確認維持 UNKNOWN，不得升級；
- 換局後舊待確認直接丟棄，不得計數、不得污染新局；
- 目標從觀察消失 → 保留（不確認、不計數），等新證據；
- 超過 1800 秒 → 丟棄；
- 離局期間不跑檢查 → 舊項目滯留但帶 match_id，
  下次同局檢查可過濾，換局檢查直接丟棄；
- 舊格式與中立擴張只有目標轉 SELF 才計入擴張。
- 敵方攻擊的目標轉 SELF 只記錄觀察到的佔領，不冒充中立擴張或攻擊 proof。

這些是離線狀態轉移測試，不連接真實遊戲。
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _fake_controller():
    from kiomet_ai.live_controller import LiveController
    ctl = LiveController.__new__(LiveController)
    ctl.journal = {"verified_expansions": 0, "pending_captures": []}
    ctl.recorded_expansions = []
    ctl.app = SimpleNamespace(
        record_expansion=ctl.recorded_expansions.append)
    return ctl


def _pending(target, match_id="m1", since=None, *, action_kind=None,
             attack_validation_status=None, dispatch_observation=None,
             target_owner_before=None):
    row = {"target": target, "match_id": match_id,
           "action_id": f"{match_id}:10->{target}:100",
           "since": time.time() if since is None else since}
    if action_kind is not None:
        row["action_kind"] = action_kind
    if attack_validation_status is not None:
        row["attack_validation_status"] = attack_validation_status
    if dispatch_observation is not None:
        row["dispatch_observation"] = dispatch_observation
    if target_owner_before is not None:
        row["target_owner_before"] = target_owner_before
    return row


def _tower(owner):
    return SimpleNamespace(owner=owner, tower_id=20)


def test_match_ends_before_after_frame_keeps_unknown():
    """對局結束前無 after 框：待確認不升級、不計數。"""
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(20)]
    ctl._check_pending_captures({}, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 0
    assert len(ctl.journal["pending_captures"]) == 1


def test_match_id_changes_drops_old_pending():
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(20, match_id="m0")]
    ctl._check_pending_captures({20: _tower("SELF")}, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 0
    assert ctl.journal["pending_captures"] == []


def test_target_disappears_stays_pending():
    """目標從觀察消失 → 保留待確認，不確認、不計數。"""
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(20)]
    ctl._check_pending_captures({99: _tower("SELF")}, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 0
    assert len(ctl.journal["pending_captures"]) == 1


def test_stale_pointer_not_confirmed():
    """by_id 缺該塔（stale 指標）→ 不確認。"""
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(20)]
    ctl._check_pending_captures({}, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 0


def test_page_recovered_target_self_confirms():
    """頁面恢復後目標轉 SELF → 確認擴張並清除該筆。"""
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(20)]
    ctl._check_pending_captures({20: _tower("SELF")}, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 1
    assert ctl.journal["pending_captures"] == []
    assert ctl.journal["last_expansion"]["match_id"] == "m1"
    assert len(ctl.recorded_expansions) == 1


def test_enemy_capture_is_not_counted_as_neutral_expansion_or_proof():
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(
        20, action_kind="ATTACK_ENEMY",
        attack_validation_status="VALIDATION_PENDING",
        dispatch_observation="FORCE_OBSERVED",
        target_owner_before="ENEMY")]

    ctl._check_pending_captures({20: _tower("SELF")}, "m1", time.time())

    assert ctl.journal["verified_expansions"] == 0
    assert ctl.recorded_expansions == []
    assert ctl.journal["pending_captures"] == []
    assert ctl.journal["observed_attack_captures"] == 1
    outcome = ctl.journal["last_attack_capture"]
    assert outcome["action_id"] == "m1:10->20:100"
    assert outcome["match_id"] == "m1"
    assert outcome["target"] == 20
    assert outcome["outcome"] == "TARGET_CAPTURED"
    assert outcome["attack_validation_status"] == "VALIDATION_PENDING"


def test_enemy_capture_without_same_action_route_proof_stays_unattributed():
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(
        20, action_kind="ATTACK_ENEMY",
        dispatch_observation="UNKNOWN", target_owner_before="ENEMY")]

    ctl._check_pending_captures({20: _tower("SELF")}, "m1", time.time())

    assert ctl.journal["verified_expansions"] == 0
    assert ctl.journal.get("observed_attack_captures", 0) == 0
    assert ctl.journal.get("last_attack_capture") is None
    assert len(ctl.journal["pending_captures"]) == 1


def test_enemy_capture_with_unknown_previous_owner_stays_unattributed():
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(
        20, action_kind="ATTACK_ENEMY",
        dispatch_observation="FORCE_OBSERVED",
        target_owner_before="UNKNOWN")]

    ctl._check_pending_captures({20: _tower("SELF")}, "m1", time.time())

    assert ctl.journal["verified_expansions"] == 0
    assert ctl.journal.get("observed_attack_captures", 0) == 0
    assert len(ctl.journal["pending_captures"]) == 1


def test_legacy_pending_capture_still_counts_as_expansion():
    """既有缺 action_kind 的日誌沿用原本的中立擴張語義。"""
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(20)]

    ctl._check_pending_captures({20: _tower("SELF")}, "m1", time.time())

    assert ctl.journal["verified_expansions"] == 1
    assert len(ctl.recorded_expansions) == 1


def test_unknown_pending_action_kind_is_not_assumed_to_be_expansion():
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(
        20, action_kind="UNKNOWN_ACTION")]

    ctl._check_pending_captures({20: _tower("SELF")}, "m1", time.time())

    assert ctl.journal["verified_expansions"] == 0
    assert ctl.recorded_expansions == []
    assert len(ctl.journal["pending_captures"]) == 1


def test_result_screen_expired_pending_dropped():
    """結算時超期待確認 → 丟棄，不計數。"""
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [
        _pending(20, since=time.time() - 2000)]
    ctl._check_pending_captures({20: _tower("SELF")}, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 0
    assert ctl.journal["pending_captures"] == []


def test_expiry_boundary_1800s_kept():
    """恰 1800 秒保留（只丟 >1800 者）。"""
    ctl = _fake_controller()
    now = time.time()
    ctl.journal["pending_captures"] = [_pending(20, since=now - 1800)]
    ctl._check_pending_captures({20: _tower("NEUTRAL")}, "m1", now)
    assert len(ctl.journal["pending_captures"]) == 1


def test_mixed_matches_only_current_processed():
    """多局混合待確認：只處理當局，他局丟棄。"""
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [
        _pending(20, match_id="m0"),
        _pending(20, match_id="m1"),
    ]
    ctl._check_pending_captures({20: _tower("SELF")}, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 1
    assert ctl.journal["pending_captures"] == []
