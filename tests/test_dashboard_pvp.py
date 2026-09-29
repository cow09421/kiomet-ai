"""儀表板 PvP 可視化回歸（P1-C）。

新增：活躍威脅、棄權原因、最近 PvP 行動。
棄權原因接 controller.no_action_reason；最近行動接 recent_decisions；
活躍威脅無後端欄位→UNKNOWN 契約（不顯示 0、不假 READY）。
不碰 GPT 的 ETA 區塊（live-inbound-threats 原樣保留）。
"""
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1]
        / "src" / "kiomet_ai" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def test_pvp_visibility_elements_exist():
    assert 'id="live-active-threats"' in HTML
    assert 'id="live-abstain-reason"' in HTML
    assert 'id="live-last-pvp-action"' in HTML


def test_pvp_elements_default_unknown_not_zero():
    for element_id in ("live-active-threats", "live-abstain-reason",
                       "live-last-pvp-action"):
        assert f'id="{element_id}">UNKNOWN' in HTML
        assert f'id="{element_id}">0<' not in HTML


def test_abstain_reason_wired_to_controller():
    assert "c.no_action_reason" in HTML


def test_last_pvp_action_wired_to_recent_decisions():
    assert "s.recent_decisions" in HTML


def test_eta_block_untouched():
    """GPT 的 ETA 區塊不得被本任務異動邏輯影響。"""
    assert 'id="live-inbound-threats"' in HTML
    assert "renderInboundThreatObservation(c.inbound_threat_observation" in HTML


def test_actions_table_has_kind_and_attack_validation_columns():
    assert "<th>種類</th>" in HTML
    assert "<th>攻擊驗證</th>" in HTML
    assert 'td.colSpan=9' in HTML
    assert 'td.colSpan=7' not in HTML


def test_action_kind_and_attack_status_rendered_with_unknown_fallback():
    assert "a.action_kind??'UNKNOWN'" in HTML
    assert "a.attack_validation_status??'UNKNOWN'" in HTML


def test_verifier_column_never_merged_with_attack_status():
    """靜態預測不得標成已驗證：驗證欄只讀 verifier／result。"""
    import re
    m = re.search(r"const tds=\[(.*?)\];", HTML)
    assert m is not None
    cells = m.group(1)
    verifier_cell = cells.split(",")[5]
    assert "attack_validation_status" not in verifier_cell
    assert "attack_proof_bundle" not in verifier_cell
    assert "a.verifier" in verifier_cell
