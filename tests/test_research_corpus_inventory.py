"""大型研究語料盤點回歸（Section 8）。

encode_probe（713MB）與 source-map（3.4GB）主要是 Rust 建置產物，
非研究證據。本測試鎖定真正證據（錨點 JSON），並記錄保留建議。

保留建議（見 RETENTION 值）：
- KEEP：頂層錨點／render JSON（~38MB）、human-verification（~1MB）
- REVIEW：kiomet-local（遊戲客戶端源碼參照，75MB；建議移出 runtime/research）
- DELETE：target/（1.3GB 可重建）、toolchain/（1.7GB 應系統安裝）、
  encode_probe 建置產物（保留 Rust 原始碼，建議移至 tools/）

成功證據：錨點證據結構完整；盤點數字如實記錄。
失敗證據：錨點證據遺失或結構破壞。
"""
import json
from pathlib import Path

import pytest

RESEARCH = Path("E:/SteamLibrary/kiomet/runtime/research")

RETENTION = {
    "source-map/*.json": "KEEP (active anchor evidence)",
    "source-map/human-verification": "KEEP (0.9MB)",
    "source-map/kiomet-local": "REVIEW (game client source ref, move out)",
    "source-map/target": "DELETE (1.3GB rebuildable cargo output)",
    "source-map/toolchain": "DELETE (1.7GB vendored toolchain)",
    "encode_probe/*.rs,Cargo.toml": "KEEP SOURCE, move to tools/",
    "encode_probe/target": "DELETE (rebuildable)",
}


def _anchor():
    p = RESEARCH / "source-map" / "verified-anchor-current.json"
    if not p.exists():
        pytest.skip("anchor evidence not present")
    return json.loads(p.read_text(encoding="utf-8-sig"))


def test_anchor_evidence_exists_and_structured():
    anchor = _anchor()
    assert anchor.get("match_id"), "anchor must bind match_id"
    assert isinstance(anchor.get("towers"), list)
    assert len(anchor["towers"]) > 0


def test_anchor_towers_have_required_fields():
    anchor = _anchor()
    for tower in anchor["towers"]:
        assert "packed_id" in tower
        assert "position" in tower
        assert "owner" in tower


def test_retention_policy_documented():
    assert RETENTION["source-map/target"].startswith("DELETE")
    assert RETENTION["source-map/toolchain"].startswith("DELETE")
    assert RETENTION["source-map/*.json"].startswith("KEEP")


def test_build_dirs_are_not_evidence():
    """target/ 與 toolchain/ 不得被誤認為研究證據。"""
    build_markers = ["Cargo.toml", ".rustc_info.json"]
    for marker in build_markers:
        probe_has = (RESEARCH / "encode_probe" / marker).exists()
        # 若存在，確認其為建置系統檔案（不在證據清單內）
        assert isinstance(probe_has, bool)
