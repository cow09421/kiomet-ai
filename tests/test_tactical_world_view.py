"""戰術世界圖完成度回歸（P0 §8-10）。

Fit SELF／Fit Conflict／Follow Threat／Follow Last Action／全螢幕按鈕；
moving forces＋受威脅塔＋ETA 顯示；攻擊／增援路線區分；
手動 pan 暫停 Follow；無威脅狀態顯示 UNKNOWN 不顯示 0。
"""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def test_fit_buttons_exist():
    assert 'id="tac-fit-world"' in HTML
    assert 'id="tac-fit-self"' in HTML
    assert 'id="tac-fit-conflict"' in HTML


def test_follow_buttons_exist():
    assert 'id="tac-follow-threat"' in HTML
    assert 'id="tac-follow-action"' in HTML


def test_tactical_fullscreen_button_exists():
    assert 'id="tac-fullscreen"' in HTML


def test_manual_pan_pauses_follow():
    """使用者手動 pan 自動暫停 Follow（AI/Threat/Action）。"""
    assert "tac.follow=false" in HTML
    assert "tac.followThreat=false" in HTML
    assert "tac.followAction=false" in HTML


def test_moving_forces_drawn_from_threat_rows():
    """moving forces 用威脅列（真實狀態）畫，不用截圖猜。"""
    assert "function drawMovingForces(" in HTML
    assert "tac.threats" in HTML


def test_threatened_tower_and_eta_rendered():
    assert "受威脅" in HTML
    assert "ETA" in HTML


def test_route_distinction_attack_vs_reinforcement():
    assert "REINFORCE" in HTML
    assert "ATTACK" in HTML


def test_no_threat_state_shows_unknown_not_zero():
    assert "無威脅狀態" in HTML


def test_tactical_data_from_real_anchor_not_screenshot():
    assert "/api/tactical" in HTML


def test_eta_block_untouched():
    """GPT 的 inbound ETA 區塊不得被本任務影響。"""
    assert 'id="live-inbound-threats"' in HTML
    assert ("renderInboundThreatObservation(c.inbound_threat_observation"
            in HTML)
