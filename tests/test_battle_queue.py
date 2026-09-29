"""Enemy battle queue is exact-identity, bounded, and fail-closed."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import battle_queue  # noqa: E402
from battle_queue import _inside_root, build_queue, main  # noqa: E402


def _units(**over):
    out = {name: 0 for name in
           ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier")}
    out.update(over)
    return out


def _diff(action_id="match-A:11->22:1000", *, match="match-A",
          source=11, target=22, source_owner="SELF", target_owner="ENEMY",
          prediction=None, target_type="Cliff"):
    return {
        "action_id": action_id, "match_id": match,
        "source_tower": source, "target_tower": target,
        "source_owner": source_owner, "target_owner": target_owner,
        "source_owner_id": 5, "target_owner_id": 17,
        "target_type": target_type,
        "before_attacker": _units(Soldier=20),
        "before_defender": _units(Soldier=5),
        "prediction": prediction,
        "after_target": {"owner": "SELF", "units": _units(Soldier=3)},
    }


def _action(action_id="match-A:11->22:1000", *, match="match-A",
            source=11, target=22, kind="ATTACK_ENEMY", origin="LIVE_CONTROLLER"):
    return {
        "action_id": action_id, "match": match,
        "source": source, "target": target,
        "action_kind": kind, "origin": origin,
        "verifier": "TARGET_CAPTURED", "result": "TARGET_CAPTURED",
    }


def _write_diff(root, name, diff):
    path = root / "runtime/research/pvp_validation" / name / "battle-differential.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(diff), encoding="utf-8")
    return path


def _write_actions(root, rows, *, suffix=""):
    path = root / "runtime/logs" / f"live_actions{suffix}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows),
                    encoding="utf-8")
    if suffix:
        path.replace(root / "runtime/logs/live_actions.jsonl")


def test_collects_enemy_case_with_mirror_prediction_and_explicit_observation(
        tmp_path):
    diff = _diff()
    _write_diff(tmp_path, "case-1", diff)
    _write_actions(tmp_path, [_action()])

    report = build_queue(tmp_path)

    assert report["status"] == "NEEDS_REVIEW"
    assert report["proof_status"] == "NOT_EVALUATED"
    assert report["summary"]["queued_cases"] == 1
    case = report["cases"][0]
    assert case["action_kind"] == "ATTACK_ENEMY"
    assert case["predicted_result"]["source"] == "BATTLE_MIRROR_REPLAY"
    assert case["predicted_result"]["value"]["winner"] == "attacker"
    assert case["observed_result"] == {
        "verifier": "TARGET_CAPTURED", "result": "TARGET_CAPTURED",
        "target_owner_after": "SELF",
    }
    assert case["supported_case"] == "SUPPORTED"
    assert case["needs_review"] is True
    assert "runtime_prediction_missing" in case["reason"]


def test_neutral_and_unknown_owners_are_never_queued(tmp_path):
    _write_diff(tmp_path, "neutral", _diff(
        action_id="m:1->2:1", match="m", source=1, target=2,
        target_owner="NEUTRAL"))
    unknown = _diff(action_id="m:3->4:2", match="m", source=3, target=4,
                    target_owner=None)
    _write_diff(tmp_path, "unknown", unknown)

    report = build_queue(tmp_path)

    assert report["status"] == "NO_CASES"
    assert report["cases"] == []
    assert report["summary"]["excluded_non_enemy"] == 1
    assert report["summary"]["excluded_unknown_owner"] == 1


def test_action_log_must_match_same_action_match_and_towers(tmp_path):
    _write_diff(tmp_path, "case-1", _diff())
    _write_actions(tmp_path, [_action(match="different-match")])

    case = build_queue(tmp_path)["cases"][0]

    assert case["action_kind"] == "UNKNOWN"
    assert case["needs_review"] is True
    assert "live_action_identity_mismatch" in case["reason"]
    assert case["observed_result"] == {"target_owner_after": "SELF"}


def test_mirror_unsupported_is_preserved_without_custom_prediction(
        tmp_path, monkeypatch):
    _write_diff(tmp_path, "case-1", _diff(prediction={
        "winner": "attacker", "attacker_survivors": {
            "Soldier": 4, "Ruler": 99, "secret": "discard"}}))
    _write_actions(tmp_path, [_action()])
    monkeypatch.setattr(battle_queue, "run_battle_differential", lambda _raw: {
        "support_status": "MIRROR_UNSUPPORTED",
        "differential": "MIRROR_UNSUPPORTED",
        "reason": "unsupported-aura",
        "prediction": None,
    })

    case = build_queue(tmp_path)["cases"][0]

    assert case["supported_case"] == "UNSUPPORTED"
    assert case["predicted_result"] == {
        "source": "LIVE_BATTLE_DIFFERENTIAL",
        "value": {"winner": "attacker", "attacker_survivors": {"Soldier": 4}},
    }
    assert "battle_mirror_unsupported" in case["reason"]
    assert case["needs_review"] is True


def test_incomplete_enemy_identity_is_counted_but_not_given_a_fake_id(tmp_path):
    _write_diff(tmp_path, "case-1", _diff(action_id=None))

    report = build_queue(tmp_path)

    assert report["summary"]["enemy_relation_candidates"] == 1
    assert report["summary"]["unidentifiable_enemy_candidates"] == 1
    assert report["cases"] == []


def test_duplicate_differential_identity_is_marked_for_review(tmp_path):
    _write_diff(tmp_path, "case-1", _diff())
    _write_diff(tmp_path, "case-2", _diff())

    report = build_queue(tmp_path)

    assert report["summary"]["queued_cases"] == 2
    assert report["summary"]["duplicate_differential_action_id_count"] == 1
    assert all("duplicate_differential_action_id" in case["reason"]
               for case in report["cases"])


def test_live_log_rows_with_wrong_action_or_origin_need_review(tmp_path):
    _write_diff(tmp_path, "case-1", _diff())
    _write_actions(tmp_path, [_action(kind="REINFORCE_SELF", origin="MANUAL")])

    case = build_queue(tmp_path)["cases"][0]

    assert case["action_kind"] == "UNKNOWN"
    assert "action_kind_not_verified_as_attack_enemy" in case["reason"]
    assert "live_controller_origin_unconfirmed" in case["reason"]


def test_queue_is_bounded_and_reports_omitted_cases(tmp_path):
    _write_diff(tmp_path, "case-1", _diff())
    _write_diff(tmp_path, "case-2", _diff(
        action_id="match-B:31->32:2000", match="match-B",
        source=31, target=32))

    report = build_queue(tmp_path, max_cases=1)

    assert report["summary"]["queued_cases"] == 1
    assert report["summary"]["omitted_case_count"] == 1


def test_output_is_atomic_and_inside_project_root(tmp_path, capsys):
    _write_diff(tmp_path, "case-1", _diff())
    _write_actions(tmp_path, [_action()])
    output = tmp_path / "runtime/state/battle_validation_queue.json"

    code = main(["--root", str(tmp_path)])
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(output.read_text(encoding="utf-8"))

    assert code == 0
    assert printed["status"] == "NEEDS_REVIEW"
    assert saved["cases"][0]["action_id"] == "match-A:11->22:1000"
    assert list(output.parent.glob(".battle_validation_queue.json.*.tmp")) == []


def test_input_or_output_paths_cannot_escape_project(tmp_path):
    with pytest.raises(ValueError):
        _inside_root(tmp_path.resolve(), tmp_path.parent / "outside.json")
