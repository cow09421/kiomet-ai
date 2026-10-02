"""Durable single-action intent and fixed-window visible-birth association."""
from __future__ import annotations

from typing import Any
from uuid import uuid4



def _vector_pairs(vector: Any) -> list[list[int]] | None:
    if not isinstance(vector, (tuple, list)):
        return None
    result = []
    seen = set()
    for pair in vector:
        if (not isinstance(pair, (tuple, list)) or len(pair) != 2 or
                type(pair[0]) is not int or type(pair[1]) is not int or
                pair[0] not in range(6) or pair[0] in seen or
                not 0 < pair[1] <= 255):
            return None
        seen.add(pair[0])
        result.append([pair[0], pair[1]])
    return sorted(result)


def build_action_intent(*, run_id: str, state: Any, source: Any, destination: Any,
                        intended_vector: Any, ui_action_type: str,
                        host_monotonic_ms: int, prior_force_ids: set[str],
                        preexisting_visible_inbound_force_to_source: bool | None,
                        source_supply_line_present: bool | None) -> dict[str, Any]:
    """Create the durable pre-gesture ledger row from the final fresh snapshot."""
    vector = _vector_pairs(intended_vector)
    if vector is None or not vector:
        raise ValueError("action ledger requires a complete positive typed intent vector")
    if (type(host_monotonic_ms) is not int or host_monotonic_ms < 0 or
            type(state.sequence) is not int or type(state.tick.value) is not int or
            not state.document_id or not state.match_id.value or
            type(state.player_id.value) is not int or state.player_id.value <= 0):
        raise ValueError("action ledger identity or clock fields are unknown")
    observed_at = state.world_sequence_observed_at_ms.value
    if type(observed_at) is not int or observed_at > host_monotonic_ms:
        raise ValueError("action ledger requires a host-monotonic first-observation time for the world sequence")
    source_type = source.tower_type.value
    destination_type = destination.tower_type.value
    if type(source_type) is not int or type(destination_type) is not int:
        raise ValueError("action ledger requires observed source and destination tower types")
    if (type(source.id) is not int or source.id < 0 or type(destination.id) is not int or
            destination.id < 0 or source.id == destination.id):
        raise ValueError("action ledger requires distinct valid endpoint IDs")
    force_rows = getattr(getattr(state, "forces", None), "value", None)
    if not isinstance(force_rows, (tuple, list)):
        raise ValueError("action ledger requires a complete pre-action force identity set")
    force_ids = []
    for force in force_rows:
        ident = getattr(getattr(force, "id", None), "value", None)
        if not isinstance(ident, str) or not ident:
            raise ValueError("action ledger rejects unknown pre-action force identity")
        force_ids.append(ident)
    if len(set(force_ids)) != len(force_ids):
        raise ValueError("action ledger rejects duplicate pre-action force identity")
    if set(force_ids) != prior_force_ids:
        raise ValueError("action ledger prior_force_ids do not exactly cover the fresh visible force set")
    if type(preexisting_visible_inbound_force_to_source) is not bool:
        raise ValueError("action ledger requires known pre-action inbound-force status")
    if source_supply_line_present is not False:
        raise ValueError("first ledger cohort requires a positively absent source supply line")
    return {
        "kind": "ACTION_INTENT",
        "intent_id": uuid4().hex,
        "cohort_id": run_id,
        "intent_host_monotonic_ms": host_monotonic_ms,
        "snapshot_sequence": state.sequence,
        "world_sequence": state.tick.value,
        "world_sequence_observed_at_host_monotonic_ms": observed_at,
        "document_id": state.document_id,
        "match_epoch": {"document_id": state.document_id,
                         "match_id": state.match_id.value,
                         "player_id": state.player_id.value,
                         "lifecycle": getattr(state.lifecycle, "value", None)},
        "player_id": state.player_id.value,
        "client_sha256": state.client_sha256,
        "source": {"tower_id": source.id, "tower_type": source_type},
        "destination": {"tower_id": destination.id,
                        "tower_type": destination_type,
                        "relation": getattr(destination.relation.value, "value", destination.relation.value)},
        "intended_action": "ALL_CURRENT_DEPLOYABLE",
        "intended_unit_vector": vector,
        "unit_vector_basis": "fresh typed deployable inventory; quantity is declared intent, not dispatch guarantee",
        "selected_tower_none_confirmed": True,
        "pre_action_source_supply_line_present": source_supply_line_present,
        "prior_force_ids": sorted(prior_force_ids),
        "preexisting_visible_inbound_force_to_source": preexisting_visible_inbound_force_to_source,
        "ui_action_type": ui_action_type,
        "input_method": "official Playwright page mouse",
        "association_window_world_offsets": [1, 2],
        "association_window_policy": "fixed next two distinct world ticks; do not move or expand after observing outcome",
    }


def ui_action_result(intent: dict[str, Any], *, status: str,
                     mouse_down_host_monotonic_ms: int | None,
                     mouse_up_host_monotonic_ms: int | None,
                     error_class: str | None = None) -> dict[str, Any]:
    if status not in {"SUCCESS", "FAILURE", "UNKNOWN"}:
        raise ValueError("invalid UI delivery status")
    return {"kind": "UI_ACTION_RESULT", "intent_id": intent["intent_id"],
            "ui_delivery_status": status,
            "mouse_down_host_monotonic_ms": mouse_down_host_monotonic_ms,
            "mouse_up_host_monotonic_ms": mouse_up_host_monotonic_ms,
            "meaning": "browser mouse delivery only; server acceptance remains UNKNOWN",
            "error_class": error_class}


def associate_fixed_window(intent: dict[str, Any], ui_result: dict[str, Any] | None,
                           after_states: list[Any], prior_force_ids: set[str],
                           player_id: int) -> dict[str, Any]:
    """Select by unique lineage/pair first, then compare quantity to intent."""
    base = {"kind": "ACTION_LEDGER_ASSOCIATION", "intent_id": intent["intent_id"],
            "window_world_offsets": [1, 2], "formal_credit": 0,
            "candidate_selection_basis": "unique own NEW_TRACK lineage and exact source/destination pair; quantity is compared only after selection"}
    if ui_result is None:
        return {**base, "status": "UNRESOLVED", "reason": "UI_RESULT_UNKNOWN"}
    if ui_result.get("intent_id") != intent.get("intent_id"):
        return {**base, "status": "UNRESOLVED", "reason": "UI_RESULT_INTENT_ID_MISMATCH"}
    if ui_result.get("ui_delivery_status") != "SUCCESS":
        return {**base, "status": "UNRESOLVED", "reason": "UI_DELIVERY_NOT_SUCCESSFUL",
                "ui_delivery_status": ui_result.get("ui_delivery_status")}
    if (intent.get("pre_action_source_supply_line_present") is not False or
            intent.get("preexisting_visible_inbound_force_to_source") is not False):
        return {**base, "status": "AMBIGUOUS",
                "reason": "AMBIGUOUS_ALTERNATIVE_BIRTH_FROM_SUPPLY_LINE_OR_INBOUND_FORCE"}
    if set(intent.get("prior_force_ids", [])) != prior_force_ids:
        return {**base, "status": "UNRESOLVED", "reason": "PRIOR_FORCE_ID_SET_MISMATCH"}
    if len(after_states) != 2:
        return {**base, "status": "UNRESOLVED", "reason": "FIXED_WINDOW_MISSING_TICKS",
                "observed_window_tick_count": len(after_states)}
    expected_scope = (intent.get("document_id"), intent.get("match_epoch", {}).get("match_id"), player_id)
    if (player_id != intent.get("player_id") or
            intent.get("match_epoch", {}).get("player_id") != intent.get("player_id")):
        return {**base, "status": "UNRESOLVED", "reason": "INTENT_PLAYER_ID_MISMATCH"}
    start_tick = intent.get("world_sequence")
    if type(start_tick) is not int:
        return {**base, "status": "UNRESOLVED", "reason": "INTENT_WORLD_SEQUENCE_UNKNOWN"}
    expected_ticks = [((start_tick + i) & 0xFFFF) for i in (1, 2)]
    ticks = [getattr(state.tick, "value", None) for state in after_states]
    if len(set(ticks)) != len(ticks):
        return {**base, "status": "UNRESOLVED", "reason": "DUPLICATE_FIXED_WINDOW_TICKS",
                "observed_ticks": ticks}
    expected_lifecycle = intent.get("match_epoch", {}).get("lifecycle")
    scopes = [(state.document_id, state.match_id.value, state.player_id.value,
               getattr(state.lifecycle, "value", None)) for state in after_states]
    expected_scope = (*expected_scope, expected_lifecycle)
    if scopes != [expected_scope, expected_scope]:
        return {**base, "status": "UNRESOLVED", "reason": "DOCUMENT_MATCH_OR_PLAYER_EPOCH_CHANGED",
                "observed_ticks": ticks}
    if ticks != expected_ticks:
        return {**base, "status": "UNRESOLVED", "reason": "MISSING_OR_OUT_OF_WINDOW_TICKS",
                "expected_ticks": expected_ticks, "observed_ticks": ticks}
    if any(state.coverage != "PLAYER_VISIBLE_COMPLETE" or state.forces.value is None
           for state in after_states):
        return {**base, "status": "UNRESOLVED", "reason": "FORCE_COVERAGE_INCOMPLETE"}
    source_id = intent["source"]["tower_id"]
    destination_id = intent["destination"]["tower_id"]
    from tools.v2_controlled_transition_capture import collect_new_force_births
    analysis = collect_new_force_births(after_states, source_id, destination_id,
                                        prior_force_ids, player_id)
    candidates = analysis.get("candidates", [])
    if not analysis.get("eligible") or len(candidates) != 1:
        return {**base, "status": "AMBIGUOUS" if candidates else "UNRESOLVED",
                "reason": "NO_UNIQUE_LINEAGE_AND_PAIR_MATCH",
                "ambiguity_reasons": analysis.get("ambiguity_reasons", []),
                "candidate_count": len(candidates)}
    candidate = candidates[0]
    expected_vector = tuple((pair[0], pair[1]) for pair in intent["intended_unit_vector"])
    quantity_matches = candidate.get("birth_units") == expected_vector
    base.update({"selected_force": {"observer_id": candidate["id"], "owner": candidate["owner"],
                  "source": candidate["source"], "destination": candidate["destination"],
                  "birth_tick": candidate["birth_tick"], "progress": candidate["birth_progress"],
                  "confidence": candidate["birth_confidence"], "birth_unit_vector": candidate["birth_units"]},
                "intended_unit_vector": intent["intended_unit_vector"],
                "quantity_matches_intent": quantity_matches,
                "ui_delivery_status": "SUCCESS"})
    if not quantity_matches:
        return {**base, "status": "UNRESOLVED", "reason": "UNIQUE_BIRTH_QUANTITY_DIFFERS_FROM_INTENT"}
    return {**base, "status": "CANDIDATE_MATCHED",
            "reason": "UNIQUE_OWN_NEW_TRACK_ON_INTENDED_PAIR_IN_FIXED_WINDOW",
            "causal_attribution": "NOT_YET_VALIDATED_SOURCE_CONSERVATION"}
