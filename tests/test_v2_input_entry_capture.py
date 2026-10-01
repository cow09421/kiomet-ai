import asyncio
from dataclasses import dataclass
import json
from types import SimpleNamespace as NS

import pytest

from tools.v2_input_entry_capture import (
    make_arm_declaration, make_stage_declaration, perform_buffered_drag,
    public_entry_metadata, validate_down_entry_identity, validate_observer_startup,
)
from tools.v2_controlled_transition_capture import parse_args


@dataclass
class Fact:
    value: object


@dataclass
class FakeState:
    player_id: Fact


def valid_status():
    return {"installed": True, "status": "DISARMED", "armed_once": False,
            "document_loading_at_install": True, "ready_state_at_install": "loading"}


def valid_lease():
    return {"input_entry_observer": {"observer_requested": True,
        "registered_before_controlled_page_creation": True,
        "source_sha256": "abc", "document_time_origin_ms": 12345.5,
        "controlled_document_observer_status": valid_status()}}


def test_startup_requires_exact_host_registration_digest_pristine_status_and_origin():
    checked = validate_observer_startup(valid_lease(), {
        "controlled_document_observer_status": valid_status(),
        "document_time_origin_ms": 12345.5}, current_source_sha256="abc",
        extractor_time_origin=12345.5)
    assert checked["registered_before_controlled_page_creation"] is True

    bad_cases = [
        ({"input_entry_observer": dict(valid_lease()["input_entry_observer"],
           observer_requested=False)}, valid_status(), 12345.5, "did not request"),
        ({"input_entry_observer": dict(valid_lease()["input_entry_observer"],
           registered_before_controlled_page_creation=False)}, valid_status(), 12345.5, "not registered"),
        ({"input_entry_observer": dict(valid_lease()["input_entry_observer"],
           controlled_document_observer_status=dict(valid_status(), armed_once=True))},
         valid_status(), 12345.5, "not initially pristine"),
        (valid_lease(), valid_status(), 12345.5, "digest differs"),
        (valid_lease(), dict(valid_status(), armed_once=True), 12345.5, "not pristine"),
        (valid_lease(), valid_status(), 999.0, "time origin differs"),
    ]
    for lease, status, origin, reason in bad_cases:
        with pytest.raises(ValueError, match=reason):
            validate_observer_startup(lease,
                {"controlled_document_observer_status": status,
                 "document_time_origin_ms": origin},
                current_source_sha256="different" if reason == "digest differs" else "abc",
                extractor_time_origin=12345.5)


def test_cdp_wrapper_embeds_existing_decoder_and_requires_tight_endpoint_bounds():
    expected = {"down": {"x": 1.25, "y": 2.5}, "up": {"x": 3, "y": 4},
                "tolerancePx": 1}
    source = "function(mode){return {mode};}"
    arm = make_arm_declaration(source, expected,
        {"init_script_registered_before_page": True, "page_created_after_registration": True})
    assert "const memories=this.filter(m=>m.buffer.byteLength>1000000)" in arm
    assert "const decoder=(function(mode){return {mode};})" in arm
    assert "expectedCanvas:document.querySelector('canvas')" in arm
    assert "root_candidate" not in arm
    assert "drainEntry(stage)" in make_stage_declaration("drain", "down")
    with pytest.raises(ValueError, match="at most one"):
        make_arm_declaration(source, dict(expected, tolerancePx=1.01), {})


def test_observer_option_is_opt_in_and_keeps_existing_execute_arguments():
    normal = parse_args(["--execute", "--source", "11", "--destination", "12"])
    opted = parse_args(["--execute", "--source", "11", "--destination", "12",
                        "--input-entry-observer"])
    assert normal.input_entry_observer is False
    assert opted.input_entry_observer is True
    assert normal.seconds == opted.seconds == 30


def test_public_metadata_never_contains_raw_extractor_root_pointers():
    row = {"stage": "MOUSEDOWN_ENTRY", "event": {"type": "mousedown"},
        "browser_clock": {"performance_now_ms": 3}, "canvas": {"width": 800},
        "raw": {"tick": 5, "sampled_at_ms": 10, "document_time_origin": 20,
            "player_id": 7, "coverage": "PLAYER_VISIBLE_COMPLETE",
            "camera_candidate": [1, 2, 3], "selected_tower": 11,
            "root_candidate": 123, "root_slot_candidate": 2,
            "towers": [{"research_ref": 555}]}}
    public = public_entry_metadata(row)
    encoded = repr(public)
    assert "root_candidate" not in encoded and "root_slot_candidate" not in encoded
    assert "research_ref" not in encoded
    assert public["camera_candidate"] == [1, 2, 3]


def test_down_entry_requires_current_visible_identity_and_selected_source():
    before = FakeState(Fact(7))
    raw = {"coverage": "PLAYER_VISIBLE_COMPLETE", "document_time_origin": 20,
        "player_id": 7, "tick": 5, "camera_candidate": [1, 2, 3],
        "root_candidate": 8, "root_slot_candidate": 1, "selected_tower": None}
    assert validate_down_entry_identity(raw, before, extractor_time_origin=20,
                                        source_id=11)
    for field, value in [("root_candidate", None), ("coverage", "PARTIAL"),
                         ("selected_tower", 11), ("document_time_origin", 21)]:
        changed = dict(raw, **{field: value})
        with pytest.raises(ValueError):
            validate_down_entry_identity(changed, before, extractor_time_origin=20,
                                         source_id=11)


class FakeCDP:
    def __init__(self, down, up):
        self.down, self.up = down, up
        self.calls = []
        self.take_result = {"valid": True, "status": "COMPLETE",
            "entries": [down, up], "drained_stages": ["down", "up"],
            "reset_free": True, "reset_history": [], "reset_history_truncated": False,
            "guard_evidence": {"pointer_lock_element_is_null": True,
                               "visibility_state": "visible"}}
        self.disarm_result = {"disarmed": True}

    async def send(self, method, params):
        self.calls.append((method, params))
        declaration = params.get("functionDeclaration", "")
        if "observer.arm" in declaration:
            return {"result": {"value": {"armed": True}}}
        if "drainEntry(stage)" in declaration:
            stage = params["arguments"][0]["value"]
            return {"result": {"value": {"valid": True, "entry": self.down if stage == "down" else self.up}}}
        if "observer.take()" in declaration:
            return {"result": {"value": self.take_result}}
        if "observer.disarm()" in declaration:
            return {"result": {"value": self.disarm_result}}
        raise AssertionError("unexpected CDP function")


class FakeMouse:
    def __init__(self, order, fail_on=None):
        self.order = order
        self.fail_on = fail_on

    async def move(self, x, y, **kwargs):
        self.order.append(("move", x, y))
        if self.fail_on == (x, y):
            raise RuntimeError("synthetic partial movement failure")

    async def down(self):
        self.order.append(("down",))

    async def up(self):
        self.order.append(("up",))


def fake_drag_parts(order, *, fail_on=None):
    raw_down = {"coverage": "PLAYER_VISIBLE_COMPLETE", "document_time_origin": 20,
        "player_id": 7, "tick": 5, "camera_candidate": [1, 2, 3],
        "root_candidate": 8, "root_slot_candidate": 1, "selected_tower": None}
    down = {"stage": "MOUSEDOWN_ENTRY", "raw": raw_down,
        "event": {"type": "mousedown"}, "browser_clock": {}, "canvas": {}}
    up = {"stage": "MOUSEUP_ENTRY", "raw": dict(raw_down, tick=6),
        "event": {"type": "mouseup"}, "browser_clock": {}, "canvas": {}}
    cdp = FakeCDP(down, up)

    class Extractor:
        def __init__(self):
            self.cdp, self.memories_id, self.owner_states_id = cdp, "memories", "owners"
            self.decoder_source, self.time_origin = "function(mode){return {mode};}", 20

        def adopt_captured_world(self, raw, *, began_monotonic_ms, received_monotonic_ms):
            return FakeState(Fact(7)), raw

    return NS(mouse=FakeMouse(order, fail_on=fail_on)), Extractor(), FakeState(Fact(7))


def test_staged_capture_adopts_down_before_destination_and_up_without_redecode():
    raw_down = {"coverage": "PLAYER_VISIBLE_COMPLETE", "document_time_origin": 20,
        "player_id": 7, "tick": 5, "camera_candidate": [1, 2, 3],
        "root_candidate": 8, "root_slot_candidate": 1, "selected_tower": None}
    raw_up = dict(raw_down, tick=6, selected_tower=None)
    down = {"stage": "MOUSEDOWN_ENTRY", "raw": raw_down,
        "event": {"type": "mousedown"}, "browser_clock": {}, "canvas": {}}
    up = {"stage": "MOUSEUP_ENTRY", "raw": raw_up,
        "event": {"type": "mouseup"}, "browser_clock": {}, "canvas": {}}
    order = []
    cdp = FakeCDP(down, up)

    class Extractor:
        def __init__(self):
            self.cdp = cdp
            self.memories_id = "memories"
            self.owner_states_id = "owners"
            self.decoder_source = "function(mode){return {mode};}"
            self.time_origin = 20

        def adopt_captured_world(self, raw, *, began_monotonic_ms, received_monotonic_ms):
            order.append(("adopt", raw["tick"]))
            assert began_monotonic_ms <= received_monotonic_ms
            return FakeState(Fact(7)), raw

    page = NS(mouse=FakeMouse(order))
    before = NS(player_id=NS(value=7))
    import tempfile
    with tempfile.TemporaryFile(mode="w+", encoding="utf8") as stream:
        result = asyncio.run(perform_buffered_drag(page=page, extractor=Extractor(),
            source_point=(10, 20), destination_point=(30, 40),
            expected={"down": {"x": 10, "y": 20}, "up": {"x": 30, "y": 40},
                      "tolerancePx": 1},
            host_prerequisite={"init_script_registered_before_page": True,
                               "page_created_after_registration": True},
            before_state=before, source_id=11, stream=stream,
            intent={"kind": "BEFORE_INTENT"}, endpoint_validator=lambda *args: {"qualified": True},
            deadline_monotonic=10**12))
        stream.seek(0)
        rows = [line for line in stream.read().splitlines() if line]
    assert result["valid"] is True
    assert [item[:2] for item in order if item[0] == "adopt"] == [("adopt", 5), ("adopt", 6)]
    assert order.index(("adopt", 5)) < order.index(("move", 30, 40))
    assert order.index(("move", 30, 40)) < order.index(("up",))
    assert len([call for call in cdp.calls if "drainEntry(stage)" in call[1].get("functionDeclaration", "")]) == 2
    assert len(rows) == 6  # intent, both canonical stages/checks, and final receipt
    assert "root_candidate" not in rows[1]
    assert "root_candidate" not in rows[2]


def test_down_validation_failure_releases_at_source_and_records_partial_receipt():
    raw_down = {"coverage": "PLAYER_VISIBLE_COMPLETE", "document_time_origin": 20,
        "player_id": 7, "tick": 5, "camera_candidate": [1, 2, 3],
        "root_candidate": 8, "root_slot_candidate": 1, "selected_tower": None}
    down = {"stage": "MOUSEDOWN_ENTRY", "raw": raw_down,
        "event": {"type": "mousedown"}, "browser_clock": {}, "canvas": {}}
    up = {"stage": "MOUSEUP_ENTRY", "raw": dict(raw_down, tick=6, selected_tower=None),
        "event": {"type": "mouseup"}, "browser_clock": {}, "canvas": {}}
    order = []
    cdp = FakeCDP(down, up)

    class Extractor:
        def __init__(self):
            self.cdp, self.memories_id, self.owner_states_id = cdp, "memories", "owners"
            self.decoder_source, self.time_origin = "function(mode){return {mode};}", 20

        def adopt_captured_world(self, raw, *, began_monotonic_ms, received_monotonic_ms):
            return FakeState(Fact(7)), raw

    import tempfile
    with tempfile.TemporaryFile(mode="w+", encoding="utf8") as stream:
        with pytest.raises(ValueError, match="source endpoint refused"):
            asyncio.run(perform_buffered_drag(page=NS(mouse=FakeMouse(order)),
                extractor=Extractor(), source_point=(10, 20), destination_point=(30, 40),
                expected={"down": {"x": 10, "y": 20}, "up": {"x": 30, "y": 40}, "tolerancePx": 1},
                host_prerequisite={"init_script_registered_before_page": True,
                                   "page_created_after_registration": True},
                before_state=FakeState(Fact(7)), source_id=11, stream=stream,
                intent={"kind": "BEFORE_INTENT"},
                endpoint_validator=lambda *args: (_ for _ in ()).throw(ValueError("source endpoint refused")),
                deadline_monotonic=10**12))
        stream.seek(0)
        rows = [json.loads(line) for line in stream.read().splitlines() if line]
    assert ("move", 30, 40) not in order
    assert order[-1] == ("up",)
    assert rows[-1]["kind"] == "INPUT_ENTRY_CAPTURE_RECEIPT"
    assert rows[-1]["status"] == "INVALID_OR_PARTIAL"
    assert rows[-1]["mouse_release_attempted"] is True
    assert rows[-1]["destination_move_attempted"] is False


@pytest.mark.parametrize("failure", ["partial_move", "expired_after_move"])
def test_destination_failure_marks_attempt_and_releases_once_without_retry(failure):
    order = []
    if failure == "partial_move":
        page, extractor, before = fake_drag_parts(order, fail_on=(30, 40))
        deadline = 10**12
        expected_error = "synthetic partial movement failure"
    else:
        page, extractor, before = fake_drag_parts(order)

        class ExpiringDeadline:
            def __init__(self):
                self.comparisons = 0

            def __le__(self, _now):
                self.comparisons += 1
                # Initial check, before down, before movement, then after movement.
                return self.comparisons >= 4

        deadline = ExpiringDeadline()
        expected_error = "after destination movement"

    import tempfile
    with tempfile.TemporaryFile(mode="w+", encoding="utf8") as stream:
        with pytest.raises((RuntimeError, TimeoutError), match=expected_error):
            asyncio.run(perform_buffered_drag(page=page, extractor=extractor,
                source_point=(10, 20), destination_point=(30, 40),
                expected={"down": {"x": 10, "y": 20}, "up": {"x": 30, "y": 40},
                          "tolerancePx": 1},
                host_prerequisite={"init_script_registered_before_page": True,
                                   "page_created_after_registration": True},
                before_state=before, source_id=11, stream=stream,
                intent={"kind": "BEFORE_INTENT"},
                endpoint_validator=lambda *args: {"qualified": True},
                deadline_monotonic=deadline))
        stream.seek(0)
        rows = [json.loads(line) for line in stream.read().splitlines() if line]
    receipt = rows[-1]
    assert receipt["kind"] == "INPUT_ENTRY_CAPTURE_RECEIPT"
    assert receipt["status"] == "INVALID_OR_PARTIAL"
    assert receipt["destination_move_attempted"] is True
    assert receipt["mouse_release_attempted"] is True
    assert order.count(("down",)) == 1
    assert order.count(("up",)) == 1
    assert order.count(("move", 30, 40)) == 1


def test_final_reset_sensitive_guard_failure_records_partial_without_credit():
    order = []
    page, extractor, before = fake_drag_parts(order)
    extractor.cdp.take_result["guard_evidence"]["pointer_lock_element_is_null"] = False
    import tempfile
    with tempfile.TemporaryFile(mode="w+", encoding="utf8") as stream:
        with pytest.raises(ValueError, match="reset-sensitive history or document guards"):
            asyncio.run(perform_buffered_drag(page=page, extractor=extractor,
                source_point=(10, 20), destination_point=(30, 40),
                expected={"down": {"x": 10, "y": 20}, "up": {"x": 30, "y": 40},
                          "tolerancePx": 1},
                host_prerequisite={"init_script_registered_before_page": True,
                                   "page_created_after_registration": True},
                before_state=before, source_id=11, stream=stream,
                intent={"kind": "BEFORE_INTENT"},
                endpoint_validator=lambda *args: {"qualified": True},
                deadline_monotonic=10**12))
        stream.seek(0)
        rows = [json.loads(line) for line in stream.read().splitlines() if line]
    receipt = rows[-1]
    assert receipt["status"] == "INVALID_OR_PARTIAL"
    assert receipt["up_canonicalized"] is True
    assert receipt["disarm"]["disarmed"] is True
    assert all("formal_credit" not in row for row in rows)


def test_disarm_failure_invalidates_successful_capture_and_is_not_retried():
    order = []
    page, extractor, before = fake_drag_parts(order)
    extractor.cdp.disarm_result = {"disarmed": False, "error": "synthetic disarm refusal"}
    import tempfile
    with tempfile.TemporaryFile(mode="w+", encoding="utf8") as stream:
        with pytest.raises(RuntimeError, match="observer disarm failed: synthetic disarm refusal"):
            asyncio.run(perform_buffered_drag(page=page, extractor=extractor,
                source_point=(10, 20), destination_point=(30, 40),
                expected={"down": {"x": 10, "y": 20}, "up": {"x": 30, "y": 40},
                          "tolerancePx": 1},
                host_prerequisite={"init_script_registered_before_page": True,
                                   "page_created_after_registration": True},
                before_state=before, source_id=11, stream=stream,
                intent={"kind": "BEFORE_INTENT"},
                endpoint_validator=lambda *args: {"qualified": True},
                deadline_monotonic=10**12))
        stream.seek(0)
        rows = [json.loads(line) for line in stream.read().splitlines() if line]
    receipt = rows[-1]
    assert receipt["kind"] == "INPUT_ENTRY_CAPTURE_RECEIPT"
    assert receipt["status"] == "INVALID_OR_PARTIAL"
    assert receipt["disarm"] == {"disarmed": False, "error": "synthetic disarm refusal"}
    assert "observer disarm failed" in receipt["error"]
    disarm_calls = [call for call in extractor.cdp.calls
                    if "observer.disarm()" in call[1].get("functionDeclaration", "")]
    assert len(disarm_calls) == 1
    assert order.count(("up",)) == 1
