"""RECENT AUTONOMOUS ACTIONS 表格欄位回歸（分數／前檢／驗證）。

成功證據：表頭含分數、前檢、驗證、種類、攻擊驗證欄；
空狀態 colSpan 與欄數一致（9）；
JS 渲染引用 planner_score／preflight／verifier 欄位。
失敗證據：欄位被移除或 colSpan 與欄數不符（表格破版）。
"""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def test_actions_table_has_score_preflight_verifier_columns():
    assert "<th>分數</th>" in HTML
    assert "<th>前檢</th>" in HTML
    assert "<th>驗證</th>" in HTML
    assert "<th>種類</th>" in HTML
    assert "<th>攻擊驗證</th>" in HTML


def test_empty_state_colspan_matches_nine_columns():
    actions_empty = [line for line in HTML.splitlines()
                     if "$('actions-body').replaceChildren(tr)" in line]
    assert len(actions_empty) == 1
    assert "td.colSpan=9" in actions_empty[0]


def test_row_renderer_uses_rich_fields():
    assert "a.planner_score" in HTML
    assert "a.preflight" in HTML
    assert "a.verifier||a.result" in HTML


def test_live_view_displays_candidate_eta_with_non_authorizing_label():
    assert 'id="live-inbound-threats"' in HTML
    assert "renderInboundThreatObservation" in HTML
    assert "候選，不授權行動" in HTML
    assert "STALE（候選 ETA 已過期）" in HTML
