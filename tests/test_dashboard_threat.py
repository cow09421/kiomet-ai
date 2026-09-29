"""儀表板威脅／ETA 顯示回歸（P1-B＋欄位重映射）。

儀表板必須顯示威脅數量／最近威脅／防守／攻擊／仲裁，
資料來源為 heartbeat 真實欄位（threat_state／defense_assessment／
pvp_arbitration／attack_assessment）。
後端未提供資料時，一律顯示 UNKNOWN，不得顯示 0 或空值。

成功證據：五個元素存在且預設 UNKNOWN；JS 引用真實 heartbeat 欄位。
失敗證據：元素缺失、預設為 0／空、或 JS 引用不存在的欄位。
"""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def test_threat_display_elements_exist():
    assert 'id="live-threat-count"' in HTML
    assert 'id="live-nearest-threat"' in HTML
    assert 'id="live-defense-status"' in HTML
    assert 'id="live-attack-status"' in HTML
    assert 'id="live-arbitration-result"' in HTML


def test_threat_elements_default_unknown_not_zero():
    for element_id in ("live-threat-count", "live-nearest-threat",
                       "live-defense-status", "live-attack-status",
                       "live-arbitration-result"):
        # 元素初始內容必須是 UNKNOWN，不得是 0 或空
        assert f'id="{element_id}">UNKNOWN' in HTML


def test_js_references_real_heartbeat_fields():
    assert "c.threat_state" in HTML
    assert "c.defense_assessment" in HTML
    assert "c.attack_assessment" in HTML
    assert "c.pvp_arbitration" in HTML


def test_js_does_not_reference_phantom_fields():
    assert "c.threat_count" not in HTML
    assert "c.nearest_threat" not in HTML
    assert "c.defense_status" not in HTML
    assert "c.attack_status" not in HTML
    assert "c.arbitration_result" not in HTML


def test_inbound_threats_element_preserved():
    assert 'id="live-inbound-threats"' in HTML
    assert "renderInboundThreatObservation" in HTML
