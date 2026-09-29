"""霅?????憛怠?甇賂?P1 禮16C嚗?
sidecar 銝?撖怠?憪?嚗 action_id 銝楊??
cycle_id ???圈＊蝷?UNKNOWN嚗??? INVERTED ?臬皜穿?
?祕隤?摮?垢?啁垢?瑁?銝?憪??批捆銝???"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from evidence_backfill import backfill_case, backfill_cases

ROOT = Path("E:/SteamLibrary/kiomet")

requires_corpus = pytest.mark.skipif(
    not (ROOT / "runtime/research/pvp_validation").is_dir(),
    reason="real replay corpus not present (gitignored)")


def _make_case(root: Path, name: str, doc: dict) -> Path:
    case_dir = root / name
    case_dir.mkdir(parents=True)
    (case_dir / "battle-differential.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return case_dir


def _actions_rows() -> dict:
    row = {"action_id": "m1-1:10->20:100",
           "dispatch": {"sent_at": 100.5, "coords": [[1, 2], [3, 4]]},
           "logged_at": 130.0, "origin": "LIVE_CONTROLLER",
           "verifier": "TARGET_CONTESTED", "result": "TARGET_CONTESTED",
           "duration_s": 25.0}
    return {row["action_id"]: row}


def _doc() -> dict:
    return {"action_id": "m1-1:10->20:100", "match_id": "m1-1",
            "source_tower": 10, "target_tower": 20}


def test_backfill_derives_dispatched_at(tmp_path):
    case_dir = _make_case(tmp_path, "m1-1_10-_20_100", _doc())
    actions = _actions_rows()
    payload = backfill_case(case_dir, _doc(), actions, {})
    assert payload["dispatched_at"] == 100.5
    assert payload["cycle_id"] == "UNKNOWN"
    assert payload["time_ordering"] == "OK"
    assert payload["origin"] == "LIVE_CONTROLLER"


def test_cycle_from_journal_used_not_unknown(tmp_path):
    case_dir = _make_case(tmp_path, "m1-1_10-_20_100", _doc())
    journal = {"recent_cycles": [{"cycle_id": 7,
                                  "dispatch": {"action_id": "m1-1:10->20:100"}}]}
    payload = backfill_case(case_dir, _doc(), _actions_rows(),
                            journal)
    assert payload["cycle_id"] == 7


def test_no_action_id_skipped_not_fabricated(tmp_path):
    case_dir = _make_case(tmp_path, "m1-1_10-_20_100",
                          {"match_id": "m1-1"})
    payload = backfill_case(case_dir, {"match_id": "m1-1"}, _actions_rows(),
                            {})
    assert payload is None
    summary = backfill_cases(tmp_path, cases_dir=tmp_path,
                             journal=None)
    assert summary["backfilled"] == 0
    assert summary["skipped"] >= 1
    assert not (case_dir / "derived-meta.json").exists()


def test_originals_never_modified(tmp_path):
    case_dir = _make_case(tmp_path, "m1-1_10-_20_100", _doc())
    original = (case_dir / "battle-differential.json").read_text(
        encoding="utf-8")
    backfill_cases(tmp_path, cases_dir=tmp_path, journal=None)
    assert (case_dir / "battle-differential.json").read_text(
        encoding="utf-8") == original
    assert (case_dir / "derived-meta.json").exists()


def test_idempotent_rerun(tmp_path):
    case_dir = _make_case(tmp_path, "m1-1_10-_20_100", _doc())
    first = backfill_cases(tmp_path, cases_dir=tmp_path, journal=None,
                           now=1.0)
    second = backfill_cases(tmp_path, cases_dir=tmp_path, journal=None,
                            now=2.0)
    assert first["backfilled"] == second["backfilled"] == 1
    payload = json.loads((case_dir / "derived-meta.json").read_text(
        encoding="utf-8"))
    assert payload["provenance"]["derived_at"] == 2.0


def test_inverted_time_ordering_detected(tmp_path):
    row = {"action_id": "m1-1:10->20:100",
           "dispatch": {"sent_at": 200.0}, "logged_at": 130.0}
    case_dir = _make_case(tmp_path, "m1-1_10-_20_100", _doc())
    payload = backfill_case(case_dir, _doc(),
                            {row["action_id"]: row}, {})
    assert payload["time_ordering"] == "INVERTED"


def test_missing_times_stay_unknown():
    payload = backfill_case(Path("m1-1_10-_20_100"), _doc(), {}, {})
    assert payload["dispatched_at"] == "UNKNOWN"
    assert payload["time_ordering"] == "UNKNOWN"
    assert payload["verifier"] == "UNKNOWN"


def test_dir_bindings_consistent_and_mismatch():
    good = backfill_case(Path("m1-1_10-_20_100"), _doc(), {}, {})
    assert good["bindings"] == {"match_consistent": True,
                                "source_consistent": True,
                                "target_consistent": True}
    bad = backfill_case(Path("m1-1_10-_20_100"),
                        {"action_id": "m1-1:10->20:100", "match_id": "m1-9",
                         "source_tower": 11, "target_tower": 20}, {}, {})
    assert bad["bindings"]["match_consistent"] is False
    assert bad["bindings"]["source_consistent"] is False


@requires_corpus
def test_real_corpus_end_to_end_originals_intact():
    real_doc = (ROOT / "runtime/research/pvp_validation"
                / "m1-1790644011_19988688-_19988687_1790644026"
                / "battle-differential.json")
    before = real_doc.read_text(encoding="utf-8")
    summary = backfill_cases(ROOT)
    after = real_doc.read_text(encoding="utf-8")
    assert before == after
    assert summary["backfilled"] >= 1
