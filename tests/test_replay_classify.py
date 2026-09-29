"""Fail-closed classification of the saved replay corpus."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.replay_classify import build_replay_index, write_index


def _case(root: Path, *, action_kind="ATTACK_ENEMY",
          source_owner="SELF", target_owner="ENEMY",
          action_id="match-1:10->11:100", match_id="match-1",
          meta_match_id=None, include_action_kind=True):
    case_id = (action_id.replace(":", "_").replace("-", "_")
               .replace(">", "_"))
    pvp = root / "runtime/research/pvp_validation" / case_id
    forces = root / "runtime/research/forces/autonomous_validation" / case_id
    pvp.mkdir(parents=True, exist_ok=True)
    forces.mkdir(parents=True, exist_ok=True)

    diff = {
        "action_id": action_id,
        "match_id": match_id,
        "source_tower": 10,
        "target_tower": 11,
        "source_owner": source_owner,
        "target_owner": target_owner,
    }
    meta = {
        "action_id": action_id,
        "match_id": meta_match_id or match_id,
        "cycle_id": 7,
        "dispatched_at": 100.0,
        "logged_at": 101.0,
        "verifier": "TARGET_CAPTURED",
    }
    bundle = {
        "action_id": action_id,
        "match_id": match_id,
        "cycle_id": 7,
        "source": 10,
        "target": 11,
        "source_owner": source_owner,
        "target_owner": target_owner,
        "t0": {"source": {"match_id": match_id, "captured_at": 99.0},
               "target": {"match_id": match_id, "captured_at": 99.0}},
        "t1": {"source": {"match_id": match_id, "captured_at": 100.5},
               "target": {"match_id": match_id, "captured_at": 100.5}},
        "t2": {"source": {"match_id": match_id, "captured_at": 100.75},
               "target": {"match_id": match_id, "captured_at": 100.75}},
    }
    action = {
        "action_id": action_id,
        "match": match_id,
        "cycle_id": 7,
        "source": 10,
        "target": 11,
        "source_owner": source_owner,
        "target_owner": target_owner,
        "verifier": "TARGET_CAPTURED",
    }
    if include_action_kind:
        action["action_kind"] = action_kind

    (pvp / "battle-differential.json").write_text(
        json.dumps(diff), encoding="utf-8")
    (pvp / "derived-meta.json").write_text(
        json.dumps(meta), encoding="utf-8")
    (forces / "bundle.json").write_text(
        json.dumps(bundle), encoding="utf-8")
    log = root / "runtime/logs/live_actions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps(action) + "\n", encoding="utf-8")
    return case_id, action


@pytest.mark.parametrize(("raw_kind", "expected", "owners"), [
    ("EXPAND_NEUTRAL", "NEUTRAL_EXPANSION", ("SELF", "NEUTRAL")),
    ("REINFORCE_SELF", "SELF_REINFORCE", ("SELF", "SELF")),
    ("ENEMY_THREAT", "ENEMY_THREAT", ("ENEMY", "SELF")),
    ("ATTACK_ENEMY", "ATTACK_ENEMY", ("SELF", "ENEMY")),
    ("FUTURE_ACTION_KIND", "UNKNOWN_ACTION", ("SELF", "NEUTRAL")),
])
def test_explicit_action_kind_is_classified_without_owner_guessing(
        tmp_path, raw_kind, expected, owners):
    _case(tmp_path, action_kind=raw_kind, source_owner=owners[0],
          target_owner=owners[1], action_id=f"match-1:10->11:{raw_kind}")

    item = build_replay_index(tmp_path, generated_at=200.0)["items"][0]

    assert item["kind"] == expected
    if expected == "UNKNOWN_ACTION":
        assert item["evidence_status"] == "COMPLETE"
        assert "unrecognized-action-kind" in item["classification_issues"]
    else:
        assert item["evidence_status"] == "COMPLETE"
    assert item["source_owner"] == owners[0]
    assert item["target_owner"] == owners[1]
    assert item["verdict"] == "TARGET_CAPTURED"
    assert item["match_id"] == "match-1"
    assert item["action_id"] == f"match-1:10->11:{raw_kind}"
    assert {Path(path).name for path in item["files"]} == {
        "battle-differential.json", "derived-meta.json",
        "bundle.json", "live_actions.jsonl",
    }


def test_missing_kind_stays_unknown_even_when_target_owner_is_neutral(tmp_path):
    _case(tmp_path, action_kind="EXPAND_NEUTRAL", source_owner="SELF",
          target_owner="NEUTRAL", include_action_kind=False)

    item = build_replay_index(tmp_path, generated_at=200.0)["items"][0]

    assert item["kind"] == "UNKNOWN_ACTION"
    assert item["target_owner"] == "NEUTRAL"
    assert item["evidence_status"] == "COMPLETE"
    assert "action-kind-unknown" in item["classification_issues"]


def test_explicit_cross_match_binding_is_invalid(tmp_path):
    _case(tmp_path, meta_match_id="other-match")

    item = build_replay_index(tmp_path, generated_at=200.0)["items"][0]

    assert item["evidence_status"] == "INVALID"
    assert item["match_id"] is None
    assert "conflicting-match_id" in item["issues"]


def test_duplicate_action_log_rows_are_invalid(tmp_path):
    _case(tmp_path)
    log = tmp_path / "runtime/logs/live_actions.jsonl"
    log.write_text(log.read_text(encoding="utf-8") * 2, encoding="utf-8")

    item = build_replay_index(tmp_path, generated_at=200.0)["items"][0]

    assert item["evidence_status"] == "INVALID"
    assert "duplicate-action-log-rows" in item["issues"]


def test_malformed_evidence_file_is_invalid(tmp_path):
    case_id, _ = _case(tmp_path)
    bundle = (tmp_path / "runtime/research/forces/autonomous_validation"
              / case_id / "bundle.json")
    bundle.write_text("{broken", encoding="utf-8")

    item = build_replay_index(tmp_path, generated_at=200.0)["items"][0]

    assert item["evidence_status"] == "INVALID"
    assert "bundle-invalid-json" in item["issues"]


def test_bundle_snapshot_from_another_match_is_invalid(tmp_path):
    case_id, _ = _case(tmp_path)
    bundle = (tmp_path / "runtime/research/forces/autonomous_validation"
              / case_id / "bundle.json")
    data = json.loads(bundle.read_text(encoding="utf-8"))
    data["t2"]["target"]["match_id"] = "other-match"
    bundle.write_text(json.dumps(data), encoding="utf-8")

    item = build_replay_index(tmp_path, generated_at=200.0)["items"][0]

    assert item["evidence_status"] == "INVALID"
    assert "t2-target-match-mismatch" in item["issues"]


def test_missing_snapshot_timestamp_is_partial(tmp_path):
    case_id, _ = _case(tmp_path)
    bundle = (tmp_path / "runtime/research/forces/autonomous_validation"
              / case_id / "bundle.json")
    data = json.loads(bundle.read_text(encoding="utf-8"))
    del data["t1"]["source"]["captured_at"]
    bundle.write_text(json.dumps(data), encoding="utf-8")

    item = build_replay_index(tmp_path, generated_at=200.0)["items"][0]

    assert item["evidence_status"] == "PARTIAL"
    assert "t1-source-time-unknown" in item["issues"]


def test_missing_evidence_components_are_partial(tmp_path):
    log = tmp_path / "runtime/logs/live_actions.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({
        "action_id": "match-1:10->11:100", "match": "match-1",
        "source": 10, "target": 11, "action_kind": "ATTACK_ENEMY",
        "source_owner": "SELF", "target_owner": "ENEMY",
        "verifier": "TARGET_CAPTURED",
    }) + "\n", encoding="utf-8")

    item = build_replay_index(tmp_path, generated_at=200.0)["items"][0]

    assert item["kind"] == "ATTACK_ENEMY"
    assert item["evidence_status"] == "PARTIAL"
    assert "missing-bundle-file" in item["issues"]
    assert "missing-differential-file" in item["issues"]


def test_writer_overwrites_one_index_and_rejects_escape(tmp_path):
    _case(tmp_path)
    output = Path("runtime/research/replay/index.json")
    destination = write_index(
        output, build_replay_index(tmp_path, generated_at=200.0),
        root=tmp_path)
    write_index(output, build_replay_index(tmp_path, generated_at=201.0),
                root=tmp_path)

    assert destination == tmp_path / output
    assert json.loads(destination.read_text(encoding="utf-8"))["generated_at"] == 201.0
    assert sorted(path.name for path in destination.parent.iterdir()) == ["index.json"]
    with pytest.raises(ValueError, match="output-path-must-stay-under-project-root"):
        write_index(tmp_path.parent / "outside.json", {}, root=tmp_path)


def test_empty_corpus_is_partial_and_has_bounded_empty_index(tmp_path):
    report = build_replay_index(tmp_path, generated_at=200.0)

    assert report["status"] == "PARTIAL"
    assert report["items"] == []
    assert report["summary"]["items"] == 0
    assert report["summary"]["evidence_status"] == {
        "COMPLETE": 0, "PARTIAL": 0, "INVALID": 0,
    }
