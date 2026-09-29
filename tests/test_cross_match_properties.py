"""跨局過期性質測試（§12F）。

以隨機案例驗證新模組的安全不變式：
- 別局資料永不 LIVE
- NEXT ACTION 在跨局／非 IN_MATCH／斷線時永不 READY
- 所有者計數自洽
- 觀戰相機未同局 VERIFIED 時永不可用
超過 100 個隨機案例。
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.dashboard_truth import classify_field, next_action_status
from kiomet_ai.spectator import SpectatorCamera
from kiomet_ai.tactical_world import build_tactical

MATCHES = ["m1", "m2", None]
STATES = ["IN_MATCH", "MENU", "JOINING", "RESULT_SCREEN", "DISCONNECTED",
          "UNKNOWN"]
OWNERS = ["SELF", "NEUTRAL", "ENEMY", "ALLY", "UNKNOWN"]


def test_field_never_live_for_other_match_200_cases():
    rng = random.Random(1234)
    for _ in range(200):
        current = rng.choice(["m1", "m2"])
        data = rng.choice(MATCHES)
        label = classify_field(
            browser_connected=True, game_state="IN_MATCH",
            current_match_id=current, data_match_id=data,
            data_age_s=rng.choice([1, 5, 100, None]))
        if data is not None and data != current:
            assert label != "LIVE", (current, data, label)


def test_next_action_never_ready_across_mismatch_200_cases():
    rng = random.Random(99)
    for _ in range(200):
        current = rng.choice(["m1", "m2"])
        game_state = rng.choice(STATES)
        connected = rng.choice([True, False])
        proposal_match = rng.choice(MATCHES)
        status = next_action_status(
            browser_connected=connected, game_state=game_state,
            current_match_id=current, proposal={"s": 1},
            proposal_match_id=proposal_match,
            proposal_cycle=rng.choice([1, 2, None]),
            current_cycle=rng.choice([1, 3, None]),
            proposal_age_s=rng.choice([1, 99, None]))
        if not connected:
            assert status == "OFFLINE"
        elif game_state != "IN_MATCH" or current is None:
            assert status == "NO_ACTIVE_MATCH"
        elif proposal_match not in (None, current):
            assert status == "LAST_MATCH"
        else:
            assert status != "LAST_MATCH"


def test_tactical_owner_counts_consistent_150_cases():
    rng = random.Random(7)
    for _ in range(150):
        towers = []
        for i in range(rng.randint(0, 12)):
            tower = {"id": i, "x": i, "y": i}
            if rng.random() < 0.8:
                tower["owner"] = rng.choice(OWNERS)
            towers.append(tower)
        result = build_tactical({"match_id": "m1", "towers": towers})
        # 未知所有者可能不列入計數（GPT PVP-TACTICAL-UNKNOWN-COUNTS），
        # 故只驗證：鍵合法、非負、不超過塔數。
        assert set(result["owners"]) <= set(OWNERS)
        assert all(v is None or v >= 0 for v in result["owners"].values())
        assert sum(v for v in result["owners"].values()
                   if isinstance(v, int)) <= len(result["towers"])
        for t in result["towers"]:
            assert t["owner"] in OWNERS


def test_tactical_routes_only_self_initiated_120_cases():
    rng = random.Random(55)
    for _ in range(120):
        src_owner = rng.choice(OWNERS)
        tgt_owner = rng.choice(OWNERS)
        towers = [{"id": 1, "owner": src_owner}, {"id": 2, "owner": tgt_owner}]
        result = build_tactical({"match_id": "m1", "towers": towers,
                                 "last_action": {"source": 1, "target": 2}})
        fired = [k for k in ("ATTACK", "REINFORCE", "EXPAND")
                 if result["routes"][k]]
        if src_owner not in ("SELF", "ALLY"):
            assert fired == []


def test_spectator_never_available_without_verified_120_cases():
    rng = random.Random(3)
    for _ in range(120):
        same = rng.choice(["VERIFIED", "BLOCKED", "UNKNOWN"])
        driver = rng.choice([True, False])
        cam = SpectatorCamera(driver=(lambda **k: True) if driver else None,
                              camera_driver_available=driver,
                              same_match=same)
        if same != "VERIFIED" or not driver:
            assert cam.available is False
        for op in (lambda: cam.pan(5, 5), lambda: cam.zoom(target=2.0)):
            r = op()
            if not cam.available:
                assert r["ok"] is False
                assert r["applied"] is False
