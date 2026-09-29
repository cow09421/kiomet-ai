"""重播報告刷新回歸（P0-A）。

replay-report.json 必須涵蓋 13 個案例（9 舊＋4 新）。
每個案例輸出 input／prediction／truth／support／differential／reason。
UNKNOWN 不得轉成假值。

成功證據：13 案例全重播；3 flagged 皆為新局案例且原因明確；
UNKNOWN dispatch（4517）維持 DISPATCH_NOT_OBSERVED。
失敗證據：案例遺漏、UNKNOWN 被升級、flag 誤發。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.replay import load_case, replay_case, replay_corpus

ROOT = Path("E:/SteamLibrary/kiomet/runtime/research/pvp_validation")

requires_corpus = pytest.mark.skipif(
    not (ROOT / "replay-report.json").exists(),
    reason="runtime corpus not present (gitignored)")


@requires_corpus
def test_corpus_covers_thirteen_cases():
    report = replay_corpus(ROOT)
    summary = report["summary"]
    assert summary["cases"] == 13, summary
    assert summary["replayed"] + summary["flagged"] == 13
    assert summary["skipped"] == []


@requires_corpus
def test_each_case_has_required_output_fields():
    report = replay_corpus(ROOT)
    for case in report["cases"]:
        assert "case_id" in case
        assert "match_id" in case
        assert "action_id" in case
        assert "id_evidence" in case
        assert "temporal" in case
        assert "force_identity" in case
        assert "force_observed" in case
        assert "runtime_prediction" in case
        assert "flags" in case
        assert "status" in case


@requires_corpus
def test_unknown_dispatch_stays_unknown():
    case = load_case(ROOT / "m1-1790644011_19988687-_19988686_1790644517")
    out = replay_case(case)
    assert out["force_observed"]["status"] == "DISPATCH_NOT_OBSERVED"
    assert out["status"] == "FLAGGED"


@requires_corpus
def test_verified_dispatch_not_flagged():
    case = load_case(ROOT / "m1-1790644011_19988688-_19988687_1790644026")
    out = replay_case(case)
    assert out["force_observed"]["status"] == "FORCE_OBSERVED"
    assert out["force_identity"]["status"] == "IDENTITY_VERIFIED"
    assert out["flags"] == []
    assert out["status"] == "REPLAYED"


@requires_corpus
def test_new_match_self_id_learned():
    report = replay_corpus(ROOT)
    assert 71 in report["summary"]["self_ids_found"]
    assert 5 in report["summary"]["self_ids_found"]


@requires_corpus
def test_flagged_cases_are_new_match_only():
    report = replay_corpus(ROOT)
    for case in report["cases"]:
        if case["status"] == "FLAGGED":
            assert case["match_id"] == "m1-1790644011", case["case_id"]
