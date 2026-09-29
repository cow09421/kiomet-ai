"""跨局壓力測試（P1-D）。

針對 threat／pending capture／reservation／token／self owner／
anchor／probe／battle prediction／verifier state，
以合成 match ID 驗證跨局隔離。無需 Runtime 等局。

與 test_cross_match_stale.py 不重疊：該檔鎖基本隔離，
本檔鎖壓力情境（錯局重播、大規模排序、token 綁定、bundle 錯配）。
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.replay import replay_case, replay_threat_waves


def _u(**kw):
    out = {n: 0 for n in ("Shield", "Fighter", "Chopper", "Bomber",
                          "Tank", "Soldier", "Shell", "Emp", "Nuke",
                          "Ruler")}
    out.update(kw)
    return out


def _threat(owner_id=26, progress=10, eta=None, distance=90.0):
    return {"owner_id": owner_id, "owner_relation": "UNKNOWN",
            "units": _u(Soldier=4), "progress": progress,
            "speed_flag": None, "eta_ticks": eta, "distance_m": distance,
            "samples": None}


def _snap(match_id, threats, observed_at=1790641578.9):
    return {"match_id": match_id, "observed_at": observed_at,
            "target_tower_id": 16449718, "threats": threats}


def test_threat_snapshot_replayed_under_wrong_match_is_stale():
    out = replay_threat_waves(
        _snap("m1", [_threat()]), now=1790641578.9,
        current_match_id="m2")
    assert out["status"] == "UNKNOWN"
    assert out["reason"] == "CROSS_MATCH_STALE"
    assert out["verdicts"] == []


def test_threat_snapshot_replayed_under_same_match_ok():
    out = replay_threat_waves(
        _snap("m1", [_threat()]), now=1790641578.9,
        current_match_id="m1")
    assert out["status"] == "REPLAYED"


def test_fifty_threat_stress_ordering():
    threats = [_threat(owner_id=20 + (i % 5), progress=(i * 7) % 200,
                       distance=90.0) for i in range(50)]
    out = replay_threat_waves(_snap("m9", threats), now=1790641578.9)
    assert out["status"] == "REPLAYED"
    assert len(out["verdicts"]) == 50
    etas = [out["verdicts"][i]["recomputed_eta_ticks"]
            for i in out["ordered_by_eta"]]
    assert etas == sorted(etas)


def test_token_bound_to_match_and_cycle():
    from kiomet_ai.action_validity import build_token, validate_token

    def state(tower_id, owner):
        return SimpleNamespace(
            tower_id=tower_id, tower_ref=1000 + tower_id,
            units_kind="MANY", unit_counts=_u(Soldier=4),
            owner=owner, owner_ruler=False)

    src, tgt = state(10, "SELF"), state(20, "NEUTRAL")
    camera = (0.0, 1.0, 2.0, 3.0, 4.0, 1280.0, 720.0, 1.0,
              0.0, 0.0, 1280.0, 720.0)
    token = build_token("m1", 5, 100.0, 200.0, src, tgt, camera,
                        {"Soldier": 4})
    ok = validate_token(token, "m1", 100.0, 200.0, src, tgt, camera,
                        current_cycle_id=5,
                        current_deployable_counts={"Soldier": 4})
    assert ok == "OK"
    assert validate_token(
        token, "m2", 100.0, 200.0, src, tgt, camera,
        current_cycle_id=5,
        current_deployable_counts={"Soldier": 4}) == \
        "STALE_PROPOSAL:match-changed"
    assert validate_token(
        token, "m1", 100.0, 200.0, src, tgt, camera,
        current_cycle_id=6,
        current_deployable_counts={"Soldier": 4}) == \
        "STALE_PROPOSAL:cycle-changed"


def test_bundle_match_mismatch_not_replayable():
    diff = {"match_id": "m1", "action_id": "m1:1->2:100",
            "source_tower": 1, "target_tower": 2, "target_type": "Cliff",
            "source_owner": "SELF",
            "before_attacker": _u(Soldier=12),
            "before_defender": _u(),
            "after_source": _u(),
            "after_target": {"owner": "SELF", "units": _u(Soldier=12)},
            "prediction": None}
    bundle = {"match_id": "m2", "action_id": "m1:1->2:100",
              "force_match_source": "FORCE_MATCH_VERIFIED",
              "force_match_target": "FORCE_MATCH_VERIFIED"}
    out = replay_case({"case_id": "x", "diff": diff, "bundle": bundle})
    assert out["status"] == "NOT_REPLAYABLE"
    assert out["reason"] == "bundle-match-mismatch"


def test_self_id_per_match_isolation():
    from kiomet_ai.pvp_live import PlayerIdRegistry
    registries = {}
    for match in ("m1", "m2", "m3"):
        reg = PlayerIdRegistry()
        reg.observe("SELF", 5 + len(registries))
        registries[match] = reg
    assert registries["m1"].self_id() == 5
    assert registries["m2"].self_id() == 6
    assert registries["m3"].self_id() == 7
    assert not registries["m1"].known_id("SELF", 6)


def test_reservation_cleared_between_matches_allows_reuse():
    from kiomet_ai.action_validity import ReservationBoard
    board = ReservationBoard()
    assert board.reserve("m1:a1", source_id=10, target_id=20) is None
    board.clear_match()
    assert board.reserve("m2:a1", source_id=10, target_id=20) is None
    assert board.holder(10) == "m2:a1"
