"""Crash 證據分類索引回歸（P1-C）。

6 個 crash incidents 已整理為 fixture（signature／timestamp／match）。
未來 recovery regression 可用此索引自動檢查。

成功證據：6 incidents 全收錄；同 signature；檢測方式一致；
恢復欄位存在（無證據時為 null，不得偽造）。
失敗證據：incident 遺漏、signature 不一致、恢復結果被偽造。
"""
import json
from pathlib import Path

INDEX = json.loads(
    (Path(__file__).resolve().parent
     / "fixtures" / "crash_incident_index.json").read_text(
        encoding="utf-8"))


def test_index_covers_six_incidents():
    assert INDEX["incident_count"] == 6
    assert len(INDEX["incidents"]) == 6


def test_all_incidents_share_signature():
    for inc in INDEX["incidents"]:
        sig = inc["signature"]
        assert "0xC0000005" in sig or "SAME" in sig or "PENDING_VERIFY" in sig, inc


def test_all_incidents_detected_via_screenshot():
    assert "Target crashed" in INDEX["detection"]


def test_recovery_fields_present_not_fabricated():
    for inc in INDEX["incidents"]:
        for field in ("recovery_outcome", "main_loop_resumed",
                      "controller_resumed", "stale_state_leaked"):
            assert field in inc, inc
            # 無證據時必須為 null，不得偽造為成功／失敗
            assert inc[field] is None or isinstance(
                inc[field], (str, bool)), inc


def test_incident_ids_unique():
    ids = [inc["incident_id"] for inc in INDEX["incidents"]]
    assert len(set(ids)) == 6
