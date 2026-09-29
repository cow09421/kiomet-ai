"""Offline server-reference ordering harness for a single Kiomet tower.

This does not model movement physics or battle arithmetic. It applies explicit,
static fixture results in the server-reference phase and collection order. A
fixture result is not evidence of production correctness or runtime validation.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SCENARIO_PATH = ROOT / "GPT_TEMPORAL_STATIC_SCENARIOS.json"
PHASE_ORDER = ("COLLISION", "ARRIVAL")


def _counts(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(unit, str)
        and type(count) is int
        and count >= 0
        for unit, count in value.items()
    )


def _unsupported(reason: str, *, tick: int | None = None) -> dict[str, Any]:
    return {
        "status": "UNSUPPORTED_TEMPORAL_CASE",
        "reason": reason,
        "tick": tick,
        "trace": [],
        "model_scope": "SERVER_REFERENCE_ORDER_ONLY; NOT A GAMEPLAY OR RUNTIME VALIDATION",
    }


def _same_state(value: Any, owner: int | None, units: dict[str, int]) -> bool:
    return value == {"owner_id": owner, "units": units}


def _fixture_state(result: Any, owner: int | None, units: dict[str, int]) -> bool:
    return (
        isinstance(result, dict)
        and result.get("status") == "STATIC_FIXTURE_ONLY"
        and result.get("tower_owner_before_id") == owner
        and result.get("tower_units_before") == units
        and type(result.get("tower_owner_after_id")) in (int, type(None))
        and _counts(result.get("tower_units_after"))
    )


def simulate(case: dict[str, Any]) -> dict[str, Any]:
    """Apply known same-tower events in authoritative server-reference order.

    Required ordering facts:
    - all possible collisions for the tick are explicitly represented;
    - collision collection indexes are exact;
    - multiple arrivals carry their current inbound Vec index;
    - combat/merge/capture effects are explicit static fixtures.
    """
    if not isinstance(case, dict) or case.get("tick_hz") != 4:
        return _unsupported("tick_hz must be the source-confirmed integer 4")
    tower = case.get("initial_tower")
    if not isinstance(tower, dict):
        return _unsupported("initial_tower is missing")
    owner = tower.get("owner_id")
    if owner is not None and (type(owner) is not int or owner <= 0):
        return _unsupported("tower owner must be a positive player id or null")
    units = tower.get("units")
    if not _counts(units):
        return _unsupported("tower units must be a complete nonnegative integer map")
    events = case.get("ticks")
    if not isinstance(events, list):
        return _unsupported("ticks must be a list")

    seen_ticks: set[int] = set()
    seen_force_ids: set[str] = set()
    known_force_ids: set[str] = set()
    active_forces: set[str] = set()
    for bucket in events:
        if not isinstance(bucket, dict) or type(bucket.get("tick")) is not int or bucket["tick"] < 0:
            return _unsupported("every tick bucket needs a nonnegative integer tick")
        tick = bucket["tick"]
        if tick in seen_ticks:
            return _unsupported("duplicate tick buckets are ambiguous; combine their events", tick=tick)
        seen_ticks.add(tick)
        arrivals = bucket.get("arrivals", [])
        if not isinstance(arrivals, list):
            return _unsupported("arrivals must be a list", tick=tick)
        for arrival in arrivals:
            if not isinstance(arrival, dict) or not isinstance(arrival.get("force_id"), str):
                return _unsupported("each arrival needs a local research force_id", tick=tick)
            fid = arrival["force_id"]
            if fid in seen_force_ids:
                return _unsupported("force_id is duplicated across this input", tick=tick)
            seen_force_ids.add(fid)
            known_force_ids.add(fid)
            active_forces.add(fid)
        collisions = bucket.get("collisions", [])
        if isinstance(collisions, list):
            for collision in collisions:
                if isinstance(collision, dict):
                    for key in ("inbound_force_id", "outbound_force_id"):
                        force_id = collision.get(key)
                        if isinstance(force_id, str):
                            known_force_ids.add(force_id)
                            active_forces.add(force_id)

    trace: list[dict[str, Any]] = []
    for bucket in sorted(events, key=lambda row: row["tick"]):
        tick = bucket["tick"]
        collisions = bucket.get("collisions", [])
        arrivals = bucket.get("arrivals", [])
        if bucket.get("collision_phase_complete") is not True:
            return _unsupported("collision phase completeness is unknown", tick=tick)
        if not isinstance(collisions, list):
            return _unsupported("collisions must be a list", tick=tick)

        collision_keys: list[tuple[int, int]] = []
        for collision in collisions:
            if not isinstance(collision, dict):
                return _unsupported("collision entry must be an object", tick=tick)
            inbound_index = collision.get("inbound_index")
            outbound_index = collision.get("outbound_index")
            if type(inbound_index) is not int or inbound_index < 0 or type(outbound_index) is not int or outbound_index < 0:
                return _unsupported("collision needs exact inbound and outbound Vec indexes", tick=tick)
            if collision.get("status") != "STATIC_FIXTURE_ONLY":
                return _unsupported("collision result is not supplied as an explicit static fixture", tick=tick)
            if type(collision.get("inbound_survived")) is not bool or type(collision.get("outbound_survived")) is not bool:
                return _unsupported("collision survivor flags are unknown", tick=tick)
            inbound_id = collision.get("inbound_force_id")
            outbound_id = collision.get("outbound_force_id")
            if not isinstance(inbound_id, str) or not isinstance(outbound_id, str):
                return _unsupported("collision force ids are missing", tick=tick)
            collision_keys.append((inbound_index, outbound_index))
        if collision_keys != sorted(collision_keys) or len(collision_keys) != len(set(collision_keys)):
            return _unsupported("collision order must match nested inbound-then-outbound Vec iteration", tick=tick)

        tick_trace: dict[str, Any] = {
            "tick": tick,
            "phase_order": list(PHASE_ORDER),
            "collisions": [],
            "arrivals": [],
        }
        for collision in collisions:
            inbound_id = collision["inbound_force_id"]
            outbound_id = collision["outbound_force_id"]
            if inbound_id not in known_force_ids or outbound_id not in known_force_ids:
                return _unsupported("collision references a force absent from the supplied state", tick=tick)
            if inbound_id not in active_forces or outbound_id not in active_forces:
                tick_trace["collisions"].append(
                    {"inbound_force_id": inbound_id, "outbound_force_id": outbound_id, "phase": "COLLISION_SKIPPED", "reason": "prior collision removed a participant"}
                )
                continue
            if not collision["inbound_survived"]:
                active_forces.discard(inbound_id)
            if not collision["outbound_survived"]:
                active_forces.discard(outbound_id)
            tick_trace["collisions"].append(
                {
                    "inbound_force_id": inbound_id,
                    "outbound_force_id": outbound_id,
                    "inbound_index": collision["inbound_index"],
                    "outbound_index": collision["outbound_index"],
                    "inbound_survived": collision["inbound_survived"],
                    "outbound_survived": collision["outbound_survived"],
                    "phase": "COLLISION_BEFORE_ARRIVAL",
                }
            )

        if len(arrivals) > 1:
            indexes = [row.get("inbound_index") if isinstance(row, dict) else None for row in arrivals]
            if any(type(index) is not int or index < 0 for index in indexes):
                return _unsupported("same-tick arrivals need the exact current inbound Vec index", tick=tick)
            if len(indexes) != len(set(indexes)):
                return _unsupported("same-tick arrivals have duplicate inbound Vec indexes", tick=tick)
        elif len(arrivals) == 1:
            index = arrivals[0].get("inbound_index")
            if index is not None and (type(index) is not int or index < 0):
                return _unsupported("inbound_index must be a nonnegative integer", tick=tick)

        ordered_arrivals = sorted(
            arrivals,
            key=lambda row: row.get("inbound_index", 0),
        )
        for arrival in ordered_arrivals:
            fid = arrival["force_id"]
            if fid not in active_forces:
                tick_trace["arrivals"].append(
                    {"force_id": fid, "phase": "ARRIVAL_SKIPPED", "reason": "removed_by_prior_collision"}
                )
                continue
            player_id = arrival.get("player_id")
            if type(player_id) is not int or player_id <= 0:
                return _unsupported("arrival owner must be a positive player id", tick=tick)
            before_owner, before_units = owner, deepcopy(units)
            allies = arrival.get("allied_owner_ids", [])
            if not isinstance(allies, list) or any(type(x) is not int or x <= 0 for x in allies):
                return _unsupported("allied_owner_ids must be an explicit list of positive ids", tick=tick)

            if owner is None and not units:
                branch = "NEUTRAL_EMPTY_CAPTURE"
                result = arrival.get("capture_result")
                if not _fixture_state(result, owner, units):
                    return _unsupported("empty neutral capture needs an exact post-reconcile fixture", tick=tick)
                if result["tower_owner_after_id"] != player_id:
                    return _unsupported("capture fixture owner does not match the arriving force", tick=tick)
            elif owner == player_id or owner in allies:
                branch = "FRIENDLY_MERGE"
                result = arrival.get("merge_result")
                if not _fixture_state(result, owner, units):
                    return _unsupported("friendly merge needs an exact post-capacity fixture", tick=tick)
                if result["tower_owner_after_id"] != owner or result.get("capacity_checked") is not True:
                    return _unsupported("merge fixture must preserve owner and explicitly check capacity", tick=tick)
            else:
                branch = "HOSTILE_BATTLE"
                result = arrival.get("battle_result")
                if not _fixture_state(result, owner, units):
                    return _unsupported("battle fixture is stale or missing for the current tower state", tick=tick)
                winner = result.get("winner")
                expected_owner = player_id if winner == "attacker" else owner if winner == "defender" else None
                if not isinstance(winner, str) or winner not in {"attacker", "defender", "contested"}:
                    return _unsupported("battle winner is outside the explicit supported fixture schema", tick=tick)
                if result["tower_owner_after_id"] != expected_owner:
                    return _unsupported("battle fixture owner writeback conflicts with the source branch", tick=tick)

            owner = result["tower_owner_after_id"]
            units = deepcopy(result["tower_units_after"])
            if branch == "HOSTILE_BATTLE":
                active_forces.discard(fid)
            tick_trace["arrivals"].append(
                {
                    "force_id": fid,
                    "inbound_index": arrival.get("inbound_index"),
                    "phase": "ARRIVAL_AND_IMMEDIATE_RESOLUTION",
                    "branch": branch,
                    "owner_read_at_execution": before_owner,
                    "owner_after": owner,
                    "tower_units_before": before_units,
                    "tower_units_after": deepcopy(units),
                    "fixture_status": result["status"],
                }
            )
        trace.append(tick_trace)

    return {
        "status": "ORDER_MODEL_ONLY",
        "tower_after": {"owner_id": owner, "units": units},
        "active_force_ids": sorted(active_forces),
        "trace": trace,
        "model_scope": "SERVER_REFERENCE_ORDER_ONLY; STATIC FIXTURES DO NOT PROVE GAMEPLAY OR PRODUCTION CORRECTNESS",
        "not_simulated": ["continuous movement", "battle arithmetic", "real tower-capacity calculation", "network scheduling", "production server runtime"],
    }


def _fixture(before_owner: int | None, before_units: dict[str, int], after_owner: int | None, after_units: dict[str, int], **extra: Any) -> dict[str, Any]:
    return {
        "status": "STATIC_FIXTURE_ONLY",
        "tower_owner_before_id": before_owner,
        "tower_units_before": deepcopy(before_units),
        "tower_owner_after_id": after_owner,
        "tower_units_after": deepcopy(after_units),
        **extra,
    }


def _arrival(force_id: str, player_id: int, index: int, *, battle: dict[str, Any] | None = None, merge: dict[str, Any] | None = None, capture: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"force_id": force_id, "player_id": player_id, "inbound_index": index}
    if battle is not None:
        result["battle_result"] = battle
    if merge is not None:
        result["merge_result"] = merge
    if capture is not None:
        result["capture_result"] = capture
    return result


def _bucket(tick: int, arrivals: list[dict[str, Any]] | None = None, collisions: list[dict[str, Any]] | None = None, *, complete: bool = True) -> dict[str, Any]:
    return {"tick": tick, "collision_phase_complete": complete, "collisions": collisions or [], "arrivals": arrivals or []}


def build_scenarios() -> list[dict[str, Any]]:
    """Build 36 auditable temporal fixtures, including safe rejections."""
    scenarios: list[dict[str, Any]] = []

    def add(name: str, case: dict[str, Any], expected: str, owner_after: int | None = None, reason: str = "") -> None:
        scenarios.append({
            "scenario_id": name,
            "case": case,
            "expected_status": expected,
            "expected_owner_after": owner_after,
            "purpose": reason,
        })

    # Single-arrival and tick-separated branches.
    add("T01_neutral_empty_capture", {"tick_hz": 4, "initial_tower": {"owner_id": None, "units": {}}, "ticks": [_bucket(1, [_arrival("f1", 1, 0, capture=_fixture(None, {}, 1, {"Soldier": 1}))])]}, "ORDER_MODEL_ONLY", 1, "Capture owner writeback is immediate in the reference path.")
    add("T02_hostile_defender_holds", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 5}}, "ticks": [_bucket(2, [_arrival("f2", 2, 0, battle=_fixture(1, {"Soldier": 5}, 1, {"Soldier": 3}, winner="defender"))])]}, "ORDER_MODEL_ONLY", 1, "One hostile arrival resolves against the current tower state.")
    add("T03_hostile_capture", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 1}}, "ticks": [_bucket(2, [_arrival("f3", 2, 0, battle=_fixture(1, {"Soldier": 1}, 2, {}, winner="attacker"))])]}, "ORDER_MODEL_ONLY", 2, "Attacker victory writes owner before later arrivals.")
    add("T04_contested_clears_owner", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 1}}, "ticks": [_bucket(2, [_arrival("f4", 2, 0, battle=_fixture(1, {"Soldier": 1}, None, {}, winner="contested"))])]}, "ORDER_MODEL_ONLY", None, "Contested result clears owner in the fixture semantics.")
    add("T05_friendly_merge_capacity_exact", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 5}}, "ticks": [_bucket(2, [_arrival("f5", 1, 0, merge=_fixture(1, {"Soldier": 5}, 1, {"Soldier": 8}, capacity_checked=True))])]}, "ORDER_MODEL_ONLY", 1, "Merge is accepted only with an exact capacity-checked fixture.")
    add("T06_owner_re_read_next_tick", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 1}}, "ticks": [_bucket(2, [_arrival("f6a", 2, 0, battle=_fixture(1, {"Soldier": 1}, 2, {"Soldier": 1}, winner="attacker"))]), _bucket(3, [_arrival("f6b", 1, 0, battle=_fixture(2, {"Soldier": 1}, 1, {"Soldier": 2}, winner="attacker"))])]}, "ORDER_MODEL_ONLY", 1, "Owner is read again for the next arrival event.")

    # Same-tick SELF reinforcement and enemy arrival: vector order, never class priority.
    for n, (first, final_owner) in enumerate((("reinforcement", 1), ("enemy", 2), ("reinforcement", 1), ("enemy", 2)), start=7):
        start_units = {"Soldier": 5}
        rmerge = _fixture(1, start_units, 1, {"Soldier": 10}, capacity_checked=True)
        rbattle = _fixture(1, {"Soldier": 10}, 1, {"Soldier": 4}, winner="defender")
        ebattle_before = 1 if first == "reinforcement" else 1
        ebattle_units = {"Soldier": 10} if first == "reinforcement" else start_units
        ebattle_owner_after = 2 if final_owner == 2 else 1
        ebattle_winner = "attacker" if final_owner == 2 else "defender"
        ebattle = _fixture(ebattle_before, ebattle_units, ebattle_owner_after, {"Soldier": 1}, winner=ebattle_winner)
        if first == "reinforcement":
            arrivals = [_arrival(f"f{n}r", 1, 2, merge=rmerge), _arrival(f"f{n}e", 2, 5, battle=ebattle)]
        else:
            # Enemy takes the tower first; the later SELF force must be evaluated as hostile to owner 2.
            enemy_first = _fixture(1, start_units, 2, {"Soldier": 1}, winner="attacker")
            self_later = _fixture(2, {"Soldier": 1}, 2 if final_owner == 2 else 1, {"Soldier": 1}, winner="defender" if final_owner == 2 else "attacker")
            arrivals = [_arrival(f"f{n}e", 2, 2, battle=enemy_first), _arrival(f"f{n}r", 1, 5, battle=self_later)]
        add(f"T{n:02d}_{first}_first", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": start_units}, "ticks": [_bucket(4, arrivals)]}, "ORDER_MODEL_ONLY", final_owner, "Explicit current inbound Vec indexes define the sequential branch; no reinforcement priority is assumed.")

    # Multiple enemies/reinforcements and neutral captures in both collection orders.
    for n, (first_owner, second_owner) in enumerate(((2, 3), (3, 2), (2, 2), (3, 3)), start=11):
        empty = {}
        first_units = {"Soldier": 1}
        capture = _fixture(None, empty, first_owner, first_units)
        after = first_owner
        if second_owner == first_owner:
            second = _fixture(after, first_units, after, {"Soldier": 2}, capacity_checked=True)
            second_arrival = _arrival(f"f{n}b", second_owner, 4, merge=second)
        else:
            second = _fixture(after, first_units, after, {"Soldier": 1}, winner="defender")
            second_arrival = _arrival(f"f{n}b", second_owner, 4, battle=second)
        arrivals = [_arrival(f"f{n}a", first_owner, 1, capture=capture), second_arrival]
        add(f"T{n:02d}_two_players_neutral_{first_owner}_{second_owner}", {"tick_hz": 4, "initial_tower": {"owner_id": None, "units": {}}, "ticks": [_bucket(5, arrivals)]}, "ORDER_MODEL_ONLY", after, "Second player re-reads owner after the first neutral capture.")

    for n, (outcome_a, outcome_b) in enumerate((("defender", "attacker"), ("attacker", "defender"), ("defender", "defender"), ("attacker", "attacker")), start=15):
        owner1 = 1
        first_after = 2 if outcome_a == "attacker" else 1
        second_after = 3 if first_after != 3 and outcome_b == "attacker" else first_after
        first = _fixture(owner1, {"Soldier": 8}, first_after, {"Soldier": 4}, winner=outcome_a)
        second = _fixture(first_after, {"Soldier": 4}, second_after, {"Soldier": 2}, winner=outcome_b)
        arrivals = [_arrival(f"f{n}a", 2, 0, battle=first), _arrival(f"f{n}b", 3, 3, battle=second)]
        add(f"T{n:02d}_two_enemies_{outcome_a}_{outcome_b}", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 8}}, "ticks": [_bucket(6, arrivals)]}, "ORDER_MODEL_ONLY", second_after, "Two enemies are processed sequentially, not merged into one battle.")

    for n, order in enumerate(((0, 1), (1, 0), (2, 5), (5, 2)), start=19):
        indexes = order
        first_units = {"Soldier": 5}
        first_after = {"Soldier": 7}
        second_after = {"Soldier": 9}
        first = _fixture(1, first_units, 1, first_after, capacity_checked=True)
        second = _fixture(1, first_after, 1, second_after, capacity_checked=True)
        ordered = sorted((("a", indexes[0]), ("b", indexes[1])), key=lambda pair: pair[1])
        arrivals = [
            _arrival(f"f{n}{suffix}", 1, index, merge=first if position == 0 else second)
            for position, (suffix, index) in enumerate(ordered)
        ]
        add(f"T{n:02d}_two_friendly_merges_{indexes[0]}_{indexes[1]}", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": first_units}, "ticks": [_bucket(7, arrivals)]}, "ORDER_MODEL_ONLY", 1, "Capacity merge is sequential and requires each exact intermediate state.")

    # Collision phase precedes arrival; known dead inbound forces never reach tower combat.
    for n, (in_survives, out_survives) in enumerate(((False, False), (False, True), (True, False), (True, True)), start=23):
        inbound_id, outbound_id = f"f{n}i", f"f{n}o"
        collision = {"status": "STATIC_FIXTURE_ONLY", "inbound_force_id": inbound_id, "outbound_force_id": outbound_id, "inbound_index": 0, "outbound_index": 0, "inbound_survived": in_survives, "outbound_survived": out_survives}
        battle = _fixture(1, {"Soldier": 2}, 2, {}, winner="attacker")
        arrivals = [_arrival(inbound_id, 2, 0, battle=battle)]
        add(f"T{n:02d}_collision_then_arrival_i{int(in_survives)}_o{int(out_survives)}", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 2}}, "ticks": [_bucket(8, arrivals, [collision])]}, "ORDER_MODEL_ONLY", 2 if in_survives else 1, "A surviving inbound force reaches arrival handling only after collision resolution.")

    # Fail-closed cases.
    bad_cases = [
        ("T27_same_tick_missing_index", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 1}}, "ticks": [_bucket(1, [_arrival("x", 2, 0, battle=_fixture(1, {"Soldier": 1}, 1, {}, winner="defender")), _arrival("y", 2, 0, battle=_fixture(1, {"Soldier": 1}, 1, {}, winner="defender"))])]}, "same-tick arrivals need the exact current inbound Vec index"),
        ("T28_collision_incomplete", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {}}, "ticks": [_bucket(1, complete=False)]}, "collision phase completeness is unknown"),
        ("T29_collision_order_unknown", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {}}, "ticks": [_bucket(1, collisions=[{"inbound_force_id": "x", "outbound_force_id": "y", "inbound_index": 0, "outbound_index": 0, "inbound_survived": True, "outbound_survived": True}])]}, "collision result is not supplied as an explicit static fixture"),
        ("T30_stale_owner_battle_fixture", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 3}}, "ticks": [_bucket(1, [_arrival("x", 2, 0, battle=_fixture(2, {"Soldier": 3}, 2, {}, winner="attacker"))])]}, "battle fixture is stale or missing for the current tower state"),
        ("T31_friendly_merge_unknown_capacity", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 1}}, "ticks": [_bucket(1, [_arrival("x", 1, 0, merge=_fixture(1, {"Soldier": 1}, 1, {"Soldier": 2}))])]}, "merge fixture must preserve owner and explicitly check capacity"),
        ("T32_eta_float", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {}}, "ticks": [{"tick": 1.0, "collision_phase_complete": True, "arrivals": [], "collisions": []}]}, "every tick bucket needs a nonnegative integer tick"),
        ("T33_duplicate_tick_bucket", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {}}, "ticks": [_bucket(1), _bucket(1)]}, "duplicate tick buckets are ambiguous; combine their events"),
        ("T34_unknown_units_not_zero", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": None}, "ticks": []}, "tower units must be a complete nonnegative integer map"),
        ("T35_missing_neutral_reconcile", {"tick_hz": 4, "initial_tower": {"owner_id": None, "units": {}}, "ticks": [_bucket(1, [_arrival("x", 2, 0)])]}, "empty neutral capture needs an exact post-reconcile fixture"),
        ("T36_second_battle_stale_snapshot", {"tick_hz": 4, "initial_tower": {"owner_id": 1, "units": {"Soldier": 1}}, "ticks": [_bucket(1, [_arrival("x", 2, 0, battle=_fixture(1, {"Soldier": 1}, 2, {"Soldier": 1}, winner="attacker")), _arrival("y", 3, 1, battle=_fixture(1, {"Soldier": 1}, 1, {}, winner="defender"))])]}, "battle fixture is stale or missing for the current tower state"),
    ]
    # Replace malformed duplicate-index cases with their intended exact fail-closed trigger.
    bad_cases[0][1]["ticks"][0]["arrivals"][1]["inbound_index"] = 1
    bad_cases[0][1]["ticks"][0]["arrivals"][0].pop("inbound_index", None)
    for name, case, reason in bad_cases:
        add(name, case, "UNSUPPORTED_TEMPORAL_CASE", None, reason)

    return scenarios


def run_static_scenarios() -> tuple[int, int, list[dict[str, Any]]]:
    passed = 0
    failures: list[dict[str, Any]] = []
    for scenario in build_scenarios():
        actual = simulate(deepcopy(scenario["case"]))
        status_ok = actual["status"] == scenario["expected_status"]
        owner_ok = actual.get("tower_after", {}).get("owner_id") == scenario["expected_owner_after"] if status_ok and scenario["expected_status"] == "ORDER_MODEL_ONLY" else True
        if status_ok and owner_ok:
            passed += 1
        else:
            failures.append({"scenario_id": scenario["scenario_id"], "expected_status": scenario["expected_status"], "actual": actual, "owner_expected": scenario["expected_owner_after"]})
    return passed, len(build_scenarios()), failures


def write_scenarios() -> None:
    rows = build_scenarios()
    SCENARIO_PATH.write_text(json.dumps({
        "artifact": "Round 11 temporal ordering static scenarios",
        "scope": "SERVER_REFERENCE_ORDER_ONLY",
        "battle_math": "STATIC_FIXTURES_ONLY_NOT_RUNTIME_VALIDATION",
        "scenario_count": len(rows),
        "scenarios": rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    write_scenarios()
    passed, total, failures = run_static_scenarios()
    print(json.dumps({"temporal_scenarios": {"passed": passed, "total": total, "failures": failures}, "scenario_file": str(SCENARIO_PATH)}, ensure_ascii=False, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
