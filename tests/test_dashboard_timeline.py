"""Dashboard 行動時間線回歸（P1 §12）。

新增 ACTION TIMELINE 區塊：最近 50 筆行動，
每筆顯示 match/cycle/kind/source/target/reason/origin/verdict；
缺欄顯示 UNKNOWN，不編造。
既有 RECENT AUTONOMOUS ACTIONS 表（GPT colSpan=9 契約）不得被動。
"""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def test_timeline_section_exists():
    assert 'id="action-timeline"' in HTML
    assert 'id="timeline-body"' in HTML


def test_timeline_columns_present():
    for header in ("對局", "週期", "種類", "原因", "來源端", "判定"):
        assert f"<th>{header}</th>" in HTML


def test_cycle_enriched_from_journal():
    assert "recent_cycles" in HTML


def test_rows_limit_50():
    assert "slice(0,50)" in HTML


def test_unknown_fallback_never_fabricated():
    assert "a.reason||'UNKNOWN'" in HTML
    assert "a.origin||'UNKNOWN'" in HTML
    assert "a.verifier||a.result||'UNKNOWN'" in HTML


def test_recent_actions_table_untouched():
    """GPT 的 colSpan=9 契約與 actions-body 不得被本任務異動。"""
    assert 'id="actions-body"' in HTML
    assert 'td.colSpan=9' in HTML
    assert "<th>種類</th>" in HTML
    assert "<th>攻擊驗證</th>" in HTML


def test_eta_block_untouched():
    """GPT 的 inbound ETA 區塊不得被本任務影響。"""
    assert 'id="live-inbound-threats"' in HTML
    assert ("renderInboundThreatObservation(c.inbound_threat_observation"
            in HTML)


def test_viewer_isolation_region_untouched():
    """GPT 的隔離契約區段不得被本任務移動或修改。"""
    assert "// ===== 觀戰器狀態（只存前端，幀更新不重設） =====" in HTML
    assert "// ===== 戰術圖 =====" in HTML
