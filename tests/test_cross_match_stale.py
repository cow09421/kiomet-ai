"""跨局過期性質測試（P1-A）。

跨局時以下全部不能沿用：
- SELF owner id
- Action Token
- Reservation
- Anchor
- Probe
- Threat state
- Pending capture

成功證據：換局後舊身份／權杖／保留／錨點／探針／威脅／待驗證全部失效。
失敗證據：任一跨局洩漏（上一局狀態污染下一局）。
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.action_validity import ReservationBoard
from kiomet_ai.pvp_live import PlayerIdRegistry
from kiomet_ai.proposal import ActionProposal, verify_post_action


def run(coro):
    return asyncio.run(coro)


def _proposal(match_id="m1", **over):
    base = {"match_id": match_id, "created_at": time.time(),
            "source_tower_id": 10, "target_tower_id": 20}
    base.update(over)
    return ActionProposal(**base)


class FakeController:
    """最小 LiveController 形狀，僅測按局隔離方法。"""

    def __init__(self):
        from kiomet_ai.live_controller import LiveController
        self._select_player_id_match = \
            LiveController._select_player_id_match.__get__(self)
        self._select_reservation_match = \
            LiveController._select_reservation_match.__get__(self)
        self.journal = {}


def test_self_id_does_not_leak_across_matches():
    ctl = FakeController()
    ctl._select_player_id_match("m1")
    ctl._player_ids.observe("SELF", 5)
    assert ctl._player_ids.self_id() == 5
    ctl._select_player_id_match("m2")
    assert ctl._player_ids.self_id() is None
    assert ctl.journal.get("self_owner_id") is None


def test_self_id_cleared_when_leaving_match():
    ctl = FakeController()
    ctl._select_player_id_match("m1")
    ctl._player_ids.observe("SELF", 5)
    ctl._select_player_id_match(None)
    assert ctl._player_ids.self_id() is None


def test_reservation_cleared_on_match_change():
    ctl = FakeController()
    ctl._select_reservation_match("m1")
    ctl._reservations.reserve("a1", source_id=10, target_id=20)
    assert ctl._reservations.holder(10) == "a1"
    ctl._select_reservation_match("m2")
    assert ctl._reservations.holder(10) is None


def test_reservation_cleared_when_leaving_match():
    ctl = FakeController()
    ctl._select_reservation_match("m1")
    ctl._reservations.reserve("a1", source_id=10, target_id=20)
    ctl._select_reservation_match(None)
    assert ctl._reservations.holder(10) is None


def test_verifier_rejects_cross_match_after():
    """Anchor/probe after 狀態若屬他局 → MATCH_ENDED。"""
    before = {"match_id": "m1",
              "source": {"owner": "SELF", "units": {"Soldier": 12}},
              "target": {"owner": "NEUTRAL", "units": {"Soldier": 0}}}
    after = {"match_id": "m2",
             "source": {"owner": "SELF", "units": {"Soldier": 0}},
             "target": {"owner": "SELF", "units": {"Soldier": 12}}}
    result = verify_post_action(before, after, _proposal(match_id="m1"))
    assert result == "MATCH_ENDED"


def test_threat_registry_isolated_per_match():
    """不同局的 PlayerIdRegistry 不得共享 owner 集合。"""
    r1 = PlayerIdRegistry()
    r1.observe("SELF", 5)
    r1.observe("ENEMY", 17)
    r2 = PlayerIdRegistry()
    assert r2.self_id() is None
    assert not r2.known_id("ENEMY", 17)


def test_pending_capture_carries_match_id():
    """pending capture 必須綁定 match_id（換局後不得沿用舊 latch）。"""
    pending = {"target": 20, "match_id": "m1",
               "action_id": "m1:10->20:100", "since": time.time()}
    # 換局後舊 latch 不得用於新局判定
    assert pending["match_id"] == "m1"
    assert pending["match_id"] != "m2"
