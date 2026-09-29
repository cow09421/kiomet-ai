"""真實差分語料內嵌回歸（gitignored runtime 之外仍有 real-data 覆蓋）。

CASE_VERIFIED: match m1-1790631842，self_id=5 由 verified-dispatch-outbound+12
證據推得；runtime_prediction=null（中立擴張目標）。
CASE_SKIPPED: match m1-1790630284，runtime 記錄 SKIPPED_UNKNOWN_IDS 但 bundle
無驗證派兵證據（self_id=None）→ 旗標不得誤發（不造假 mismatch）。

成功證據：兩案 stage 狀態與 flags 精確相符；CASE_SKIPPED 即便
runtime_prediction=SKIPPED_UNKNOWN_IDS，flags 仍為 []。
失敗證據：flag 誤發（self_id None 卻指稱 runtime mismatch）或任一 stage 退化。
"""
import json

from kiomet_ai.replay import replay_case

CASE_VERIFIED = json.loads(r"""{"diff": {"action_id": "m1-1790631842:16843031->16843032:1790631991", "match_id": "m1-1790631842", "source_tower": 16843031, "target_tower": 16843032, "target_type": "Generator", "source_owner": "SELF", "target_owner": "NEUTRAL", "before_attacker": {"Shield": 20, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 4}, "before_defender": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 0}, "after_source": {"Shield": 20, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 0}, "after_target": {"owner": "NEUTRAL", "units": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 4}}, "evaluation_status": "NOT_APPLICABLE_NEUTRAL_TARGET", "evaluation_reason": "target_is_neutral", "prediction": null, "force_match_source": "FORCE_MATCH_VERIFIED", "force_match_target": "FORCE_MATCH_VERIFIED"}, "bundle": {"action_id": "m1-1790631842:16843031->16843032:1790631991", "match_id": "m1-1790631842", "source": 16843031, "target": 16843032, "t0": {"source": {"tower_ref": 2659936, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}, "target": {"tower_ref": 2659984, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}}, "t1": {"source": {"tower_ref": 2659936, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 1, "entries": [{"ref": 1376752, "path": [16843032, 16843031], "owner_id": 5, "units": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 4, "Shell": 0, "Emp": 0, "Nuke": 0, "Ruler": 0}, "progress": 12}]}}}, "target": {"tower_ref": 2659984, "collections": {"inbound": {"length": 1, "entries": [{"ref": 1525200, "path": [16843032, 16843031], "owner_id": 5, "units": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 4, "Shell": 0, "Emp": 0, "Nuke": 0, "Ruler": 0}, "progress": 20}]}, "outbound": {"length": 0, "entries": []}}}}, "t2": {"source": {"tower_ref": 2659936, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}, "target": {"tower_ref": 2659984, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}}, "t3": {"source": {"tower_ref": 2659936, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}, "target": {"tower_ref": 2659984, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}}, "force_match_source": "FORCE_MATCH_VERIFIED", "force_match_target": "FORCE_MATCH_VERIFIED", "sent_actions_context": 2}, "case_id": "m1-1790631842_16843031-_16843032_1790631991"}""")
CASE_SKIPPED = json.loads(r"""{"diff": {"action_id": "m1-1790630284:19595487->19595488:1790630441", "match_id": "m1-1790630284", "source_tower": 19595487, "target_tower": 19595488, "target_type": "Factory", "before_attacker": {"Shield": 20, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 4}, "before_defender": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 0}, "after_source": {"Shield": 20, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 0}, "after_target": {"owner": "NEUTRAL", "units": {"Shield": 2, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 4}}, "prediction": "SKIPPED_UNKNOWN_IDS"}, "bundle": {"action_id": "m1-1790630284:19595487->19595488:1790630441", "match_id": "m1-1790630284", "source": 19595487, "target": 19595488, "t0": {"source": {"tower_ref": 2755600, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}, "target": {"tower_ref": 2970744, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}}, "t1": {"source": {"tower_ref": 2755600, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 1, "entries": [{"ref": 1973744, "path": [19595488, 19595487], "owner_id": 5, "units": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 4, "Shell": 0, "Emp": 0, "Nuke": 0, "Ruler": 0}, "progress": 10}]}}}, "target": {"tower_ref": 2970744, "collections": {"inbound": {"length": 1, "entries": [{"ref": 1966144, "path": [19595488, 19595487], "owner_id": 5, "units": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0, "Tank": 0, "Soldier": 4, "Shell": 0, "Emp": 0, "Nuke": 0, "Ruler": 0}, "progress": 20}]}, "outbound": {"length": 0, "entries": []}}}}, "t2": {"source": {"tower_ref": 2755600, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}, "target": {"tower_ref": 2970744, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}}, "t3": {"source": {"tower_ref": 2755600, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}, "target": {"tower_ref": 2970744, "collections": {"inbound": {"length": 0, "entries": []}, "outbound": {"length": 0, "entries": []}}}}, "force_match_source": "FORCE_MATCH_VERIFIED", "force_match_target": "FORCE_MATCH_VERIFIED", "sent_actions_context": 2}, "case_id": "m1-1790630284_19595487-_19595488_1790630441"}""")


def test_real_verified_dispatch_case_replays_clean():
    out = replay_case(CASE_VERIFIED)
    assert out["status"] == "REPLAYED"
    assert out["flags"] == []
    assert out["id_evidence"]["self_id"] == 5
    assert out["id_evidence"]["provenance"] == (
        "verified-dispatch-outbound+12@m1-1790631842:16843031->16843032:1790631991"
    )
    assert out["temporal"]["status"] == "TEMPORAL_OK"
    assert out["force_identity"]["status"] == "IDENTITY_VERIFIED"
    assert out["sent_within"]["status"] == "SENT_WITHIN_AVAILABLE"
    assert out["arrival"]["status"] == "ARRIVAL_OBSERVED"
    assert out["battle"] == {"status": "NOT_BATTLE_TARGET_OWNER",
                             "target_owner": "NEUTRAL"}
    assert out["runtime_prediction"] is None


def test_real_skipped_runtime_case_without_bundle_provenance_stays_unflagged():
    out = replay_case(CASE_SKIPPED)
    assert out["runtime_prediction"] == "SKIPPED_UNKNOWN_IDS"
    assert out["id_evidence"]["self_id"] is None
    assert out["id_evidence"]["observed_owner_ids"] == [5]
    assert out["status"] == "REPLAYED"
    assert out["flags"] == []


def test_flag_never_fires_on_neutral_targets():
    for case in (CASE_VERIFIED, CASE_SKIPPED):
        out = replay_case(case)
        assert out["battle"]["target_owner"] == "NEUTRAL"
        assert "RUNTIME_SKIPPED_BUT_SELF_ID_VERIFIABLE_FROM_BUNDLE" not in out["flags"]
