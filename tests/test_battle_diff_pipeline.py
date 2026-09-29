"""戰鬥差分證據管線回歸（P0-A）。

未來 GPT 產出 enemy combat evidence 後可直接餵入管線，
無需等待真實敵方案例。本檔以合成敵方案例鎖定契約。

管線：證據→評估器輸入→預測→真值→差分→報告。
UNKNOWN 永不轉成假值。

成功證據：勝／負／不符／無真值／非法輸入各有明確輸出。
失敗證據：非法證據被評估，或差分被誤判為一致。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.replay import (run_battle_differential,
                              validate_battle_evidence_schema)


def _units6(**kw):
    out = {n: 0 for n in ("Shield", "Fighter", "Chopper", "Bomber",
                          "Tank", "Soldier")}
    out.update(kw)
    return out


def _evidence(**over):
    base = {
        "attacker_units": _units6(Soldier=20),
        "defender_units": _units6(Soldier=5),
        "tower_type": "Cliff",
        "self_id": 5,
        "enemy_id": 17,
    }
    base.update(over)
    return base


def test_attacker_win_match():
    out = run_battle_differential(
        _evidence(recorded_truth={"winner": "attacker"}))
    assert out["support_status"] == "MATCH"
    assert out["differential"] == "PREDICTION_MATCHES_TRUTH"
    assert out["prediction"]["winner"] == "attacker"


def test_defender_win_match():
    out = run_battle_differential(_evidence(
        attacker_units=_units6(Soldier=3),
        defender_units=_units6(Soldier=30),
        recorded_truth={"winner": "defender"}))
    assert out["support_status"] == "MATCH"
    assert out["prediction"]["winner"] == "defender"


def test_prediction_truth_mismatch():
    out = run_battle_differential(
        _evidence(recorded_truth={"winner": "defender"}))
    assert out["support_status"] == "MISMATCH"
    assert out["differential"] == "PREDICTION_DIFFERS_FROM_TRUTH"


def test_no_truth_predicted_only():
    out = run_battle_differential(_evidence())
    assert out["support_status"] == "PREDICTED_NO_TRUTH"
    assert out["prediction"]["winner"] == "attacker"
    assert out["recorded_truth"] is None


def test_missing_field_invalid():
    out = run_battle_differential({"attacker_units": _units6(Soldier=1)})
    assert out["support_status"] == "UNKNOWN"
    assert out["differential"] == "EVIDENCE_INVALID"
    assert any("missing-field" in e for e in out["reason"].split(";"))


def test_invalid_units_rejected():
    out = run_battle_differential(_evidence(
        attacker_units={"Soldier": -1}))
    assert out["support_status"] == "UNKNOWN"
    assert out["differential"] == "EVIDENCE_INVALID"


def test_self_enemy_id_conflict_rejected():
    out = run_battle_differential(_evidence(self_id=5, enemy_id=5))
    assert out["support_status"] == "UNKNOWN"
    assert "self-enemy-id-conflict" in out["reason"]


def test_unknown_tower_type_rejected():
    out = run_battle_differential(_evidence(tower_type="UnknownType"))
    assert out["support_status"] == "UNKNOWN"
    assert "tower-capacity-unknown" in out["reason"]


def test_non_object_evidence_rejected():
    out = run_battle_differential(None)
    assert out["support_status"] == "UNKNOWN"
    assert out["differential"] == "EVIDENCE_INVALID"


def test_malformed_truth_not_compared():
    out = run_battle_differential(_evidence(recorded_truth=[1, 2]))
    assert out["support_status"] == "UNKNOWN"
    assert out["differential"] == "TRUTH_MALFORMED"
    assert out["prediction"]["winner"] == "attacker"


def test_schema_validator_accepts_valid():
    checked = validate_battle_evidence_schema(_evidence())
    assert checked["valid"] is True
    assert checked["errors"] == []
    assert checked["evidence"]["self_id"] == 5


def test_cli_battle_evidence_mode(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(_evidence(
        recorded_truth={"winner": "attacker"})), encoding="utf-8")
    out_path = tmp_path / "battle-report.json"
    tool = (Path(__file__).resolve().parents[1] / "tools"
            / "replay_battle_differential.py")
    proc = subprocess.run(
        [sys.executable, str(tool), "--battle-evidence",
         str(evidence_path), "--battle-out", str(out_path)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-500:]
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["support_status"] == "MATCH"
    assert report["differential"] == "PREDICTION_MATCHES_TRUTH"


def test_cli_battle_evidence_missing_file(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    tool = (Path(__file__).resolve().parents[1] / "tools"
            / "replay_battle_differential.py")
    proc = subprocess.run(
        [sys.executable, str(tool), "--battle-evidence",
         str(tmp_path / "nope.json")],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2
    assert "error" in proc.stdout
