"""攻擊 proof envelope 離線驗證回歸。

與產生器不同程式、同一規範（canonical JSON＋sha256）：
只驗證「此 ID 確實對應此內容」，不判斷內容真假。
硬編碼測試向量鎖定格式，防分隔符／排序漂移。

成功證據：有效封包通過；竄改／缺欄／格式錯誤全拒絕。
失敗證據：任何無效封包被接受。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.replay import (PROOF_BINDING_FIELDS, verify_attack_proof_bundle,
                              verify_proof_envelope)

# 硬編碼向量：{"cycle_id":8,"match_id":"m1","source_tower_id":1,
#              "target_tower_id":2} 經 canonical 編碼的雜湊。
# 若有人改分隔符／排序／編碼，此測試即失敗。
HARDCODED_PAYLOAD = {"cycle_id": 8, "match_id": "m1",
                     "source_tower_id": 1, "target_tower_id": 2}
HARDCODED_ID = ("sha256:7f7e386ccf9262db48c3917ea81d296d431664db6787a8c3f76"
                "57459124b3743")


def test_hardcoded_vector_locks_canonical_format():
    envelope = {**HARDCODED_PAYLOAD, "evidence_id": HARDCODED_ID}
    result = verify_proof_envelope(envelope)
    assert result == {"valid": True, "reason": "hash-matches-content",
                      "evidence_id": HARDCODED_ID}


def test_tampered_content_rejected():
    envelope = {**HARDCODED_PAYLOAD, "source_tower_id": 99,
                "evidence_id": HARDCODED_ID}
    result = verify_proof_envelope(envelope)
    assert result == {"valid": False, "reason": "hash-mismatch"}


def test_missing_evidence_id_rejected():
    result = verify_proof_envelope(dict(HARDCODED_PAYLOAD))
    assert result == {"valid": False, "reason": "evidence-id-malformed"}


def test_malformed_evidence_id_rejected():
    for bad in ("sha256:xyz", "md5:abc", "", 12345, None):
        result = verify_proof_envelope({**HARDCODED_PAYLOAD,
                                        "evidence_id": bad})
        assert result == {"valid": False,
                          "reason": "evidence-id-malformed"}, bad


def test_missing_binding_fields_rejected():
    envelope = {"match_id": "m1", "evidence_id": HARDCODED_ID}
    result = verify_proof_envelope(envelope)
    assert result["valid"] is False
    assert result["reason"] in ("hash-mismatch", "binding-fields-missing")


def test_non_object_rejected():
    for bad in (None, [], "envelope", 42):
        result = verify_proof_envelope(bad)
        assert result == {"valid": False,
                          "reason": "envelope-must-be-object"}, bad


def test_binding_fields_constant():
    assert PROOF_BINDING_FIELDS == (
        "match_id", "cycle_id", "source_tower_id", "target_tower_id")


def _bundle(battle=None, server=None, battle_id="b1", server_id="s1"):
    return {"battle_differential_evidence": battle,
            "server_acceptance_evidence": server,
            "battle_differential_evidence_id": battle_id,
            "server_acceptance_evidence_id": server_id}


def _signed_payload(payload):
    import hashlib
    import json
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return payload, "sha256:" + hashlib.sha256(encoded).hexdigest()


def test_bundle_requires_both_envelopes():
    assert verify_attack_proof_bundle(None)["reason"] == \
        "bundle-must-be-object"
    assert verify_attack_proof_bundle(
        _bundle())["reason"] == "bundle-evidences-missing"
    assert verify_attack_proof_bundle(
        _bundle(battle={}, server={}))["reason"] == \
        "battle-envelope-invalid"


def test_bundle_server_id_missing():
    import hashlib
    import json
    battle = {"match_id": "m1", "cycle_id": 8, "source_tower_id": 1,
              "target_tower_id": 2}
    encoded = json.dumps(battle, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    battle_id = "sha256:" + hashlib.sha256(encoded).hexdigest()
    server = {"match_id": "m1", "cycle_id": 8, "source_tower_id": 1,
              "target_tower_id": 2}
    result = verify_attack_proof_bundle(_bundle(
        battle=battle, server=server,
        battle_id=battle_id, server_id=""))
    assert result == {"valid": False,
                      "reason": "server-evidence-id-missing"}


def test_bundle_rejects_tampered_battle_envelope():
    import hashlib
    import json
    battle = {"match_id": "m1", "cycle_id": 8, "source_tower_id": 1,
              "target_tower_id": 2, "result": "ATTACK_WIN"}
    encoded = json.dumps(battle, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    good_id = "sha256:" + hashlib.sha256(encoded).hexdigest()
    server = {"match_id": "m1", "cycle_id": 8, "source_tower_id": 1,
              "target_tower_id": 2, "server_accepted": True}
    encoded_s = json.dumps(server, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode(
                               "utf-8")
    server_id = "sha256:" + hashlib.sha256(encoded_s).hexdigest()
    good = _bundle(battle=battle, server=server,
                   battle_id=good_id, server_id=server_id)
    assert verify_attack_proof_bundle(good)["valid"] is True
    bad = _bundle(battle={**battle, "result": "ATTACK_LOSE"},
                  server=server, battle_id=good_id, server_id=server_id)
    result = verify_attack_proof_bundle(bad)
    assert result == {"valid": False,
                      "reason": "battle-envelope-invalid",
                      "detail": "hash-mismatch"}


def test_bundle_rejects_match_mismatch():
    battle, battle_id = _signed_payload(
        {"match_id": "m1", "cycle_id": 8, "source_tower_id": 1,
         "target_tower_id": 2})
    server, server_id = _signed_payload(
        {"match_id": "m2", "cycle_id": 8, "source_tower_id": 1,
         "target_tower_id": 2})
    result = verify_attack_proof_bundle(_bundle(
        battle=battle, server=server,
        battle_id=battle_id, server_id=server_id))
    assert result == {"valid": False,
                      "reason": "bundle-binding-mismatch",
                      "field": "match_id"}


def test_bundle_rejects_cycle_or_route_mismatch():
    base = {"match_id": "m1", "cycle_id": 8, "source_tower_id": 1,
            "target_tower_id": 2}
    battle, battle_id = _signed_payload(base)
    for field, wrong_value in (("cycle_id", 9),
                               ("source_tower_id", 3),
                               ("target_tower_id", 3)):
        server, server_id = _signed_payload({**base, field: wrong_value})
        result = verify_attack_proof_bundle(_bundle(
            battle=battle, server=server,
            battle_id=battle_id, server_id=server_id))
        assert result == {"valid": False,
                          "reason": "bundle-binding-mismatch",
                          "field": field}


def test_bundle_binding_rejects_bool_vs_int_even_when_equal():
    battle, battle_id = _signed_payload({
        "match_id": "m1", "cycle_id": 8,
        "source_tower_id": 1, "target_tower_id": 2})
    server, server_id = _signed_payload({
        "match_id": "m1", "cycle_id": 8,
        "source_tower_id": True, "target_tower_id": 2})
    result = verify_attack_proof_bundle(_bundle(
        battle=battle, server=server,
        battle_id=battle_id, server_id=server_id))
    assert result == {"valid": False,
                      "reason": "bundle-binding-mismatch",
                      "field": "source_tower_id"}


def test_bundle_rejects_invalid_shared_binding_types_and_ids():
    valid = {"match_id": "m1", "cycle_id": 8,
             "source_tower_id": 1, "target_tower_id": 2}
    for field, invalid_value in (("cycle_id", True),
                                 ("source_tower_id", 0),
                                 ("target_tower_id", 1)):
        invalid = {**valid, field: invalid_value}
        battle, battle_id = _signed_payload(invalid)
        server, server_id = _signed_payload(invalid)
        result = verify_attack_proof_bundle(_bundle(
            battle=battle, server=server,
            battle_id=battle_id, server_id=server_id))
        assert result == {"valid": False,
                          "reason": "bundle-binding-invalid",
                          "field": field}
