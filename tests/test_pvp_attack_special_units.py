"""攻擊案例建立器不得忽略來源部隊中的特殊單位。"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.observe import TowerUnitCounts
from kiomet_ai.pvp_live import battle_case_for_tower_attack


def many(**values):
    return TowerUnitCounts(
        units_kind="MANY", fighter=values.get("fighter", 0),
        chopper=values.get("chopper", 0), bomber=values.get("bomber", 0),
        tank=values.get("tank", 0), soldier=values.get("soldier", 0),
        shield=values.get("shield", 0))


def test_any_special_source_unit_rejects_attack_case():
    target = SimpleNamespace(unit_counts=many(soldier=2, shield=3),
                             tower_type="Cliff")

    for special in ("Ruler", "Shell", "Emp", "Nuke"):
        source = SimpleNamespace(
            unit_counts=many(soldier=8, shield=4),
            deployable_force=SimpleNamespace(
                counts={"Soldier": 4, special: 1}))

        case = battle_case_for_tower_attack(
            source, target, 7, 7, 12, False, False, CAPACITIES)

        assert case is None, f"{special} must not enter a v0 attack case"
