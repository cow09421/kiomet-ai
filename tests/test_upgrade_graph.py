"""升級來源圖提取＋乾跑排序確定性測試。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

ROOT = Path(__file__).resolve().parents[1]

from extract_upgrade_graph import extract
from kiomet_ai.dry_rank import rank_expansion_targets
from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    TowerUnitCounts,
    build_real_tower_states,
)


def many(**values):
    return TowerUnitCounts(units_kind="MANY", fighter=values.get("fighter", 0),
                           chopper=values.get("chopper", 0),
                           bomber=values.get("bomber", 0),
                           tank=values.get("tank", 0),
                           soldier=values.get("soldier", 0),
                           shield=values.get("shield", 0))


def test_source_graph_has_nineteen_edges():
    edges = extract()
    assert len(edges) == 19
    by_pair = {(e["from"], e["to"]): e for e in edges}
    assert by_pair[("Runway", "Airfield")]["extras"] == {"Factory": 2, "Radar": 1}
    assert by_pair[("Mine", "Bunker")]["extras"] == {"Headquarters": 1, "Ews": 1}
    assert by_pair[("Village", "Town")]["extras"] == {"Generator": 1, "Village": 3}
    assert all(e["status"] == "SOURCE_EXPECTED" for e in edges)


def test_ranker_ordering_deterministic_on_ties():
    now = time.time()
    towers = (
        ObservedTower(tower_id=1, tower_ref=11, owner="SELF",
                      tower_type="Runway", units_detail=many(fighter=4, shield=5)),
        ObservedTower(tower_id=2, tower_ref=22, owner="NEUTRAL",
                      tower_type="Cliff", units_detail=many(shield=3)),
        ObservedTower(tower_id=3, tower_ref=33, owner="NEUTRAL",
                      tower_type="Cliff", units_detail=many(shield=3)),
    )
    obs = MatchObservation(match_id="m1", timestamp=now, towers=towers,
                           edges=(ObservedEdge(1, 2), ObservedEdge(1, 3)))
    states = build_real_tower_states(obs)
    first = [c["target"] for c in rank_expansion_targets(states, "m1", now)]
    second = [c["target"] for c in rank_expansion_targets(states, "m1", now)]
    assert first == second == [2, 3]  # 同分按 target_id 穩定排序


def test_production_comparison_milestone():
    import json
    path = (ROOT / "runtime/research/upgrade/source_vs_production.json")
    data = json.loads(path.read_text(encoding="utf8"))
    assert data["total_edges"] == 19
    assert data["production_confirmed"] >= 8
    assert data["production_deltas"] == 0
    matched = {r["edge"] for r in data["rows"] if r["status"] == "SOURCE_MATCH"}
    for edge in ("Runway->Airfield", "Barracks->Armory", "Mine->Bunker",
                 "Factory->Centrifuge", "Factory->Refinery",
                 "Village->Headquarters", "Village->Town",
                 "Generator->Reactor"):
        assert edge in matched, edge
