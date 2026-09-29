"""威脅狀態橋接測試（整合腳手架）。

把 LiveController threat_state 列格式映射到 replay 快照 schema。
目前正式列缺 progress／distance 輸入，橋接後 ETA 重算必須是
ETA_UNKNOWN（不信任記錄值、不編造），待 GPT 補欄位後升級。

只含測試內 adapter，不改任何 Production 檔案。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.replay import (_normalize_units, replay_threat_waves,
                              validate_threat_snapshot)


def adapt_threat_row(row: dict | None) -> dict | None:
    """Live threat_state 列 → replay 快照 threat。

    正式列欄位：match_id／cycle_id／source_force_id／owner_id／
    relation／source_tower／target_tower／units／eta_ticks／
    eta_seconds／eta_status／confidence／freshness／provenance。
    缺 progress／distance_m → 重算所需輸入不存在。
    """
    if not isinstance(row, dict):
        return None
    owner_id = row.get("owner_id")
    if type(owner_id) is not int or owner_id <= 0:
        return None
    units = _normalize_units(row.get("units"))
    if units is None:
        return None
    recorded = row.get("eta_ticks")
    if recorded is not None and (
            type(recorded) is not int or recorded < 0):
        recorded = None
    return {
        "owner_id": owner_id,
        "owner_relation": row.get("relation"),
        "units": units,
        "progress": row.get("progress", 0)
        if type(row.get("progress", 0)) is int else 0,
        "speed_flag": None,
        "eta_ticks": recorded,
        "distance_m": row.get("distance_m"),
        "samples": None,
        "_inputs_complete": (
            type(row.get("progress")) is int
            and row.get("distance_m") is not None),
    }


def _live_row(**over):
    base = {"match_id": "m1", "cycle_id": 3, "source_force_id": 99,
            "owner_id": 26, "relation": "UNKNOWN",
            "source_tower": 16384182, "target_tower": 16449718,
            "units": {"Shield": 0, "Fighter": 1, "Chopper": 0,
                      "Bomber": 1, "Tank": 0, "Soldier": 0,
                      "Shell": 0, "Emp": 0, "Nuke": 0, "Ruler": 0},
            "eta_ticks": 88, "eta_seconds": 22.0, "eta_status": "CANDIDATE",
            "confidence": "CANDIDATE", "freshness": "FRESH",
            "provenance": {"source": "WASM_INBOUND_COLLECTION"}}
    base.update(over)
    return base


def _snap(threats, match_id="m1", observed_at=1790641578.9):
    return {"match_id": match_id, "observed_at": observed_at,
            "target_tower_id": 16449718, "threats": threats}


def test_bridge_preserves_relation_unknown():
    adapted = adapt_threat_row(_live_row())
    assert adapted is not None
    assert adapted["owner_relation"] == "UNKNOWN"
    out = replay_threat_waves(_snap([adapted]), now=1790641578.9)
    assert out["verdicts"][0]["owner_relation"] == "UNKNOWN"


def test_bridge_without_inputs_yields_eta_unknown():
    adapted = adapt_threat_row(_live_row())
    assert adapted["_inputs_complete"] is False
    out = replay_threat_waves(_snap([adapted]), now=1790641578.9)
    assert out["verdicts"][0]["eta_verdict"] == "ETA_UNKNOWN"
    assert out["status"] == "REPLAYED"


def test_bridge_does_not_trust_recorded_ticks():
    """即使列帶 recorded eta，無輸入仍不判 MATCH。"""
    adapted = adapt_threat_row(_live_row(eta_ticks=88))
    out = replay_threat_waves(_snap([adapted]), now=1790641578.9)
    assert out["verdicts"][0]["eta_verdict"] == "ETA_UNKNOWN"
    assert out["status"] != "FLAGGED"


def test_bridge_with_inputs_enables_match():
    adapted = adapt_threat_row(_live_row(progress=18, distance_m=90.0))
    assert adapted["_inputs_complete"] is True


def test_bridge_rejects_bad_owner():
    assert adapt_threat_row(_live_row(owner_id=0)) is None
    assert adapt_threat_row(_live_row(owner_id="26")) is None
    assert adapt_threat_row(None) is None


def test_bridge_rejects_bad_units():
    assert adapt_threat_row(_live_row(units=None)) is None
    assert adapt_threat_row(_live_row(units={"Soldier": -1})) is None


def test_bridge_schema_accepts_adapted_row():
    adapted = adapt_threat_row(_live_row())
    assert adapted is not None
    clean = {k: v for k, v in adapted.items()
             if not k.startswith("_")}
    checked = validate_threat_snapshot(_snap([clean]))
    assert checked["valid"] is True, checked["errors"]
