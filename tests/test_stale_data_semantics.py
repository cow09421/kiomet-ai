"""資料新鮮度語意回歸（P1 §4+15）。

Backend ONLINE/OFFLINE 指示；fetch 失敗時目前資料標 STALE 不冒充 LIVE；
每項重要資料攜帶 updated_at/age/provenance；UNKNOWN 不得轉 0。
"""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def test_backend_online_offline_indicator_exists():
    assert 'id="backend-state"' in HTML
    assert "ONLINE" in HTML
    assert "OFFLINE" in HTML


def test_backend_last_success_and_data_age():
    assert 'id="backend-last-success"' in HTML
    assert 'id="backend-data-age"' in HTML


def test_fetch_failure_marks_stale():
    """fetch /api/status 失敗時：current data = STALE，不看起來像 LIVE。"""
    assert "backendOffline" in HTML
    assert "STALE（後端離線）" in HTML


def test_status_success_sets_backend_online():
    assert "backendOnline" in HTML


def test_unknown_not_becomes_zero():
    assert "next-source>0<" not in HTML
    assert "N/A（沒有進行中的對局）" in HTML


def test_eta_block_untouched():
    """GPT 的 inbound ETA 區塊不得被本任務影響。"""
    assert 'id="live-inbound-threats"' in HTML
    assert ("renderInboundThreatObservation(c.inbound_threat_observation"
            in HTML)


def test_lifecycle_gate_untouched():
    """本任務不得破壞 lifecycle 閘。"""
    assert "function lifecycleOf(" in HTML
    assert "lc==='IN_MATCH'" in HTML
