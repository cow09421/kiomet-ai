import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import replay_auto_ingest
from replay_auto_ingest import (build_auto_index, validate_case_integrity,
                                write_report)


def _evidence():
    action_id = "m1:10->20:100"
    diff = {
        "action_id": action_id, "match_id": "m1", "cycle_id": 8,
        "source_tower": 10, "target_tower": 20,
        "source_owner": "SELF", "target_owner": "ENEMY",
        "source_owner_id": 7, "target_owner_id": 22,
    }
    bundle = {
        "action_id": action_id, "match_id": "m1", "cycle_id": 8,
        "source": 10, "target": 20, "dispatched_at": 20.0,
    }
    for sample, captured_at in (("t0", 19.0), ("t1", 21.0),
                                ("t2", 22.0), ("t3", 23.0)):
        bundle[sample] = {
            "source": {"match_id": "m1", "tower_ref": 100,
                       "captured_at": captured_at,
                       "collections": {"outbound": {"entries": []},
                                       "inbound": {"entries": []}}},
            "target": {"match_id": "m1", "tower_ref": 200,
                       "captured_at": captured_at,
                       "collections": {"outbound": {"entries": []},
                                       "inbound": {"entries": []}}},
        }
    action = {
        "action_id": action_id, "match": "m1", "match_id": "m1",
        "cycle_id": 8,
        "source": 10, "target": 20, "action_kind": "ATTACK_ENEMY",
    }
    return diff, bundle, action


def test_case_integrity_accepts_matching_bound_fresh_enemy_attack():
    diff, bundle, action = _evidence()

    result = validate_case_integrity(diff, bundle, action)

    assert result["status"] == "PASS"
    assert result["issues"] == []


@pytest.mark.parametrize(("where", "field", "value"), [
    ("bundle", "match_id", "other-match"),
    ("bundle", "cycle_id", 9),
    ("bundle", "source", 11),
    ("bundle", "target", 21),
    ("action", "source", 11),
    ("action", "cycle_id", 9),
])
def test_case_integrity_rejects_cross_action_binding(where, field, value):
    diff, bundle, action = _evidence()
    {"bundle": bundle, "action": action}[where][field] = value

    result = validate_case_integrity(diff, bundle, action)

    assert result["status"] == "INVALID"
    assert result["issues"]


@pytest.mark.parametrize(("sample", "side", "captured_at"), [
    ("t0", "source", 21.0),
    ("t1", "target", 19.0),
    ("t3", "source", 55.0),
])
def test_case_integrity_rejects_invalid_time_order_and_stale_samples(
        sample, side, captured_at):
    diff, bundle, action = _evidence()
    bundle[sample][side]["captured_at"] = captured_at

    result = validate_case_integrity(diff, bundle, action)

    assert result["status"] == "INVALID"
    assert any("time" in issue or "stale" in issue
               for issue in result["issues"])


def test_case_integrity_rejects_cross_match_snapshot_contamination():
    diff, bundle, action = _evidence()
    bundle["t2"]["target"]["match_id"] = "m2"

    result = validate_case_integrity(diff, bundle, action)

    assert result["status"] == "INVALID"
    assert any("match" in issue for issue in result["issues"])


def test_case_integrity_rejects_owner_relation_mismatch():
    diff, bundle, action = _evidence()
    diff["target_owner"] = "NEUTRAL"

    result = validate_case_integrity(diff, bundle, action)

    assert result["status"] == "INVALID"
    assert any("owner" in issue for issue in result["issues"])


def test_case_integrity_keeps_missing_proof_fields_unknown():
    diff, bundle, action = _evidence()
    bundle.pop("dispatched_at")

    result = validate_case_integrity(diff, bundle, action)

    assert result["status"] == "UNKNOWN"
    assert result["issues"]


def test_auto_ingest_picks_up_bundle_and_crash_on_next_scan(tmp_path):
    diff, bundle, action = _evidence()
    case_name = "m1_10_20_100"
    validation = tmp_path / "runtime/research/pvp_validation" / case_name
    validation.mkdir(parents=True)
    (validation / "battle-differential.json").write_text(
        json.dumps(diff), encoding="utf-8")

    first = build_auto_index(tmp_path, generated_at=30.0)
    assert first["replay"]["summary"]["cases"] == 1
    assert first["evidence"]["bundles"] == []

    bundle_dir = (tmp_path / "runtime/research/forces"
                  / "autonomous_validation" / case_name)
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "bundle.json").write_text(
        json.dumps(bundle), encoding="utf-8")
    log = tmp_path / "runtime/logs/live_actions.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps(action) + "\n", encoding="utf-8")
    incident_dir = tmp_path / "runtime/research/crash/incidents"
    incident_dir.mkdir(parents=True)
    (incident_dir / "crash-1.json").write_text(json.dumps({
        "incident_id": "crash-1", "timestamp": 24.0,
        "signature": "renderer-exit", "match_context": "m1",
    }), encoding="utf-8")

    second = build_auto_index(tmp_path, generated_at=31.0)
    assert second["replay"]["summary"]["cases"] == 1
    assert len(second["evidence"]["bundles"]) == 1
    assert second["integrity"]["status"] == "PASS", second["integrity"]
    assert second["integrity"]["pass"] == 1
    assert len(second["evidence"]["crashes"]) == 1

    out = tmp_path / "runtime/research/replay-auto-index.json"
    write_report(out, second, root=tmp_path)
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["generated_at"] == 31.0


def test_watch_rebuilds_and_overwrites_one_report(tmp_path, monkeypatch,
                                                 capsys):
    reports = iter((
        {"generated_at": 1.0, "replay": {"summary": {
            "cases": 1, "flagged": 0}}, "integrity": {
                "status": "UNKNOWN", "invalid": 0},
         "evidence": {"crashes": []}},
        {"generated_at": 2.0, "replay": {"summary": {
            "cases": 2, "flagged": 1}}, "integrity": {
                "status": "INVALID", "invalid": 1},
         "evidence": {"crashes": [{"incident_id": "crash-1"}]}}))
    sleeps = []

    monkeypatch.setattr(replay_auto_ingest, "build_auto_index",
                        lambda _root: next(reports))

    def stop_after_second_scan(_interval):
        sleeps.append(True)
        if len(sleeps) == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(replay_auto_ingest.time, "sleep",
                        stop_after_second_scan)
    out = tmp_path / "runtime/research/replay-auto-index.json"

    result = replay_auto_ingest.main([
        "--root", str(tmp_path), "--out", str(out), "--watch",
        "--interval", "0.01",
    ])

    assert result == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["generated_at"] == 2.0
    assert saved["replay"]["summary"]["cases"] == 2
    assert len(list(out.parent.iterdir())) == 1
    assert len(capsys.readouterr().out.splitlines()) == 2


def test_report_output_cannot_escape_project_root(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside.json")

    with pytest.raises(ValueError, match="under-project-root"):
        write_report(outside, {"schema_version": 1}, root=tmp_path)

    assert not outside.exists()
