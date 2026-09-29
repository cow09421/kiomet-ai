"""控制權互斥回歸（P0）。

AI 與 HUMAN 互斥；REACQUIRING/NONE 兩者皆禁；
交還 AI 需所有 freshness 檢查通過；換局安全重置。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from kiomet_ai.control_owner import ControlOwner


def test_default_is_ai():
    owner = ControlOwner()
    assert owner.owner == "AI"
    assert owner.allow_ai_dispatch() is True
    assert owner.allow_manual_input() is False


def test_bad_owner_rejected():
    with pytest.raises(ValueError):
        ControlOwner("WIZARD")


def test_manual_engages_and_blocks_ai():
    owner = ControlOwner()
    result = owner.request_manual()
    assert result["owner"] == "HUMAN"
    assert owner.allow_manual_input() is True
    assert owner.allow_ai_dispatch() is False


def test_ai_dispatch_blocked_in_human():
    owner = ControlOwner()
    owner.request_manual()
    assert owner.allow_ai_dispatch() is False


def test_manual_input_blocked_in_reacquiring():
    owner = ControlOwner()
    owner.request_manual()
    owner.request_return_to_ai()
    assert owner.owner == "REACQUIRING"
    assert owner.allow_manual_input() is False
    assert owner.allow_ai_dispatch() is False


def test_ai_dispatch_blocked_in_reacquiring():
    owner = ControlOwner()
    owner.request_return_to_ai()
    assert owner.allow_ai_dispatch() is False


def test_return_requires_all_checks():
    owner = ControlOwner()
    owner.request_manual()
    owner.request_return_to_ai()
    owner.note_return_check("fresh_observation")
    owner.note_return_check("fresh_camera")
    partial = owner.complete_return()
    assert partial["ok"] is False
    assert partial["code"] == "RETURN_NOT_READY"
    assert "mapping_rebuilt" in partial["missing"]
    assert owner.owner == "REACQUIRING"


def test_return_completes_only_when_all_fresh():
    owner = ControlOwner()
    owner.request_manual()
    owner.request_return_to_ai()
    for name in ("fresh_observation", "fresh_camera", "mapping_rebuilt",
                 "match_verified"):
        owner.note_return_check(name)
    result = owner.complete_return()
    assert result["ok"] is True
    assert result["code"] == "AUTONOMY_RESUMED"
    assert owner.allow_ai_dispatch() is True


def test_complete_return_without_reacquiring_fails():
    owner = ControlOwner()
    assert owner.complete_return()["code"] == "NOT_REACQUIRING"


def test_owner_survives_ui_refresh():
    owner = ControlOwner()
    owner.request_manual()
    # 一般刷新只讀取狀態，不得改變 owner
    for _ in range(5):
        owner.status()
    assert owner.owner == "HUMAN"


def test_match_change_resets_to_ai():
    owner = ControlOwner()
    owner.on_match_change("m1")
    owner.request_manual()
    assert owner.owner == "HUMAN"
    changed = owner.on_match_change("m2")
    assert changed is True
    assert owner.owner == "AI"
    assert owner.allow_ai_dispatch() is True


def test_same_match_no_reset():
    owner = ControlOwner()
    owner.on_match_change("m1")
    owner.request_manual()
    assert owner.on_match_change("m1") is False
    assert owner.owner == "HUMAN"


def test_none_owner_blocks_both():
    owner = ControlOwner("NONE")
    assert owner.allow_ai_dispatch() is False
    assert owner.allow_manual_input() is False


def test_status_shape():
    status = ControlOwner().status()
    for key in ("owner", "ai_dispatch_allowed", "manual_input_allowed",
                "match_id", "return_checks", "owner_since"):
        assert key in status
