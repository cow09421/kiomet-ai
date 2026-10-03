"""Deterministic, information-bounded typed baselines for Goal013.

These providers only choose among the immutable view's existing legal
whole-mobile actions. They do not simulate a transition or interpret the
route, owner, progress, or composition of a visible force marker.
"""
from __future__ import annotations

from typing import Any

from tools.v2_goal_decision_harness import Action, VisiblePolicyState


_SLOT_SHIELD = 0
_SLOT_SOLDIER = 5
_SLOT_RULER = 9


def _unknown(provider: str, reason: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "provider": provider,
        "status": "UNKNOWN",
        "action": None,
        "reason": reason,
        "evidence": evidence or {},
    }


def _inspect_view(state: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Validate public fields without consulting scenario/evaluator attributes."""
    if not isinstance(state, VisiblePolicyState):
        return None, "INPUT_NOT_VISIBLE_POLICY_STATE"
    if type(state.player) is not int or state.player <= 0:
        return None, "PLAYER_ID_INVALID"
    if type(state.tick) is not int or not 0 <= state.tick <= 0xFFFF:
        return None, "VISIBLE_TICK_INVALID"
    if not isinstance(state.towers, tuple) or not isinstance(state.forces, tuple):
        return None, "VISIBLE_COLLECTIONS_INVALID"

    towers: dict[int, Any] = {}
    for tower in state.towers:
        ident = getattr(tower, "id", None)
        xy = getattr(tower, "xy", None)
        kind = getattr(tower, "kind", None)
        owner = getattr(tower, "owner", None)
        units = getattr(tower, "units", None)
        delay = getattr(tower, "delay", None)
        supply = getattr(tower, "supply", None)
        if (type(ident) is not int or ident < 0 or ident in towers
                or type(kind) is not int or not 0 <= kind <= 255
                or (owner is not None and (type(owner) is not int or owner <= 0))
                or not isinstance(xy, tuple) or len(xy) != 2
                or any(type(value) is not int or value < 0 for value in xy)
                or not isinstance(units, tuple) or len(units) != 10
                or any(type(value) is not int or not 0 <= value <= 255
                       for value in units)
                or type(delay) is not int or not 0 <= delay <= 255
                or (supply is not None and type(supply) is not bool)):
            return None, "VISIBLE_TOWER_FACTS_INVALID"
        singles = [slot for slot in range(6, 10) if units[slot] > 0]
        if (len(singles) > 1 or (singles and any(units[1:6]))
                or units[_SLOT_RULER] > 1):
            return None, "TOWER_SINGLE_MANY_EXCLUSIVITY_INVALID"
        towers[ident] = tower

    # ForceView's visible marker is the only field this policy reads. All
    # endpoint, owner, progress, and unit facts are intentionally untouched.
    force_markers = 0
    for force in state.forces:
        visible = getattr(force, "visible", None)
        if type(visible) is not bool:
            return None, "VISIBLE_FORCE_MARKER_INVALID"
        force_markers += int(visible)

    if not isinstance(state.legal_choices, tuple):
        return None, "LEGAL_MENU_INVALID"
    waits: list[Action] = []
    actions: list[Action] = []
    seen: set[tuple[str, int | None, int | None]] = set()
    for action in state.legal_choices:
        if not isinstance(action, Action):
            return None, "LEGAL_MENU_ACTION_INVALID"
        if action.kind == "WAIT":
            if action.source is not None or action.target is not None:
                return None, "WAIT_ACTION_MALFORMED"
            waits.append(action)
        elif action.kind == "DEPLOY":
            source_id, target_id = action.source, action.target
            if (type(source_id) is not int or type(target_id) is not int
                    or source_id == target_id
                    or source_id not in towers or target_id not in towers
                    or towers[source_id].owner != state.player
                    or towers[source_id].delay != 0
                    or not _has_known_mobile(towers[source_id])):
                return None, "DEPLOY_MENU_ROW_INVALID"
            actions.append(action)
        else:
            return None, "UNSUPPORTED_MENU_ACTION"
        key = (action.kind, action.source, action.target)
        if key in seen:
            return None, "DUPLICATE_MENU_ACTION"
        seen.add(key)
    if len(waits) != 1:
        return None, "WAIT_MENU_ENTRY_NOT_UNIQUE"

    return {
        "towers": towers,
        "actions": tuple(actions),
        "wait": waits[0],
        "force_markers": force_markers,
        "player": state.player,
        # The global world tick is recorded, never treated as match age.
        "visible_tick": state.tick,
    }, None


def _empty(tower: Any) -> bool:
    return all(value == 0 for value in tower.units)


def _ruler_count(tower: Any) -> int:
    return tower.units[_SLOT_RULER]


def _garrison_proxy(tower: Any) -> int:
    """Visible count proxy only; deliberately not a combat outcome estimate."""
    return sum(tower.units[:6]) + tower.units[_SLOT_RULER]


def _mobile_proxy(tower: Any) -> int:
    """Typed ordinary-Many count heuristic, never a dispatch reconstruction."""
    return sum(tower.units[1:6])


def _stationary_shield_reserve(tower: Any) -> int:
    """Conservative fixed reserve proxy; Projector Shield may deploy."""
    return 0 if tower.kind == 15 else tower.units[_SLOT_SHIELD]


def _required_shield_reserve(enemy_ids: list[int], towers: dict[int, Any]) -> int:
    """Fixed reserve heuristic: one stationary Shield per ten enemy counts."""
    if not enemy_ids:
        return 0
    max_enemy = max(_garrison_proxy(towers[enemy_id]) for enemy_id in enemy_ids)
    return max(1, (max_enemy + 9) // 10)


def _observation_opening(view: dict[str, Any], decision_index: int | None,
                         first_observed_tick: int | None) -> dict[str, Any]:
    """Use only caller-supplied session history, never global tick as age."""
    if decision_index is None or first_observed_tick is None:
        return {"status": "UNKNOWN", "elapsed_ticks": None,
                "early_window": False,
                "basis": "CALLER_HISTORY_INCOMPLETE"}
    elapsed = (view["visible_tick"] - first_observed_tick) & 0xFFFF
    if elapsed > 0x7FFF:
        return {"status": "UNKNOWN", "elapsed_ticks": None,
                "early_window": False,
                "basis": "WRAPPED_ELAPSED_AMBIGUOUS"}
    early = decision_index < 6 and elapsed <= 80
    return {"status": "KNOWN", "elapsed_ticks": elapsed,
            "decision_index": decision_index, "early_window": early,
            "basis": "CALLER_OBSERVATION_SESSION_HISTORY"}


def _has_known_mobile(tower: Any) -> bool:
    """Recognized mobile facts admitted by this bounded policy surface."""
    return (_mobile_proxy(tower) > 0 or _ruler_count(tower) > 0
            or (tower.kind == 15 and tower.units[_SLOT_SHIELD] > 0))


def _enemy_neighbors(view: dict[str, Any], tower_id: int) -> list[Any]:
    towers = view["towers"]
    player = view["player"]
    return [towers[action.target] for action in view["actions"]
            if action.source == tower_id
            and towers[action.target].owner not in (None, player)]


def _pressure(view: dict[str, Any], tower: Any) -> tuple[float, list[int]]:
    """Enemy ratio among visible targets in the legal menu only."""
    enemies = _enemy_neighbors(view, tower.id)
    if not enemies:
        return 0.0, []
    denominator = max(1, _garrison_proxy(tower))
    ratios = [(float(_garrison_proxy(enemy)) / denominator, enemy.id)
              for enemy in enemies]
    risk, _ = max(ratios, key=lambda row: (row[0], -row[1]))
    return risk, sorted(enemy_id for _, enemy_id in ratios)


def _decision(provider: str, action: Action, reason: str,
              evidence: dict[str, Any]) -> dict[str, Any]:
    return {"provider": provider, "status": "DECIDED", "action": action,
            "reason": reason, "evidence": evidence}


def choose_b0(state: VisiblePolicyState, *, decision_index: int | None = None,
              first_observed_tick: int | None = None) -> dict[str, Any]:
    """Fixed no-search priority policy over the current legal menu.

    Priority is pressured-Ruler withdrawal, local own-tower reinforcement,
    obvious visible-enemy attack, then known empty-neutral expansion. All
    thresholds are fixed heuristics; no transition or future state is scored.
    """
    view, error = _inspect_view(state)
    if error:
        return _unknown("B0", error)
    assert view is not None
    if (decision_index is not None
            and (type(decision_index) is not int or decision_index < 0)):
        return _unknown("B0", "DECISION_INDEX_INVALID")
    if (first_observed_tick is not None
            and (type(first_observed_tick) is not int
                 or not 0 <= first_observed_tick <= 0xFFFF)):
        return _unknown("B0", "FIRST_OBSERVED_TICK_INVALID")
    evidence_base = {
        "visible_tick": view["visible_tick"],
        "decision_index": decision_index,
        "first_observed_tick": first_observed_tick,
        "unrouted_force_markers": view["force_markers"],
        "neighbor_feature_scope": "VISIBLE_ENEMY_TARGETS_IN_CURRENT_LEGAL_MENU_ONLY; ABSENCE_IS_NOT_SAFETY_PROOF",
    }
    towers = view["towers"]
    own = [tower for tower in towers.values() if tower.owner == view["player"]]
    pressure = {tower.id: _pressure(view, tower) for tower in own}

    # Keep Ruler-containing towers out of ordinary all-mobile dispatch. A
    # pressured Ruler may leave only for a visibly safer own tower.
    retreats = []
    for source in own:
        risk, enemy_ids = pressure[source.id]
        if _ruler_count(source) == 0 or risk < 1.0:
            continue
        for action in view["actions"]:
            if action.source != source.id:
                continue
            target = towers[action.target]
            target_risk = pressure.get(target.id, (0.0, []))[0]
            if (target.owner == view["player"] and _ruler_count(target) == 0
                    and target_risk < risk):
                retreats.append((-risk, target_risk, source.id, target.id,
                                 action, enemy_ids))
    if retreats:
        row = min(retreats, key=lambda item: item[:4])
        _, target_risk, source_id, target_id, action, enemy_ids = row
        return _decision("B0", action, "FIXED_PRESSURED_RULER_WITHDRAWAL",
                         {**evidence_base, "source_id": source_id,
                          "target_id": target_id,
                          "source_enemy_neighbors": enemy_ids,
                          "target_pressure_ratio": target_risk,
                          "action_amount": "ALL_CURRENT_MOBILE_BY_MENU"})

    # Fixed visible defense: reinforce the most pressured own non-Ruler tower
    # from the strongest safer non-Ruler donor. A Ruler tower is reserved.
    reinforcements = []
    for target in own:
        target_risk, enemy_ids = pressure[target.id]
        if _ruler_count(target) or target_risk < 1.0:
            continue
        for action in view["actions"]:
            if action.target != target.id or action.source == target.id:
                continue
            source = towers[action.source]
            source_risk = pressure.get(source.id, (0.0, []))[0]
            mobile = _mobile_proxy(source)
            exposed = bool(pressure.get(source.id, (0.0, []))[1])
            reserve = _stationary_shield_reserve(source)
            if (_ruler_count(source) == 0 and mobile > 0
                    and (not exposed or reserve >= 1)
                    and source_risk < target_risk):
                reinforcements.append((-target_risk, source_risk, -mobile,
                                       target.id, source.id, action, enemy_ids))
    if reinforcements:
        row = min(reinforcements, key=lambda item: item[:5])
        _, source_risk, neg_mobile, target_id, source_id, action, enemy_ids = row
        return _decision("B0", action, "FIXED_LOCAL_DEFENSE_REINFORCEMENT",
                         {**evidence_base, "source_id": source_id,
                          "target_id": target_id,
                          "target_enemy_neighbors": enemy_ids,
                          "target_pressure_ratio": pressure[target_id][0],
                          "source_pressure_ratio": source_risk,
                          "donor_mobile_proxy": -neg_mobile,
                          "source_stationary_shield_reserve": _stationary_shield_reserve(towers[source_id]),
                          "source_exposure_scope": "CURRENT_LEGAL_MENU_ONLY",
                          "action_amount": "ALL_CURRENT_MOBILE_BY_MENU"})

    # Force markers expose no certified route or owner. They block attacks
    # and speculative expansion, while visible tower-to-tower defense above
    # remains available from positive tower facts.
    if view["force_markers"]:
        return _decision("B0", view["wait"], "VISIBLE_FORCE_ROUTES_UNKNOWN",
                         {**evidence_base, "route_inference": "NONE"})

    # Engage a visibly weaker adjacent enemy only with a fixed count margin.
    # This is a local heuristic, not a combat prediction.
    attacks = []
    for action in view["actions"]:
        source, target = towers[action.source], towers[action.target]
        if (source.owner != view["player"] or target.owner in (None, view["player"])
                or _ruler_count(source) > 0):
            continue
        mobile = _mobile_proxy(source)
        enemy = max(1, _garrison_proxy(target))
        ratio = float(mobile) / enemy
        exposed = bool(pressure.get(source.id, (0.0, []))[1])
        if (mobile > 0 and ratio >= 2.0
                and (not exposed or _stationary_shield_reserve(source) >= 1)):
            attacks.append((-ratio, target.id, source.id, action, mobile, enemy))
    if attacks:
        _, target_id, source_id, action, mobile, enemy = min(
            attacks, key=lambda item: item[:3])
        return _decision("B0", action, "FIXED_OBVIOUS_VISIBLE_ATTACK",
                         {**evidence_base, "source_id": source_id,
                          "target_id": target_id,
                          "source_mobile_proxy": mobile,
                          "target_garrison_proxy": enemy,
                          "heuristic_ratio": mobile / enemy,
                          "action_amount": "ALL_CURRENT_MOBILE_BY_MENU"})

    candidates = []
    for action in view["actions"]:
        source, target = towers[action.source], towers[action.target]
        source_risk = pressure.get(source.id, (0.0, []))[0]
        mobile = _mobile_proxy(source)
        exposed = bool(pressure.get(source.id, (0.0, []))[1])
        if (source.owner == view["player"] and target.owner is None
                and _empty(target) and _ruler_count(source) == 0
                and mobile > 0
                and (not exposed or _stationary_shield_reserve(source) >= 1)):
            candidates.append((source_risk, -mobile, target.id,
                               source.id, action))
    if candidates:
        source_risk, neg_mobile, target_id, source_id, action = min(
            candidates, key=lambda row: row[:4])
        return _decision("B0", action, "HEURISTIC_EMPTY_NEUTRAL_EXPANSION",
                         {**evidence_base, "source_id": source_id,
                          "target_id": target_id,
                          "target_units": list(towers[target_id].units),
                          "target_owner": towers[target_id].owner,
                          "source_pressure_ratio": source_risk,
                          "source_mobile_proxy": -neg_mobile,
                          "source_stationary_shield_reserve": _stationary_shield_reserve(towers[source_id]),
                          "source_exposure_scope": "CURRENT_LEGAL_MENU_ONLY",
                          "action_amount": "ALL_CURRENT_MOBILE_BY_MENU"})
    return _decision("B0", view["wait"], "NO_HIGHER_PRIORITY_FIXED_ACTION",
                     evidence_base)


def choose_b1(state: VisiblePolicyState, *, decision_index: int | None = None,
              first_observed_tick: int | None = None) -> dict[str, Any]:
    """Deterministic local greedy policy using only current visible tower facts."""
    view, error = _inspect_view(state)
    if error:
        return _unknown("B1", error)
    assert view is not None
    if (decision_index is not None
            and (type(decision_index) is not int or decision_index < 0)):
        return _unknown("B1", "DECISION_INDEX_INVALID")
    if (first_observed_tick is not None
            and (type(first_observed_tick) is not int
                 or not 0 <= first_observed_tick <= 0xFFFF)):
        return _unknown("B1", "FIRST_OBSERVED_TICK_INVALID")

    towers = view["towers"]
    player = view["player"]
    own = [tower for tower in towers.values() if tower.owner == player]
    pressure = {tower.id: _pressure(view, tower) for tower in own}
    opening = _observation_opening(view, decision_index, first_observed_tick)
    evidence_base = {
        "visible_tick": view["visible_tick"],
        "decision_index": decision_index,
        "first_observed_tick": first_observed_tick,
        "unrouted_force_markers": view["force_markers"],
        "force_routes_used": False,
        "neighbor_feature_scope": "VISIBLE_ENEMY_TARGETS_IN_CURRENT_LEGAL_MENU_ONLY; ABSENCE_IS_NOT_SAFETY_PROOF",
        "observation_session_opening": opening,
        "garrison_proxy": "sum visible Shield/Fighter/Chopper/Bomber/Tank/Soldier/Ruler counts; heuristic only",
    }

    # Heuristic royal response: evacuate only toward an own non-Ruler tower
    # with lower observed-menu pressure. This is not a safety certification.
    retreats = []
    for core in own:
        core_risk, enemy_ids = pressure[core.id]
        if _ruler_count(core) == 0 or core_risk < 1.0:
            continue
        for action in view["actions"]:
            if action.source != core.id:
                continue
            target = towers[action.target]
            target_risk, _ = pressure.get(target.id, (0.0, []))
            if (target.owner == player and _ruler_count(target) == 0
                    and target_risk < core_risk):
                retreats.append(( -core_risk, target_risk, core.id,
                                  target.id, action, enemy_ids))
    if retreats:
        _, target_risk, source_id, target_id, action, enemy_ids = min(
            retreats, key=lambda row: row[:4])
        return _decision("B1", action, "HEURISTIC_PRESSURED_RULER_WITHDRAWAL",
                         {**evidence_base, "source_id": source_id,
                          "target_id": target_id,
                          "source_enemy_neighbors": enemy_ids,
                          "target_pressure_ratio": target_risk,
                          "escape_certified_safe": False,
                          "action_amount": "ALL_CURRENT_MOBILE_BY_MENU"})

    # Allocate a safe non-Ruler donor to the most exposed own tower. The ratio
    # is a local priority feature, never a predicted battle or merge result.
    reinforcements = []
    for target in own:
        target_risk, enemy_ids = pressure[target.id]
        if _ruler_count(target) or target_risk < 1.0:
            continue
        for action in view["actions"]:
            if action.target != target.id or action.source == target.id:
                continue
            source = towers[action.source]
            source_risk, source_enemy_ids = pressure.get(source.id, (0.0, []))
            mobile = _mobile_proxy(source)
            exposed = bool(source_enemy_ids)
            reserve = _stationary_shield_reserve(source)
            reserve_needed = _required_shield_reserve(source_enemy_ids, towers)
            if (_ruler_count(source) == 0 and mobile > 0
                    and (not exposed or reserve >= reserve_needed)
                    and source_risk < target_risk):
                enemy_power = max((_garrison_proxy(towers[eid])
                                   for eid in enemy_ids), default=0)
                needed = max(1, enemy_power - _mobile_proxy(target))
                if mobile < needed:
                    continue
                # This chooses among whole-mobile menu actions; the count
                # deficit is a fixed priority proxy, not an exact battle result.
                reinforcements.append((-target_risk, source_risk, mobile,
                                       target.id, source.id, needed, action,
                                       enemy_ids, source_enemy_ids,
                                       reserve_needed, reserve))
    if reinforcements:
        row = min(reinforcements, key=lambda item: item[:5])
        (_, source_risk, mobile, target_id, source_id, needed, action,
         enemy_ids, source_enemy_ids, reserve_needed, reserve) = row
        return _decision("B1", action, "LOCAL_THREAT_RATIO_REINFORCEMENT",
                         {**evidence_base, "source_id": source_id,
                          "target_id": target_id,
                          "target_enemy_neighbors": enemy_ids,
                          "source_enemy_neighbors": source_enemy_ids,
                          "target_pressure_ratio": pressure[target_id][0],
                          "source_pressure_ratio": source_risk,
                          "donor_mobile_proxy": mobile,
                          "local_count_deficit_proxy": needed,
                          "donor_rule": "SMALLEST_SAFE_DONOR_MEETING_FIXED_COUNT_DEFICIT",
                          "source_stationary_shield_reserve": reserve,
                          "source_stationary_shield_reserve_required": reserve_needed,
                          "source_exposure_scope": "CURRENT_LEGAL_MENU_ONLY",
                          "action_amount": "ALL_CURRENT_MOBILE_BY_MENU"})

    # A force marker has no certified endpoint or owner. It globally blocks
    # offensive inference but does not become a fabricated enemy threat.
    if view["force_markers"]:
        return _decision("B1", view["wait"], "VISIBLE_FORCE_ROUTES_UNKNOWN",
                         {**evidence_base, "route_inference": "NONE"})

    # During a supplied, known observation-session opening, expansion gets
    # priority over attacks. This is a fixed session heuristic, not match age.
    if opening["early_window"]:
        opening_expansions = []
        for action in view["actions"]:
            source, target = towers[action.source], towers[action.target]
            source_risk, enemy_ids = pressure.get(source.id, (0.0, []))
            reserve = _stationary_shield_reserve(source)
            reserve_needed = _required_shield_reserve(enemy_ids, towers)
            if (source.owner == player and _ruler_count(source) == 0
                    and target.owner is None and _empty(target)
                    and _mobile_proxy(source) > 0
                    and (not enemy_ids or reserve >= reserve_needed)):
                opening_expansions.append((source_risk,
                                           -_mobile_proxy(source), target.id,
                                           source.id, action, enemy_ids,
                                           reserve, reserve_needed))
        if opening_expansions:
            (source_risk, neg_mobile, target_id, source_id, action, enemy_ids,
             reserve, reserve_needed) = min(
                 opening_expansions, key=lambda item: item[:4])
            return _decision("B1", action,
                             "OBSERVATION_SESSION_OPENING_EXPANSION_HEURISTIC",
                             {**evidence_base, "source_id": source_id,
                              "target_id": target_id,
                              "source_enemy_neighbors": enemy_ids,
                              "source_pressure_ratio": source_risk,
                              "source_mobile_proxy": -neg_mobile,
                              "source_stationary_shield_reserve": reserve,
                              "source_stationary_shield_reserve_required": reserve_needed,
                              "action_amount": "ALL_CURRENT_MOBILE_BY_MENU"})

    # Engage only a visible enemy neighbor with a strong local count margin;
    # Ruler-carrying sources are excluded by the fixed royal-safety rule.
    engagements = []
    for action in view["actions"]:
        source, target = towers[action.source], towers[action.target]
        if (source.owner != player or target.owner in (None, player)
                or _ruler_count(source) > 0):
            continue
        source_power = _mobile_proxy(source)
        target_power = max(1, _garrison_proxy(target))
        ratio = float(source_power) / target_power
        exposed = bool(pressure.get(source.id, (0.0, []))[1])
        enemy_ids = pressure.get(source.id, (0.0, []))[1]
        reserve = _stationary_shield_reserve(source)
        reserve_needed = _required_shield_reserve(enemy_ids, towers)
        if (source_power > 0 and ratio >= 1.5
                and (not exposed or reserve >= reserve_needed)):
            engagements.append((-ratio, target.id, source.id, action,
                                source_power, target_power, enemy_ids,
                                reserve, reserve_needed))
    if engagements:
        (_, target_id, source_id, action, source_power, target_power,
         enemy_ids, reserve, reserve_needed) = min(
             engagements, key=lambda row: row[:3])
        return _decision("B1", action, "LOCAL_VISIBLE_ENEMY_ENGAGEMENT",
                         {**evidence_base, "source_id": source_id,
                          "target_id": target_id,
                          "source_mobile_proxy": source_power,
                          "target_garrison_proxy": target_power,
                          "heuristic_ratio": source_power / target_power,
                          "source_enemy_neighbors": enemy_ids,
                          "source_stationary_shield_reserve": reserve,
                          "source_stationary_shield_reserve_required": reserve_needed,
                          "action_amount": "ALL_CURRENT_MOBILE_BY_MENU"})

    # Expand only into a fully known empty neutral tower. Prefer a source with
    # lower observed-menu pressure ratio, then smaller IDs; a visible marker is never treated as a
    # route to this target.
    expansions = []
    for action in view["actions"]:
        source, target = towers[action.source], towers[action.target]
        source_risk, source_enemy_ids = pressure.get(source.id, (0.0, []))
        exposed = bool(source_enemy_ids)
        reserve = _stationary_shield_reserve(source)
        reserve_needed = _required_shield_reserve(source_enemy_ids, towers)
        if (source.owner == player and _ruler_count(source) == 0
                and target.owner is None and _empty(target)
                and _mobile_proxy(source) > 0
                and (not exposed or reserve >= reserve_needed)):
            expansions.append((source_risk, -_mobile_proxy(source),
                               target.id, source.id, action, source_enemy_ids,
                               reserve, reserve_needed))
    if expansions:
        row = min(expansions, key=lambda item: item[:4])
        (source_risk, neg_mobile, target_id, source_id, action, enemy_ids,
         reserve, reserve_needed) = row
        return _decision("B1", action, "HEURISTIC_EMPTY_NEUTRAL_EXPANSION",
                         {**evidence_base, "source_id": source_id,
                          "target_id": target_id,
                          "source_enemy_neighbors": enemy_ids,
                          "source_pressure_ratio": source_risk,
                          "source_mobile_proxy": -neg_mobile,
                          "source_stationary_shield_reserve": reserve,
                          "source_stationary_shield_reserve_required": reserve_needed,
                          "source_exposure_scope": "CURRENT_LEGAL_MENU_ONLY",
                          "target_units": list(towers[target_id].units),
                          "action_amount": "ALL_CURRENT_MOBILE_BY_MENU"})

    return _decision("B1", view["wait"], "NO_HIGHER_PRIORITY_LOCAL_ACTION",
                     evidence_base)


def b1_or_wait(state: VisiblePolicyState, *, decision_index: int | None = None,
               first_observed_tick: int | None = None) -> dict[str, Any]:
    """Use WAIT only after the visible view and its complete menu validate."""
    decision = choose_b1(state, decision_index=decision_index,
                          first_observed_tick=first_observed_tick)
    if decision["status"] != "UNKNOWN":
        return decision
    view, error = _inspect_view(state)
    if error or view is None:
        return decision
    return {
        "provider": "B1_FALLBACK",
        "status": "FALLBACK_WAIT",
        "action": view["wait"],
        "reason": decision["reason"],
        "evidence": {"fallback": "UNCHANGED_LEGAL_MENU_WAIT",
                     "primary_status": "UNKNOWN"},
    }
