"""戰鬥證據驗證器不把缺證據或未評估結果標成通過。"""
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from validate_combat_evidence import validate_bundle, validate_document  # noqa: E402


def _binding(action_id="match-A:101->202:1000", *, source=101, target=202,
             cycle=7, reservation="reservation-7"):
    return {
        "action_id": action_id, "match_id": "match-A", "cycle_id": cycle,
        "source_tower_id": source, "target_tower_id": target,
        "action_kind": "ATTACK_ENEMY", "source_owner": "SELF",
        "target_owner": "ENEMY", "route": [source, target],
        "world_hash": "world-7", "proposal_version": "proposal-7",
        "token_version": "token-7", "reservation_id": reservation,
        "dispatched_at": 1000.0,
    }


def _stage(binding, timestamp, *, cycle=7, **extra):
    return {
        "action_id": binding["action_id"],
        "match_id": binding["match_id"],
        "cycle_id": cycle,
        "source_tower_id": binding["source_tower_id"],
        "target_tower_id": binding["target_tower_id"],
        "captured_at": timestamp,
        **extra,
    }


def _bundle(action_id="match-A:101->202:1000", *, source=101, target=202,
            reservation="reservation-7"):
    binding = _binding(action_id, source=source, target=target,
                       reservation=reservation)
    stages = {
        "t_minus_2": _stage(binding, 990.0, cycle=5),
        "t_minus_1": _stage(binding, 995.0, cycle=6),
        "t0": _stage(binding, 999.0, source_owner="SELF",
                     target_owner="ENEMY"),
        "pre_dispatch": _stage(binding, 999.5, source_owner="SELF",
                                target_owner="ENEMY"),
        "dispatch": {"action_id": action_id, "match_id": "match-A",
                     "cycle_id": 7, "sent_at": 1000.0},
        "post_dispatch": _stage(binding, 1001.0),
        "moving": _stage(binding, 1003.0, cycle=8),
        "arrival": _stage(binding, 1005.0, cycle=8,
                           target_force_match="FORCE_MATCH_VERIFIED"),
        "battle": _stage(binding, 1006.0, cycle=8,
                         evaluation_status="RUNTIME_DIFFERENTIAL"),
        "verdict": {"action_id": action_id, "match_id": "match-A",
                    "cycle_id": 8, "observed_at": 1007.0,
                    "verifier": "TARGET_CAPTURED"},
        "t_plus_1": _stage(binding, 1008.0, cycle=9),
        "t_plus_2": _stage(binding, 1009.0, cycle=10),
        "post_state": _stage(binding, 1010.0, cycle=10,
                             source_owner="SELF", target_owner="SELF"),
    }
    return {"case_type": "ACTION", "action_kind": "ATTACK_ENEMY",
            "binding": binding, "stages": stages,
            "collection_status": "COLLECTED", "proof_status": "NOT_EVALUATED"}


def test_complete_bundle_passes_integrity_without_claiming_battle_proof(tmp_path):
    result = validate_bundle(_bundle(), tmp_path)

    assert result["status"] == "PASS"
    assert result["proof_status"] == "NOT_EVALUATED"
    assert result["missing"] == []
    assert result["issues"] == []


def test_missing_arrival_battle_or_post_state_is_partial_never_pass(tmp_path):
    bundle = _bundle()
    bundle["stages"].pop("arrival")
    bundle["stages"].pop("battle")
    bundle["stages"].pop("post_state")

    result = validate_bundle(bundle, tmp_path)

    assert result["status"] == "PARTIAL"
    assert {"arrival", "battle", "post_state"}.issubset(result["missing"])


def test_rejects_cross_match_action_and_owner_conflicts(tmp_path):
    bundle = _bundle()
    bundle["stages"]["arrival"]["match_id"] = "match-B"
    bundle["stages"]["battle"]["action_id"] = "other-action"
    bundle["binding"]["target_owner"] = "SELF"

    result = validate_bundle(bundle, tmp_path)

    assert result["status"] == "FAIL"
    codes = {item["code"] for item in result["issues"]}
    assert "cross-match-stage" in codes
    assert "cross-action-stage" in codes
    assert "action-owner-relation-conflict" in codes


def test_route_endpoints_must_match_source_and_target(tmp_path):
    bundle = _bundle()
    bundle["binding"]["route"] = [101, 303, 202]
    bundle["binding"]["target_tower_id"] = 204

    result = validate_bundle(bundle, tmp_path)

    assert result["status"] == "FAIL"
    assert any(item["code"] == "invalid-route" for item in result["issues"])


def test_cycle_or_timestamp_reversal_fails_closed(tmp_path):
    bundle = _bundle()
    bundle["stages"]["post_dispatch"]["cycle_id"] = 10
    bundle["stages"]["moving"]["cycle_id"] = 8
    bundle["stages"]["post_dispatch"]["captured_at"] = 998.0

    result = validate_bundle(bundle, tmp_path)

    assert result["status"] == "FAIL"
    codes = {item["code"] for item in result["issues"]}
    assert "cycle-order-reversal" in codes
    assert "timestamp-order-reversal" in codes


def test_stale_or_escaping_evidence_pointer_cannot_pass(tmp_path):
    stale = _bundle()
    stale["stages"]["t0"] = {"source": "runtime/logs/missing.jsonl",
                              "evidence": stale["stages"]["t0"]}

    stale_result = validate_bundle(stale, tmp_path)
    assert stale_result["status"] == "PARTIAL"
    assert any(item["code"] == "stale-evidence-pointer"
               for item in stale_result["issues"])

    escaping = _bundle()
    escaping["stages"]["t0"] = {"source": "runtime/../../outside.json",
                                 "evidence": escaping["stages"]["t0"]}
    escape_result = validate_bundle(escaping, tmp_path)
    assert escape_result["status"] == "FAIL"
    assert any(item["code"] == "evidence-pointer-outside-project"
               for item in escape_result["issues"])


def test_matching_source_pointer_is_verified_against_action_binding(tmp_path):
    source = tmp_path / "runtime/logs/live_actions.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({
        "action_id": "match-A:101->202:1000", "match": "match-A",
        "cycle_id": 7, "source": 101, "target": 202,
    }) + "\n", encoding="utf-8")
    bundle = _bundle()
    bundle["stages"]["dispatch"] = {
        "source": "runtime/logs/live_actions.jsonl",
        "evidence": bundle["stages"]["dispatch"],
    }

    result = validate_bundle(bundle, tmp_path)

    assert result["status"] == "PASS"


def test_duplicate_action_and_reservation_are_report_level_failures(tmp_path):
    first = _bundle()
    duplicate_action = _bundle()
    different_action_same_reservation = _bundle(
        "match-A:103->204:1001", source=103, target=204)
    report = validate_document({"bundles": [
        first, duplicate_action, different_action_same_reservation]}, tmp_path)

    assert report["status"] == "FAIL"
    assert all(case["status"] == "FAIL" for case in report["cases"])
    assert any(item["code"] == "duplicate-action-id"
               for case in report["cases"] for item in case["issues"])
    assert any(item["code"] == "duplicate-reservation-id"
               for case in report["cases"] for item in case["issues"])


def test_unknown_threat_and_empty_report_do_not_pass(tmp_path):
    threat = {
        "case_type": "THREAT", "threat_id": "threat-1",
        "classification": "UNKNOWN",
        "binding": {"match_id": "match-A", "cycle_id": 7,
                    "source_force_id": 44, "source_tower_id": 101,
                    "target_tower_id": 202, "route": [101, 202],
                    "observed_at": 1000.0, "freshness": "UNKNOWN"},
    }
    result = validate_document({"bundles": [threat]}, tmp_path)
    empty = validate_document({"bundles": []}, tmp_path)

    assert result["status"] == "PARTIAL"
    assert result["cases"][0]["status"] == "PARTIAL"
    assert result["proof_status"] == "NOT_EVALUATED"
    assert empty["status"] == "NO_CASES"


def test_existing_arming_output_is_partial_not_pvp_proof(tmp_path):
    report = {"bundles": [_bundle()]}
    report["bundles"][0]["stages"].pop("post_state")

    result = validate_document(report, tmp_path)

    assert result["status"] == "PARTIAL"
    assert result["cases"][0]["proof_status"] == "NOT_EVALUATED"


def test_invalid_duplicate_reservation_or_wrong_dispatch_time_is_rejected(tmp_path):
    bundle = _bundle()
    bundle["binding"]["reservation_id"] = ""
    bundle["stages"]["dispatch"]["sent_at"] = 1001.0

    result = validate_bundle(bundle, tmp_path)

    assert result["status"] == "FAIL"
    codes = {item["code"] for item in result["issues"]}
    assert "dispatch-time-binding-conflict" in codes


def test_non_bundle_document_is_rejected():
    result = validate_document({"unexpected": True})

    assert result["status"] == "FAIL"
    assert result["issues"][0]["code"] == "unsupported-document"
