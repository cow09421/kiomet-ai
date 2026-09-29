"""真實證據資產化：UNKNOWN dispatch（force_match NOT_FOUND）。

Match m1-1790644011 的真實案例：controller 計入 sent_actions，
但 WASM 中從未出現己方部隊（force_match NOT_FOUND）。
replay 必須標記 DISPATCH_NOT_OBSERVED，不得假裝已觀察。

成功證據：force_observed=DISPATCH_NOT_OBSERVED + flag；
force_identity=UNKNOWN（no-t1-entries）。
失敗證據：NOT_FOUND 被放行或誤判為已觀察。
"""
import json

from kiomet_ai.replay import replay_case

CASE_UNKNOWN = json.loads(r"""{"diff": {"action_id": "m1-1790644011:19988687->19988686:1790644517", "match_id": "m1-1790644011", "source_tower": 19988687, "target_tower": 19988686, "target_type": "Runway", "source_owner": "SELF", "target_owner": "NEUTRAL", "source_owner_id": 71, "target_owner_id": null, "before_attacker": {"Shield": 5, "Fighter": 4, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 0}, "before_defender": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 0}, "after_source": {"Shield": 5, "Fighter": 4, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 0}, "after_target": {"owner": "NEUTRAL", "units": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 0}}, "evaluation_status": "NOT_APPLICABLE_NEUTRAL_TARGET", "evaluation_reason": "target_is_neutral", "prediction": null, "force_match_source": "FORCE_MATCH_NOT_FOUND", "force_match_target": "FORCE_MATCH_NOT_FOUND"}, "bundle": {"action_id": "m1-1790644011:19988687->19988686:1790644517", "match_id": "m1-1790644011", "source": 19988687, "target": 19988686, "t0": {"source": {"tower_ref": 2597240, "match_id": "m1-1790644011", "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}, "target": {"tower_ref": 2597192, "match_id": "m1-1790644011", "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}}, "t1": {"source": {"tower_ref": 2597240, "match_id": "m1-1790644011", "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}, "target": {"tower_ref": 2597192, "match_id": "m1-1790644011", "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}}, "t2": {"source": {"tower_ref": 2597240, "match_id": "m1-1790644011", "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}, "target": {"tower_ref": 2597192, "match_id": "m1-1790644011", "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}}, "t3": {"source": {"tower_ref": 2597240, "match_id": "m1-1790644011", "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 1, "entries": [{"ref": 2969280, "path": [19988688, 19988687], "owner_id": 31, "units": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 4, "Tank": 0, "Soldier": 0, "Shell": 0, "Emp": 0, "Nuke": 0, "Ruler": 0}, "progress": 45}]}}}, "target": {"tower_ref": 2597192, "match_id": "m1-1790644011", "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}}, "force_match_source": "FORCE_MATCH_NOT_FOUND", "force_match_target": "FORCE_MATCH_NOT_FOUND", "sent_actions_context": 2}, "case_id": "m1-1790644011_19988687-_19988686_1790644517"}""")


def test_unknown_dispatch_is_flagged():
    out = replay_case(CASE_UNKNOWN)
    assert out["force_observed"]["status"] == "DISPATCH_NOT_OBSERVED"
    assert out["force_observed"]["reason"] == "force_match_not_found"
    assert "force_observed:DISPATCH_NOT_OBSERVED" in out["flags"]
    assert out["status"] == "FLAGGED"


def test_unknown_dispatch_force_identity_unknown():
    out = replay_case(CASE_UNKNOWN)
    assert out["force_identity"]["status"] == "UNKNOWN"
    assert out["force_identity"]["reason"] == "no-t1-entries"


def test_unknown_dispatch_no_self_id():
    """force_match NOT_FOUND → 無 self_id 證據（不得猜）。"""
    out = replay_case(CASE_UNKNOWN)
    assert out["id_evidence"]["self_id"] is None
