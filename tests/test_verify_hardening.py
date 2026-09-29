"""verify_post_action 誤判成功硬化回歸測試（§32 P0-B）。

成功不得只憑 force_observed：DERIVED、錯方向、錯 action_id、
非 OK 時序、UNKNOWN 來源一律不得拿到 FORCE_OBSERVED。
"""
from kiomet_ai.proposal import (ActionProposal, PROPOSAL_READY,
                                verify_post_action)


def proposal():
    return ActionProposal(
        match_id="m1", created_at=100.0,
        source_tower_id=10, target_tower_id=20,
        path=(10, 20), path_length=1,
        status=PROPOSAL_READY)


def before():
    return {"match_id": "m1",
            "source": {"owner": "SELF", "units": {"Soldier": 12}},
            "target": {"owner": "NEUTRAL", "units": {"Soldier": 0}}}


def after(**over):
    base = {"match_id": "m1",
            "source": {"owner": "SELF", "units": {"Soldier": 0}},
            "target": {"owner": "NEUTRAL", "units": {"Soldier": 0}},
            "force_observed": True,
            "force_match": "FORCE_MATCH_VERIFIED",
            "force_match_target": "FORCE_MATCH_VERIFIED"}
    base.update(over)
    return base


def test_verified_force_with_bindings_is_credited():
    a = after(force_path=(10, 20),
              action_id="m1:10->20:1790000000",
              temporal_status="TEMPORAL_OK",
              action_origin="LIVE_CONTROLLER")
    assert verify_post_action(before(), a, proposal()) == "FORCE_OBSERVED"


def test_derived_force_match_is_not_credited():
    a = after(force_match="FORCE_MATCH_DERIVED")
    # 目標未變（target 相同）→ 落到 SOURCE_CHANGED 而非 FORCE_OBSERVED
    b = before()
    a["target"] = b["target"]
    a["source"] = b["source"]
    assert verify_post_action(b, a, proposal()) != "FORCE_OBSERVED"


def test_wrong_direction_force_path_is_not_credited():
    a = after(force_path=(20, 10), action_origin="LIVE_CONTROLLER")
    b = before()
    a["target"] = b["target"]
    a["source"] = b["source"]
    assert verify_post_action(b, a, proposal()) != "FORCE_OBSERVED"


def test_foreign_action_id_is_not_credited():
    a = after(action_id="m1:99->20:1790000000")
    b = before()
    a["target"] = b["target"]
    a["source"] = b["source"]
    assert verify_post_action(b, a, proposal()) != "FORCE_OBSERVED"


def test_temporal_anomaly_is_not_credited():
    a = after(temporal_status="TEMPORAL_ANOMALY")
    b = before()
    a["target"] = b["target"]
    a["source"] = b["source"]
    assert verify_post_action(b, a, proposal()) != "FORCE_OBSERVED"


def test_unknown_origin_is_not_credited():
    a = after(action_origin="UNKNOWN")
    b = before()
    a["target"] = b["target"]
    a["source"] = b["source"]
    assert verify_post_action(b, a, proposal()) != "FORCE_OBSERVED"


def test_capture_still_wins_before_force_gate():
    a = after(target={"owner": "SELF", "units": {"Soldier": 12}},
              force_match="FORCE_MATCH_DERIVED")
    assert verify_post_action(before(), a, proposal()) == "TARGET_CAPTURED"


def test_legacy_after_without_bindings_keeps_old_behavior():
    b = before()
    a = {"match_id": "m1",
         "source": {"owner": "SELF", "units": {"Soldier": 0}},
         "target": b["target"],
         "force_observed": True}
    assert verify_post_action(b, a, proposal()) == "FORCE_OBSERVED"


def test_no_force_and_no_change_is_unknown():
    b = before()
    a = {"match_id": "m1", "source": b["source"], "target": b["target"]}
    assert verify_post_action(b, a, proposal()) == "UNKNOWN"


def reinforce_proposal():
    return ActionProposal(
        match_id="m1", created_at=100.0,
        source_tower_id=10, target_tower_id=20,
        path=(10, 20), path_length=1,
        status=PROPOSAL_READY, action_kind="REINFORCE_SELF")


def reinforce_before():
    return {"match_id": "m1",
            "source": {"owner": "SELF", "units": {"Soldier": 12}},
            "target": {"owner": "SELF", "units": {"Soldier": 5}}}


def test_reinforce_self_staying_self_is_never_captured():
    """己方增援後目標仍 SELF → 絕非 TARGET_CAPTURED。"""
    a = {"match_id": "m1",
         "source": {"owner": "SELF", "units": {"Soldier": 8}},
         "target": {"owner": "SELF", "units": {"Soldier": 9}},
         "force_observed": True,
         "force_match": "FORCE_MATCH_VERIFIED",
         "force_match_target": "FORCE_MATCH_VERIFIED",
         "force_path": (10, 20),
         "action_id": "m1:10->20:1790000000",
         "temporal_status": "TEMPORAL_OK",
         "action_origin": "LIVE_CONTROLLER"}
    assert verify_post_action(
        reinforce_before(), a, reinforce_proposal()) == "FORCE_OBSERVED"


def test_reinforce_self_lost_target_is_contested():
    a = {"match_id": "m1",
         "source": {"owner": "SELF", "units": {"Soldier": 8}},
         "target": {"owner": "OTHER", "units": {"Soldier": 4}}}
    assert verify_post_action(
        reinforce_before(), a, reinforce_proposal()) == "TARGET_CONTESTED"


def test_reinforce_self_without_force_evidence_is_unknown():
    b = reinforce_before()
    a = {"match_id": "m1", "source": b["source"], "target": b["target"]}
    assert verify_post_action(b, a, reinforce_proposal()) == "UNKNOWN"
