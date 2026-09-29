"""執行期證據索引回歸（P1-B）。

索引必須 machine-readable：以 match_id／action_id／origin／
verdict 等欄位查詢，不必人工翻 JSON。

成功證據：真實索引含 19 actions、13 differentials、39 bundles、
6 crashes；query 按欄位等值過濾；None 永不匹配。
失敗證據：索引遺漏區段、query 把 UNKNOWN 當成值匹配。
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from evidence_index import build_index, query

def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def synthetic_runtime_root(tmp_path):
    """固定、合成語料；測試資料不是正式對局或攻擊證據。"""
    log = tmp_path / "runtime" / "logs" / "live_actions.jsonl"
    log.parent.mkdir(parents=True)
    actions = []
    for index in range(19):
        actions.append({
            "action_id": f"fixture:{index}",
            "match": "m1-1790644011" if index < 4 else "fixture-match-2",
            "origin": "LIVE_CONTROLLER",
            "verifier": ("TARGET_CONTESTED" if index < 3 else
                         "UNKNOWN" if index == 3 else "FORCE_OBSERVED"),
        })
    log.write_text("".join(json.dumps(row) + "\n" for row in actions),
                   encoding="utf-8")

    validation = tmp_path / "runtime" / "research" / "pvp_validation"
    for index in range(13):
        _write_json(validation / f"case-{index:02d}" /
                    "battle-differential.json", {
                        "action_id": f"fixture:{index}",
                        "match_id": ("m1-1790644011" if index < 4 else
                                     "fixture-match-2"),
                        "after_target": {"owner": "NEUTRAL"},
                    })
    for index in range(5):
        _write_json(validation / f"episode-{index:02d}.json", {
            "episode": f"fixture-episode-{index}",
            "match_id": "fixture-match-2",
        })

    bundles = (tmp_path / "runtime" / "research" / "forces" /
               "autonomous_validation")
    for index in range(39):
        _write_json(bundles / f"bundle-{index:02d}" / "bundle.json", {
            "action_id": f"fixture:{index}",
            "match_id": "fixture-match-2",
        })

    crashes = tmp_path / "runtime" / "research" / "crash" / "incidents"
    for index in range(6):
        _write_json(crashes / f"incident-{index:02d}.json", {
            "incident_id": f"fixture-crash-{index}",
            "match_context": "fixture-match-2",
        })

    _write_json(tmp_path / "runtime" / "state" /
                "live_controller.json", {"journal": {
                    "mode": "SYNTHETIC_FIXTURE",
                    "sent_actions": 4,
                    "verified_moves": 3,
                    "verified_expansions": 2,
                    "failed_actions": 0,
                    "cycles": 19,
                    "recent_cycles": [],
                }})
    return tmp_path


def test_index_covers_all_sections(synthetic_runtime_root):
    index = build_index(synthetic_runtime_root)
    assert len(index["actions"]) == 19
    assert len(index["differentials"]) == 13
    assert len(index["bundles"]) == 39
    assert len(index["crashes"]) == 6
    assert len(index["episodes"]) == 5
    assert index["journal"]["sent_actions"] == 4


def test_query_by_match_and_verdict(synthetic_runtime_root):
    index = build_index(synthetic_runtime_root)
    rows = query(index["actions"], match_id="m1-1790644011",
                 verdict="TARGET_CONTESTED")
    assert len(rows) == 3
    rows = query(index["actions"], match_id="m1-1790644011",
                 verdict="UNKNOWN")
    assert len(rows) == 1


def test_query_by_origin(synthetic_runtime_root):
    index = build_index(synthetic_runtime_root)
    rows = query(index["actions"], origin="LIVE_CONTROLLER")
    assert len(rows) == 19
    rows = query(index["actions"], origin="MANUAL_PROBE")
    assert rows == []


def test_differentials_queryable_by_match(synthetic_runtime_root):
    index = build_index(synthetic_runtime_root)
    rows = query(index["differentials"], match_id="m1-1790644011")
    assert len(rows) == 4


def test_none_filter_never_matches():
    records = [{"action_id": "a1", "verdict": None},
               {"action_id": "a2", "verdict": "TARGET_CONTESTED"}]
    assert query(records, verdict=None) == []
    assert [r["action_id"] for r in query(
        records, verdict="TARGET_CONTESTED")] == ["a2"]


def test_build_index_tolerates_missing_root(tmp_path):
    index = build_index(tmp_path)
    assert index["attack_validation"] == {
        "status": "VALIDATION_PENDING", "attack_actions": 0,
        "validated_actions": 0, "reason": "no_enemy_attack_record"}
    assert index["actions"] == []
    assert index["differentials"] == []
    assert index["bundles"] == []
    assert index["crashes"] == []
    assert index["journal"] == {"mode": None, "sent_actions": None,
                                "verified_moves": None,
                                "verified_expansions": None,
                                "failed_actions": None, "cycles": None,
                                "no_safe_proposals": 0,
                                "abstain_reasons": {},
                                "arbitration_action": None,
                                "arbitration_reason": None,
                                "threat_state_status": None,
                                "threat_state_reason": None,
                                "defense_assessment_status": None,
                                "attack_assessment_status": None,
                                "pending_captures": {"count": 0,
                                                     "targets": [],
                                                     "matches": []},
                                "last_action": None,
                                "last_verification": None}


def test_journal_indexes_abstain_cycles():
    from evidence_index import build_index
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = root / "runtime/state"
        state.mkdir(parents=True)
        journal = {"journal": {"recent_cycles": [
            {"phase": "NO_SAFE_PROPOSAL",
             "no_action_reason": "OTHER_EXPLICIT_REASON"},
            {"phase": "NO_SAFE_PROPOSAL",
             "no_action_reason": "no_candidate"},
            {"phase": "DISPATCHED"},
        ]}}
        (state / "live_controller.json").write_text(
            json.dumps(journal), encoding="utf-8")
        index = build_index(root)
    assert index["journal"]["no_safe_proposals"] == 2
    assert index["journal"]["abstain_reasons"] == {
        "OTHER_EXPLICIT_REASON": 1, "no_candidate": 1}


def test_journal_indexes_arbitration_and_threat_fields():
    from evidence_index import build_index
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = root / "runtime/state"
        state.mkdir(parents=True)
        journal = {"journal": {
            "pvp_arbitration": {"action": "EXPAND_NEUTRAL",
                                "reason": "no projected loss"},
            "threat_state": {"status": "CLEAR", "reason": "complete-empty"},
            "defense_assessment": {"status": "SUPPORTED"},
            "attack_assessment": "not-a-dict"}}
        (state / "live_controller.json").write_text(
            json.dumps(journal), encoding="utf-8")
        index = build_index(root)
    indexed = index["journal"]
    assert indexed["arbitration_action"] == "EXPAND_NEUTRAL"
    assert indexed["arbitration_reason"] == "no projected loss"
    assert indexed["threat_state_status"] == "CLEAR"
    assert indexed["threat_state_reason"] == "complete-empty"
    assert indexed["defense_assessment_status"] == "SUPPORTED"
    assert indexed["attack_assessment_status"] is None


def test_journal_indexes_pending_captures():
    from evidence_index import build_index
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = root / "runtime/state"
        state.mkdir(parents=True)
        journal = {"journal": {"pending_captures": [
            {"target": 20, "match_id": "m1",
             "action_id": "m1:10->20:100", "since": 1000.0},
            {"target": 30, "match_id": "m1",
             "action_id": "m1:10->30:200", "since": 1100.0},
            "malformed-entry",
        ]}}
        (state / "live_controller.json").write_text(
            json.dumps(journal), encoding="utf-8")
        index = build_index(root)
    pending = index["journal"]["pending_captures"]
    assert pending["count"] == 2
    assert pending["targets"] == [20, 30]
    assert pending["matches"] == ["m1"]


def _digest_envelope(payload):
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return {**payload,
            "evidence_id": "sha256:" + hashlib.sha256(encoded).hexdigest()}


def _logged_attack(*, server_relation="ENEMY", server_kind="ATTACK_ENEMY"):
    force = {name: 0 for name in (
        "Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
        "Shell", "Emp", "Nuke", "Ruler")}
    force["Soldier"] = 12
    binding = {
        "match_id": "m1", "cycle_id": 8,
        "source_tower_id": 10, "target_tower_id": 20,
        "attacker_owner_id": 7, "defender_owner_id": 22,
        "target_relation": "ENEMY", "proposed_units": force,
    }
    battle = _digest_envelope({
        **binding,
        "status": "VALIDATED", "support_status": "MATCH",
        "result": "ATTACK_WIN", "legality": "LEGAL_STATIC_SHAPE",
        "safety_margin": "ROBUST_WIN", "runtime_validated": True,
    })
    server_binding = {**binding, "target_relation": server_relation}
    server = _digest_envelope({
        **server_binding,
        "status": "ACCEPTED", "server_accepted": True,
        "command_kind": "DeployForce", "action_kind": server_kind,
    })
    return {
        "action_id": "m1:10->20:900", "origin": "LIVE_CONTROLLER",
        "action_kind": "ATTACK_ENEMY", "match": "m1", "cycle_id": 8,
        "source": 10, "target": 20, "verifier": "FORCE_OBSERVED",
        "attack_proof_bundle": {
            "schema_version": 1,
            "battle_differential_evidence_id": battle["evidence_id"],
            "server_acceptance_evidence_id": server["evidence_id"],
            "battle_differential_evidence": battle,
            "server_acceptance_evidence": server,
        },
    }


def test_attack_proofs_are_indexed_and_cross_checked_against_action(tmp_path):
    log = tmp_path / "runtime/logs/live_actions.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps(_logged_attack()) + "\n", encoding="utf-8")

    index = build_index(tmp_path)

    assert index["actions"][0]["action_kind"] == "ATTACK_ENEMY"
    assert index["actions"][0]["attack_proof_status"] == "VALIDATED"
    assert index["actions"][0]["attack_proof_bundle"]
    assert index["attack_validation"] == {
        "status": "PASS", "attack_actions": 1,
        "validated_actions": 1, "reason": None}


def test_attack_proof_from_another_cycle_is_not_reused(tmp_path):
    log = tmp_path / "runtime/logs/live_actions.jsonl"
    log.parent.mkdir(parents=True)
    action = _logged_attack()
    action["cycle_id"] = 9
    log.write_text(json.dumps(action) + "\n", encoding="utf-8")

    index = build_index(tmp_path)

    assert index["actions"][0]["attack_proof_status"] == "INVALID"
    assert index["attack_validation"]["status"] == "VALIDATION_PENDING"
    assert index["attack_validation"]["validated_actions"] == 0


def test_attack_proof_without_logged_cycle_is_not_independently_verifiable(
        tmp_path):
    log = tmp_path / "runtime/logs/live_actions.jsonl"
    log.parent.mkdir(parents=True)
    action = _logged_attack()
    action.pop("cycle_id")
    log.write_text(json.dumps(action) + "\n", encoding="utf-8")

    index = build_index(tmp_path)

    assert index["actions"][0]["attack_proof_status"] == "INVALID"
    assert index["attack_validation"]["status"] == "VALIDATION_PENDING"


def test_self_reinforcement_server_proof_does_not_validate_attack(tmp_path):
    log = tmp_path / "runtime/logs/live_actions.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps(_logged_attack(
        server_relation="SELF", server_kind="REINFORCE_SELF")) + "\n",
        encoding="utf-8")

    index = build_index(tmp_path)

    assert index["actions"][0]["attack_proof_status"] == "INVALID"
    assert index["attack_validation"]["status"] == "VALIDATION_PENDING"
    assert index["attack_validation"]["validated_actions"] == 0


def test_attack_dispatch_without_runtime_proofs_stays_validation_pending(tmp_path):
    log = tmp_path / "runtime/logs/live_actions.jsonl"
    log.parent.mkdir(parents=True)
    action = _logged_attack()
    action.pop("attack_proof_bundle")
    action["attack_validation_status"] = "VALIDATION_PENDING"
    log.write_text(json.dumps(action) + "\n", encoding="utf-8")

    index = build_index(tmp_path)

    assert index["actions"][0]["attack_proof_status"] == (
        "AWAITING_VERIFICATION")
    assert index["attack_validation"] == {
        "status": "VALIDATION_PENDING", "attack_actions": 1,
        "validated_actions": 0, "reason": "attack_verification_pending"}
