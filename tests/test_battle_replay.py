"""Battle differential replay harness 回歸測試（內嵌 fixture，無 runtime 依賴）。

最後一項 test 會在 runtime 語料存在時重播真實證據（否則 skip）。
"""
import json
from pathlib import Path

import pytest

from kiomet_ai.replay import (derive_id_evidence, load_case, replay_case,
                              replay_corpus)

NAMES = ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier")


def _units(**kw):
    out = {n: 0 for n in NAMES}
    out.update(kw)
    return out


def _diff(**over):
    base = {
        "action_id": "m:1->2:100",
        "match_id": "m",
        "source_tower": 1,
        "target_tower": 2,
        "target_type": "Cliff",
        "source_owner": "SELF",
        "before_attacker": _units(Soldier=12),
        "before_defender": _units(),
        "after_source": _units(Soldier=0),
        "after_target": {"owner": "SELF", "units": _units(Soldier=12)},
        "prediction": None,
    }
    base.update(over)
    return base


def _bundle(**over):
    entry = {"ref": 9, "path": [2, 1], "owner_id": 5,
             "units": _units(Soldier=12), "progress": 10}
    base = {
        "action_id": "m:1->2:100",
        "match_id": "m",
        "force_match_source": "FORCE_MATCH_VERIFIED",
        "force_match_target": "FORCE_MATCH_VERIFIED",
        "t0": {"source": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}},
               "target": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}}},
        "t1": {"source": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": [dict(entry)]}}},
               "target": {"collections": {"inbound": {"entries": [dict(entry)]},
                                          "outbound": {"entries": []}}}},
        "t2": {"source": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}},
               "target": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}}},
        "t3": {"source": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}},
               "target": {"collections": {"inbound": {"entries": []},
                                          "outbound": {"entries": []}}}},
    }
    base.update(over)
    return base


def test_happy_path_replay_verifies_all_stages():
    case = {"case_id": "x", "diff": _diff(), "bundle": _bundle()}
    out = replay_case(case)
    assert out["status"] == "REPLAYED"
    assert out["temporal"]["status"] == "TEMPORAL_OK"
    assert out["force_identity"]["status"] == "IDENTITY_VERIFIED"
    assert out["sent_within"]["status"] == "SENT_WITHIN_AVAILABLE"
    assert out["source_drop"]["status"] == "DROP_MATCHES_SENT"
    assert out["arrival"]["status"] == "ARRIVAL_OBSERVED"
    assert out["id_evidence"]["self_id"] == 5
    assert "verified-dispatch-outbound+12" in out["id_evidence"]["provenance"]


def test_identity_mismatch_flags_case():
    b = _bundle()
    b["t1"]["target"]["collections"]["inbound"]["entries"][0]["units"] = \
        _units(Soldier=7)
    out = replay_case({"case_id": "x", "diff": _diff(), "bundle": b})
    assert out["status"] == "FLAGGED"
    assert out["force_identity"]["status"] == "IDENTITY_MISMATCH"
    assert "force_identity:IDENTITY_MISMATCH" in out["flags"]


@pytest.mark.parametrize("side", ("source", "target"))
def test_duplicate_force_signature_is_not_collapsed_in_identity_check(side):
    b = _bundle()
    duplicate = dict(b["t1"]["source"]["collections"]["outbound"]
                     ["entries"][0])
    duplicate["ref"] = 10
    if side == "source":
        b["t1"]["source"]["collections"]["outbound"][
            "entries"].append(duplicate)
    else:
        b["t1"]["target"]["collections"]["inbound"][
            "entries"].append(duplicate)

    out = replay_case({"case_id": "duplicate", "diff": _diff(),
                       "bundle": b})

    assert out["force_identity"]["status"] == "IDENTITY_MISMATCH"
    assert "force_identity:IDENTITY_MISMATCH" in out["flags"]


def test_drop_exceeds_sent_flags_case():
    below = replay_case({"case_id": "x",
                         "diff": _diff(after_source=_units(Soldier=4)),
                         "bundle": _bundle()})
    # before12-after4=8 < sent12：生產回填不確定，不得假裝匹配
    assert below["source_drop"]["status"] == \
        "DROP_BELOW_SENT_PRODUCTION_UNKNOWN"
    b = _bundle()
    b["t1"]["source"]["collections"]["outbound"]["entries"][0]["units"] = \
        _units(Soldier=5)
    over = replay_case({"case_id": "z",
                        "diff": _diff(after_source=_units()), "bundle": b})
    assert over["source_drop"]["status"] == "DROP_EXCEEDS_SENT"
    assert over["status"] == "FLAGGED"


def test_sent_exceeds_available_flags_case():
    out = replay_case({"case_id": "x",
                       "diff": _diff(before_attacker=_units(Soldier=3)),
                       "bundle": _bundle()})
    assert out["sent_within"]["status"] == "SENT_EXCEEDS_AVAILABLE"
    assert out["status"] == "FLAGGED"


def test_missing_bundle_all_stages_unknown_not_zero():
    out = replay_case({"case_id": "x", "diff": _diff(), "bundle": None})
    assert out["temporal"]["status"] == "UNKNOWN"
    assert out["force_identity"]["status"] == "UNKNOWN"
    assert out["source_drop"]["status"] == "UNKNOWN"
    assert out["id_evidence"]["self_id"] is None
    assert out["status"] == "REPLAYED"  # 未知不是 flag，但也絕不假裝 MATCH


def test_enemy_target_without_ids_skips_battle():
    out = replay_case({"case_id": "x",
                       "diff": _diff(
                           after_target={"owner": "OTHER",
                                         "units": _units(Soldier=2)}),
                       "bundle": None})
    assert out["battle"]["status"] == "SKIPPED_UNKNOWN_IDS"


def test_enemy_target_with_self_id_gets_offline_verdict():
    enemy = {"ref": 11, "path": [2, 3], "owner_id": 17,
             "units": _units(Soldier=8), "progress": 5}
    bundle = _bundle()
    bundle["t1"]["target"]["collections"]["outbound"]["entries"].append(enemy)
    out = replay_case({"case_id": "x",
                       "diff": _diff(
                           before_defender=_units(Soldier=5),
                           after_target={"owner": "OTHER",
                                         "units": _units(Soldier=2)},
                           prediction="SKIPPED_UNKNOWN_IDS"),
                       "bundle": bundle})
    assert out["id_evidence"]["self_id"] == 5
    assert out["battle"]["status"] == "OFFLINE_VERDICT"
    assert out["battle"]["winner"] == "attacker"
    assert out["battle"]["confidence"] == "DERIVED"
    assert ("RUNTIME_SKIPPED_BUT_SELF_ID_VERIFIABLE_FROM_BUNDLE"
            in out["flags"])
    assert out["status"] == "FLAGGED"


def test_match_mismatch_not_replayable():
    out = replay_case({"case_id": "x", "diff": _diff(match_id="m1"),
                       "bundle": _bundle(match_id="m2")})
    assert out["status"] == "NOT_REPLAYABLE"


def test_unverified_bundle_yields_no_id_evidence():
    ev = derive_id_evidence(
        _bundle(force_match_source="FORCE_MATCH_DERIVED"), _diff())
    assert ev["self_id"] is None
    assert ev["observed_owner_ids"] == []


def test_temporal_anomaly_flags_case():
    b = _bundle()
    b["t2"]["source"]["collections"]["outbound"]["entries"] = [
        {"ref": 10, "path": [2, 1], "owner_id": 5,
         "units": _units(Soldier=12), "progress": 90}]
    out = replay_case({"case_id": "x", "diff": _diff(), "bundle": b})
    assert out["temporal"]["status"] == "TEMPORAL_ANOMALY"
    assert out["status"] == "FLAGGED"


def test_real_corpus_replay_if_present():
    root = Path(__file__).resolve().parents[1] / \
        "runtime/research/pvp_validation"
    if not root.is_dir() or not any(root.glob("*/battle-differential.json")):
        pytest.skip("runtime corpus not present")
    report = replay_corpus(root)
    assert report["summary"]["cases"] >= 1
    # 真實語料：self-id-001 證據指出 match m1-1790631842 SELF=5
    assert 5 in report["summary"]["self_ids_found"]
    # 未知絕不變 0：SKIPPED/UNKNOWN 類判定不得輸出虛構 winner
    for c in report["cases"]:
        assert c.get("battle", {}).get("winner") is None
