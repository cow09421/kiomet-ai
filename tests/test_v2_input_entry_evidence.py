from dataclasses import replace
import gzip
import json
import math
from pathlib import Path

import pytest

from kiomet_ai.camera import world_to_page
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.state import Fact, Knowledge, Relation
from tools.v2_input_entry_evidence import (
    validate_input_entry_down,
    validate_input_entry_pair,
)


SOURCE_ID = 14090505
DESTINATION_ID = 14090504
ORIGIN = 1790869272631.5
CAMERA = (1326.0, 1077.0, 20.0)
CANVAS = {"left": 0.0, "top": 0.0, "css_width": 1280.0,
          "css_height": 900.0, "width": 1280, "height": 900, "dpr": 1.0}


def before_state():
    path = Path(__file__).parent / "fixtures/v2/controlled-transition-77636cad4e97.jsonl.gz"
    rows = [json.loads(line) for line in gzip.decompress(path.read_bytes()).decode("utf8").splitlines()]
    return state_from_dict(next(row["state"] for row in rows if row["kind"] == "BEFORE_INTENT"))


def fresh_state(state, step):
    sampled_at = state.sampled_at_ms + step
    browser_at = state.client_sampled_at_ms.value + step

    def fresh_fact(fact):
        if fact.knowledge == Knowledge.UNKNOWN:
            return fact
        return Fact(fact.value, fact.knowledge, fact.source, sampled_at)

    towers = tuple(replace(tower, **{
        name: fresh_fact(getattr(tower, name))
        for name in tower.__dataclass_fields__
        if isinstance(getattr(tower, name), Fact)
    }) for tower in state.towers)
    facts = {
        name: fresh_fact(getattr(state, name))
        for name in state.__dataclass_fields__
        if isinstance(getattr(state, name), Fact)
    }
    facts["client_sampled_at_ms"] = Fact(browser_at, Knowledge.OBSERVED,
        state.client_sampled_at_ms.source, sampled_at)
    return replace(state, sequence=state.sequence + step, sampled_at_ms=sampled_at,
        received_at_ms=state.received_at_ms + step, towers=towers, **facts)


def _units7(units):
    counts = dict(units.counts)
    if any(counts[k] for k in range(6, 10)):
        special = next(k for k in range(6, 10) if counts[k])
        return [1, counts[special], special, 0, 0, 0, 0]
    return [0, counts[1], counts[2], counts[3], counts[4], counts[5], counts[0]]


def raw_world(state, camera=CAMERA):
    towers = []
    for tower in state.towers:
        towers.append({
            "id": tower.id, "visible": True,
            "visibility_source": "official Visible.refs positive + generated tower",
            "owner": tower.owner.value,
            "relation": (tower.relation.value.value if isinstance(tower.relation.value, Relation)
                         else tower.relation.value),
            "type": tower.tower_type.value,
            "units7": _units7(tower.units.value),
            "position": list(tower.position.value),
        })
    return {
        "sampled_at_ms": state.client_sampled_at_ms.value,
        "document_time_origin": ORIGIN,
        "player_id": state.player_id.value,
        "root_candidate": 100,
        "root_slot_candidate": 200,
        "tick": state.tick.value,
        "active": True, "visible_pending": False,
        "online": True, "transport_mode": "NETWORK",
        "transport_connected": True, "expanded_visibility": False,
        "play_text": None, "owned_transports": [{"kind": "WEBSOCKET", "state": 1}],
        "camera_candidate": list(camera),
        "coverage": "PLAYER_VISIBLE_COMPLETE", "positive_refs": len(towers),
        "selected_tower": None, "towers": towers,
    }


def entry(state, stage, *, camera=CAMERA, coords=None, time_stamp=10.0,
          performance_now=10.0, origin=ORIGIN, raw_patch=None, event_patch=None,
          canvas=CANVAS):
    raw = raw_world(state, camera)
    if raw_patch:
        raw.update(raw_patch)
    ident = SOURCE_ID if stage == "MOUSEDOWN_ENTRY" else DESTINATION_ID
    actor = next(row for row in raw["towers"] if row["id"] == ident)
    if coords is None:
        coords = world_to_page(*actor["position"], *camera,
            canvas["css_width"], canvas["css_height"], 1,
            canvas["left"], canvas["top"])
    event = {
        "type": "mousedown" if stage == "MOUSEDOWN_ENTRY" else "mouseup",
        "isTrusted": True, "button": 0,
        "buttons": 1 if stage == "MOUSEDOWN_ENTRY" else 0,
        "client_x": coords[0], "client_y": coords[1],
        "page_x": coords[0], "page_y": coords[1],
        "timeStamp": time_stamp,
        "ctrlKey": False, "shiftKey": False, "altKey": False, "metaKey": False,
    }
    if event_patch:
        event.update(event_patch)
    return {"stage": stage, "event": event, "browser_clock": {
        "date_now_ms": state.client_sampled_at_ms.value,
        "performance_time_origin_ms": origin, "performance_now_ms": performance_now,
    }, "canvas": dict(canvas), "raw": raw}


def pair(state=None, *, down_patch=None, up_patch=None):
    state = state or before_state()
    down_state, up_state = fresh_state(state, 1), fresh_state(state, 2)
    down = entry(down_state, "MOUSEDOWN_ENTRY", **(down_patch or {}))
    up_options = {"time_stamp": 11.0, "performance_now": 11.0}
    up_options.update(up_patch or {})
    up = entry(up_state, "MOUSEUP_ENTRY", **up_options)
    return validate_input_entry_pair(state, down, up,
        client_sha256=CLIENT_SHA256, document_time_origin_ms=ORIGIN,
        expected_source_id=SOURCE_ID, expected_destination_id=DESTINATION_ID,
        down_state=down_state, up_state=up_state)


def test_entry_pair_qualifies_only_fresh_projected_trusted_endpoints():
    result = pair()
    assert result["qualified"] is True
    assert result["certificate"]["scope"] == "ENTRY_ENDPOINTS_ONLY"
    assert result["certificate"]["gesture_route_continuity"] == "UNKNOWN"
    assert result["certificate"]["source"]["tower_id"] == SOURCE_ID
    assert result["certificate"]["destination"]["tower_id"] == DESTINATION_ID


def test_down_helper_can_reject_before_pointer_moves():
    state = before_state()
    down_state = fresh_state(state, 1)
    down = entry(down_state, "MOUSEDOWN_ENTRY")
    result = validate_input_entry_down(state, down, client_sha256=CLIENT_SHA256,
        document_time_origin_ms=ORIGIN, expected_source_id=SOURCE_ID, entry_state=down_state)
    assert result["qualified"] is True
    assert result["certificate"]["scope"] == "DOWN_SOURCE_ENDPOINT_ONLY"
    assert result["certificate"]["gesture_route_continuity"] == "UNKNOWN"


@pytest.mark.parametrize("patch,reason", [
    ({"up_patch": {"camera": (1326.0, 1077.0, 19.0)}}, "entry_camera_changed_during_gesture"),
    ({"up_patch": {"coords": (0.0, 0.0)}}, "entry_coordinate_matches_no_visible_tower_center"),
    ({"up_patch": {"raw_patch": {"selected_tower": False}}}, "up_selection_not_explicitly_none"),
    ({"up_patch": {"raw_patch": {"selected_tower": 0}}}, "up_selection_not_explicitly_none"),
    ({"up_patch": {"raw_patch": {"selected_tower": "missing"}}}, "up_selection_not_explicitly_none"),
    ({"up_patch": {"raw_patch": {"document_time_origin": ORIGIN + 1}}},
     "entry_raw_document_or_sample_identity_mismatch"),
    ({"up_patch": {"origin": ORIGIN + 1}}, "entry_browser_clock_invalid"),
    ({"up_patch": {"time_stamp": 9.0, "performance_now": 9.0}},
     "entry_browser_performance_clock_not_monotonic"),
    ({"up_patch": {"event_patch": {"button": True}}},
     "entry_not_trusted_unmodified_left_button_endpoint"),
    ({"up_patch": {"camera": (1326.0, 1077.0, math.nan), "coords": (300.0, 300.0)}},
     "entry_canvas_or_camera_invalid"),
])
def test_pair_rejects_changed_unknown_or_malformed_evidence(patch, reason):
    result = pair(up_patch=patch["up_patch"])
    assert result["qualified"] is False
    assert result["reason"] == reason
    assert result["certificate"]["gesture_route_continuity"] == "UNKNOWN"


def test_pair_rejects_camera_projection_ties_and_missing_or_hidden_endpoint():
    state = before_state()
    # At extreme zoom all visible centers collapse into the same one-pixel target.
    tie = pair(state, down_patch={"camera": (1326.0, 1077.0, 1e9)},
               up_patch={"camera": (1326.0, 1077.0, 1e9)})
    assert tie["qualified"] is False
    assert "entry_coordinate" in tie["reason"]

    up_state = fresh_state(state, 2)
    up = entry(up_state, "MOUSEUP_ENTRY", time_stamp=11.0, performance_now=11.0)
    up["raw"]["towers"] = [row for row in up["raw"]["towers"] if row["id"] != DESTINATION_ID]
    up["raw"]["positive_refs"] -= 1
    down_state = fresh_state(state, 1)
    result = validate_input_entry_pair(state, entry(down_state, "MOUSEDOWN_ENTRY"), up,
        client_sha256=CLIENT_SHA256, document_time_origin_ms=ORIGIN,
        expected_source_id=SOURCE_ID, expected_destination_id=DESTINATION_ID,
        down_state=down_state, up_state=up_state)
    assert result["qualified"] is False

    absent_selection = entry(up_state, "MOUSEUP_ENTRY", time_stamp=11.0, performance_now=11.0)
    del absent_selection["raw"]["selected_tower"]
    result = validate_input_entry_pair(state, entry(down_state, "MOUSEDOWN_ENTRY"), absent_selection,
        client_sha256=CLIENT_SHA256, document_time_origin_ms=ORIGIN,
        expected_source_id=SOURCE_ID, expected_destination_id=DESTINATION_ID,
        down_state=down_state, up_state=up_state)
    assert result["qualified"] is False
    assert result["reason"] == "up_selection_not_explicitly_none"


def test_pair_rejects_backwards_displayed_tick_with_monotonic_browser_clocks():
    state = before_state()
    down_state = fresh_state(state, 1)
    up_state = fresh_state(state, 2)
    up_state = replace(up_state, tick=Fact((down_state.tick.value - 1) & 0xffff,
        Knowledge.OBSERVED, up_state.tick.source, up_state.sampled_at_ms))
    down = entry(down_state, "MOUSEDOWN_ENTRY", time_stamp=10.0, performance_now=10.0)
    up = entry(up_state, "MOUSEUP_ENTRY", time_stamp=11.0, performance_now=11.0)
    result = validate_input_entry_pair(state, down, up,
        client_sha256=CLIENT_SHA256, document_time_origin_ms=ORIGIN,
        expected_source_id=SOURCE_ID, expected_destination_id=DESTINATION_ID,
        down_state=down_state, up_state=up_state)
    assert result["qualified"] is False
    assert result["reason"] == "entry_displayed_tick_order_not_forward"


@pytest.mark.parametrize("field", ["received_at_ms", "sequence"])
def test_pair_rejects_nonmonotonic_canonical_order_with_valid_browser_clocks(field):
    state = before_state()
    down_state = fresh_state(state, 1)
    up_state = fresh_state(state, 2)
    up_state = replace(up_state, **{field: getattr(down_state, field)})
    down = entry(down_state, "MOUSEDOWN_ENTRY", time_stamp=10.0, performance_now=10.0)
    up = entry(up_state, "MOUSEUP_ENTRY", time_stamp=11.0, performance_now=11.0)
    result = validate_input_entry_pair(state, down, up,
        client_sha256=CLIENT_SHA256, document_time_origin_ms=ORIGIN,
        expected_source_id=SOURCE_ID, expected_destination_id=DESTINATION_ID,
        down_state=down_state, up_state=up_state)
    assert result["qualified"] is False
    assert result["reason"] == "entry_canonical_sample_order_not_monotonic"


def test_pair_rejects_stale_canonical_source_facts_and_mismatched_document_identity():
    state = before_state()
    source = next(t for t in state.towers if t.id == SOURCE_ID)
    stale_source = replace(source, position=Fact(source.position.value,
        Knowledge.DERIVED, source.position.source, state.sampled_at_ms + 1))
    stale = replace(state, towers=tuple(stale_source if t.id == SOURCE_ID else t for t in state.towers))
    result = pair(stale)
    assert result["qualified"] is False
    assert "not_fresh" in result["reason"]

    other_match = replace(state, match_id=Fact("other-match", Knowledge.DERIVED,
        state.match_id.source, state.sampled_at_ms))
    down_state, up_state = fresh_state(state, 1), fresh_state(state, 2)
    down, up = entry(down_state, "MOUSEDOWN_ENTRY"), entry(up_state, "MOUSEUP_ENTRY", time_stamp=11, performance_now=11)
    result = validate_input_entry_pair(state, down, up, client_sha256=CLIENT_SHA256,
        document_time_origin_ms=ORIGIN, expected_source_id=SOURCE_ID,
        expected_destination_id=DESTINATION_ID, down_state=down_state,
        up_state=fresh_state(other_match, 2))
    assert result["qualified"] is False
    assert result["reason"] == "entry_canonical_identity_changed"
