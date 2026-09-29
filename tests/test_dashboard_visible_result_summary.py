"""LIVE VIEW 結算資訊必須只顯示同局、可見 UI 來源的摘要。"""
from pathlib import Path


HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def test_live_view_has_unknown_score_and_rank_fallback():
    assert 'id="live-score-rank">UNKNOWN<' in HTML
    assert "resultSummary.high_score??'UNKNOWN'" in HTML
    assert "resultSummary.current_rank??'UNKNOWN'" in HTML


def test_result_summary_must_match_visible_source_and_current_match():
    assert "resultSummary.source==='VISIBLE_UI_DOM_TEXT'" in HTML
    assert "resultSummary.match_id===(gg.match||{}).id" in HTML
    assert "const visibleScore=summaryMatches?" in HTML
    assert "const visibleRank=summaryMatches?" in HTML


def test_score_and_rank_are_rendered_as_text():
    assert "$('live-score-rank').textContent='本局最高分：'+visibleScore+' · 階級：'+visibleRank" in HTML
    assert "['本局最高分',visibleScore],['Rank',visibleRank]" in HTML
    assert "live-score-rank').innerHTML" not in HTML
