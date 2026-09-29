"""Renderer crash UI 回歸（P1 §14）。

崩潰不再只顯示原始錯誤；恢復面板含
DETECTED/RECOVERING PAGE/RECOVERING CHROMIUM/REACQUIRING MATCH/READY/FAILED；
最後正常 frame 保留但標示 STALE FRAME · Age。
"""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
    encoding="utf-8")

RECOVERY_STATES = ["DETECTED", "RECOVERING PAGE", "RECOVERING CHROMIUM",
                   "REACQUIRING MATCH", "READY", "FAILED"]


def test_recovery_panel_exists():
    assert 'id="render-recovery"' in HTML
    assert 'id="recovery-state"' in HTML


def test_all_six_states_present():
    for state in RECOVERY_STATES:
        assert state in HTML


def test_stale_frame_age_display():
    assert "STALE FRAME · Age: " in HTML


def test_crash_detection_in_next_frame_catch():
    assert "/crash/i.test(" in HTML


def test_recovery_buttons_trigger_real_backend_commands():
    assert 'id="btn-recover-page"' in HTML
    assert 'id="btn-recover-chromium"' in HTML
    assert "runRecovery('recover-page'" in HTML
    assert "runRecovery('recover-chromium'" in HTML


def test_last_good_frame_kept_on_crash():
    """崩潰時最後正常 frame 保留，不得清空。"""
    start = HTML.find("async function nextFrame()")
    end = HTML.find("// ===== 觀戰器狀態", start)
    body = HTML[start:end]
    catch_i = body.find("}catch(e)")
    catch_body = body[catch_i:body.find("}finally{", catch_i)]
    assert "frameUrl=null" not in catch_body
    assert "$('game-image').src=''" not in catch_body


def test_reacquiring_match_honest_signal():
    """REACQUIRING MATCH 只在恢復後非 IN_MATCH 顯示，不捏造。"""
    assert "gs==='IN_MATCH'?'READY':'REACQUIRING MATCH'" in HTML


def test_eta_block_untouched():
    """GPT 的 inbound ETA 區塊不得被本任務影響。"""
    assert 'id="live-inbound-threats"' in HTML
    assert ("renderInboundThreatObservation(c.inbound_threat_observation"
            in HTML)
