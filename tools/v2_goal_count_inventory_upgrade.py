"""Goal017 count-only normal-panel identity and bounded Cliff -> Quarry gate.

The identity projection uses only explicit normal-panel unit-count numerators.
Capacity denominators and observer morale/capacity facts are intentionally not
interpreted. Every current visible tower is compared before owner, type, or
upgrade eligibility is considered; omitted panel rows add no zero constraints.
"""
from __future__ import annotations

from kiomet_ai.observe import TOWER_TYPES, UNIT_NAMES
from tools import v2_goal_inventory_upgrade as prior
from tools.v2_goal_upgrade_probe import (
    _known, candidate_rows, inspect_upgrade_dom,
)


CLIFF = TOWER_TYPES.index("Cliff")
QUARRY = TOWER_TYPES.index("Quarry")
_OVERFLOW = prior._OVERFLOW
_LABEL_TO_UNIT = prior._LABEL_TO_UNIT
_SOURCE_RULE_CONDITIONAL = (
    "pinned public raw TowerType capacity plus fixed overflow rule; "
    "conservative clamp only, not an observed current UI capacity"
)

# Keep the known-good parser/scope/vector and scoped DOM implementation shared.
_vector = prior._vector
_parse_rows = prior._parse_rows
_scope_reasons = prior._scope_reasons
dom_snapshot = prior.async_dom_snapshot


def _fact_value(fact, state):
    ok, value = _known(fact, state, coherent=True)
    return value if ok else None


def _current_visible_towers(state):
    """Return all visible towers, refusing invalid or duplicated identities."""
    towers = getattr(state, "towers", None)
    if not isinstance(towers, (tuple, list)):
        return None, ["VISIBLE_TOWER_SET_UNKNOWN"]
    ids = []
    reasons = []
    for tower in towers:
        tower_id = getattr(tower, "id", None)
        if type(tower_id) is not int or tower_id < 0:
            reasons.append("VISIBLE_TOWER_ID_INVALID")
        else:
            ids.append(tower_id)
        visible_ok, visible = _known(getattr(tower, "visibility", None), state, coherent=True)
        if not visible_ok or visible is not True:
            reasons.append("VISIBLE_TOWER_VISIBILITY_UNKNOWN_OR_STALE")
    if len(ids) != len(set(ids)):
        reasons.append("VISIBLE_TOWER_ID_DUPLICATE")
    return list(towers), list(dict.fromkeys(reasons))


def _count_signature_matches(state, parsed_rows):
    """Project explicit displayed counts against every complete visible vector.

    Row denominators are deliberately ignored. A unit kind absent from the DOM
    imposes no constraint, including when the canonical count for that kind is
    positive or zero.
    """
    towers, reasons = _current_visible_towers(state)
    if towers is None or reasons:
        return [], reasons
    if not parsed_rows:
        return [], ["PANEL_HAS_NO_EXPLICIT_UNIT_COUNTS"]

    constraints = []
    for name, pair in parsed_rows.items():
        if name not in UNIT_NAMES or not isinstance(pair, tuple) or len(pair) != 2:
            return [], ["PANEL_COUNT_PROJECTION_MALFORMED"]
        count, _capacity_denominator = pair
        if type(count) is not int or not 0 <= count <= 255:
            return [], ["PANEL_COUNT_PROJECTION_MALFORMED"]
        constraints.append((UNIT_NAMES.index(name), count))

    matches = []
    for tower in towers:
        units_ok, units = _known(getattr(tower, "units", None), state, coherent=True)
        vector = _vector(units) if units_ok else None
        if vector is None:
            return [], ["VISIBLE_TOWER_UNITS_UNKNOWN_STALE_OR_MALFORMED"]
        if all(vector[unit_id] == count for unit_id, count in constraints):
            matches.append(tower)
    return matches, []


def _count_source_legal_reasons(state, tower):
    """Apply the frozen public Cliff -> Quarry clamp without UI capacity facts."""
    reasons = []
    owner_ok, owner = _known(getattr(tower, "owner", None), state, coherent=True)
    player_ok, player = _known(getattr(state, "player_id", None), state, coherent=True)
    if (not owner_ok or not player_ok or type(owner) is not int or type(player) is not int or
            not 1 <= owner <= 65535 or not 1 <= player <= 65535):
        reasons.append("SOURCE_OWNER_OR_PLAYER_UNKNOWN_OR_INVALID")
    elif owner != player:
        reasons.append("SOURCE_NOT_OWNED_BY_PLAYER")
    relation_ok, relation = _known(getattr(tower, "relation", None), state, coherent=True)
    if not relation_ok or getattr(relation, "value", relation) != "SELF":
        reasons.append("SOURCE_RELATION_NOT_KNOWN_SELF")

    type_ok, source_type = _known(getattr(tower, "tower_type", None), state, coherent=True)
    if not type_ok:
        reasons.append("SOURCE_TYPE_UNKNOWN_OR_STALE")
    elif source_type != CLIFF:
        reasons.append("SOURCE_TYPE_NOT_CLIFF")

    counts = _vector(_fact_value(getattr(tower, "units", None), state))
    if counts is None:
        reasons.append("SOURCE_UNITS_VECTOR_INCOMPLETE")
    else:
        if counts[9] != 0:
            reasons.append("SOURCE_HAS_RULER")
        source_caps = prior._public_capacity(CLIFF)
        target_caps = prior._public_capacity(QUARRY)
        for unit_id, name in enumerate(UNIT_NAMES):
            if counts[unit_id] > min(255, source_caps[name] + _OVERFLOW[name]):
                reasons.append("SOURCE_UNITS_EXCEED_PUBLIC_CAPACITY_PLUS_OVERFLOW")
                break
        if counts[0] > 45:
            reasons.append("SHIELD_INPUT_EXCEEDS_FROZEN_45_BOUND")
        if any(counts[i] != 0 for i in (6, 7, 8)):
            reasons.append("SHELL_EMP_NUKE_NOT_LEGAL_IN_CLIFF_VECTOR")
        if any(counts[i] > min(255, target_caps[name] + _OVERFLOW[name]) or
               target_caps[name] + _OVERFLOW[name] < source_caps[name] + _OVERFLOW[name]
               for i, name in enumerate(UNIT_NAMES) if i != 0):
            reasons.append("NONSHIELD_VECTOR_NOT_PRESERVED_BY_PUBLIC_CAPACITY")
        shield_after = min(255, target_caps["Shield"] + _OVERFLOW["Shield"])
        shield_loss = max(0, counts[0] - shield_after)
        if shield_loss > 20:
            reasons.append("SHIELD_LOSS_EXCEEDS_FROZEN_20_BOUND")

    delay_ok, delay = _known(getattr(tower, "delay_ticks", None), state, coherent=True)
    if not delay_ok or type(delay) is not int or delay != 0:
        reasons.append("SOURCE_DELAY_NOT_KNOWN_ZERO")
    return list(dict.fromkeys(reasons)), counts


def count_candidate_rows(state):
    """Return eligible Cliff -> Quarry action rows using independent clamp facts.

    Existing prerequisite/count/unlock and delay guards are reused from the
    prior candidate projection. Only its capacity-derived unknown/lower-capacity
    reasons are replaced by the frozen raw-type-plus-overflow clamp above.
    This function does not require or rewrite morale/capacity facts.
    """
    rows = []
    towers, identity_reasons = _current_visible_towers(state)
    if towers is None:
        return []
    by_id = {}
    for tower in towers:
        tower_id = getattr(tower, "id", None)
        if type(tower_id) is int:
            by_id.setdefault(tower_id, []).append(tower)

    for original in candidate_rows(state):
        if original.get("source_type") != CLIFF or original.get("target_type") != QUARRY:
            continue
        row = dict(original)
        # These legacy keys are consumed as exact-capacity fields in probe
        # logs; the count mode makes no current UI capacity claim.
        row["shield_before"] = None
        row["shield_after"] = None
        reasons = [reason for reason in original.get("reasons", ())
                   if reason not in {"SHIELD_CAPACITY_UNKNOWN", "TARGET_SHIELD_CAPACITY_LOWER"}]
        tower_id = original.get("tower_id")
        matched_towers = by_id.get(tower_id, [])
        if len(matched_towers) != 1:
            reasons.append("SOURCE_TOWER_ID_NOT_UNIQUE")
        else:
            extra, counts = _count_source_legal_reasons(state, matched_towers[0])
            reasons.extend(extra)
            if counts is not None:
                source_caps = prior._public_capacity(CLIFF)
                target_caps = prior._public_capacity(QUARRY)
                shield_after_with_overflow = min(255, target_caps["Shield"] + _OVERFLOW["Shield"])
                row.update({
                    "public_clamp_source_raw_capacity": source_caps["Shield"],
                    "public_clamp_target_raw_capacity": target_caps["Shield"],
                    "public_clamp_source_with_overflow": min(
                        255, source_caps["Shield"] + _OVERFLOW["Shield"]),
                    "public_clamp_target_with_overflow": shield_after_with_overflow,
                    "public_clamp_provenance": _SOURCE_RULE_CONDITIONAL,
                    "shield_before_max_with_overflow": None,
                    "shield_after_max_with_overflow": None,
                    "shield_loss_at_current_inventory": None,
                    "public_clamp_shield_loss_upper_bound": max(
                        0, counts[0] - shield_after_with_overflow),
                    "shield_loss_bound": 20,
                    "nonshield_units_preserved_for_source_legal_vector":
                        "NONSHIELD_VECTOR_NOT_PRESERVED_BY_PUBLIC_CAPACITY" not in reasons,
                })
        reasons.extend(identity_reasons)
        reasons.extend(_scope_reasons(state))
        row["reasons"] = list(dict.fromkeys(reasons))
        row["eligible"] = not row["reasons"]
        rows.append(row)
    return rows


def certify_count_inventory_panel(state, dom, tower_id=None):
    """Bind one normal Cliff panel by explicit counts, then check action gates.

    Count identity is established across all visible towers before owner/type
    or candidate eligibility filters run. Returned capacity denominators are
    preserved as parsed display data but never used to identify or qualify a
    source. The current UI capacity formula remains UNKNOWN.
    """
    reasons = _scope_reasons(state)
    if tower_id is not None and (type(tower_id) is not int or tower_id < 0):
        reasons.append("REQUESTED_TOWER_ID_INVALID")

    panels = dom.get("panels") if isinstance(dom, dict) else None
    if not isinstance(panels, list) or not panels:
        reasons.append("SCOPED_PANEL_SET_UNKNOWN_OR_EMPTY")
        panels = []
    if isinstance(dom, dict) and dom.get("errors"):
        reasons.append("DOM_SNAPSHOT_ERRORS")
    if len(panels) != 1:
        reasons.append("SCOPED_PANEL_ROOT_NOT_UNIQUE")
    panel = panels[0] if len(panels) == 1 and isinstance(panels[0], dict) else {}

    headings = panel.get("headings")
    if not isinstance(headings, list) or len(headings) != 1 or headings[0] != "Cliff":
        reasons.append("SCOPED_SOURCE_HEADING_NOT_EXACT_CLIFF")
        headings = headings if isinstance(headings, list) else []
    button_check = inspect_upgrade_dom(
        {"headings": headings, "buttons": panel.get("buttons")}, CLIFF, QUARRY)
    if not button_check.get("eligible"):
        reasons.extend(button_check.get("reasons", ()))

    panel_rows = panel.get("unit_rows")
    parsed, parse_reasons = _parse_rows(panel_rows)
    reasons.extend(parse_reasons)
    matches, projection_reasons = _count_signature_matches(
        state, parsed if not parse_reasons else {})
    reasons.extend(projection_reasons)
    if len(matches) > 1:
        reasons.append("CANONICAL_COUNT_SIGNATURE_NOT_UNIQUE")
    elif not matches and not projection_reasons:
        reasons.append("CANONICAL_COUNT_SIGNATURE_NOT_FOUND")

    matched = matches[0] if len(matches) == 1 else None
    matched_id = getattr(matched, "id", None) if matched is not None else None
    action_row = None
    if matched is not None:
        owner_ok, owner = _known(getattr(matched, "owner", None), state, coherent=True)
        player_ok, player = _known(getattr(state, "player_id", None), state, coherent=True)
        relation_ok, relation = _known(getattr(matched, "relation", None), state, coherent=True)
        type_ok, source_type = _known(getattr(matched, "tower_type", None), state, coherent=True)
        if (not owner_ok or not player_ok or type(owner) is not int or type(player) is not int or
                not 1 <= owner <= 65535 or not 1 <= player <= 65535):
            reasons.append("COUNT_MATCH_OWNER_OR_PLAYER_UNKNOWN_STALE_OR_INVALID")
        elif owner != player:
            reasons.append("COUNT_MATCH_NOT_OWNED_BY_PLAYER")
        if not relation_ok:
            reasons.append("COUNT_MATCH_RELATION_UNKNOWN_STALE")
        elif getattr(relation, "value", relation) != "SELF":
            reasons.append("COUNT_MATCH_RELATION_NOT_SELF")
        if not type_ok:
            reasons.append("COUNT_MATCH_TYPE_UNKNOWN_STALE")
        elif source_type != CLIFF:
            reasons.append("COUNT_MATCH_TYPE_NOT_CLIFF")

        candidate_rows = count_candidate_rows(state)
        rows_for_match = [row for row in candidate_rows
                          if row.get("tower_id") == matched_id and
                          row.get("target_type") == QUARRY]
        if len(rows_for_match) != 1:
            reasons.append("MATCHING_SOURCE_ACTION_CANDIDATE_NOT_UNIQUE")
        else:
            action_row = rows_for_match[0]
            if action_row.get("eligible") is not True:
                reasons.extend(action_row.get("reasons", ()))
                reasons.append("MATCHING_SOURCE_NOT_ACTION_ELIGIBLE")
    if tower_id is not None and matched_id != tower_id:
        reasons.append("REQUESTED_TOWER_ID_DOES_NOT_MATCH_PANEL_COUNTS")

    reasons = list(dict.fromkeys(reasons))
    return {
        "eligible": not reasons,
        "tower_id": matched_id,
        "requested_tower_id": tower_id,
        "source_type": CLIFF,
        "target_type": QUARRY,
        "reasons": reasons,
        "panel_heading": headings[0] if len(headings) == 1 else None,
        "unit_rows": parsed,
        "upgrade_title": button_check.get("exact_title"),
        "upgrade_bbox": button_check.get("bbox"),
        "signature_match_ids": [getattr(t, "id", None) for t in matches],
        "identity_basis": "explicit unit-count numerators only; capacity denominators ignored; omitted rows unconstrained",
        "capacity_formula_status": "UNKNOWN",
        "atomicity_note": "Fact freshness is per-field; panel and canonical snapshot are not atomic.",
    }


# The optional CLI protocol hook names match the existing bounded-mode adapter.
bounded_candidate_rows = count_candidate_rows
certify_inventory_panel = certify_count_inventory_panel
