"""重播階段分支覆蓋（覆蓋率稽核補齊）。

鎖定既有測試未觸及的分支：
TEMPORAL_NO_FORCE、ARRIVAL_NOT_OBSERVED、SOURCE_REGAINED、
NOT_VERIFIED、單側 t1、bundle 缺失、向量缺失、sent 缺失。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.replay import (_check_arrival, _check_force_identity,
                              _check_force_observed, _check_sent_within,
                              _check_source_drop, _check_temporal,
                              derive_id_evidence)


def _units(**kw):
    out = {n: 0 for n in ("Shield", "Fighter", "Chopper", "Bomber",
                          "Tank", "Soldier")}
    out.update(kw)
    return out


def _coll(entries):
    return {"entries": entries}


def _stage(source_out=(), source_in=(), target_out=(), target_in=()):
    return {"source": {"collections": {
                "outbound": _coll(list(source_out)),
                "inbound": _coll(list(source_in))}},
            "target": {"collections": {
                "outbound": _coll(list(target_out)),
                "inbound": _coll(list(target_in))}}}


def _entry(**over):
    base = {"ref": 9, "path": [2, 1], "owner_id": 5,
            "units": _units(Soldier=12), "progress": 10}
    base.update(over)
    return base


def _empty_bundle(**over):
    base = {"action_id": "m:1->2:100", "match_id": "m",
            "force_match_source": "FORCE_MATCH_VERIFIED",
            "force_match_target": "FORCE_MATCH_VERIFIED",
            "t0": _stage(), "t1": _stage(),
            "t2": _stage(), "t3": _stage()}
    base.update(over)
    return base


def test_temporal_no_force_when_t1_empty():
    bundle = _empty_bundle()
    out = _check_temporal(bundle)
    assert out["status"] == "TEMPORAL_NO_FORCE"
    assert out["counts"] == [0, 0, 0, 0]


def test_temporal_bundle_missing_is_unknown():
    out = _check_temporal(None)
    assert out == {"status": "UNKNOWN", "reason": "bundle-missing"}
    out = _check_force_identity(None)
    assert out == {"status": "UNKNOWN", "reason": "bundle-missing"}
    out = _check_force_observed(None, 5)
    assert out == {"status": "UNKNOWN", "reason": "bundle-missing"}


def test_one_sided_t1_identity_mismatch():
    bundle = _empty_bundle()
    bundle["t1"] = _stage(source_out=[_entry()])
    out = _check_force_identity(bundle)
    assert out["status"] == "IDENTITY_MISMATCH"
    assert out["reason"] == "one-sided t1 entries"
    assert out["outbound"] == 1 and out["inbound"] == 0


def test_arrival_not_observed_when_target_short():
    diff = {"after_target": {"owner": "NEUTRAL",
                             "units": _units(Soldier=3)}}
    bundle = _empty_bundle()
    bundle["t1"] = _stage(source_out=[_entry()])
    out = _check_arrival(diff, bundle)
    assert out["status"] == "ARRIVAL_NOT_OBSERVED"
    assert out["short"] == ["Soldier"]


def test_source_regained_when_after_exceeds_before():
    diff = {"before_attacker": _units(Soldier=12),
            "after_source": _units(Soldier=15)}
    bundle = _empty_bundle()
    bundle["t1"] = _stage(source_out=[_entry()])
    out = _check_source_drop(diff, bundle)
    assert out["status"] == "SOURCE_REGAINED"
    assert out["drop"]["Soldier"] == -3


def test_vectors_unavailable_without_before_attacker():
    diff = {"after_source": _units(), "after_target": {
        "owner": "NEUTRAL", "units": _units()}}
    bundle = _empty_bundle()
    bundle["t1"] = _stage(source_out=[_entry()])
    assert _check_sent_within(diff, bundle)["status"] == "UNKNOWN"
    assert _check_sent_within(diff, bundle)["reason"] == \
        "vectors-unavailable"
    assert _check_source_drop(diff, bundle)["status"] == "UNKNOWN"


def test_bundle_sent_unavailable_when_no_t1_outbound():
    diff = {"before_attacker": _units(Soldier=12),
            "after_source": _units(Soldier=12)}
    out = _check_source_drop(diff, _empty_bundle())
    assert out["status"] == "UNKNOWN"
    assert out["reason"] == "bundle-sent-unavailable"
    assert out["drop"]["Soldier"] == 0


def test_not_verified_bundle_yields_no_ids():
    bundle = _empty_bundle(force_match_source="DERIVED",
                           force_match_target="FORCE_MATCH_VERIFIED")
    out = derive_id_evidence(bundle, {"source_owner": "SELF"})
    assert out["self_id"] is None
    assert out["sources"][0]["status"] == "NOT_VERIFIED"
    assert out["observed_owner_ids"] == []
