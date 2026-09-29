import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from decode_units import decode, validate


def test_known_many_layout():
    tower = [0] * 48
    tower[38:45] = [0, 4, 0, 0, 0, 12, 20]
    result = decode(tower)
    assert result["Shield"] == 20
    assert result["Fighter"] == 4
    assert result["Soldier"] == 12


def test_ui_memory_fixture():
    path = ROOT / "runtime/research/units/units_ground_truth.json"
    series = json.loads(path.read_text(encoding="utf8"))
    rows = validate(series)
    assert len(series["rounds"]) == 3
    assert len({row["packed_id"] for row in rows}) == 10
    assert len(rows) == 30
    assert all(row["matches_ui"] for row in rows)
