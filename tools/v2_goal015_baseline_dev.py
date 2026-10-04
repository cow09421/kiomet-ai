"""Generate and, after an explicit clean freeze, run Goal-015 B1 baseline cases.

The default generation/qualification path uses only the independent harness's
metadata admission and detached visible-state projection.  Episode evaluation
is available only through ``--evaluate`` with the frozen commit and fixture
hash supplied explicitly.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, is_dataclass
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.v2_goal_decision_harness import admit_case, visible_state


FIXTURE = ROOT / "tests" / "fixtures" / "v2_goal015_baseline_dev.json"
RESULTS = ROOT / "runtime" / "research" / "v2" / "goal" / "goal015-baseline-dev.json"
HORIZON_TICKS = 120
SUPPORTED_KINDS = (3, 4, 7, 9, 10, 15, 17, 25, 26)
STRATA = (
    ("S1_expansion", "Expansion"),
    ("S2_contested_expansion", "ContestedExpansion"),
    ("S3_threat_defense", "ThreatDefense"),
    ("S4_reinforcement_choice", "ReinforcementChoice"),
    ("S5_combat_risk", "CombatRisk"),
    ("S6_uncertainty", "Uncertainty"),
)
CORES = {1: (0, 0), 2: (15, 15)}
GRID = tuple((x, y) for y in range(4, 12) for x in range(4, 12))


def _units(*, shield: int = 0, soldier: int = 0, ruler: int = 0) -> list[int]:
    values = [0] * 10
    values[0], values[5], values[9] = shield, soldier, ruler
    return values


def _tower(
    ident: int,
    xy: tuple[int, int],
    kind: int,
    owner: int | None,
    *,
    shield: int = 0,
    soldier: int = 0,
    ruler: int = 0,
    delay: int = 0,
) -> dict[str, Any]:
    return {
        "id": ident,
        "xy": [xy[0], xy[1]],
        "kind": kind,
        "owner": owner,
        "units": _units(shield=shield, soldier=soldier, ruler=ruler),
        "delay": delay,
        "supply": False,
        "visible": True,
    }


def _geometry_case(a: tuple[int, int], b: tuple[int, int]) -> dict[str, Any]:
    return {
        "case_id": "g015-public-road-probe",
        "stratum": "metadata_geometry_probe",
        "start_tick": 481,
        "horizon_ticks": HORIZON_TICKS,
        "player": 1,
        "alive": {"1": True, "2": True},
        "closed_by_construction": True,
        "towers": [
            _tower(900001, a, 3, 1, soldier=1),
            _tower(900002, b, 26, None),
        ],
        "forces": [],
        "future_opponents": [],
    }


def _road_graph() -> dict[tuple[int, int], tuple[tuple[int, int], ...]]:
    """Derive only the static legal adjacent menu graph from public view input."""
    graph: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {}
    for a in GRID:
        neighbors = []
        for b in GRID:
            if a == b or max(abs(a[0] - b[0]), abs(a[1] - b[1])) != 1:
                continue
            view = visible_state(_geometry_case(a, b))
            if any(action.kind == "DEPLOY" and action.source == 900001
                   and action.target == 900002 for action in view.legal_choices):
                neighbors.append(b)
        graph[a] = tuple(sorted(neighbors))
    return graph


def _pick_layouts(graph: Mapping[tuple[int, int], tuple[tuple[int, int], ...]]) -> dict[str, list[tuple[tuple[int, int], ...]]]:
    layouts: dict[str, list[tuple[tuple[int, int], ...]]] = {}

    one_source_two_neutrals = []
    for source in GRID:
        adjacent = graph[source]
        for i, first in enumerate(adjacent):
            for second in adjacent[i + 1:]:
                one_source_two_neutrals.append((source, first, second))
    layouts["S1_expansion"] = one_source_two_neutrals

    contested = []
    for neutral in GRID:
        for player_source in graph[neutral]:
            for enemy_source in graph[neutral]:
                if (player_source != enemy_source
                        and enemy_source not in graph[player_source]):
                    contested.append((player_source, neutral, enemy_source))
    layouts["S2_contested_expansion"] = contested

    threat = []
    for target in GRID:
        for enemy in graph[target]:
            for donor in graph[target]:
                if donor != enemy and enemy not in graph[donor]:
                    threat.append((target, enemy, donor))
    layouts["S3_threat_defense"] = threat

    donor_choice = []
    for target in GRID:
        for enemy in graph[target]:
            safe_donors = [d for d in graph[target]
                           if d != enemy and enemy not in graph[d]]
            for i, donor_a in enumerate(safe_donors):
                for donor_b in safe_donors[i + 1:]:
                    donor_choice.append((target, enemy, donor_a, donor_b))
    layouts["S4_reinforcement_choice"] = donor_choice

    combat = []
    for source in GRID:
        for enemy in graph[source]:
            combat.append((source, enemy))
    layouts["S5_combat_risk"] = combat

    uncertain = []
    for source in GRID:
        for neutral in graph[source]:
            for force_source in GRID:
                if force_source in (source, neutral) or force_source in graph[source]:
                    continue
                for threatened_tower in graph[force_source]:
                    if (threatened_tower in (source, neutral)
                            or force_source == neutral
                            or threatened_tower in graph[source]):
                        continue
                    uncertain.append((source, neutral, force_source, threatened_tower))
    layouts["S6_uncertainty"] = uncertain

    return layouts


def _kind(stratum_index: int, case_index: int, role_index: int) -> int:
    offset = (stratum_index * 5 + case_index * 2 + role_index * 3) % len(SUPPORTED_KINDS)
    return SUPPORTED_KINDS[offset]


def _new_case(
    stratum_index: int,
    case_index: int,
    layout: tuple[tuple[int, int], ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    stratum, stratum_name = STRATA[stratum_index]
    serial = stratum_index * 10 + case_index
    base_id = 50000 + serial * 20
    start_tick = 481 + 4 * case_index
    roles: dict[str, int] = {}
    towers = [
        _tower(base_id, CORES[1], _kind(stratum_index, case_index, 80), 1,
               shield=20, ruler=1),
        _tower(base_id + 1, CORES[2], _kind(stratum_index, case_index, 81), 2,
               shield=20, ruler=1),
    ]
    next_id = base_id + 2

    def add_role(name: str, xy: tuple[int, int], kind: int, owner: int | None,
                 *, shield: int = 0, soldier: int = 0, delay: int = 0) -> int:
        nonlocal next_id
        ident = next_id
        next_id += 1
        towers.append(_tower(ident, xy, kind, owner, shield=shield,
                             soldier=soldier, delay=delay))
        roles[name] = ident
        return ident

    script_rows: list[dict[str, int]] = []
    force_rows: list[dict[str, Any]] = []
    qualifying_facts: list[str] = []
    risk_design: str | None = None

    if stratum == "S1_expansion":
        source_xy, neutral_a_xy, neutral_b_xy = layout
        add_role("expansion_source", source_xy, _kind(stratum_index, case_index, 1), 1,
                 shield=case_index % 4, soldier=2 + case_index)
        add_role("empty_neutral_a", neutral_a_xy, _kind(stratum_index, case_index, 2), None)
        add_role("empty_neutral_b", neutral_b_xy, _kind(stratum_index, case_index, 3), None)
        qualifying_facts = ["own_ready_soldier_source", "two_empty_neutral_menu_targets"]

    elif stratum == "S2_contested_expansion":
        source_xy, neutral_xy, enemy_source_xy = layout
        neutral_id = add_role("contested_neutral", neutral_xy,
                              _kind(stratum_index, case_index, 2), None)
        source_id = add_role("expansion_source", source_xy,
                             _kind(stratum_index, case_index, 1), 1,
                             shield=case_index % 3, soldier=4 + case_index)
        enemy_id = add_role("script_source", enemy_source_xy,
                            _kind(stratum_index, case_index, 3), 2,
                            soldier=5 + case_index)
        script_rows.append({"at_tick": start_tick + 65, "owner": 2,
                            "source": enemy_id, "target": neutral_id})
        qualifying_facts = ["own_ready_source_to_empty_neutral", "predeclared_opponent_contest_script",
                            "script_source_not_in_own_current_menu"]

    elif stratum == "S3_threat_defense":
        target_xy, enemy_xy, donor_xy = layout
        target_soldiers = 1 + case_index % 3
        enemy_soldiers = 4 + case_index % 6
        needed = max(1, enemy_soldiers - target_soldiers)
        donor_soldiers = needed + 1 + case_index % 4
        add_role("threatened_own_target", target_xy,
                 _kind(stratum_index, case_index, 1), 1,
                 shield=case_index % 2, soldier=target_soldiers)
        add_role("visible_enemy_neighbor", enemy_xy,
                 _kind(stratum_index, case_index, 2), 2,
                 soldier=enemy_soldiers)
        add_role("safe_donor", donor_xy,
                 _kind(stratum_index, case_index, 3), 1,
                 shield=case_index % 3, soldier=donor_soldiers)
        qualifying_facts = ["visible_enemy_in_target_legal_menu", "lower_pressure_safe_donor",
                            "donor_meets_fixed_visible_count_deficit"]

    elif stratum == "S4_reinforcement_choice":
        target_xy, enemy_xy, donor_a_xy, donor_b_xy = layout
        target_soldiers = 1 + case_index % 3
        enemy_soldiers = 5 + case_index % 5
        needed = max(1, enemy_soldiers - target_soldiers)
        low_donor = needed + 1 + case_index % 2
        high_donor = low_donor + 2 + case_index % 3
        if case_index % 2:
            donor_a_soldiers, donor_b_soldiers = high_donor, low_donor
        else:
            donor_a_soldiers, donor_b_soldiers = low_donor, high_donor
        add_role("threatened_own_target", target_xy,
                 _kind(stratum_index, case_index, 1), 1,
                 soldier=target_soldiers)
        add_role("visible_enemy_neighbor", enemy_xy,
                 _kind(stratum_index, case_index, 2), 2,
                 soldier=enemy_soldiers)
        add_role("donor_a", donor_a_xy,
                 _kind(stratum_index, case_index, 3), 1,
                 shield=case_index % 2, soldier=donor_a_soldiers)
        add_role("donor_b", donor_b_xy,
                 _kind(stratum_index, case_index, 4), 1,
                 shield=(case_index + 1) % 3, soldier=donor_b_soldiers)
        qualifying_facts = ["visible_enemy_in_target_legal_menu", "two_safe_donor_menu_actions",
                            "both_donors_meet_fixed_visible_count_deficit"]

    elif stratum == "S5_combat_risk":
        source_xy, enemy_xy = layout
        mode = case_index % 3
        if mode == 0:
            soldiers = 5 + case_index
            enemy_soldiers = math.ceil(soldiers / 1.4)
            shields = 1
            risk_design = "below_fixed_1_5_visible_ratio"
        elif mode == 1:
            soldiers = 6 + case_index
            enemy_soldiers = max(2, soldiers // 2)
            shields = 0
            risk_design = "ratio_passes_but_exposed_source_lacks_shield_reserve"
        else:
            soldiers = 6 + case_index
            enemy_soldiers = max(2, math.floor(soldiers / 1.6))
            shields = 1 + case_index % 2
            risk_design = "ratio_and_visible_stationary_reserve_pass"
        add_role("combat_source", source_xy,
                 _kind(stratum_index, case_index, 1), 1,
                 shield=shields, soldier=soldiers)
        add_role("visible_enemy_target", enemy_xy,
                 _kind(stratum_index, case_index, 2), 2,
                 soldier=enemy_soldiers)
        qualifying_facts = ["own_attack_and_wait_in_unchanged_menu", risk_design]

    elif stratum == "S6_uncertainty":
        source_xy, neutral_xy, force_source_xy, threatened_xy = layout
        add_role("expansion_source", source_xy,
                 _kind(stratum_index, case_index, 1), 1,
                 soldier=3 + case_index)
        add_role("empty_neutral", neutral_xy,
                 _kind(stratum_index, case_index, 2), None)
        threatened_id = add_role("force_target_own_tower", threatened_xy,
                                 _kind(stratum_index, case_index, 4), 1,
                                 delay=0)
        force_units = 8 + case_index % 5
        force_source_id = add_role("hidden_force_source", force_source_xy,
                                   _kind(stratum_index, case_index, 3), 2,
                                   soldier=force_units + 2)
        force_rows.append({"owner": 2, "src": force_source_id,
                           "dst": threatened_id, "progress": 0, "fuel": 150,
                           "units": _units(soldier=force_units), "visible": True})
        qualifying_facts = ["own_empty_neutral_menu_option", "one_actual_visible_force_marker",
                            "force_owner_route_progress_composition_hidden_from_policy"]

    else:  # pragma: no cover - STRATA is frozen above.
        raise ValueError(f"unsupported generator stratum {stratum}")

    case = {
        "case_id": f"g015-{stratum.split('_', 1)[0].lower()}-{case_index + 1:02d}",
        "stratum": stratum,
        "start_tick": start_tick,
        "horizon_ticks": HORIZON_TICKS,
        "player": 1,
        "alive": {"1": True, "2": True},
        "closed_by_construction": True,
        "towers": towers,
        "forces": force_rows,
        "future_opponents": script_rows,
    }
    design = {
        "stratum_name": stratum_name,
        "qualifying_facts": qualifying_facts,
        "role_ids": roles,
        "role_coordinates": {row["id"]: row["xy"] for row in towers
                              if row["id"] in set(roles.values())},
        "tick_alignment": {
            "initial_observed_tick": start_tick - 1,
            "episode_endpoint_tick": start_tick + HORIZON_TICKS - 1,
            "both_divisible_by_four": (start_tick - 1) % 4 == 0
                                      and (start_tick + HORIZON_TICKS - 1) % 4 == 0,
        },
    }
    if risk_design is not None:
        design["combat_risk_band"] = risk_design
    return case, design


def _chebyshev(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _qualify_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    counts = Counter()
    qualifications = []
    seen_ids: set[str] = set()
    all_supported = True
    for row in rows:
        case = row["case"]
        design = row["design"]
        case_id, stratum = case["case_id"], case["stratum"]
        if case_id in seen_ids:
            raise ValueError(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)
        admission = admit_case(case)
        view = visible_state(case)
        menu = view.legal_choices
        count = sum(action.kind == "DEPLOY" for action in menu)
        tower_by_id = {tower["id"]: tower for tower in case["towers"]}
        core_rows = [tower_by_id[case["towers"][0]["id"]],
                     tower_by_id[case["towers"][1]["id"]]]
        core_positions = [tuple(tower["xy"]) for tower in core_rows]
        endpoint_ids = {force.get(key) for force in case["forces"]
                        for key in ("src", "dst")}
        endpoint_ids.update(script.get(key) for script in case["future_opponents"]
                            for key in ("source", "target"))
        endpoints_clear = all(
            _chebyshev(tuple(tower_by_id[ident]["xy"]), core_xy) > 1
            for ident in endpoint_ids if ident in tower_by_id
            for core_xy in core_positions
        )
        core_isolation = all(
            _chebyshev(tuple(tower["xy"]), core_xy) > 1
            for tower in case["towers"] if tower not in core_rows
            for core_xy in core_positions
        )
        target_enemy = design["role_ids"].get("visible_enemy_neighbor")
        threatened_target = design["role_ids"].get("threatened_own_target")
        donor_ids = [ident for name, ident in design["role_ids"].items()
                     if name.startswith("donor") or name == "safe_donor"]
        if stratum in ("S3_threat_defense", "S4_reinforcement_choice"):
            threat_menu = any(action.kind == "DEPLOY"
                              and action.source == threatened_target
                              and action.target == target_enemy for action in menu)
            donor_menu = all(any(action.kind == "DEPLOY" and action.source == donor
                                 and action.target == threatened_target for action in menu)
                             for donor in donor_ids)
        else:
            threat_menu = None
            donor_menu = None
        if stratum == "S6_uncertainty":
            force_marker_projection = bool(view.forces) and all(
                marker.owner is None and marker.source is None and marker.target is None
                and marker.progress is None and marker.units is None for marker in view.forces)
        else:
            force_marker_projection = None

        checks = {
            "admitted_supported": admission["status"] == "SUPPORTED",
            "unchanged_menu_has_wait_and_deploy": len(menu) >= 2 and count >= 1,
            "both_owners_alive": case["alive"].get("1") is True
                                 and case["alive"].get("2") is True,
            "one_ruler_per_owner": sum(t["units"][9] for t in case["towers"]
                                        if t["owner"] == 1) == 1
                                   and sum(t["units"][9] for t in case["towers"]
                                           if t["owner"] == 2) == 1,
            "cores_isolated_from_all_body_towers": core_isolation,
            "force_and_script_endpoints_clear_of_cores": endpoints_clear,
            "source_score_tick_boundaries_aligned": design["tick_alignment"]["both_divisible_by_four"],
        }
        if stratum in ("S1_expansion", "S2_contested_expansion", "S6_uncertainty"):
            source_id = design["role_ids"]["expansion_source"]
            neutral_ids = [ident for name, ident in design["role_ids"].items()
                           if name.startswith("empty_neutral") or name in ("contested_neutral", "empty_neutral")]
            checks["expansion_source_has_neutral_menu_action"] = any(
                action.kind == "DEPLOY" and action.source == source_id
                and action.target in neutral_ids for action in menu)
        if stratum == "S2_contested_expansion":
            script = case["future_opponents"][0]
            checks["script_contests_neutral_target"] = (
                script["target"] == design["role_ids"]["contested_neutral"]
                and any(action.kind == "DEPLOY" and action.source == design["role_ids"]["expansion_source"]
                        and action.target == script["target"] for action in menu)
                and not any(action.kind == "DEPLOY" and action.target == script["source"]
                            for action in menu)
            )
        if stratum in ("S3_threat_defense", "S4_reinforcement_choice"):
            checks["visible_threat_and_donor_menu_options"] = bool(threat_menu and donor_menu)
        if stratum == "S5_combat_risk":
            source = tower_by_id[design["role_ids"]["combat_source"]]
            target = tower_by_id[design["role_ids"]["visible_enemy_target"]]
            checks["combat_risk_has_visible_enemy_menu_target"] = any(
                action.kind == "DEPLOY" and action.source == source["id"]
                and action.target == target["id"] for action in menu)
        if stratum == "S6_uncertainty":
            checks["actual_force_is_visible_unknown_marker"] = (
                len(case["forces"]) == 1 and case["forces"][0]["visible"] is True
                and force_marker_projection is True)

        passed = all(checks.values())
        all_supported = all_supported and passed
        counts[stratum] += 1
        qualifications.append({
            "case_id": case_id,
            "stratum": stratum,
            "admission": admission,
            "visible_legal_choice_count": len(menu),
            "visible_deploy_choice_count": count,
            "visible_force_marker_count": len(view.forces),
            "checks": checks,
            "qualified": passed,
        })

    expected_counts = {name: 10 for name, _ in STRATA}
    actual_counts = {name: counts.get(name, 0) for name, _ in STRATA}
    summary = {
        "case_count": len(rows),
        "expected_case_count": 60,
        "stratum_counts": actual_counts,
        "expected_stratum_counts": expected_counts,
        "all_cases_qualified": all_supported and len(rows) == 60 and actual_counts == expected_counts,
        "policy_calls": 0,
        "episode_calls": 0,
        "qualification_calls": ["admit_case", "visible_state"],
    }
    return summary, qualifications


def build_fixture() -> dict[str, Any]:
    graph = _road_graph()
    layouts = _pick_layouts(graph)
    generated_rows: list[dict[str, Any]] = []
    for stratum_index, (stratum, _name) in enumerate(STRATA):
        candidates = layouts[stratum]
        if len(candidates) < 10:
            raise ValueError(f"insufficient metadata-only layouts for {stratum}: {len(candidates)}")
        # Layout selection is deterministic and depends only on the public legal-road graph.
        for case_index in range(10):
            layout_index = (case_index * 17 + stratum_index * 29) % len(candidates)
            case, design = _new_case(stratum_index, case_index, candidates[layout_index])
            generated_rows.append({"case": case, "design": design})
    summary, qualifications = _qualify_rows(generated_rows)
    if not summary["all_cases_qualified"]:
        failed = [row for row in qualifications if not row["qualified"]]
        raise ValueError("generated metadata qualification failed: "
                         + json.dumps(failed, sort_keys=True))
    return {
        "schema": "goal015-b1-baseline-dev-v1",
        "prereg_id": "goal-015",
        "fixed_horizon_ticks": HORIZON_TICKS,
        "fixed_horizon_seconds": 30,
        "baseline": "B1",
        "recipe": {
            "strata": [{"id": name, "name": label, "count": 10}
                       for name, label in STRATA],
            "source": "new deterministic layouts formed from current public VisiblePolicyState legal-road menus",
            "admission": "closed supported independent harness envelope via admit_case",
            "policy_projection": "visible_state current positive tower facts and unchanged complete legal action menu",
            "policy_history": {
                "decision_index": 0,
                "first_observed_tick": "the case's detached visible_state.tick",
                "basis": "fresh measurement session per case; never global match age",
            },
            "tick_sampling": {
                "start_tick_values": [481 + 4 * index for index in range(10)],
                "initial_observed_tick": "start_tick - 1, divisible by four",
                "endpoint_tick": "start_tick + 119, divisible by four",
                "neutral_phase": "all neutral rows avoid phase 240 downgrade boundaries over the 120-update window",
            },
            "force_policy_boundary": "S6 cases contain one real visible force row; visible_state emits only its unknown ForceView marker; raw evaluator route/composition remain inside case input",
            "terminal_protection": "one isolated Ruler tower for each alive owner; no body, force, or opponent-script endpoint is adjacent to either core",
            "score_lineage": "all case towers begin with source-default delay0; the score recipe consumes complete closed-world ownership/type/delay snapshots at the preregistered divisible-by-four initial and 120-update endpoint boundaries",
            "official_score_scale": "all 60 signed B1 score deltas; nearest_rank_scale applies |delta|; any unknown delta blocks scale instead of excluding an episode",
            "no_outcome_selection": True,
        },
        "qualification_summary": summary,
        "qualifications": qualifications,
        "cases": generated_rows,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any], *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    else:
        encoded = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(encoded + "\n", encoding="utf-8")


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("prereg_id") != "goal-015":
        raise ValueError("fixture is not a Goal-015 baseline DEV payload")
    rows = payload.get("cases")
    if not isinstance(rows, list) or any(not isinstance(row, dict) or "case" not in row for row in rows):
        raise ValueError("fixture cases must contain detached case mappings")
    return payload


def qualify_fixture(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = _load_fixture(path)
    summary, qualifications = _qualify_rows(payload["cases"])
    return summary, qualifications


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "as_dict"):
        return _jsonable(value.as_dict())
    return repr(value)


def _git_value(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=True,
                            capture_output=True, text=True)
    return result.stdout.strip()


def _require_clean_freeze(freeze_commit: str, fixture_hash: str, fixture_path: Path) -> dict[str, Any]:
    actual_commit = _git_value("rev-parse", "HEAD")
    if actual_commit != freeze_commit:
        raise RuntimeError(f"freeze commit mismatch: expected {freeze_commit}, got {actual_commit}")
    dirty = _git_value("status", "--porcelain")
    if dirty:
        raise RuntimeError("evaluation requires a clean frozen worktree; git status is non-empty")
    actual_fixture_hash = _sha256(fixture_path)
    if actual_fixture_hash != fixture_hash:
        raise RuntimeError(f"fixture hash mismatch: expected {fixture_hash}, got {actual_fixture_hash}")
    return {"commit": actual_commit, "clean_worktree": True,
            "fixture_sha256": actual_fixture_hash}


def _action_json(action: Any) -> Any:
    if action is None:
        return None
    if hasattr(action, "as_dict"):
        return action.as_dict()
    return _jsonable(action)


def evaluate_fixture(path: Path, output_path: Path, freeze_commit: str,
                     fixture_hash: str) -> dict[str, Any]:
    freeze = _require_clean_freeze(freeze_commit, fixture_hash, path)
    payload = _load_fixture(path)
    summary, qualifications = _qualify_rows(payload["cases"])

    # These imports are intentionally inside the post-freeze evaluation path.
    from tools.v2_goal_typed_baselines import choose_b1
    from tools.v2_goal_decision_harness import run_policy
    from tools.v2_goal_official_utility import nearest_rank_scale, score_delta

    rows: list[dict[str, Any]] = []
    score_results: list[Any] = []
    for fixture_row in payload["cases"]:
        case = fixture_row["case"]
        capture: dict[str, Any] = {}

        def choose(view: Any, _unchanged_menu: tuple[Any, ...]) -> Any:
            decision = choose_b1(view, decision_index=0,
                                 first_observed_tick=view.tick)
            capture["decision"] = {
                **{key: value for key, value in decision.items() if key != "action"},
                "action": _action_json(decision.get("action")),
            }
            return decision.get("action")

        row: dict[str, Any] = {
            "case_id": case.get("case_id"),
            "stratum": case.get("stratum"),
            "design": fixture_row.get("design", {}),
            "metadata_qualification": next(
                (qual for qual in qualifications if qual["case_id"] == case.get("case_id")),
                {"qualified": False, "checks": {"qualification_row_missing": False}},
            ),
            "provider": "B1",
        }
        try:
            raw_run = run_policy(case, choose)
            row["raw_run"] = _jsonable(raw_run)
            row["b1_decision"] = capture.get("decision")
            menu = raw_run.get("policy_input", {}).get("legal_choices", [])
            selected = raw_run.get("policy_choice")
            row["choice_in_unchanged_menu"] = (
                selected is not None and any(_jsonable(choice) == _jsonable(selected)
                                             for choice in menu)
            )
            outcome = raw_run.get("evaluation", {})
            row["status"] = outcome.get("status", raw_run.get("status", "UNKNOWN"))
            row["episode_status"] = row["status"]
        except Exception as exc:  # Retain each crashed case in the fixed denominator.
            raw_run = {"status": "CRASH", "exception_type": type(exc).__name__,
                       "exception": str(exc)}
            row["raw_run"] = raw_run
            row["b1_decision"] = capture.get("decision")
            row["choice_in_unchanged_menu"] = False
            row["status"] = "CRASH"
            row["episode_status"] = "CRASH"
            outcome = {"status": "UNKNOWN", "reason": "RUN_POLICY_CRASH"}
        try:
            score = score_delta(case, outcome)
        except Exception as exc:
            score = {"status": "UNKNOWN", "value": None,
                     "reason": f"SCORE_DELTA_CRASH:{type(exc).__name__}:{exc}"}
        score_results.append(score)
        row["source_score_delta"] = _jsonable(score)
        rows.append(row)

    signed_deltas: list[float] = []
    scale_inputs: list[float | None] = []
    scale_input_records: list[dict[str, Any]] = []
    all_deltas_known = len(score_results) == 60
    for row, score in zip(rows, score_results):
        score_data = _jsonable(score)
        known = score_data.get("status") == "KNOWN"
        value = score_data.get("value")
        numeric = type(value) in (int, float) and math.isfinite(float(value))
        known = bool(known and numeric)
        all_deltas_known = all_deltas_known and known
        if known:
            signed_deltas.append(float(value))
        scale_inputs.append(float(value) if known else None)
        scale_input_records.append({
            "case_id": row["case_id"],
            "status": "KNOWN" if known else "UNKNOWN",
            "delta": float(value) if known else None,
            "reason": score_data.get("reason") if not known else None,
            "included": known,
        })

    scale_value: float | None = None
    scale_status = "BLOCKED_UNKNOWN_DELTA"
    scale_reason: str | None = None
    if all_deltas_known and len(signed_deltas) == 60:
        try:
            candidate = nearest_rank_scale(signed_deltas)
            if type(candidate) not in (int, float) or not math.isfinite(float(candidate)) or candidate <= 0:
                raise ValueError("nearest-rank scale was not positive finite")
            scale_value = float(candidate)
            scale_status = "KNOWN"
        except Exception as exc:
            scale_status = "UNKNOWN"
            scale_reason = f"SCALE_INVALID:{type(exc).__name__}:{exc}"
    else:
        scale_reason = "ALL_60_EPISODE_DELTAS_ARE_REQUIRED; UNKNOWN_EPISODES_ARE_NOT_EXCLUDED"

    manifest_files = (
        "tools/v2_goal015_baseline_dev.py",
        "tools/v2_goal_decision_harness.py",
        "tools/v2_goal_typed_baselines.py",
        "tools/v2_goal_official_utility.py",
        "tests/fixtures/v2_goal015_baseline_dev.json",
    )
    hashes = {name: _sha256(ROOT / name) for name in manifest_files}
    result = {
        "schema": "goal015-b1-baseline-dev-results-v1",
        "prereg_id": "goal-015",
        "baseline": "B1",
        "freeze": freeze,
        "source_sha256": hashes,
        "fixture_sha256": _sha256(path),
        "qualification_summary": summary,
        "policy_history": payload["recipe"]["policy_history"],
        "scale_recipe": "nearest-rank 90th percentile over absolute source_score_delta for all 60 episodes; no exclusions or epsilon; unknown delta blocks scale",
        "scale_status": scale_status,
        "scale_reason": scale_reason,
        "scale": scale_value,
        "scale_inputs": scale_inputs,
        "scale_input_records": scale_input_records,
        "rows": rows,
    }
    _write_json(output_path, result, compact=True)
    return result


def _summary_for_console(path: Path, summary: Mapping[str, Any],
                         qualifications: list[dict[str, Any]]) -> dict[str, Any]:
    by_stratum: dict[str, dict[str, Any]] = {}
    for stratum, _label in STRATA:
        selected = [row for row in qualifications if row["stratum"] == stratum]
        by_stratum[stratum] = {
            "count": len(selected),
            "qualified": sum(bool(row["qualified"]) for row in selected),
            "supported": sum(row["admission"]["status"] == "SUPPORTED" for row in selected),
            "min_legal_choices": min((row["visible_legal_choice_count"] for row in selected), default=0),
            "force_marker_cases": sum(row["visible_force_marker_count"] > 0 for row in selected),
        }
    return {
        "fixture": str(path),
        "fixture_sha256": _sha256(path),
        "qualification_summary": summary,
        "strata": by_stratum,
        "recipe": {
            "cases_per_stratum": 10,
            "total_cases": 60,
            "horizon_ticks": 120,
            "start_ticks": [481 + 4 * index for index in range(10)],
            "history": "fresh B1 observation session per episode, decision_index=0, first_observed_tick=view.tick",
            "pre-freeze_calls": ["admit_case", "visible_state"],
            "pre-freeze_forbidden_calls": ["choose_b1", "run_policy", "evaluate", "episode"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--generate", action="store_true",
                      help="generate the new fixed 60-case fixture and metadata qualification")
    mode.add_argument("--evaluate", action="store_true",
                      help="run each frozen B1 episode once and write the full raw result artifact")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path, default=RESULTS)
    parser.add_argument("--freeze-commit", help="required clean Git commit hash for --evaluate")
    parser.add_argument("--fixture-sha256", help="required frozen fixture SHA-256 for --evaluate")
    args = parser.parse_args(argv)

    if args.generate:
        payload = build_fixture()
        _write_json(args.fixture, payload)
        summary, qualifications = _qualify_rows(payload["cases"])
        print(json.dumps(_summary_for_console(args.fixture, summary, qualifications),
                         indent=2, sort_keys=True))
        return 0

    if args.evaluate:
        if not args.freeze_commit or not args.fixture_sha256:
            parser.error("--evaluate requires --freeze-commit and --fixture-sha256")
        result = evaluate_fixture(args.fixture, args.output,
                                  args.freeze_commit, args.fixture_sha256)
        print(json.dumps({
            "output": str(args.output),
            "fixture_sha256": result["fixture_sha256"],
            "baseline": result["baseline"],
            "row_count": len(result["rows"]),
            "scale_input_count": len(result["scale_inputs"]),
            "scale_status": result["scale_status"],
            "scale": result["scale"],
            "qualification_summary": result["qualification_summary"],
        }, indent=2, sort_keys=True))
        return 0

    summary, qualifications = qualify_fixture(args.fixture)
    print(json.dumps(_summary_for_console(args.fixture, summary, qualifications),
                     indent=2, sort_keys=True))
    return 0 if summary["all_cases_qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
