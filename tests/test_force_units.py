import json
from pathlib import Path

from kiomet_ai.force_units import mirror_force_units
from kiomet_ai.observe import TowerUnitCounts, ObservedTower, MatchObservation, build_real_tower_states

ROOT = Path(__file__).resolve().parents[1]


def many(**values):
    return TowerUnitCounts(units_kind="MANY",fighter=values.get("fighter",0),
                           chopper=values.get("chopper",0),bomber=values.get("bomber",0),
                           tank=values.get("tank",0),soldier=values.get("soldier",0),
                           shield=values.get("shield",0))


def test_runway_excludes_shield_but_keeps_all_mobile_types():
    result = mirror_force_units(many(fighter=4,soldier=4,shield=15),"Runway")
    assert result.total == 8
    assert result.counts["Fighter"] == 4
    assert result.counts["Soldier"] == 4
    assert result.counts["Shield"] == 0
    assert result.production_rule == "PRODUCTION_PROVEN"


def test_projector_includes_shield():
    result = mirror_force_units(many(soldier=2,shield=12),"Projector")
    assert result.counts["Shield"] == 12
    assert result.total == 14


def test_single_ruler_is_not_automatically_reserved():
    counts = TowerUnitCounts(units_kind="SINGLE",single_unit_type="Ruler",
                             single_count=1,shield=20)
    result = mirror_force_units(counts,"Barracks")
    assert result.counts["Ruler"] == 1
    assert result.counts["Shield"] == 0
    assert result.input_evidence == "INFERRED"


def test_single_special_units_are_kept_separate():
    for name in ("Shell","Emp","Nuke"):
        counts = TowerUnitCounts(units_kind="SINGLE",single_unit_type=name,
                                 single_count=1,shield=3)
        result = mirror_force_units(counts,"Launcher")
        assert result.counts[name] == 1
        assert result.total == 1


def test_unknown_and_invalid_inputs_do_not_become_zero():
    assert mirror_force_units(None,"Runway") is None
    assert mirror_force_units(many(shield=5),None) is None
    assert mirror_force_units(many(shield=5),"UnknownTower") is None
    assert mirror_force_units(TowerUnitCounts(units_kind="MANY",fighter=None,
                chopper=0,bomber=0,tank=0,soldier=0,shield=5),"Runway") is None
    assert mirror_force_units(TowerUnitCounts(units_kind="SINGLE",single_unit_type="Ruler",
                single_count=None,shield=5),"Runway") is None


def test_observer_contract_derives_many_and_keeps_single_unknown():
    towers = (
        ObservedTower(tower_id=1,tower_type="Runway",
                      units_detail=many(fighter=4,soldier=4,shield=15)),
        ObservedTower(tower_id=2,tower_type="Barracks",
                      units_detail=TowerUnitCounts(units_kind="SINGLE",single_unit_type="Ruler",
                                                   single_count=1,shield=20)),
    )
    states = build_real_tower_states(MatchObservation(match_id="fixture",timestamp=1.0,towers=towers))
    assert states[0].deployable_force.counts["Fighter"] == 4
    assert states[0].deployable_force_confidence == "DERIVED"
    assert states[0].deployable_units is None
    assert states[0].freshness("fixture", now=100) == "STALE"
    assert states[1].deployable_force is None
    assert states[1].deployable_force_confidence == "UNKNOWN"


def test_historical_fixture_covers_multiple_owners_and_tower_types():
    fixture = json.loads((ROOT / "runtime/research/force_units/fixtures.json").read_text(encoding="utf8"))
    assert fixture["sample_count"] >= 10
    rows = fixture["examples"]
    assert {r["owner"] for r in rows} == {"SELF","NEUTRAL","ENEMY"}
    assert len({r["tower_type"] for r in rows}) >= 5
    assert any(r["current_counts"]["units_kind"] == "SINGLE" for r in rows)
    by_id = {(r["round"],r["tower_id"]):r for r in rows}
    assert by_id[(1,17498402)]["mirror"]["total"] == 8   # 跑道 15 盾、4 Fighter、4 Soldier
    assert by_id[(1,17563938)]["mirror"]["counts"]["Ruler"] == 1
    assert by_id[(1,17563936)]["mirror"]["total"] == 0  # Quarry 僅有 21 護盾
    assert [by_id[(i,17432865)]["mirror"]["total"] for i in (1,2,3)] == [2,4,1]
