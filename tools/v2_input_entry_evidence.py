"""Fail-closed checks for ordinary trusted drag endpoint entry samples."""
import math

from kiomet_ai.camera import world_to_page
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256, decode_units
from kiomet_ai.v2.state import Fact, GameState, Knowledge, Lifecycle, Relation, Tower, Units


_VISIBLE_SOURCE = "official Visible.refs positive + generated tower"
_POSITION_SOURCE = "official integer-position offset table"
_UNIT_NAMES = range(10)
_ORDINARY_UNITS = range(1, 6)
_NON_ORDINARY_UNITS = range(6, 10)
_CANVAS_KEYS = ("left", "top", "css_width", "css_height", "width", "height", "dpr")


def _failure(reason, scope):
    return {"qualified": False, "reason": reason,
            "certificate": {"scope": scope, "gesture_route_continuity": "UNKNOWN"}}


def _success(scope, **fields):
    return {"qualified": True, "reason": None,
            "certificate": {"scope": scope, "gesture_route_continuity": "UNKNOWN", **fields}}


def _number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float)) and
            math.isfinite(value))


def _fresh(fact, sampled_at_ms):
    return (isinstance(fact, Fact) and fact.knowledge in (Knowledge.OBSERVED, Knowledge.DERIVED) and
            fact.value is not None and isinstance(fact.source, str) and bool(fact.source.strip()) and
            type(fact.observed_at_ms) is int and fact.observed_at_ms == sampled_at_ms)


def _ordinary_units(units):
    if not isinstance(units, Units) or tuple(kind for kind, _ in units.counts) != tuple(_UNIT_NAMES):
        return False
    counts = dict(units.counts)
    return (all(counts[kind] == 0 for kind in _NON_ORDINARY_UNITS) and
            sum(counts[kind] for kind in _ORDINARY_UNITS) > 0)


def _fresh_state(state, client_sha256, origin, *, baseline=None):
    if not isinstance(state, GameState):
        return "canonical_entry_state_missing"
    if (client_sha256 != CLIENT_SHA256 or state.client_sha256 != CLIENT_SHA256 or
            state.client_sha256 != client_sha256):
        return "client_pin_mismatch"
    if (type(state.sampled_at_ms) is not int or type(state.received_at_ms) is not int or
            state.received_at_ms < state.sampled_at_ms or not state.session_id or
            not state.document_id or type(state.sequence) is not int or state.sequence < 1):
        return "canonical_snapshot_identity_malformed"
    for name in ("match_id", "tick", "player_id", "document_time_origin_ms", "lifecycle",
                 "source_mode", "coverage_evidence", "client_sampled_at_ms"):
        if not _fresh(getattr(state, name), state.sampled_at_ms):
            return f"canonical_fact_not_fresh:{name}"
    if not isinstance(state.match_id.value, str) or not state.match_id.value:
        return "canonical_match_identity_unknown"
    if (type(state.tick.value) is not int or not 0 <= state.tick.value <= 65535 or
            type(state.player_id.value) is not int or not 1 <= state.player_id.value <= 65535):
        return "canonical_tick_or_player_malformed"
    if state.lifecycle.value != Lifecycle.IN_MATCH or state.source_mode.value != "NETWORK":
        return "canonical_state_not_live_network_match"
    if state.coverage != "PLAYER_VISIBLE_COMPLETE":
        return "canonical_visible_coverage_incomplete"
    evidence_value = state.coverage_evidence.value
    if (not isinstance(evidence_value, tuple) or len(evidence_value) != 2 or
            any(not isinstance(row, tuple) or len(row) != 2 for row in evidence_value)):
        return "canonical_visible_coverage_evidence_malformed"
    coverage_evidence = dict(evidence_value)
    if (coverage_evidence.get("positive_sensor_slots") != len(state.towers) or
            coverage_evidence.get("decoded_current_towers") != len(state.towers)):
        return "canonical_visible_coverage_evidence_mismatch"
    if (not _number(state.document_time_origin_ms.value) or state.document_time_origin_ms.value <= 0 or
            not _number(origin) or state.document_time_origin_ms.value != origin):
        return "canonical_document_origin_mismatch"
    if (type(state.client_sampled_at_ms.value) is not int or
            state.client_sampled_at_ms.value < 0):
        return "canonical_browser_sample_clock_unknown"
    if baseline is not None and (
            state.session_id != baseline.session_id or state.document_id != baseline.document_id or
            state.match_id.value != baseline.match_id.value or
            state.player_id.value != baseline.player_id.value or
            state.client_sha256 != baseline.client_sha256 or
            state.sampled_at_ms <= baseline.sampled_at_ms or
            state.received_at_ms <= baseline.received_at_ms or
            state.sequence <= baseline.sequence):
        return "entry_canonical_identity_changed"
    return None


def _before_endpoints(before, source_id, destination_id=None):
    if type(source_id) is not int or (destination_id is not None and type(destination_id) is not int):
        return None, "endpoint_id_malformed"
    if source_id < 0 or (destination_id is not None and destination_id < 0):
        return None, "endpoint_id_malformed"
    if destination_id is not None and source_id == destination_id:
        return None, "endpoints_must_be_distinct"
    by_id = {tower.id: tower for tower in before.towers}
    if source_id not in by_id or (destination_id is not None and destination_id not in by_id):
        return None, "before_endpoint_not_currently_visible"
    used = [by_id[source_id]] + ([by_id[destination_id]] if destination_id is not None else [])
    for tower in used:
        for name in ("visibility", "owner", "relation", "tower_type", "units", "position"):
            if not _fresh(getattr(tower, name), before.sampled_at_ms):
                return None, f"before_endpoint_fact_not_fresh:{tower.id}:{name}"
        if tower.visibility.value is not True:
            return None, f"before_endpoint_not_visible:{tower.id}"
        if (type(tower.tower_type.value) is not int or not 0 <= tower.tower_type.value < 27 or
                not isinstance(tower.units.value, Units) or
                not isinstance(tower.position.value, tuple) or len(tower.position.value) != 2 or
                any(type(v) is not int for v in tower.position.value)):
            return None, f"before_endpoint_malformed:{tower.id}"
    source = by_id[source_id]
    if (source.owner.value != before.player_id.value or source.relation.value != Relation.SELF or
            not _fresh(source.deployable, before.sampled_at_ms) or
            not _ordinary_units(source.units.value) or not _ordinary_units(source.deployable.value)):
        return None, "before_source_not_own_ordinary_deployable"
    dest = by_id[destination_id] if destination_id is not None else None
    return (source, dest), None


def _raw_identity(raw, entry_state, origin):
    if not isinstance(raw, dict):
        return "entry_raw_missing"
    if (raw.get("active") is not True or raw.get("online") is not True or
            raw.get("transport_mode") != "NETWORK" or raw.get("transport_connected") is not True or
            raw.get("visible_pending") is not False or raw.get("expanded_visibility") is not False or
            raw.get("play_text") is not None or raw.get("coverage") != "PLAYER_VISIBLE_COMPLETE"):
        return "entry_raw_not_live_complete_network_state"
    if (raw.get("player_id") != entry_state.player_id.value or
            type(raw.get("player_id")) is not int or
            raw.get("tick") != entry_state.tick.value or type(raw.get("tick")) is not int or
            not 0 <= raw["tick"] <= 65535):
        return "entry_raw_player_or_tick_mismatch"
    if (not _number(raw.get("document_time_origin")) or raw["document_time_origin"] != origin or
            type(raw.get("sampled_at_ms")) is not int or raw["sampled_at_ms"] < 0 or
            raw["sampled_at_ms"] != entry_state.client_sampled_at_ms.value):
        return "entry_raw_document_or_sample_identity_mismatch"
    if raw.get("match_id") is not None and raw.get("match_id") != entry_state.match_id.value:
        return "entry_raw_match_identity_mismatch"
    roots = (raw.get("root_candidate"), raw.get("root_slot_candidate"))
    if any(type(root) is not int or root <= 0 for root in roots):
        return "entry_client_root_identity_unknown"
    refs, towers = raw.get("positive_refs"), raw.get("towers")
    if (type(refs) is not int or refs < 0 or refs > 512 * 512 or not isinstance(towers, list) or
            refs != len(towers) or len(towers) != len(entry_state.towers)):
        return "entry_raw_visible_coverage_mismatch"
    transports = raw.get("owned_transports")
    if not isinstance(transports, list) or not any(
            isinstance(row, dict) and row.get("kind") in ("WEBSOCKET", "WEBTRANSPORT", "HTTP_POLL") and
            type(row.get("state")) is int and row["state"] == 1 for row in transports):
        return "entry_owned_network_transport_not_proved"
    return None


def _camera(raw):
    camera = raw.get("camera_candidate") if isinstance(raw, dict) else None
    if (not isinstance(camera, (tuple, list)) or len(camera) != 3 or
            any(not _number(value) for value in camera) or camera[2] <= 0):
        return None
    return tuple(camera)


def _canvas(entry):
    canvas = entry.get("canvas") if isinstance(entry, dict) else None
    if not isinstance(canvas, dict):
        return None
    if any(not _number(canvas.get(key)) for key in ("left", "top", "css_width", "css_height", "dpr")):
        return None
    if (canvas["css_width"] <= 0 or canvas["css_height"] <= 0 or canvas["dpr"] != 1 or
            type(canvas.get("width")) is not int or type(canvas.get("height")) is not int or
            canvas["width"] <= 0 or canvas["height"] <= 0 or
            canvas["width"] != canvas["css_width"] or canvas["height"] != canvas["css_height"]):
        return None
    return {key: canvas[key] for key in _CANVAS_KEYS}


def _entry_header(entry, expected_stage, state, origin, player):
    if not isinstance(entry, dict) or entry.get("stage") != expected_stage:
        return None, "entry_stage_mismatch"
    raw_error = _raw_identity(entry.get("raw"), state, origin)
    if raw_error:
        return None, raw_error
    clock, event = entry.get("browser_clock"), entry.get("event")
    if not isinstance(clock, dict) or not isinstance(event, dict):
        return None, "entry_clock_or_event_missing"
    if (not _number(clock.get("performance_time_origin_ms")) or
            clock["performance_time_origin_ms"] != origin or
            not _number(clock.get("performance_now_ms")) or clock["performance_now_ms"] < 0 or
            not _number(event.get("timeStamp")) or event["timeStamp"] < 0):
        return None, "entry_browser_clock_invalid"
    want_type = "mousedown" if expected_stage == "MOUSEDOWN_ENTRY" else "mouseup"
    want_buttons = 1 if want_type == "mousedown" else 0
    if (event.get("type") != want_type or event.get("isTrusted") is not True or
            type(event.get("button")) is not int or event["button"] != 0 or
            type(event.get("buttons")) is not int or event["buttons"] != want_buttons or
            any(event.get(key) is not False or type(event.get(key)) is not bool
                for key in ("ctrlKey", "shiftKey", "altKey", "metaKey"))):
        return None, "entry_not_trusted_unmodified_left_button_endpoint"
    if any(not _number(event.get(key)) for key in ("client_x", "client_y")):
        return None, "entry_client_coordinates_invalid"
    canvas = _canvas(entry)
    camera = _camera(entry.get("raw"))
    if canvas is None or camera is None:
        return None, "entry_canvas_or_camera_invalid"
    towers = entry["raw"]["towers"]
    by_raw_id, by_state_id = {}, {tower.id: tower for tower in state.towers}
    if len(by_state_id) != len(state.towers):
        return None, "entry_canonical_tower_ids_ambiguous"
    for row in towers:
        if not isinstance(row, dict):
            return None, "entry_visible_tower_malformed"
        ident, pos = row.get("id"), row.get("position")
        if (type(ident) is not int or not 0 <= ident <= 0xffffffff or ident in by_raw_id or
                (ident & 65535) >= 512 or (ident >> 16) >= 512 or row.get("visible") is not True or
                row.get("visibility_source") != _VISIBLE_SOURCE or
                not isinstance(pos, (tuple, list)) or len(pos) != 2 or
                any(type(value) is not int for value in pos)):
            return None, "entry_visible_tower_identity_or_position_invalid"
        x, y = ident & 65535, ident >> 16
        if not (x * 5 <= pos[0] <= x * 5 + 4 and y * 5 <= pos[1] <= y * 5 + 4):
            return None, "entry_visible_tower_position_mapping_invalid"
        tower = by_state_id.get(ident)
        if tower is None:
            return None, "entry_raw_canonical_visible_ids_differ"
        if (not _fresh(tower.visibility, state.sampled_at_ms) or tower.visibility.value is not True or
                tower.visibility.source != _VISIBLE_SOURCE or
                not _fresh(tower.position, state.sampled_at_ms) or
                tower.position.source != _POSITION_SOURCE or tower.position.value != tuple(pos)):
            return None, "entry_visible_position_fact_not_fresh_or_coherent"
        by_raw_id[ident] = row
    if set(by_raw_id) != set(by_state_id):
        return None, "entry_raw_canonical_visible_ids_differ"
    return {"entry": entry, "raw": entry["raw"], "event": event, "clock": clock,
            "canvas": canvas, "camera": camera, "by_id": by_raw_id,
            "by_state_id": by_state_id}, None


def _endpoint(header, ident):
    event, canvas, camera = header["event"], header["canvas"], header["camera"]
    candidates = []
    for tower_id, row in header["by_id"].items():
        try:
            x, y = world_to_page(*row["position"], *camera,
                canvas["css_width"], canvas["css_height"], 1,
                canvas["left"], canvas["top"])
        except (ArithmeticError, TypeError, ValueError, OverflowError):
            return None, "entry_projection_failed"
        if not all(math.isfinite(coord) for coord in (x, y)):
            return None, "entry_projection_nonfinite"
        distance = math.hypot(event["client_x"] - x, event["client_y"] - y)
        if distance <= 1.0:
            candidates.append((tower_id, distance, x, y))
    if not candidates:
        return None, "entry_coordinate_matches_no_visible_tower_center"
    if len(candidates) != 1:
        return None, "entry_coordinate_matches_multiple_visible_tower_centers"
    tower_id, distance, x, y = candidates[0]
    if tower_id != ident:
        return None, "entry_coordinate_resolved_to_unexpected_tower"
    return {"tower_id": tower_id, "position": list(header["by_id"][tower_id]["position"]),
            "projected_client_center": [x, y], "event_client_point": [event["client_x"], event["client_y"]],
            "distance_css_px": distance}, None


def _entry_actor(header, tower_id, player, require_source):
    raw_tower = header["by_id"].get(tower_id)
    state_tower = header["by_state_id"].get(tower_id)
    if raw_tower is None or state_tower is None:
        return "entry_endpoint_not_currently_visible"
    if (type(raw_tower.get("owner")) is not int or not 0 <= raw_tower["owner"] <= 65535 or
            type(raw_tower.get("type")) is not int or not 0 <= raw_tower["type"] < 27):
        return "entry_endpoint_owner_or_type_unknown"
    if (not _fresh(state_tower.owner, state_tower.position.observed_at_ms) or
            not _fresh(state_tower.relation, state_tower.position.observed_at_ms) or
            not _fresh(state_tower.tower_type, state_tower.position.observed_at_ms) or
            not _fresh(state_tower.units, state_tower.position.observed_at_ms)):
        return "entry_endpoint_identity_facts_not_fresh"
    if (raw_tower["owner"] != state_tower.owner.value or raw_tower["type"] != state_tower.tower_type.value or
            raw_tower.get("relation") != (state_tower.relation.value.value if isinstance(state_tower.relation.value, Relation)
                                          else state_tower.relation.value)):
        return "entry_raw_canonical_endpoint_facts_differ"
    if not require_source:
        return None
    if (raw_tower["owner"] != header["raw"]["player_id"] or raw_tower.get("relation") != "SELF" or
            state_tower.owner.value != header["raw"]["player_id"] or
            state_tower.relation.value != Relation.SELF):
        return "entry_source_not_currently_own"
    try:
        entry_units = decode_units(raw_tower.get("units7"))
    except (TypeError, ValueError):
        return "entry_source_units_unknown_or_malformed"
    if not _ordinary_units(entry_units) or entry_units != state_tower.units.value:
        return "entry_source_not_ordinary_or_units_snapshot_mismatch"
    return None


def _check_entry_state(state, baseline, raw, client_sha256, origin):
    error = _fresh_state(state, client_sha256, origin, baseline=baseline)
    if error:
        return error
    return _raw_identity(raw, state, origin)


def validate_input_entry_down(before, down_entry, *, client_sha256, document_time_origin_ms,
                              expected_source_id, entry_state=None):
    """Validate the captured down endpoint before the builder moves the pointer."""
    scope = "DOWN_SOURCE_ENDPOINT_ONLY"
    error = _fresh_state(before, client_sha256, document_time_origin_ms)
    if error:
        return _failure(error, scope)
    endpoints, error = _before_endpoints(before, expected_source_id)
    if error:
        return _failure(error, scope)
    source, _ = endpoints
    error = _check_entry_state(entry_state, before, down_entry.get("raw") if isinstance(down_entry, dict) else None,
                               client_sha256, document_time_origin_ms)
    if error:
        return _failure(error, scope)
    header, error = _entry_header(down_entry, "MOUSEDOWN_ENTRY", entry_state,
                                  document_time_origin_ms, before.player_id.value)
    if error:
        return _failure(error, scope)
    if down_entry["raw"].get("selected_tower", "__missing__") is not None:
        return _failure("down_selection_not_explicitly_none", scope)
    entry_source = header["by_state_id"].get(expected_source_id)
    if entry_source is None or entry_source.position.value != source.position.value:
        return _failure("down_source_position_differs_from_before", scope)
    error = _entry_actor(header, expected_source_id, before.player_id.value, require_source=True)
    if error:
        return _failure(error, scope)
    endpoint, error = _endpoint(header, expected_source_id)
    if error:
        return _failure(error, scope)
    return _success(scope, source=endpoint, document_id=before.document_id,
        match_id=before.match_id.value, player_id=before.player_id.value,
        before_tick=before.tick.value, down_tick=entry_state.tick.value)


def validate_input_entry_pair(before, down_entry, up_entry, *, client_sha256,
                              document_time_origin_ms, expected_source_id,
                              expected_destination_id, down_state=None, up_state=None):
    """Prove fresh visible source/down and destination/up centers for one entry pair."""
    scope = "ENTRY_ENDPOINTS_ONLY"
    down_result = validate_input_entry_down(before, down_entry,
        client_sha256=client_sha256, document_time_origin_ms=document_time_origin_ms,
        expected_source_id=expected_source_id, entry_state=down_state)
    if not down_result["qualified"]:
        return _failure("down_" + str(down_result["reason"]), scope)
    if type(expected_destination_id) is not int or expected_destination_id == expected_source_id:
        return _failure("endpoint_id_malformed_or_not_distinct", scope)
    endpoints, error = _before_endpoints(before, expected_source_id, expected_destination_id)
    if error:
        return _failure(error, scope)
    source, destination = endpoints
    error = _check_entry_state(up_state, before, up_entry.get("raw") if isinstance(up_entry, dict) else None,
                               client_sha256, document_time_origin_ms)
    if error:
        return _failure(error, scope)
    up_header, error = _entry_header(up_entry, "MOUSEUP_ENTRY", up_state,
                                     document_time_origin_ms, before.player_id.value)
    if error:
        return _failure(error, scope)
    down_header, error = _entry_header(down_entry, "MOUSEDOWN_ENTRY", down_state,
                                       document_time_origin_ms, before.player_id.value)
    if error:
        return _failure("down_" + str(error), scope)
    if (down_entry["raw"].get("root_candidate") != up_entry["raw"].get("root_candidate") or
            down_entry["raw"].get("root_slot_candidate") != up_entry["raw"].get("root_slot_candidate")):
        return _failure("entry_client_root_identity_changed", scope)
    if down_header["camera"] != up_header["camera"]:
        return _failure("entry_camera_changed_during_gesture", scope)
    if down_header["canvas"] != up_header["canvas"]:
        return _failure("entry_canvas_geometry_changed_during_gesture", scope)
    if (down_header["clock"]["performance_now_ms"] > up_header["clock"]["performance_now_ms"] or
            down_header["event"]["timeStamp"] > up_header["event"]["timeStamp"]):
        return _failure("entry_browser_performance_clock_not_monotonic", scope)
    if (up_state.sampled_at_ms <= down_state.sampled_at_ms or
            up_state.received_at_ms <= down_state.received_at_ms or
            up_state.sequence <= down_state.sequence):
        return _failure("entry_canonical_sample_order_not_monotonic", scope)
    tick_delta = (up_state.tick.value - down_state.tick.value) & 0xffff
    # SourceClock's 16-bit ordering is only unambiguous within the forward half-range.
    # Equal ticks are valid for a gesture within one simulation tick; deltas >= 2^15
    # are backward or ambiguous and must fail closed.
    if tick_delta >= 0x8000:
        return _failure("entry_displayed_tick_order_not_forward", scope)
    if "selected_tower" not in up_entry["raw"] or up_entry["raw"]["selected_tower"] is not None:
        return _failure("up_selection_not_explicitly_none", scope)
    for tower, ident in ((source, expected_source_id), (destination, expected_destination_id)):
        current = up_header["by_state_id"].get(ident)
        if current is None or current.position.value != tower.position.value:
            return _failure(f"up_endpoint_position_differs_from_before:{ident}", scope)
    error = _entry_actor(up_header, expected_source_id, before.player_id.value, require_source=True)
    if error:
        return _failure(error, scope)
    error = _entry_actor(up_header, expected_destination_id, before.player_id.value, require_source=False)
    if error:
        return _failure(error, scope)
    endpoint, error = _endpoint(up_header, expected_destination_id)
    if error:
        return _failure(error, scope)
    return _success(scope, source=down_result["certificate"]["source"], destination=endpoint,
        document_id=before.document_id, match_id=before.match_id.value,
        player_id=before.player_id.value, before_tick=before.tick.value,
        down_tick=down_state.tick.value, up_tick=up_state.tick.value,
        document_time_origin_ms=document_time_origin_ms,
        camera=list(down_header["camera"]), canvas=down_header["canvas"])
