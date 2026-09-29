"""驗證器 UNKNOWN 回歸（P0-C）。

第二動作 verifier=UNKNOWN 且對局已結束、pending capture 懸置。
UNKNOWN 不得被升級為 TARGET_CONTESTED／CAPTURED／VERIFIED_MOVE。

Finalize 規則：
- match_id 不符 → MATCH_ENDED（終端狀態，非 UNKNOWN）
- force 未觀察到 → UNKNOWN（fail-closed，不得升級）
- pending capture 無 after 狀態 → UNKNOWN（不得假裝已驗證）

成功證據：UNKNOWN 維持 UNKNOWN；MATCH_ENDED 明確區分。
失敗證據：UNKNOWN 被升級為任何成功狀態。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.proposal import ActionProposal, verify_post_action


def _proposal(**over):
    base = {
        "match_id": "m1",
        "created_at": time.time(),
        "source_tower_id": 10,
        "target_tower_id": 20,
    }
    base.update(over)
    return ActionProposal(**base)


def _before(**over):
    base = {
        "match_id": "m1",
        "source": {"owner": "SELF", "units": {"Soldier": 12}},
        "target": {"owner": "NEUTRAL", "units": {"Soldier": 0}},
    }
    base.update(over)
    return base


def _after(**over):
    base = {
        "match_id": "m1",
        "source": {"owner": "SELF", "units": {"Soldier": 0}},
        "target": {"owner": "NEUTRAL", "units": {"Soldier": 0}},
    }
    base.update(over)
    return base


def test_force_not_observed_not_upgraded():
    """force_observed=False → 不得升級為成功狀態。

    來源確實改變（兵派出）但 force 未觀察到 → SOURCE_CHANGED（事實），
    絕非 TARGET_CONTESTED／CAPTURED／FORCE_OBSERVED。
    """
    result = verify_post_action(
        _before(), _after(force_observed=False), _proposal())
    assert result not in ("TARGET_CONTESTED", "TARGET_CAPTURED",
                          "FORCE_OBSERVED", "VERIFIED_MOVE")


def test_force_match_not_found_not_upgraded():
    """force_match NOT_FOUND → _force_credit_ok 拒絕 → 不得升級。"""
    result = verify_post_action(
        _before(),
        _after(force_observed=True, force_match="FORCE_MATCH_NOT_FOUND"),
        _proposal())
    assert result != "FORCE_OBSERVED"
    assert result not in ("TARGET_CONTESTED", "TARGET_CAPTURED")


def test_force_match_derived_not_credited():
    """DERIVED 不予信用 → UNKNOWN（不得升級為 FORCE_OBSERVED）。"""
    result = verify_post_action(
        _before(),
        _after(force_observed=True, force_match="DERIVED"),
        _proposal())
    assert result != "FORCE_OBSERVED"


def test_match_ended_is_terminal_not_unknown():
    """match_id 不符 → MATCH_ENDED（明確終端狀態）。"""
    result = verify_post_action(
        _before(), _after(match_id="m2"), _proposal(match_id="m1"))
    assert result == "MATCH_ENDED"


def test_pending_capture_without_after_state_is_unknown():
    """pending capture 無 after 狀態 → UNKNOWN（不得假裝已驗證）。

    Finalize 規則：對局結束時，未解決的 pending capture
    必須記為 UNKNOWN，不得升級為任何成功狀態。
    """
    # 空 after（無觀察資料）
    result = verify_post_action(
        _before(), {"match_id": "m1"}, _proposal())
    assert result == "UNKNOWN"


def test_source_unchanged_without_force_is_unknown():
    """來源未變且無 force 證據 → UNKNOWN（非 ACTION_SENT 誤判）。

    注意：after.get('sent') 為真時回 ACTION_SENT；
    但無 sent 旗標且來源未變時必須是 UNKNOWN。
    """
    result = verify_post_action(
        _before(source={"owner": "SELF", "units": {"Soldier": 12}}),
        _after(source={"owner": "SELF", "units": {"Soldier": 12}}),
        _proposal())
    # 來源未變、目標未變、無 force → UNKNOWN
    assert result == "UNKNOWN"
