"""驗證器統計一致性回歸（P0-D）。

稽核發現：verified_expansions > 0 但 TARGET_CAPTURED = 0。
本檔鎖定語意：
- TARGET_CONTESTED 絕不等於佔領，不得計入 verified_expansions；
- 只有 TARGET_CAPTURED 或待確認目標後續轉 SELF 才計擴張；
- 待確認（pending capture）只保留同局、1800 秒內項目；
- 跨局待確認直接丟棄，不得污染。

只寫 tests，不改正式邏輯（live_controller.py／app.py 為 FOREIGN_ACTIVE）。
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.proposal import ActionProposal, verify_post_action


def _proposal(**over):
    base = {"match_id": "m1", "created_at": time.time(),
            "source_tower_id": 10, "target_tower_id": 20}
    base.update(over)
    return ActionProposal(**base)


def _units(**kw):
    out = {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0,
           "Tank": 0, "Soldier": 0}
    out.update(kw)
    return out


def test_contested_is_never_captured():
    """目標改變但非 SELF → CONTESTED，絕非 CAPTURED。"""
    before = {"match_id": "m1",
              "source": {"owner": "SELF", "units": _units(Soldier=12)},
              "target": {"owner": "NEUTRAL", "units": _units()}}
    after = {"match_id": "m1",
             "source": {"owner": "SELF", "units": _units()},
             "target": {"owner": "NEUTRAL", "units": _units(Soldier=4)}}
    result = verify_post_action(before, after, _proposal())
    assert result == "TARGET_CONTESTED"
    assert result != "TARGET_CAPTURED"


def test_captured_requires_self_owner():
    before = {"match_id": "m1",
              "source": {"owner": "SELF", "units": _units(Soldier=12)},
              "target": {"owner": "NEUTRAL", "units": _units()}}
    after = {"match_id": "m1",
             "source": {"owner": "SELF", "units": _units()},
             "target": {"owner": "SELF", "units": _units(Soldier=12)}}
    assert verify_post_action(before, after, _proposal()) == "TARGET_CAPTURED"


def _fake_controller():
    from kiomet_ai.live_controller import LiveController
    ctl = LiveController.__new__(LiveController)
    ctl.journal = {"verified_expansions": 0, "pending_captures": []}
    ctl.app = SimpleNamespace(record_expansion=lambda item: None)
    return ctl


def _pending(target, match_id="m1", since=None):
    return {"target": target, "match_id": match_id,
            "action_id": f"{match_id}:10->{target}:100",
            "since": time.time() if since is None else since}


def test_pending_confirmed_only_when_target_becomes_self():
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(20)]
    by_id = {20: SimpleNamespace(owner="SELF", tower_id=20)}
    ctl._check_pending_captures(by_id, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 1
    assert ctl.journal["pending_captures"] == []
    assert ctl.journal["last_expansion"]["target"] == 20


def test_pending_neutral_target_stays_pending_without_count():
    """目標仍中立 → 保留待確認，不計擴張。"""
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(20)]
    by_id = {20: SimpleNamespace(owner="NEUTRAL", tower_id=20)}
    ctl._check_pending_captures(by_id, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 0
    assert len(ctl.journal["pending_captures"]) == 1


def test_pending_enemy_target_stays_pending_without_count():
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(20)]
    by_id = {20: SimpleNamespace(owner="OTHER", tower_id=20)}
    ctl._check_pending_captures(by_id, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 0
    assert len(ctl.journal["pending_captures"]) == 1


def test_pending_other_match_dropped_without_count():
    """跨局待確認直接丟棄，不得污染新局計數。"""
    ctl = _fake_controller()
    ctl.journal["pending_captures"] = [_pending(20, match_id="m0")]
    by_id = {20: SimpleNamespace(owner="SELF", tower_id=20)}
    ctl._check_pending_captures(by_id, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 0
    assert ctl.journal["pending_captures"] == []


def test_pending_older_than_1800s_dropped():
    ctl = _fake_controller()
    old = time.time() - 1801
    ctl.journal["pending_captures"] = [_pending(20, since=old)]
    by_id = {20: SimpleNamespace(owner="SELF", tower_id=20)}
    ctl._check_pending_captures(by_id, "m1", time.time())
    assert ctl.journal["verified_expansions"] == 0
    assert ctl.journal["pending_captures"] == []


def test_contested_flow_never_counts_expansion():
    """三次 CONTESTED、零 CAPTURED → verified_expansions 維持 0。

    對應稽核觀察：verified_expansions 只能來自 CAPTURED 或
    待確認轉 SELF，不能來自 CONTESTED。
    """
    expansions = 0
    for _ in range(3):
        before = {"match_id": "m1",
                  "source": {"owner": "SELF", "units": _units(Soldier=12)},
                  "target": {"owner": "NEUTRAL", "units": _units()}}
        after = {"match_id": "m1",
                 "source": {"owner": "SELF", "units": _units()},
                 "target": {"owner": "NEUTRAL",
                            "units": _units(Soldier=4)}}
        verdict = verify_post_action(before, after, _proposal())
        assert verdict == "TARGET_CONTESTED"
        if verdict == "TARGET_CAPTURED":
            expansions += 1
    assert expansions == 0
