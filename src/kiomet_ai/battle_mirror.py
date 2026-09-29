"""Conservative static-only battle mirror subset.

This file never invokes the production WASM. Unsupported or malformed inputs
return UNSUPPORTED_CASE instead of guessing a winner.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ORDER = ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier")
SINGLE_OR_RULER = {"Shell", "Emp", "Nuke", "Ruler"}
ALL_UNITS = set(ORDER) | SINGLE_OR_RULER
AIR = 1
SURFACE = 0
I32_MAX = 2**31 - 1


def _unsupported(reason: str) -> dict[str, Any]:
    return {
        "status": "UNSUPPORTED_CASE",
        "supported": False,
        "unsupported_reason": reason,
    }


def _load_capacities() -> dict[str, dict[str, int]]:
    path = Path(__file__).with_name("GPT_BATTLE_FINAL_TABLES.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("production_wasm_sha256") != (
            "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c"
        ):
            return {}
        return {
            row["tower_type"]: row["capacity_by_unit"]
            for row in payload["production_capacity_rows"]
            if row.get("mapping_status", "").startswith("HIGH_CONFIDENCE_SOURCE_MATCH_22_OF_22")
        }
    except (OSError, KeyError, TypeError, ValueError):
        return {}


CAPACITIES = _load_capacities()


def _i32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def _morale(units: dict[str, int]) -> int:
    # Shield and Ruler count; Shell, EMP, and Nuke do not. The input gate
    # excludes the latter and Ruler, while Shield is counted after prebattle
    # shield stripping.
    count = sum(units.get(unit, 0) for unit in ORDER) + units.get("Ruler", 0)
    return min(3, count // 2)


def _is_alive(units: dict[str, int]) -> bool:
    return any(
        units.get(unit, 0)
        for unit in ORDER
        if unit != "Shield"
    ) or bool(units.get("Ruler", 0))


def _unit_field(
    unit: str,
    overflow: bool,
    in_force: bool,
    any_air: bool,
) -> int:
    if unit == "Shield":
        return AIR if any_air else SURFACE
    if unit in {"Fighter", "Chopper", "Bomber"} and (overflow or in_force):
        return AIR
    return SURFACE


def _unused_count(units: dict[str, int], last: str | None, unit: str) -> int:
    count = units.get(unit, 0)
    if unit == last:
        count -= 1
    return max(0, count)


def _next_unit(
    units: dict[str, int],
    last: str | None,
    field: int,
    is_force: bool,
    tower_type: str | None,
    any_air: bool,
) -> tuple[str, int] | None:
    for unit in ORDER:
        count = _unused_count(units, last, unit)
        if count == 0:
            continue
        overflow = False
        if tower_type is not None:
            capacity = CAPACITIES.get(tower_type)
            if capacity is None or unit not in capacity:
                return None
            overflow = count > capacity[unit]
        unit_field = _unit_field(unit, overflow, is_force, any_air)
        if unit_field >= field:
            return unit, unit_field
    return None


def _next_for_side(
    units: dict[str, int],
    last: str | None,
    field: int,
    is_force: bool,
    tower_type: str | None,
) -> tuple[str, int] | None:
    next_unit = _next_unit(units, last, field, is_force, tower_type, False)
    if next_unit is not None and field == AIR:
        return _next_unit(units, last, field, is_force, tower_type, True)
    return next_unit


def _damage(unit: str, unit_field: int, enemy_field: int) -> int:
    if unit == "Tank":
        return 3
    if unit in {"Fighter", "Chopper"} and unit_field == AIR:
        return 3
    if unit == "Bomber" and unit_field == AIR and enemy_field == SURFACE:
        return 5
    return 1


def _damage_delta(
    unit: str,
    unit_field: int,
    enemy_field: int,
    enemy_is_attacker: bool,
    previous_damage: int,
) -> int:
    damage = _damage(unit, unit_field, enemy_field)
    direction = -1 if enemy_is_attacker else 1
    # For this supported subset, no ranged/single-use unit reaches the
    # infinite-damage / anti-annihilation branch in production function 2022.
    if damage == 31:
        damage = I32_MAX
        if _i32(_i32(previous_damage * -direction) - 1) < -(I32_MAX // 2):
            damage = min(damage, 1000)
    return _i32(damage * direction)


def _replace(units: dict[str, int], last: str | None, current: str | None) -> str | None:
    if last is not None:
        units[last] -= 1
        if units[last] == 0:
            del units[last]
    return current


def predict_battle(case: dict[str, Any]) -> dict[str, Any]:
    """Resolve verified ordinary-unit force fights; reject every unmapped case."""
    relation = case.get("relation")
    force_vs_force = relation == "enemy_force" or case.get("battle_kind") == "force_vs_force"
    if relation not in ({"enemy_force"} if force_vs_force else {"enemy", "neutral"}):
        return _unsupported("friendly/allied relations use separate arrival branches")

    target_branch = case.get("target_branch")
    if force_vs_force:
        if target_branch not in {None, "force_collision"}:
            return _unsupported("target branch conflicts with force-versus-force combat")
        if case.get("tower_type") is not None or case.get("tower_owner") is not None:
            return _unsupported("force-versus-force combat has no tower owner or tower type")
        attacker_owner = case.get("attacker_owner")
        defender_owner = case.get("defender_owner")
        if (
            type(attacker_owner) is not int
            or attacker_owner <= 0
            or type(defender_owner) is not int
            or defender_owner <= 0
            or attacker_owner == defender_owner
        ):
            return _unsupported("force owners must be distinct known positive player ids")
        tower_owner = None
        tower_type = None
    else:
        if target_branch == "neutral_empty":
            return _unsupported("neutral empty capture is an arrival branch, not a battle")
        if target_branch not in {None, "tower_combat"}:
            return _unsupported("target branch is outside the supported tower-combat path")

        attacker_owner = case.get("attacker_owner")
        tower_owner = case.get("tower_owner")
        if type(attacker_owner) is not int or attacker_owner <= 0:
            return _unsupported("capturing force owner must be a known positive player id")
        if relation == "neutral" and tower_owner is not None:
            return _unsupported("neutral relation conflicts with a nonempty tower owner")
        if relation == "enemy" and (
            type(tower_owner) is not int or tower_owner <= 0 or tower_owner == attacker_owner
        ):
            return _unsupported("enemy relation conflicts with the supplied owner ids")

        tower_type = case.get("tower_type")
        if not CAPACITIES:
            return _unsupported("validated production capacity table is unavailable")
        if tower_type not in CAPACITIES:
            return _unsupported("tower type has no source-order-confirmed production row")

    units_by_side: dict[str, dict[str, int]] = {}
    for key in ("attacker_units", "defender_units"):
        raw = case.get(key)
        if not isinstance(raw, dict):
            return _unsupported(f"{key} must be a unit-count object")
        unknown = set(raw) - ALL_UNITS
        if unknown:
            return _unsupported(f"unknown unit names: {sorted(unknown)}")
        if any(unit in raw and raw[unit] for unit in SINGLE_OR_RULER):
            return _unsupported("Shell/EMP/Nuke/Ruler callbacks are excluded from this subset")
        if any(type(n) is not int or n < 0 or n > 255 for n in raw.values()):
            return _unsupported("unit counts must be unsigned 8-bit values")
        units_by_side[key] = {u: n for u, n in raw.items() if n}
    if not units_by_side["attacker_units"]:
        return _unsupported("an empty force cannot enter production battle resolution")
    if force_vs_force and not units_by_side["defender_units"]:
        return _unsupported("an empty opposing force cannot enter collision combat")
    if not force_vs_force and not units_by_side["defender_units"]:
        return _unsupported("empty defender tower follows direct capture, not combat")

    if not isinstance(case.get("attacker_aura"), bool) or not isinstance(
        case.get("defender_aura"), bool
    ):
        return _unsupported("aura inputs must be explicit booleans")

    attacker = units_by_side["attacker_units"]
    defender = units_by_side["defender_units"]
    # Production 448 strips only the attacking Force's Shield before aura
    # calculation. Production 522 passes sentinel tower type 27 for both sides,
    # so Shield remains for force-versus-force combat.
    if not force_vs_force:
        attacker.pop("Shield", None)
    attacker_morale = _morale(attacker)
    defender_morale = _morale(defender)
    a_aura = case["attacker_aura"]
    d_aura = case["defender_aura"]
    damage = (
        attacker_morale
        if a_aura and not d_aura
        else -defender_morale
        if d_aura and not a_aura
        else 0
    )
    initial_damage = damage

    last_attacker: str | None = None
    last_defender: str | None = None

    def next_for(side: str, last: str | None, field: int) -> tuple[str, int] | None:
        return _next_for_side(
            attacker if side == "attacker" else defender,
            last,
            field,
            force_vs_force or side == "attacker",
            None if force_vs_force or side == "attacker" else tower_type,
        )

    for field in (AIR, SURFACE):
        while True:
            next_attacker = next_for("attacker", last_attacker, field)
            next_defender = next_for("defender", last_defender, field)
            if damage < 0:
                next_attacker, next_defender = next_attacker, None
            elif damage > 0:
                next_attacker, next_defender = None, next_defender
            else:
                # Option::and in the production-matched source path chooses
                # the attacker only when both sides have a unit available.
                next_attacker = next_attacker if next_defender is not None else None
                next_defender = None

            if next_attacker is not None:
                unit, unit_field = next_attacker
                last_attacker = _replace(attacker, last_attacker, unit)
                delta = _damage_delta(unit, unit_field, field, False, damage)
            elif next_defender is not None:
                unit, unit_field = next_defender
                last_defender = _replace(defender, last_defender, unit)
                delta = _damage_delta(unit, unit_field, field, True, damage)
            else:
                break
            damage = _i32(damage + delta)

    next_attacker = next(
        (u for u in ORDER if _unused_count(attacker, last_attacker, u)), None
    )
    next_defender = next(
        (u for u in ORDER if _unused_count(defender, last_defender, u)), None
    )
    if next_attacker is not None and next_defender is not None:
        return _unsupported("terminal production invariant expects at most one unused side")

    terminal_order = ["attacker", "defender"]
    if next_defender is not None:
        terminal_order.reverse()
    for side in terminal_order:
        if side == "attacker" and damage <= 0:
            if next_attacker is not None:
                damage = _i32(
                    damage
                    + _damage_delta(next_attacker, SURFACE, SURFACE, False, damage)
                )
            last_attacker = _replace(attacker, last_attacker, next_attacker)
        elif side == "defender" and damage >= 0:
            if next_defender is not None:
                damage = _i32(
                    damage
                    + _damage_delta(next_defender, SURFACE, SURFACE, True, damage)
                )
            last_defender = _replace(defender, last_defender, next_defender)

    attacker_alive = _is_alive(attacker)
    defender_alive = _is_alive(defender)
    if attacker_alive:
        winner = "attacker"
    elif defender_alive or (not force_vs_force and damage <= 0):
        winner = "defender"
    else:
        winner = "contested"

    new_owner = (
        None
        if force_vs_force or winner == "contested"
        else attacker_owner
        if winner == "attacker"
        else tower_owner
    )
    scope = (
        "ordinary units only; force against force"
        if force_vs_force
        else "ordinary units only; force against nonempty tower"
    )
    return {
        "status": "PARTIAL_RESULT",
        "supported": True,
        "support_status": "SUPPORTED_STATIC_SUBSET",
        "supported_scope": scope,
        "winner": winner,
        "attacker_survivors": dict(attacker),
        "defender_survivors": dict(defender),
        "new_owner": new_owner,
        "new_owner_relation": (
            "not_applicable"
            if force_vs_force
            else "changed_to_attacker"
            if winner == "attacker"
            else "cleared_after_contested_result"
            if winner == "contested"
            else "unchanged"
        ),
        "remaining_tower_units": None if force_vs_force else dict(defender),
        "special_effects": [],
        "morale": {
            "attacker": attacker_morale,
            "defender": defender_morale,
            "initial_accumulator": initial_damage,
        },
        "final_accumulator": damage,
        "confidence": "STATIC_PRODUCTION_MAPPING; NOT RUNTIME_DIFFERENTIALLY_VALIDATED",
        "unsupported_reason": None,
    }


def main() -> None:
    try:
        case = json.load(sys.stdin)
        if not isinstance(case, dict):
            raise ValueError("top-level input must be a JSON object")
        result = predict_battle(case)
    except (json.JSONDecodeError, ValueError) as exc:
        result = _unsupported(str(exc))
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
