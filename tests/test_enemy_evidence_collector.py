"""敵方執行期證據收集器的綁定與保留規則。"""
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from enemy_evidence_collector import collect_once  # noqa: E402


def _action(**overrides):
    row = {
        "action_id": "match-A:101->202:1000",
        "origin": "LIVE_CONTROLLER",
        "action_kind": "ATTACK_ENEMY",
        "match": "match-A",
        "cycle_id": 7,
        "source": 101,
        "target": 202,
        "dispatch": {"sent_at": 1000.0},
        "logged_at": 1004.0,
        "verifier": "TARGET_CAPTURED",
        "result": "TARGET_CAPTURED",
    }
    row.update(overrides)
    return row


def _force_bundle(**overrides):
    bundle = {
        "action_id": "match-A:101->202:1000",
        "match_id": "match-A",
        "cycle_id": 7,
        "source": 101,
        "target": 202,
        "dispatched_at": 1000.0,
        "t0": {"source": {"captured_at": 999.0},
               "target": {"captured_at": 999.0}},
        "t1": {"source": {"captured_at": 1001.0},
               "target": {"captured_at": 1001.0}},
        "t2": {"source": {"captured_at": 1002.0},
               "target": {"captured_at": 1002.0}},
        "t3": {"source": {"captured_at": 1003.0},
               "target": {"captured_at": 1003.0}},
        "force_match_source": "FORCE_MATCH_VERIFIED",
        "force_match_target": "FORCE_MATCH_VERIFIED",
        "dispatch_observation": "FORCE_OBSERVED",
    }
    bundle.update(overrides)
    return bundle


def _battle(**overrides):
    battle = {
        "action_id": "match-A:101->202:1000",
        "match_id": "match-A",
        "cycle_id": 7,
        "source_tower": 101,
        "target_tower": 202,
        "source_owner": "SELF",
        "target_owner": "ENEMY",
        "source_owner_id": 7,
        "target_owner_id": 22,
        "evaluation_status": "SUPPORTED",
        "after_target": {"owner": "SELF"},
    }
    battle.update(overrides)
    return battle


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(root: Path, *, action=None, force=None, battle=None,
             pending=None):
    log = root / "runtime" / "logs" / "live_actions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps(action or _action()) + "\n", encoding="utf-8")
    if force is not False:
        _write_json(root / "runtime" / "research" / "forces"
                    / "autonomous_validation" / "case" / "bundle.json",
                    force or _force_bundle())
    if battle is not False:
        _write_json(root / "runtime" / "research" / "pvp_validation"
                    / "case" / "battle-differential.json",
                    battle or _battle())
    if pending is not False:
        action_kind = (action or _action()).get("action_kind")
        _write_json(root / "runtime" / "state" / "pending-live-dispatch.json",
                    pending or {
                        "action_id": "match-A:101->202:1000",
                        "match_id": "match-A", "cycle_id": 7,
                        "source_tower_id": 101, "target_tower_id": 202,
                        "action_kind": action_kind,
                        "sent_at": 1000.0,
                        "before": {"source": {"owner": "SELF"},
                                   "target": {"owner": "ENEMY"}},
                    })


def test_collects_bound_enemy_attack_stages_and_verdict(tmp_path):
    _fixture(tmp_path)

    report = collect_once(tmp_path)

    assert report["candidate_count"] == 1
    assert report["written_count"] == 1
    case_path = next((tmp_path / "runtime" / "research"
                      / "enemy_evidence").glob("*.json"))
    case = json.loads(case_path.read_text(encoding="utf-8"))
    assert case["binding"] == {
        "action_id": "match-A:101->202:1000",
        "match_id": "match-A",
        "cycle_id": 7,
        "source_tower_id": 101,
        "target_tower_id": 202,
        "source_owner": "SELF",
        "target_owner": "ENEMY",
        "origin": "LIVE_CONTROLLER",
        "dispatched_at": 1000.0,
    }
    assert all(case["stages"][name] is not None for name in (
        "t0_pre_dispatch", "t1_post_dispatch", "t2_post_dispatch",
        "arrival_observation", "t3_post_battle", "battle_differential",
        "verification"))
    assert case["collection_status"] == "COMPLETE"
    assert case["proof_status"] == "NOT_EVALUATED"
    assert case["timestamps"]["status"] == "BOUND"


def test_does_not_collect_neutral_expansion_or_infer_attack_from_owner(tmp_path):
    action = _action(action_kind="EXPAND_NEUTRAL")
    _fixture(tmp_path, action=action,
             battle=_battle(target_owner="NEUTRAL"))

    report = collect_once(tmp_path)

    assert report["candidate_count"] == 0
    assert report["written_count"] == 0
    assert not (tmp_path / "runtime" / "research"
                / "enemy_evidence").exists()


def test_old_action_without_kind_is_not_guessed_as_enemy(tmp_path):
    action = _action()
    action.pop("action_kind")
    _fixture(tmp_path, action=action)

    report = collect_once(tmp_path)

    assert report["candidate_count"] == 0
    assert report["action_rows_scanned"] == 1
    assert report["unclassified_action_rows"] == 1


def test_mismatched_force_bundle_is_not_attached_and_marks_invalid(tmp_path):
    _fixture(tmp_path, force=_force_bundle(cycle_id=8))

    collect_once(tmp_path)

    case = json.loads(next((tmp_path / "runtime" / "research"
                            / "enemy_evidence").glob("*.json")
                           ).read_text(encoding="utf-8"))
    assert case["stages"]["t1_post_dispatch"] is None
    assert case["collection_status"] == "BINDING_CONFLICT"
    assert any("cycle_id" in issue for issue in case["issues"])


def test_unknown_target_owner_or_missing_stage_stays_incomplete(tmp_path):
    _fixture(tmp_path, battle=_battle(target_owner=None), force=False,
             pending=False)

    collect_once(tmp_path)

    case = json.loads(next((tmp_path / "runtime" / "research"
                            / "enemy_evidence").glob("*.json")
                           ).read_text(encoding="utf-8"))
    assert case["binding"]["target_owner"] == "UNKNOWN"
    assert case["collection_status"] == "INCOMPLETE"
    assert "target_owner" in case["missing"]
    assert "t0_pre_dispatch" in case["missing"]


def test_post_dispatch_snapshot_is_not_claimed_as_arrival_without_force_match(
        tmp_path):
    force = _force_bundle(force_match_target="FORCE_MATCH_NOT_FOUND",
                          dispatch_observation="DISPATCH_NOT_OBSERVED")
    _fixture(tmp_path, force=force)

    collect_once(tmp_path)

    case = json.loads(next((tmp_path / "runtime" / "research"
                            / "enemy_evidence").glob("*.json")
                           ).read_text(encoding="utf-8"))
    assert case["stages"]["t2_post_dispatch"] is not None
    assert case["stages"]["arrival_observation"] is None
    assert "arrival_observation" in case["missing"]
    assert case["collection_status"] == "INCOMPLETE"


def test_differential_must_match_full_action_identity(tmp_path):
    _fixture(tmp_path, battle=_battle(target_tower=303))

    collect_once(tmp_path)

    case = json.loads(next((tmp_path / "runtime" / "research"
                            / "enemy_evidence").glob("*.json")
                           ).read_text(encoding="utf-8"))
    assert case["stages"]["battle_differential"] is None
    assert case["collection_status"] == "BINDING_CONFLICT"
    assert any("target_tower_id" in issue for issue in case["issues"])


def test_repeat_scan_overwrites_one_case_file(tmp_path):
    _fixture(tmp_path)

    first = collect_once(tmp_path)
    second = collect_once(tmp_path)

    files = list((tmp_path / "runtime" / "research"
                  / "enemy_evidence").glob("*.json"))
    assert first["written_count"] == 1
    assert second["written_count"] == 0
    assert len(files) == 1


def test_custom_output_must_remain_inside_project_root(tmp_path):
    with pytest.raises(ValueError, match="inside project root"):
        collect_once(tmp_path, tmp_path.parent / "outside")


def test_malformed_action_log_rows_are_skipped(tmp_path):
    log = tmp_path / "runtime" / "logs" / "live_actions.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("{bad json}\n" + json.dumps(_action()) + "\n",
                   encoding="utf-8")
    _write_json(tmp_path / "runtime" / "research" / "forces"
                / "autonomous_validation" / "case" / "bundle.json",
                _force_bundle())
    _write_json(tmp_path / "runtime" / "research" / "pvp_validation"
                / "case" / "battle-differential.json", _battle())
    _write_json(tmp_path / "runtime" / "state" / "pending-live-dispatch.json",
                {"action_id": "match-A:101->202:1000",
                 "match_id": "match-A", "cycle_id": 7,
                 "source_tower_id": 101, "target_tower_id": 202,
                 "before": {"target": {"owner": "ENEMY"}}})

    report = collect_once(tmp_path)

    assert report["candidate_count"] == 1
    assert report["malformed_action_rows"] == 1


@pytest.mark.parametrize(("sample", "captured_at"), [
    ("t0", 1001.0),
    ("t1", 999.0),
    ("t2", 1000.5),
])
def test_snapshot_timestamps_must_follow_dispatch_and_stage_order(
        tmp_path, sample, captured_at):
    bundle = _force_bundle()
    bundle[sample]["source"]["captured_at"] = captured_at
    _fixture(tmp_path, force=bundle)

    collect_once(tmp_path)

    case = json.loads(next((tmp_path / "runtime" / "research"
                            / "enemy_evidence").glob("*.json")
                           ).read_text(encoding="utf-8"))
    assert case["collection_status"] == "BINDING_CONFLICT"
    assert case["timestamps"]["status"] == "INVALID"


def test_watch_rescans_and_keeps_one_file_per_action(
        tmp_path, monkeypatch, capsys):
    import enemy_evidence_collector

    _fixture(tmp_path)
    intervals = []
    monkeypatch.setattr(enemy_evidence_collector.time, "sleep",
                        lambda seconds: intervals.append(seconds))

    enemy_evidence_collector.watch(tmp_path, interval=0.5,
                                   max_iterations=2)

    assert intervals == [0.5]
    assert len(capsys.readouterr().out.splitlines()) == 2
    assert len(list((tmp_path / "runtime" / "research"
                     / "enemy_evidence").glob("*.json"))) == 1
