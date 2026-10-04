"""Bounded public-source transition harness for the goal-006 DEV envelope.

The policy receives an immutable projection of current visible facts only.
Future scripts and evaluator state never enter that projection.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

HORIZON_TICKS = 120
SLOT_NAMES = ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
              "Shell", "Emp", "Nuke", "Ruler")
SUPPORTED_TOWERS = {3, 4, 7, 9, 10, 15, 17, 25, 26}
WORLD_TOWER_LIMIT = 512
CAPACITY = {
    3: {0: 10, 5: 12, 9: 1}, 4: {0: 40, 5: 6, 9: 1},
    7: {0: 30, 5: 4, 9: 1}, 9: {0: 10, 5: 4, 9: 1},
    10: {0: 10, 5: 4, 9: 1}, 15: {0: 10, 5: 4, 9: 1},
    17: {0: 10, 5: 4, 9: 1}, 25: {0: 10, 5: 4, 9: 1},
    26: {0: 5, 5: 4, 9: 1},
}
OVERFLOW = {0: 15, 5: 10, 9: 0}
DEFAULT_GENERATION = {0: 20}
TYPE_GENERATION = {3: {5: 24}, 15: {0: 12}}


@dataclass(frozen=True, order=True)
class Action:
    kind: str
    source: int | None = None
    target: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"kind": "WAIT"} if self.kind == "WAIT" else {
            "kind": "DEPLOY", "source": self.source, "target": self.target}


@dataclass(frozen=True)
class TowerView:
    id: int
    xy: tuple[int, int]
    kind: int
    owner: int | None
    units: tuple[int, ...]
    delay: int
    supply: bool | None


@dataclass(frozen=True)
class ForceView:
    visible: bool = True
    owner: int | None = None
    source: int | None = None
    target: int | None = None
    progress: int | None = None
    units: tuple[int, ...] | None = None


@dataclass(frozen=True)
class VisiblePolicyState:
    tick: int
    player: int
    towers: tuple[TowerView, ...]
    forces: tuple[ForceView, ...]
    legal_choices: tuple[Action, ...]


def _vector(raw: Any, label: str) -> tuple[int, ...]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 10:
        raise ValueError(f"{label}: expected complete ten-slot vector")
    if any(type(n) is not int or not 0 <= n <= 255 for n in raw):
        raise ValueError(f"{label}: counts must be integers from 0 to 255")
    return tuple(raw)


def _fnv(data: bytes) -> int:
    value = 2166136261
    for byte in data:
        value = (value * 16777619) & 0xFFFFFFFF
        value ^= byte
    return value


def _condense(value: int) -> int:
    half = (value & 0xFFFF) ^ ((value >> 16) & 0xFFFF)
    return (half & 0xFF) ^ (half >> 8)


def _offset(x: int, y: int) -> tuple[int, int]:
    h = _fnv(x.to_bytes(2, "little") + y.to_bytes(2, "little"))
    c = _condense(h)
    return 1 + (c & 3), 1 + ((c >> 4) & 3)


def _position(xy: Sequence[int]) -> tuple[int, int]:
    x, y = int(xy[0]), int(xy[1])
    ox, oy = _offset(x, y)
    return x * 5 + ox, y * 5 + oy


def _distance_squared(a: Sequence[int], b: Sequence[int]) -> int:
    ax, ay = _position(a)
    bx, by = _position(b)
    return (ax - bx) ** 2 + (ay - by) ** 2


def _road(a: Sequence[int], b: Sequence[int]) -> bool:
    if tuple(a) == tuple(b) or max(abs(a[0] - b[0]), abs(a[1] - b[1])) != 1:
        return False
    d2 = _distance_squared(a, b)
    if d2 > 35:
        return False
    if a[0] != b[0] and a[1] != b[1]:
        if _distance_squared((a[0], b[1]), (b[0], a[1])) <= d2:
            return False
    return True


def _mobile(kind: int, units: Sequence[int]) -> tuple[int, ...]:
    result = [0] * 10
    result[5], result[9] = units[5], units[9]
    if kind == 15:
        result[0] = units[0]
    return tuple(result)


def _speed(units: Sequence[int]) -> int:
    occupied = [i for i, count in enumerate(units) if count]
    return 3 if occupied == [0] else 2


def _is_alive(units: Sequence[int]) -> bool:
    return units[5] > 0 or units[9] > 0


def _validated_alive(alive: Any) -> dict[int, bool]:
    """Normalize only the two supported owner keys, rejecting ambiguous aliases."""
    if not isinstance(alive, Mapping):
        raise ValueError("alive must be a mapping")
    normalized: dict[int, bool] = {}
    for key, value in alive.items():
        if type(key) is int and key in (1, 2):
            owner = key
        elif type(key) is str and key in ("1", "2"):
            owner = int(key)
        else:
            raise ValueError("alive keys must be 1 or 2")
        if type(value) is not bool:
            raise ValueError("alive flags must be booleans")
        if owner in normalized and normalized[owner] is not value:
            raise ValueError(f"conflicting alive aliases for owner {owner}")
        normalized[owner] = value
    return normalized


def _menu(towers: Sequence[TowerView], player: int) -> tuple[Action, ...]:
    actions = [Action("WAIT")]
    for source in sorted(towers, key=lambda t: t.id):
        if source.owner != player or source.delay or not any(_mobile(source.kind, source.units)):
            continue
        for target in sorted(towers, key=lambda t: t.id):
            if source.id != target.id and _road(source.xy, target.xy):
                actions.append(Action("DEPLOY", source.id, target.id))
    return tuple(actions)


def visible_state(case: Mapping[str, Any]) -> VisiblePolicyState:
    """Build a detached view; latent scripts, labels, and world outcome are omitted."""
    if not isinstance(case, Mapping) or type(case.get("player")) is not int or case["player"] != 1:
        raise ValueError("visible player must be exactly 1")
    if type(case.get("start_tick")) is not int or not 0 <= case["start_tick"] <= 0xFFFF:
        raise ValueError("visible start_tick must be a u16")
    if not isinstance(case.get("towers"), list) or not isinstance(case.get("forces"), list):
        raise ValueError("visible towers and forces must be lists")
    player = case["player"]
    # `start_tick` names the first simulated world update. Inputs are selected
    # from the preceding visible snapshot, before that update is advanced.
    observed_tick = (int(case["start_tick"]) - 1) & 0xFFFF
    tower_views = []
    for row in case["towers"]:
        if not isinstance(row, Mapping) or type(row.get("visible")) is not bool:
            raise ValueError("tower visibility must be explicit boolean")
        if row["visible"] is False:
            continue
        required = {"id", "xy", "kind", "owner", "units", "delay"}
        if not required.issubset(row):
            raise ValueError("visible tower is missing current facts")
        ident, xy, kind, owner, delay = row["id"], row["xy"], row["kind"], row["owner"], row["delay"]
        if (type(ident) is not int or ident < 0 or type(kind) is not int or not 0 <= kind <= 255
                or (owner is not None and (type(owner) is not int or owner not in (1, 2)))
                or not isinstance(xy, list) or len(xy) != 2
                or any(type(v) is not int or not 0 <= v < WORLD_TOWER_LIMIT for v in xy)
                or type(delay) is not int or not 0 <= delay <= 255):
            raise ValueError("visible tower has malformed current facts")
        if owner == player:
            if "supply" not in row or type(row["supply"]) is not bool:
                raise ValueError("own tower supply presence must be known boolean")
            supply = row["supply"]
        else:
            supply = None
        tower_views.append(TowerView(ident, tuple(xy), kind, owner,
                                     _vector(row["units"], "tower units"), delay,
                                     supply))
    towers = tuple(sorted(tower_views, key=lambda t: t.id))
    force_views = []
    for row in case["forces"]:
        if not isinstance(row, Mapping) or type(row.get("visible")) is not bool:
            raise ValueError("force visibility must be explicit boolean")
        if row["visible"] is False:
            continue
        # The scenario force row is evaluator input. Presence alone is not a
        # fieldwise normal-observation certificate for owner, route, progress,
        # or composition, so only its visible entity marker crosses the policy
        # boundary. Preserve visible-row multiplicity and order.
        force_views.append(ForceView())
    forces = tuple(force_views)
    return VisiblePolicyState(observed_tick, player, towers, forces, _menu(towers, player))


def admit_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Check the closed supported envelope without simulating any outcome."""
    reasons: list[str] = []
    if not isinstance(case, Mapping):
        return {"status": "UNSUPPORTED", "reasons": ["CASE_NOT_MAPPING"]}
    required_case = {"case_id", "stratum", "start_tick", "horizon_ticks", "player",
                    "alive", "closed_by_construction", "towers", "forces", "future_opponents"}
    if not required_case.issubset(case):
        return {"status": "UNSUPPORTED",
                "reasons": ["MISSING_CASE_FIELDS:" + ",".join(sorted(required_case - set(case)))]}
    if not isinstance(case.get("case_id"), str) or not isinstance(case.get("stratum"), str):
        reasons.append("CASE_ID_AND_STRATUM_MUST_BE_STRINGS")
    if type(case.get("horizon_ticks")) is not int or case.get("horizon_ticks") != HORIZON_TICKS:
        reasons.append("HORIZON_NOT_120")
    if type(case.get("player")) is not int or case.get("player") != 1:
        reasons.append("PLAYER_NOT_1")
    start = case.get("start_tick")
    if type(start) is not int or not 0 <= start <= 0xFFFF:
        reasons.append("START_TICK_NOT_U16")
    if case.get("closed_by_construction") is not True:
        reasons.append("WORLD_NOT_CLOSED_BY_CONSTRUCTION")
    alive = case.get("alive")
    try:
        normalized_alive = _validated_alive(alive)
    except (TypeError, ValueError):
        normalized_alive = {}
        reasons.append("ALIVE_FLAGS_OR_KEYS_INVALID")
    if normalized_alive.get(1) is not True:
        reasons.append("PLAYER_ALIVE_STATE_REQUIRED")
    tower_rows = case.get("towers")
    force_rows = case.get("forces")
    scripts = case.get("future_opponents")
    if not isinstance(tower_rows, list) or not tower_rows:
        reasons.append("TOWERS_REQUIRED")
        tower_rows = []
    if not isinstance(force_rows, list):
        reasons.append("FORCES_MUST_BE_LIST")
        force_rows = []
    if not isinstance(scripts, list):
        reasons.append("FUTURE_OPPONENTS_MUST_BE_LIST")
        scripts = []
    towers: dict[int, Mapping[str, Any]] = {}
    chunk = None
    for index, row in enumerate(tower_rows):
        try:
            required_tower = {"id", "xy", "kind", "owner", "units", "delay", "supply", "visible"}
            if not isinstance(row, Mapping) or not required_tower.issubset(row):
                raise ValueError("missing required tower fields")
            ident, xy, kind, owner = row["id"], row["xy"], row["kind"], row["owner"]
            if type(ident) is not int or ident < 0 or not isinstance(xy, list) or len(xy) != 2:
                raise ValueError
            if any(type(v) is not int or v < 0 or v >= WORLD_TOWER_LIMIT for v in xy):
                raise ValueError
            if ident in towers:
                reasons.append(f"DUPLICATE_TOWER_ID:{ident}")
            if any(existing.get("xy") == xy for existing in towers.values()):
                reasons.append(f"DUPLICATE_TOWER_COORDINATE:{ident}")
            towers[ident] = row
            this_chunk = (xy[0] // 16, xy[1] // 16)
            if chunk is None:
                chunk = this_chunk
            elif this_chunk != chunk:
                reasons.append("MULTI_CHUNK_WORLD")
            if row.get("visible") is not True:
                reasons.append(f"TOWER_NOT_VISIBLE:{ident}")
            if type(kind) is not int or kind not in SUPPORTED_TOWERS:
                reasons.append(f"UNSUPPORTED_TOWER_TYPE:{ident}")
            if owner is not None and (type(owner) is not int or owner not in (1, 2)):
                reasons.append(f"UNSUPPORTED_TOWER_OWNER:{ident}")
            if row["supply"] is not False:
                reasons.append(f"SUPPLY_LINE_PRESENT:{ident}")
            if type(row["delay"]) is not int or not 0 <= row["delay"] <= 255:
                reasons.append(f"INVALID_DELAY:{ident}")
            units = _vector(row.get("units"), f"tower {ident}")
            if any(units[u] for u in (1, 2, 3, 4, 6, 7, 8)):
                reasons.append(f"UNSUPPORTED_TOWER_UNIT:{ident}")
            if units[9] > 1 or (units[9] and owner is None) or (units[5] and units[9]):
                reasons.append(f"INVALID_TOWER_RULER:{ident}")
            shield_cap = CAPACITY.get(kind, {}).get(0, 0) + (10 if units[9] else 0)
            max_counts = {
                0: shield_cap + (OVERFLOW[0] if owner is not None else 0),
                5: CAPACITY.get(kind, {}).get(5, 0) + (OVERFLOW[5] if owner is not None else 0),
                9: CAPACITY.get(kind, {}).get(9, 0),
            }
            if kind in CAPACITY and any(units[u] > max_counts[u] for u in (0, 5, 9)):
                reasons.append(f"INITIAL_OVERFLOW_EXCEEDS_RULE:{ident}")
        except (KeyError, TypeError, ValueError, IndexError):
            reasons.append(f"MALFORMED_TOWER:{index}")
    if not towers:
        reasons.append("NO_TOWER_ROWS")
    if reasons:
        return {"status": "UNSUPPORTED", "reasons": sorted(set(reasons))}
    for index, row in enumerate(force_rows):
        try:
            required_force = {"owner", "src", "dst", "progress", "fuel", "units", "visible"}
            if not isinstance(row, Mapping) or not required_force.issubset(row):
                raise ValueError("missing required force fields")
            if row.get("visible") is not True:
                reasons.append(f"FORCE_NOT_VISIBLE:{index}")
            src, dst = row["src"], row["dst"]
            if type(src) is not int or type(dst) is not int or src not in towers or dst not in towers:
                reasons.append(f"FORCE_ENDPOINT_NOT_IN_WORLD:{index}")
                continue
            if not _road(towers[src]["xy"], towers[dst]["xy"]):
                reasons.append(f"FORCE_NOT_DIRECT_ROAD:{index}")
            if type(row.get("owner")) is not int or row.get("owner") not in (1, 2):
                reasons.append(f"UNSUPPORTED_FORCE_OWNER:{index}")
            units = _vector(row.get("units"), f"force {index}")
            if any(units[u] for u in (1, 2, 3, 4, 6, 7, 8)):
                reasons.append(f"UNSUPPORTED_FORCE_UNIT:{index}")
            if not any(units) or units[9] > 1 or (units[5] and units[9]):
                reasons.append(f"UNSUPPORTED_FORCE_COMPOSITION:{index}")
            if units[0] and towers[src].get("kind") != 15:
                reasons.append(f"SHIELD_FORCE_ORIGIN_NOT_SUPPORTED:{index}")
            if type(row["progress"]) is not int or not 0 <= row["progress"] <= 255:
                reasons.append(f"INVALID_FORCE_PROGRESS:{index}")
            else:
                required_progress = min(255, _distance(towers[src], towers[dst]) * 18)
                if row["progress"] >= required_progress:
                    reasons.append(f"FORCE_ALREADY_AT_DESTINATION:{index}")
            if type(row["fuel"]) is not int or row["fuel"] != 150:
                reasons.append(f"INVALID_FORCE_FUEL:{index}")
        except (KeyError, TypeError, ValueError, IndexError):
            reasons.append(f"MALFORMED_FORCE:{index}")
    if reasons:
        return {"status": "UNSUPPORTED", "reasons": sorted(set(reasons))}
    # Validate script row types before using any row values as mapping/set keys.
    # This keeps malformed latent input an ordinary UNSUPPORTED case.
    for index, row in enumerate(scripts):
        required_script = {"at_tick", "owner", "source", "target"}
        if (not isinstance(row, Mapping) or not required_script.issubset(row)
                or type(row.get("at_tick")) is not int
                or type(row.get("owner")) is not int
                or type(row.get("source")) is not int
                or type(row.get("target")) is not int):
            reasons.append(f"MALFORMED_OPPONENT_SCRIPT:{index}")
    if reasons:
        return {"status": "UNSUPPORTED", "reasons": sorted(set(reasons))}
    if isinstance(alive, Mapping):
        owner_ids = {row.get("owner") for row in tower_rows if isinstance(row, Mapping)}
        owner_ids.update(row.get("owner") for row in force_rows if isinstance(row, Mapping))
        owner_ids.update(row.get("owner") for row in scripts if isinstance(row, Mapping))
        def alive_value(owner: int) -> Any:
            return normalized_alive.get(owner)
        for owner in owner_ids:
            if owner in (1, 2) and alive_value(owner) is not True:
                reasons.append(f"OWNER_ALIVE_STATE_MISSING:{owner}")
        for row in [*force_rows, *scripts]:
            owner = row.get("owner")
            if owner in (1, 2) and alive_value(owner) is not True:
                reasons.append(f"ACTIVE_OWNER_ALIVE_STATE_MISSING:{owner}")
    ruler_counts = {1: 0, 2: 0}
    for row in tower_rows:
        if isinstance(row, Mapping) and row.get("owner") in (1, 2):
            try:
                ruler_counts[row["owner"]] += _vector(row["units"], "tower units")[9]
            except (KeyError, TypeError, ValueError):
                pass
    for row in force_rows:
        if isinstance(row, Mapping) and row.get("owner") in (1, 2):
            try:
                ruler_counts[row["owner"]] += _vector(row["units"], "force units")[9]
            except (KeyError, TypeError, ValueError):
                pass
    if isinstance(alive, Mapping):
        for owner in (1, 2):
            is_alive = normalized_alive.get(owner)
            if is_alive is True and ruler_counts[owner] != 1:
                reasons.append(f"ALIVE_OWNER_REQUIRES_EXACTLY_ONE_RULER:{owner}")
            if ruler_counts[owner] > 1:
                reasons.append(f"MULTIPLE_RULERS_FOR_OWNER:{owner}")
    script_rows = []
    for index, row in enumerate(scripts):
        try:
            if not isinstance(row, Mapping):
                raise TypeError("script row must be a mapping")
            if not {"at_tick", "owner", "source", "target"}.issubset(row):
                raise ValueError("missing required script fields")
            at, owner = row["at_tick"], row.get("owner")
            src, dst = row["source"], row["target"]
            if type(at) is not int or not 0 <= at <= 0xFFFF:
                reasons.append(f"SCRIPT_TICK_NOT_U16:{index}")
            elif start is not None and not 0 < ((at - start) & 0xFFFF) < HORIZON_TICKS:
                reasons.append(f"SCRIPT_NOT_STRICTLY_FUTURE_IN_WINDOW:{index}")
            if type(owner) is not int or owner != 2 or src not in towers or dst not in towers:
                reasons.append(f"UNSUPPORTED_OPPONENT_SCRIPT:{index}")
                continue
            if towers[src].get("owner") != 2:
                reasons.append(f"SCRIPT_SOURCE_NOT_OWNED:{index}")
            if not _road(towers[src]["xy"], towers[dst]["xy"]):
                reasons.append(f"SCRIPT_NOT_DIRECT_ROAD:{index}")
            if "units" in row:
                reasons.append(f"SCRIPT_CANNOT_OVERRIDE_DEPLOY_INVENTORY:{index}")
            script_rows.append((src, dst))
        except (KeyError, TypeError, ValueError, IndexError):
            reasons.append(f"MALFORMED_OPPONENT_SCRIPT:{index}")
    if reasons:
        return {"status": "UNSUPPORTED", "reasons": sorted(set(reasons))}
    script_sources = [src for src, _ in script_rows]
    if len(script_sources) != len(set(script_sources)):
        reasons.append("MULTIPLE_NORMAL_DEPLOYS_FROM_ONE_SOURCE_UNSUPPORTED")
    for script in scripts:
        if not isinstance(script, Mapping):
            continue
        src = script.get("source")
        if src not in towers:
            continue
        try:
            mobile = _mobile(int(towers[src].get("kind", -1)),
                             _vector(towers[src].get("units"), f"script source {src}"))
        except (TypeError, ValueError):
            continue
        if not any(mobile):
            reasons.append(f"SCRIPT_SOURCE_HAS_NO_INITIAL_MOBILE_UNITS:{src}")
        delta = ((int(script.get("at_tick", start or 0)) - int(start or 0)) & 0xFFFF)
        if int(towers[src].get("delay", 0)) > delta + 1:
            reasons.append(f"SCRIPT_SOURCE_STILL_DELAYED:{src}")
        if any(isinstance(force, Mapping) and force.get("dst") == src for force in force_rows):
            reasons.append(f"SCRIPT_SOURCE_HAS_INBOUND_FORCE:{src}")
        if any(isinstance(other, Mapping) and other.get("target") == src for other in scripts if other is not script):
            reasons.append(f"SCRIPT_SOURCE_HAS_COMPETING_SCRIPT:{src}")
        try:
            own_actions_to_source = [
                action for action in visible_state(case).legal_choices
                if action.kind == "DEPLOY" and action.target == src
            ]
            if own_actions_to_source:
                reasons.append(f"POLICY_ACTION_CAN_CHANGE_SCRIPT_SOURCE:{src}")
        except (KeyError, TypeError, ValueError):
            pass
    # Same-edge crossing is modeled for one hostile opponent per direction.
    # Initial progress beyond the meeting point is inconsistent; multi-opponent
    # lane bundles need ordering rules outside this minimum envelope.
    valid_forces = [f for f in force_rows if isinstance(f, Mapping)]
    valid_scripts = [s for s in scripts if isinstance(s, Mapping)]
    for i, first in enumerate(valid_forces):
        for second in valid_forces[i + 1:]:
            if (first.get("owner") != second.get("owner")
                    and first.get("src") == second.get("dst")
                    and first.get("dst") == second.get("src")
                    and first.get("src") in towers):
                try:
                    req = _distance({"xy": towers[first["src"]]["xy"]},
                                    {"xy": towers[first["dst"]]["xy"]}) * 18
                    if int(first.get("progress", 0)) + int(second.get("progress", 0)) >= req:
                        reasons.append("INITIAL_HOSTILE_FORCES_ALREADY_CROSSED")
                except (KeyError, TypeError, ValueError):
                    pass
    base_legs = [(f.get("src"), f.get("dst"), f.get("owner")) for f in valid_forces]
    base_legs.extend((s.get("source"), s.get("target"), s.get("owner")) for s in valid_scripts)
    try:
        menu = visible_state(case).legal_choices
    except (KeyError, TypeError, ValueError):
        menu = ()
    possible_sets = [base_legs]
    possible_sets.extend(base_legs + [(a.source, a.target, 1)]
                         for a in menu if a.kind == "DEPLOY")
    for legs in possible_sets:
        for src, dst, owner in legs:
            opposing = sum(1 for other_src, other_dst, other_owner in legs
                           if other_src == dst and other_dst == src and other_owner != owner)
            if opposing > 1:
                reasons.append("MULTIPLE_OPPONENTS_ON_EDGE_UNSUPPORTED")
                break
    if not reasons:
        try:
            menu = visible_state(case).legal_choices
            if len(menu) < 2:
                reasons.append("FEWER_THAN_TWO_VISIBLE_LEGAL_CHOICES")
        except (KeyError, TypeError, ValueError):
            reasons.append("VISIBLE_STATE_MALFORMED")
    # Downgrade metadata comes from the external TowerTypeData macro, outside
    # the frozen support files. Do not silently cross an unowned downgrade tick.
    if chunk is not None and start is not None:
        phase0 = _phase(start, chunk)
        for row in tower_rows:
            if row.get("owner") is None and any(((phase0 + i) & 0xFFFF) % 240 == 0 for i in range(HORIZON_TICKS)):
                reasons.append(f"NEUTRAL_DOWNGRADE_PHASE_UNSUPPORTED:{row.get('id')}")
    return {
        "status": "UNSUPPORTED" if reasons else "SUPPORTED",
        "reasons": sorted(set(reasons)),
        "features": [] if reasons else [
            "one_chunk", "complete_visible_world", "soldier_shield_ruler",
            "typed_generation", "delay_and_capacity", "direct_roads", "120_ticks",
        ],
    }


def load_cases(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    """Load scenario rows while keeping independent references out of the case."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("cases") if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise ValueError("fixture must be a JSON list or an object with a cases list")
    scenarios = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each fixture row must be an object")
        scenario = row.get("case", row)
        if not isinstance(scenario, Mapping):
            raise ValueError("row case must be an object")
        scenarios.append(scenario)
    return tuple(scenarios)


def run_policy(
    case: Mapping[str, Any],
    choose: Callable[[VisiblePolicyState, tuple[Action, ...]], Action | Mapping[str, Any]],
) -> dict[str, Any]:
    """Invoke a chooser with only visible state and legal actions, then evaluate."""
    # Deliberately do not gate chooser invocation on latent-script admission:
    # an unsupported hidden script must not become a policy observation.
    try:
        view = visible_state(case)
    except (KeyError, TypeError, ValueError, IndexError):
        return {"status": "UNSUPPORTED", "reasons": ["VISIBLE_STATE_MALFORMED"]}
    selected = choose(view, view.legal_choices)
    try:
        action = _as_action(selected)
    except (TypeError, ValueError):
        return {"status": "UNSUPPORTED", "reasons": ["CHOICE_FORMAT_INVALID"],
                "policy_input": {"tick": view.tick, "player": view.player,
                                 "towers": tuple(asdict(t) for t in view.towers),
                                 "forces": tuple(asdict(f) for f in view.forces),
                                 "legal_choices": tuple(a.as_dict() for a in view.legal_choices)}}
    result = evaluate(case, action)
    return {
        "status": result["status"],
        "policy_choice": action.as_dict(),
        "policy_input": {
            "tick": view.tick,
            "player": view.player,
            "towers": tuple(asdict(t) for t in view.towers),
            "forces": tuple(asdict(f) for f in view.forces),
            "legal_choices": tuple(a.as_dict() for a in view.legal_choices),
        },
        "evaluation": result,
    }



def _chunk_xy(case: Mapping[str, Any]) -> tuple[int, int]:
    first = case["towers"][0]["xy"]
    return int(first[0]) // 16, int(first[1]) // 16


def _phase(tick: int, chunk_xy: tuple[int, int]) -> int:
    offset = (chunk_xy[0] & 255) | ((chunk_xy[1] & 255) << 8)
    return ((tick & 0xFFFF) + offset) & 0xFFFF


def _distance(a: Mapping[str, Any], b: Mapping[str, Any]) -> int:
    pa, pb = _position(a["xy"]), _position(b["xy"])
    return __import__("math").isqrt((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2)


def _capacity(tower: dict[str, Any], unit: int) -> int:
    capacity = CAPACITY[tower["kind"]].get(unit, 0)
    if unit == 0 and tower["units"][9] > 0:
        capacity += 10
    return capacity


def _tick_tower(tower: dict[str, Any], phase: int) -> None:
    if tower["owner"] is None:
        if phase % 40 == 0:  # neutral mobile-unit/shield decay: once per 10 seconds
            for unit in (0, 5, 9):
                tower["units"][unit] = max(0, tower["units"][unit] - 1)
        if phase % 240 == 0:
            # The tower macro's downgrade relation is not in this frozen source
            # envelope; admission prevents this boundary for neutral towers.
            return
    elif phase % 120 == 0:  # owned overflow diminishment, once per 30 seconds
        for unit in (0, 5, 9):
            if tower["units"][unit] > _capacity(tower, unit):
                tower["units"][unit] -= 1
    if tower["delay"] > 0:
        tower["delay"] -= 1
        return
    if tower["owner"] is None:
        return
    periods = dict(DEFAULT_GENERATION)
    periods.update(TYPE_GENERATION.get(tower["kind"], {}))
    for unit, period in periods.items():
        if (phase % period == 0 and tower["units"][unit] < _capacity(tower, unit)
                and not (unit == 5 and tower["units"][9] > 0)):
            # Source: add two, then remove all but one of those added.
            tower["units"][unit] += 1


def _merge(tower: dict[str, Any], incoming: Sequence[int]) -> None:
    owned = tower["owner"] is not None
    # Match source Unit::iter order. Shield is added before the Ruler boost applies.
    for unit in (0, 5, 9):
        count = int(incoming[unit])
        if not count:
            continue
        if unit == 5 and tower["units"][9] > 0:
            continue
        if unit == 9 and tower["units"][9] == 0:
            tower["units"][5] = 0
        cap = _capacity(tower, unit) + (OVERFLOW[unit] if owned else 0)
        tower["units"][unit] = min(cap, tower["units"][unit] + count)


def _power(units: Sequence[int]) -> int:
    return int(units[0]) + int(units[5]) + int(units[9])


def _consume(units: list[int], count: int) -> None:
    for unit in (0, 5, 9):
        taken = min(units[unit], count)
        units[unit] -= taken
        count -= taken
        if count == 0:
            return


def _force_crossing(a: Mapping[str, Any], b: Mapping[str, Any],
                    towers: Mapping[int, Mapping[str, Any]]) -> bool:
    if a["owner"] == b["owner"] or a["src"] != b["dst"] or a["dst"] != b["src"]:
        return False
    r_a = min(255, _distance(towers[a["src"]], towers[a["dst"]]) * 18)
    r_b = min(255, _distance(towers[b["src"]], towers[b["dst"]]) * 18)
    p_a, p_b = int(a["progress"]), int(b["progress"])
    s_a = _speed(a["units"])
    s_b = _speed(b["units"])
    # Exact cross-multiplied interval overlap from Chunk::tick.
    lower = max(max(0, r_a - min(r_a, p_a + s_a)) * r_b, p_b * r_a)
    upper = min(max(0, r_a - p_a) * r_b, min(r_b, p_b + s_b) * r_a)
    return lower <= upper


def _force_fight(a: dict[str, Any], b: dict[str, Any]) -> tuple[bool, bool]:
    """Bounded same-lane surface combat; no tower shield stripping."""
    before_a_ruler, before_b_ruler = a["units"][9], b["units"][9]
    power_a, power_b = _power(a["units"]), _power(b["units"])
    casualties = min(power_a, power_b)
    _consume(a["units"], casualties)
    _consume(b["units"], casualties)
    lost_a = bool(before_a_ruler and not a["units"][9])
    lost_b = bool(before_b_ruler and not b["units"][9])
    # Units::is_alive excludes a Shield-only remainder after combat.
    if not _is_alive(a["units"]):
        a["units"] = [0] * 10
    if not _is_alive(b["units"]):
        b["units"] = [0] * 10
    return lost_a, lost_b


def _tower_fight(force: dict[str, Any], tower: dict[str, Any]) -> tuple[bool, bool, bool]:
    """Bounded source-order combat; return win and each side's Ruler loss."""
    # Combatants::fight removes the attacking force's Shield when its opponent is a tower.
    force["units"][0] = 0
    before_force_ruler = force["units"][9]
    before_tower_ruler = tower["units"][9]
    attack, defense = _power(force["units"]), _power(tower["units"])
    if attack == 0:
        return False, bool(before_force_ruler), False
    if defense == 0:
        return True, False, False
    casualties = min(attack, defense)
    _consume(force["units"], casualties)
    _consume(tower["units"], casualties)
    won = attack > defense
    force_lost = bool(before_force_ruler and not force["units"][9])
    tower_lost = bool(before_tower_ruler and not tower["units"][9])
    return won, force_lost, tower_lost


def _normalize(case: Mapping[str, Any]) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], tuple[int, int], dict[int, bool]]:
    towers = {
        int(t["id"]): {"id": int(t["id"]), "xy": tuple(t["xy"]), "kind": int(t["kind"]),
                       "owner": t.get("owner"), "units": list(_vector(t["units"], "tower units")),
                       "delay": int(t.get("delay", 0)), "supply": bool(t.get("supply", False))}
        for t in case["towers"]
    }
    forces = [{
        "owner": int(f["owner"]), "src": int(f["src"]), "dst": int(f["dst"]),
        "progress": int(f.get("progress", 0)), "fuel": int(f.get("fuel", 150)),
        "units": list(_vector(f["units"], "force units")),
        "_had_ruler": bool(_vector(f["units"], "force units")[9]),
    } for f in case.get("forces", [])]
    alive = _validated_alive(case["alive"])
    return towers, forces, _chunk_xy(case), alive


def _new_deploy(towers: dict[int, dict[str, Any]], source: int, target: int,
                owner: int) -> tuple[dict[str, Any] | None, str]:
    tower = towers[source]
    units = list(_mobile(tower["kind"], tower["units"]))
    if tower["owner"] != owner:
        return None, "REJECTED_SOURCE_OWNER_CHANGED"
    if tower["delay"] > 0:
        return None, "REJECTED_SOURCE_DELAYED"
    if not any(units):
        return None, "REJECTED_NO_MOBILE_UNITS"
    for unit, count in enumerate(units):
        tower["units"][unit] -= count
    return ({"owner": owner, "src": source, "dst": target, "progress": 0,
             "fuel": 150, "units": units, "_had_ruler": bool(units[9])}, "ACCEPTED")


def _as_action(choice: Action | Mapping[str, Any]) -> Action:
    if isinstance(choice, Action):
        kind, source, target = choice.kind, choice.source, choice.target
    elif isinstance(choice, Mapping):
        kind, source, target = choice.get("kind"), choice.get("source"), choice.get("target")
        expected = {"kind"} if kind == "WAIT" else {"kind", "source", "target"}
        if set(choice) != expected:
            raise ValueError("action has missing or unexpected fields")
    else:
        raise ValueError("choice must be Action or mapping")
    if type(kind) is not str or kind not in ("WAIT", "DEPLOY"):
        raise ValueError("unknown action kind")
    if kind == "WAIT":
        if source is not None or target is not None:
            raise ValueError("WAIT cannot name endpoints")
        return Action("WAIT")
    if type(source) is not int or type(target) is not int or source < 0 or target < 0:
        raise ValueError("DEPLOY endpoints must be nonnegative integer IDs")
    return Action("DEPLOY", source, target)


def evaluate(case: Mapping[str, Any], choice: Action | Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one visible-menu action for a 120-tick episode."""
    admission = admit_case(case)
    if admission["status"] != "SUPPORTED":
        return {"status": "UNSUPPORTED", "reasons": admission["reasons"]}
    view = visible_state(case)
    try:
        action = _as_action(choice)
    except (TypeError, ValueError):
        return {"status": "UNSUPPORTED", "reasons": ["CHOICE_FORMAT_INVALID"]}
    if action not in view.legal_choices:
        return {"status": "UNSUPPORTED", "reasons": ["CHOICE_NOT_IN_VISIBLE_MENU"]}
    towers, forces, chunk_xy, alive = _normalize(case)
    scripts: dict[int, list[Mapping[str, Any]]] = {}
    for script in case["future_opponents"]:
        scripts.setdefault(int(script["at_tick"]), []).append(script)
    pending_death: set[int] = set()
    terminal: str | None = None
    terminal_processed = False
    trace: list[dict[str, Any]] = []
    start = int(case["start_tick"])
    for offset in range(HORIZON_TICKS):
        tick = (start + offset) & 0xFFFF
        phase = _phase(tick, chunk_xy)
        # Player service converts LostRuler to death at the next update boundary.
        if pending_death:
            for dead_player in pending_death:
                alive[dead_player] = False
            terminal = "CORE_LOSS:" + ",".join(str(p) for p in sorted(pending_death))
            terminal_processed = True
            pending_death.clear()
            break
        tower_order = sorted(
            towers.values(),
            key=lambda t: (t["xy"][1] % 16) * 16 + (t["xy"][0] % 16),
        )
        for tower in tower_order:
            _tick_tower(tower, phase)
        # Chunk::tick resolves crossing force pairs before force-to-tower arrivals.
        used: set[int] = set()
        for i in range(len(forces)):
            if i in used:
                continue
            for j in range(i + 1, len(forces)):
                if j in used or not _force_crossing(forces[i], forces[j], towers):
                    continue
                lost_a, lost_b = _force_fight(forces[i], forces[j])
                if lost_a:
                    pending_death.add(forces[i]["owner"])
                if lost_b:
                    pending_death.add(forces[j]["owner"])
                used.add(i)
                used.add(j)
                # The source lane pair can collide once in a single chunk tick.
                break
        forces = [f for f in forces if _power(f["units"]) > 0]
        for force in forces:
            force["progress"] = min(255, int(force["progress"]) + _speed(force["units"]))
        arrived = [f for f in forces if f["progress"] >= min(
            255, _distance(towers[f["src"]], towers[f["dst"]]) * 18)]
        arrived.sort(key=lambda f: ((towers[f["dst"]]["xy"][1] % 16) * 16
                                   + (towers[f["dst"]]["xy"][0] % 16)))
        for force in arrived:
            forces.remove(force)
            tower = towers[force["dst"]]
            owner = force["owner"]
            if force["fuel"] == 0:
                continue
            if tower["owner"] == owner:
                _merge(tower, force["units"])
                continue
            if tower["owner"] is None and not _power(tower["units"]) and _is_alive(force["units"]):
                tower["owner"] = owner
                _merge(tower, force["units"])
                continue
            old_owner = tower["owner"]
            won, force_ruler_lost, tower_ruler_lost = _tower_fight(force, tower)
            if force_ruler_lost:
                pending_death.add(owner)
            if tower_ruler_lost and old_owner in (1, 2):
                pending_death.add(old_owner)
            if won:
                tower["owner"] = owner
                _merge(tower, force["units"])
        input_rows: list[dict[str, Any]] = []
        if offset == 0 and action.kind == "DEPLOY":
            deployed, status = _new_deploy(towers, int(action.source), int(action.target), int(case["player"]))
            if deployed is not None:
                forces.append(deployed)
            input_rows.append({"kind": "DEPLOY", "owner": int(case["player"]),
                               "source": action.source, "target": action.target,
                               "status": status,
                               "units": tuple(deployed["units"]) if deployed else ()})
        for script in scripts.get(tick, []):
            deployed, status = _new_deploy(towers, int(script["source"]), int(script["target"]), 2)
            if deployed is not None:
                forces.append(deployed)
            input_rows.append({"kind": "DEPLOY", "owner": 2, "source": script["source"],
                               "target": script["target"], "status": status,
                               "units": tuple(deployed["units"]) if deployed else ()})
        trace.append({
            "tick": tick, "local_phase": phase, "inputs_after_tick": input_rows,
            "tower_owners": tuple(sorted((i, t["owner"]) for i, t in towers.items())),
            "tower_units": tuple(sorted((i, tuple(t["units"])) for i, t in towers.items())),
            "tower_delays": tuple(sorted((i, t["delay"]) for i, t in towers.items())),
            "forces": tuple(sorted((f["owner"], f["src"], f["dst"], f["progress"],
                                    tuple(f["units"])) for f in forces)),
            "alive": tuple(sorted(alive.items())),
        })
    if pending_death and terminal is None:
        # A Ruler can be lost on the final simulated tick; the public service
        # applies player death at the following update boundary, outside this
        # 120-tick horizon. Preserve that pending state instead of reporting the
        # player as unconditionally alive at the endpoint.
        terminal = "CORE_LOSS_PENDING_AT_HORIZON"
    return {
        "status": "EVALUATED", "case_id": case.get("case_id"), "choice": action.as_dict(),
        "ticks_evaluated": len(trace), "terminal": terminal, "alive": dict(alive),
        "terminal_processed": terminal_processed,
        "pending_core_losses": tuple(sorted(pending_death)),
        "final_towers": tuple(sorted((i, t["kind"], t["owner"], tuple(t["units"]))
                                     for i, t in towers.items())),
        "final_tower_delays": tuple(sorted((i, t["delay"]) for i, t in towers.items())),
        "final_forces": tuple(sorted((f["owner"], f["src"], f["dst"], f["progress"],
                                      tuple(f["units"])) for f in forces)),
        "trace": trace,
    }
