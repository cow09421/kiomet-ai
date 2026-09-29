"""錨點品質閘共用邏輯：抽檢探測首塔，拒絕細胞誤捕等壞錨點。"""
import json
from pathlib import Path

from kiomet_ai.observe import TOWER_TYPES


def anchor_quality_ok(root: Path, match_id: str) -> bool:
    """探測首 3 塔：tag 須 0/1、+46 合法塔型；全集不得有 ≥8 連號。"""
    try:
        probe = json.loads((root / f"runtime/research/units/unit-struct-probe-{match_id}.json").read_text(encoding="utf8"))
    except (OSError, ValueError):
        return False
    rows = probe.get("rows", [])[:3]
    if len(rows) < 3:
        return False
    good = 0
    for row in rows:
        raw = row["bytes"][32:32 + 48]
        if raw[38] in (0, 1) and 0 <= raw[46] < len(TOWER_TYPES):
            good += 1
    if good < 2:
        return False
    ids = sorted(r["packed_id"] for r in probe.get("rows", []))
    run = 1
    for a, b in zip(ids, ids[1:]):
        run = run + 1 if b == a + 1 else 1
        if run >= 8:
            return False
    return True
