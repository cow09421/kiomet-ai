"""測試分層 meta 回歸（P1 §13）。

分層表本身必須有效：檔案存在、無重複、不含 GPT 檔案、
未知分層拋錯；smoke 保持小而快。
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path("E:/SteamLibrary/kiomet")


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "tiers_tool", ROOT / "tools/test_tiers.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["tiers_tool"] = module
    spec.loader.exec_module(module)
    return module


_tool = _load_tool()
TIERS = _tool.TIERS
tier_files = _tool.tier_files

FOREIGN_TESTS = {
    "test_live_wiring.py", "test_pvp_live.py", "test_pvp.py",
    "test_round11_gates.py", "test_dry_rank.py", "test_live_threat_state.py",
    "test_pvp_attack_identity_validation.py",
}


def test_all_listed_files_exist():
    missing = [n for tier in TIERS.values() for n in tier
               if not (ROOT / "tests" / n).exists()]
    assert missing == []


def test_no_file_in_two_tiers():
    seen: dict = {}
    dupes = set()
    for tier, names in TIERS.items():
        for name in names:
            if name in seen:
                dupes.add(name)
            seen[name] = tier
    assert not dupes, f"files in multiple tiers: {dupes}"


def test_no_foreign_files_listed():
    listed = {n for tier in TIERS.values() for n in tier}
    assert not (listed & FOREIGN_TESTS)


def test_tier_files_resolve_under_tests():
    for tier in TIERS:
        for path in tier_files(tier):
            assert Path(path).parent == ROOT / "tests", path


def test_unknown_tier_raises():
    with pytest.raises(KeyError):
        tier_files("nope")


def test_smoke_stays_small():
    assert len(TIERS["smoke"]) <= 8


def test_expected_tiers_present():
    assert set(TIERS) == {"smoke", "pvp", "replay", "evidence",
                          "runtime-contract", "recovery"}
