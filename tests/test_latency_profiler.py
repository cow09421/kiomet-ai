"""Latency profiling must use explicit same-row timings and preserve UNKNOWN."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from latency_profiler import (  # noqa: E402
    _inside_root, _stats, main, profile_actions,
)


def _row(action_id, *, kind="ATTACK_ENEMY", sent=100.0, logged=103.0,
         duration=4.0, match="match-A", **extra):
    row = {
        "action_id": action_id,
        "match": match,
        "action_kind": kind,
        "dispatch": {"sent_at": sent},
        "logged_at": logged,
        "duration_s": duration,
        "result": "TARGET_CONTESTED",
    }
    row.update(extra)
    return row


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows),
                    encoding="utf-8")


def test_profiles_explicit_durations_and_same_row_dispatch_intervals(tmp_path):
    source = tmp_path / "runtime/logs/live_actions.jsonl"
    _write(source, [
        _row("action-1", kind="ATTACK_ENEMY", sent=100, logged=102,
             duration=2),
        _row("action-2", kind="REINFORCE_SELF", sent=200, logged=204,
             duration=5),
    ])

    report = profile_actions(tmp_path)

    assert report["status"] == "OK"
    assert report["proof_status"] == "NOT_EVALUATED"
    assert report["metrics"]["controller_reported_duration_seconds"] == {
        "count": 2, "min": 2.0, "median": 3.5, "p95": 5.0,
        "max": 5.0, "mean": 3.5,
    }
    assert report["metrics"]["dispatch_to_completion_log_seconds"] == {
        "count": 2, "min": 2.0, "median": 3.0, "p95": 4.0,
        "max": 4.0, "mean": 3.0,
    }
    assert report["by_action_kind"]["ATTACK_ENEMY"][
        "controller_reported_duration_seconds"]["count"] == 1
    assert report["slowest_actions"][0]["action_id"] == "action-2"


def test_missing_action_kind_stays_unknown_even_when_owner_fields_suggest_enemy(
        tmp_path):
    source = tmp_path / "runtime/logs/live_actions.jsonl"
    row = _row("action-1", kind=None, source=11, target=22,
               source_owner="SELF", target_owner="ENEMY")
    row.pop("action_kind")
    _write(source, [row])

    report = profile_actions(tmp_path)

    assert report["status"] == "PARTIAL"
    assert report["coverage"]["rows_with_unknown_action_kind"] == 1
    assert report["by_action_kind"]["UNKNOWN"][
        "controller_reported_duration_seconds"]["count"] == 1
    assert report["slowest_actions"][0]["action_kind"] == "UNKNOWN"
    assert "ATTACK_ENEMY" not in report["by_action_kind"]


def test_duplicate_action_ids_are_excluded_from_latency_metrics(tmp_path):
    source = tmp_path / "runtime/logs/live_actions.jsonl"
    _write(source, [_row("duplicate"), _row("duplicate", sent=110,
                                              logged=115, duration=8)])

    report = profile_actions(tmp_path)

    assert report["status"] == "PARTIAL"
    assert report["coverage"]["duplicate_action_id_count"] == 1
    assert report["coverage"]["duplicate_rows_excluded"] == 2
    assert report["metrics"]["controller_reported_duration_seconds"][
        "count"] == 0
    assert report["metrics"]["dispatch_to_completion_log_seconds"][
        "count"] == 0


def test_malformed_rows_and_reversed_wall_clock_are_counted_not_measured(
        tmp_path):
    source = tmp_path / "runtime/logs/live_actions.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(_row("bad-clock", sent=110, logged=109, duration=3))
        + "\nnot-json\n[]\n", encoding="utf-8")

    report = profile_actions(tmp_path)

    assert report["status"] == "PARTIAL"
    assert report["source_health"]["malformed_rows"] == 2
    assert report["coverage"]["timestamp_order_errors"] == 1
    assert report["metrics"]["controller_reported_duration_seconds"][
        "count"] == 1
    assert report["metrics"]["dispatch_to_completion_log_seconds"][
        "count"] == 0


def test_non_finite_values_are_rejected(tmp_path):
    source = tmp_path / "runtime/logs/live_actions.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        '{"action_id":"nan","match":"m","action_kind":"ATTACK_ENEMY",'
        '"duration_s":NaN}\n', encoding="utf-8")

    report = profile_actions(tmp_path)

    assert report["status"] == "PARTIAL"
    assert report["source_health"]["malformed_rows"] == 1
    assert report["metrics"]["controller_reported_duration_seconds"][
        "count"] == 0


def test_missing_source_is_reported_without_inventing_zero_samples(tmp_path):
    report = profile_actions(tmp_path)

    assert report["status"] == "NO_DATA"
    assert report["source_health"]["status"] == "MISSING"
    assert report["metrics"]["controller_reported_duration_seconds"] == {
        "count": 0, "min": None, "median": None, "p95": None,
        "max": None, "mean": None,
    }


def test_report_marks_historical_sample_age_and_match_identity(tmp_path):
    source = tmp_path / "runtime/logs/live_actions.jsonl"
    logged_at = time.time() - 3600
    _write(source, [_row("old-action", sent=logged_at - 2,
                         logged=logged_at, duration=4, match="old-match")])

    report = profile_actions(tmp_path)

    assert report["source_health"]["latest_action"] == {
        "action_id": "old-action", "match_id": "old-match",
        "logged_at": logged_at,
    }
    assert 3599 <= report["source_health"][
        "latest_action_age_seconds"] <= 3601


def test_input_and_output_paths_must_remain_inside_project(tmp_path):
    outside = tmp_path.parent / "outside.jsonl"

    with pytest.raises(ValueError):
        _inside_root(tmp_path.resolve(), outside)


def test_empty_stats_are_explicitly_unavailable():
    assert _stats([]) == {
        "count": 0, "min": None, "median": None, "p95": None,
        "max": None, "mean": None,
    }


def test_cli_writes_one_atomic_report_inside_project_root(tmp_path, capsys):
    source = tmp_path / "runtime/logs/live_actions.jsonl"
    output = tmp_path / "runtime/research/latency.json"
    _write(source, [_row("action-1")])

    code = main(["--root", str(tmp_path), "--input",
                 "runtime/logs/live_actions.jsonl", "--out",
                 "runtime/research/latency.json"])
    printed = json.loads(capsys.readouterr().out)

    assert code == 0
    assert printed["status"] == "OK"
    assert json.loads(output.read_text(encoding="utf-8")) == printed
    assert list(output.parent.glob(".latency.json.*.tmp")) == []
