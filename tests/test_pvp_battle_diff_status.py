"""PvP 差分紀錄不得把追蹤證據誤寫成戰鬥預測。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.live_controller import LiveController


def record(tmp_path, *, target_owner, force_match="FORCE_MATCH_VERIFIED",
           owner_ids=None):
    controller = LiveController.__new__(LiveController)
    controller.root = tmp_path
    refreshed = SimpleNamespace(source_tower_id=10, target_tower_id=20)
    before = {
        "source": {"units": {"Soldier": 4}},
        "target": {"units": {"Soldier": 2}},
    }
    after = {
        "source": {"units": {"Soldier": 0}},
        "target": {"owner": target_owner, "units": {"Soldier": 4}},
        "force_match": force_match,
        "force_match_target": "FORCE_MATCH_VERIFIED",
    }
    candidate = {"source_owner": "SELF", "target_owner": target_owner,
                 "target_type": "Generator"}
    if owner_ids is not None:
        candidate["source_owner_id"], candidate["target_owner_id"] = owner_ids
    controller._record_battle_differential(
        "match-1", "match-1:10->20:123", refreshed, before, after,
        candidate)
    path = (tmp_path / "runtime/research/pvp_validation"
            / "match-1_10-_20_123" / "battle-differential.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_neutral_expansion_is_not_reported_as_skipped_pvp_prediction(tmp_path):
    row = record(tmp_path, target_owner="NEUTRAL")

    assert row["evaluation_status"] == "NOT_APPLICABLE_NEUTRAL_TARGET"
    assert row["evaluation_reason"] == "target_is_neutral"
    assert row["prediction"] is None
    assert row["source_owner"] == "SELF"
    assert row["target_owner"] == "NEUTRAL"
    assert row["force_match_source"] == "FORCE_MATCH_VERIFIED"
    assert row["force_match_target"] == "FORCE_MATCH_VERIFIED"


def test_enemy_target_without_owner_ids_is_explicitly_not_evaluated(tmp_path):
    row = record(tmp_path, target_owner="ENEMY")

    assert row["evaluation_status"] == "NOT_EVALUATED_UNKNOWN_IDS"
    assert row["evaluation_reason"] == "owner_ids_not_recorded"
    assert row["prediction"] is None


def test_known_owner_ids_do_not_claim_a_model_prediction(tmp_path):
    row = record(tmp_path, target_owner="ENEMY", owner_ids=(7, 12))

    assert row["evaluation_status"] == "NOT_EVALUATED_MODEL"
    assert row["evaluation_reason"] == "battle_evaluator_not_invoked"
    assert row["source_owner_id"] == 7
    assert row["target_owner_id"] == 12
    assert row["prediction"] is None


def test_unknown_target_relation_fails_closed_in_evidence(tmp_path):
    row = record(tmp_path, target_owner=None, force_match="FORCE_MATCH_AMBIGUOUS")

    assert row["evaluation_status"] == "NOT_EVALUATED_UNKNOWN_RELATION"
    assert row["evaluation_reason"] == "target_owner_relation_unknown"
    assert row["prediction"] is None
    assert row["force_match_source"] == "FORCE_MATCH_AMBIGUOUS"
