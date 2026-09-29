"""儀表板生命週期真實性回歸（P0 §3）。

NEXT ACTION 只在 GAME STATE=IN_MATCH 顯示目前資料；
MENU／JOINING／RESULT_SCREEN／DISCONNECTED／UNKNOWN 顯示 NO ACTIVE MATCH；
上一局資料放 LAST MATCH 區，不得冒充目前資料。
UNKNOWN 不得轉 0。
"""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
    encoding="utf-8")

LIFECYCLE_STATES = ["MENU", "JOINING", "IN_MATCH", "RESULT_SCREEN",
                    "DISCONNECTED", "UNKNOWN"]


def test_lifecycle_helper_exists():
    assert "function lifecycleOf(" in HTML


def test_lifecycle_covers_all_required_states():
    for state in LIFECYCLE_STATES:
        assert f"'{state}'" in HTML


def test_next_action_gated_on_in_match():
    assert "lc==='IN_MATCH'" in HTML
    assert "lc!=='IN_MATCH'" in HTML


def test_no_active_match_pathway_exists():
    assert "NO ACTIVE MATCH（沒有進行中的對局）" in HTML


def test_last_match_section_exists():
    assert 'id="last-match"' in HTML
    assert "LAST MATCH" in HTML


def test_last_match_clearly_labeled_not_current():
    assert "上一局" in HTML
    assert "非目前資料" in HTML


def test_na_fallback_not_zero():
    assert "N/A（沒有進行中的對局）" in HTML


def test_world_top_also_gated():
    """Top Proposal 也不得在非對局狀態冒充目前資料。"""
    assert "lc==='IN_MATCH'&&(s.next_action&&s.next_action.source!=null)" in \
        HTML


def test_eta_block_untouched():
    """GPT 的 inbound ETA 區塊不得被本任務影響。"""
    assert 'id="live-inbound-threats"' in HTML
    assert ("renderInboundThreatObservation(c.inbound_threat_observation"
            in HTML)
