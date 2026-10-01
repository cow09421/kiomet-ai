"""Small host adapter for the opt-in buffered input-entry observer.

This module only orchestrates ordinary Playwright mouse events and adopts the
observer's already-buffered visible-world samples through ClientExtractor.
It never evaluates a new decoder or reads game memory between the event stages.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time


def validate_observer_startup(lease, page_status, *, current_source_sha256, extractor_time_origin):
    """Require the observer to have been installed before controlled-page creation."""
    metadata = lease.get("input_entry_observer") if isinstance(lease, dict) else None
    if not isinstance(metadata, dict):
        raise ValueError("headless lease has no input-entry observer metadata")
    if metadata.get("observer_requested") is not True:
        raise ValueError("headless host did not request the input-entry observer")
    if metadata.get("registered_before_controlled_page_creation") is not True:
        raise ValueError("input-entry observer was not registered before page creation")
    if metadata.get("source_sha256") != current_source_sha256:
        raise ValueError("input-entry observer source digest differs from current JavaScript")
    lease_status = metadata.get("controlled_document_observer_status")
    if not isinstance(lease_status, dict):
        raise ValueError("headless lease has no initial controlled-document observer status")
    if (lease_status.get("installed") is not True or lease_status.get("status") != "DISARMED" or
            lease_status.get("armed_once") is not False or
            lease_status.get("document_loading_at_install") is not True or
            lease_status.get("ready_state_at_install") != "loading"):
        raise ValueError("headless lease observer was not initially pristine and startup-qualified")
    status = page_status.get("controlled_document_observer_status") if isinstance(page_status, dict) else None
    if not isinstance(status, dict):
        raise ValueError("controlled-page input-entry observer status is missing")
    if (status.get("installed") is not True or status.get("status") != "DISARMED" or
            status.get("armed_once") is not False or
            status.get("document_loading_at_install") is not True or
            status.get("ready_state_at_install") != "loading"):
        raise ValueError("controlled-page input-entry observer is not pristine or startup-qualified")
    origin = page_status.get("document_time_origin_ms")
    if (isinstance(origin, bool) or not isinstance(origin, (int, float)) or
            not math.isfinite(origin) or origin <= 0 or origin != extractor_time_origin):
        raise ValueError("observer document time origin differs from the attached extractor")
    prior_origin = metadata.get("document_time_origin_ms")
    if (isinstance(prior_origin, bool) or not isinstance(prior_origin, (int, float)) or
            prior_origin != extractor_time_origin):
        raise ValueError("headless lease observer origin differs from the attached extractor")
    return {"source_sha256": current_source_sha256,
            "document_time_origin_ms": extractor_time_origin,
            "registered_before_controlled_page_creation": True,
            "initial_status": status}


def make_arm_declaration(decoder_source, expected, host_prerequisite):
    """Build the CDP wrapper around the exact pinned decoder text."""
    if not isinstance(decoder_source, str) or not decoder_source.strip():
        raise ValueError("pinned decoder source is missing")
    if not isinstance(expected, dict) or set(expected) != {"down", "up", "tolerancePx"}:
        raise ValueError("both expected coordinates and tolerance are required")
    if (isinstance(expected["tolerancePx"], bool) or
            not isinstance(expected["tolerancePx"], (int, float)) or
            not 0 <= expected["tolerancePx"] <= 1):
        raise ValueError("input-entry endpoint tolerance must be at most one CSS pixel")
    expected_json = json.dumps(expected, separators=(",", ":"))
    prerequisite_json = json.dumps(host_prerequisite, separators=(",", ":"))
    decoder_literal = "(" + decoder_source + ")"
    return ("function(owners){const observer=window[Symbol.for('kiomet.inputEntryObserver.v1')];"
            "if(!observer||typeof observer.arm!=='function')throw Error('observer API unavailable');"
            "const memories=this.filter(m=>m.buffer.byteLength>1000000);const decoder=" + decoder_literal + ";"
            "return observer.arm({decoder,memories,owners,expectedCanvas:document.querySelector('canvas'),"
            "expected:" + expected_json + ",hostPrerequisite:" + prerequisite_json + "});}")


def make_stage_declaration(method, stage=None):
    if method == "drain":
        if stage not in ("down", "up"):
            raise ValueError("entry stage must be down or up")
        return ("function(stage){const observer=window[Symbol.for('kiomet.inputEntryObserver.v1')];"
                "if(!observer)throw Error('observer API unavailable');return observer.drainEntry(stage);}")
    if method == "take":
        return ("function(){const observer=window[Symbol.for('kiomet.inputEntryObserver.v1')];"
                "if(!observer)throw Error('observer API unavailable');return observer.take();}")
    if method == "disarm":
        return ("function(){const observer=window[Symbol.for('kiomet.inputEntryObserver.v1')];"
                "if(!observer)throw Error('observer API unavailable');return observer.disarm();}")
    raise ValueError("unsupported observer method")


async def call_observer(cdp, memories_id, method, stage=None):
    declaration = make_stage_declaration(method, stage)
    params = {"objectId": memories_id, "returnByValue": True,
              "functionDeclaration": declaration}
    if method == "drain":
        params["arguments"] = [{"value": stage}]
    response = await cdp.send("Runtime.callFunctionOn", params)
    if "exceptionDetails" in response:
        detail = response["exceptionDetails"].get("exception", {}).get("description", "observer call failed")
        raise ValueError(detail)
    result = response.get("result", {}).get("value")
    if not isinstance(result, dict):
        raise ValueError("observer returned a malformed result")
    return result


def public_entry_metadata(entry):
    """Persist entry timing/UI evidence and raw camera only; drop root pointers."""
    if not isinstance(entry, dict):
        raise ValueError("entry is not an object")
    raw = entry.get("raw") if isinstance(entry.get("raw"), dict) else {}
    camera = raw.get("camera_candidate")
    selected = raw.get("selected_tower", "__MISSING__")
    return {"stage": entry.get("stage"), "event": entry.get("event"),
            "browser_clock": entry.get("browser_clock"), "canvas": entry.get("canvas"),
            "visible_sample": {key: raw.get(key) for key in (
                "tick", "sampled_at_ms", "document_time_origin", "player_id", "coverage",
                "active", "online", "transport_connected", "transport_mode",
                "visible_pending", "expanded_visibility")},
            "camera_candidate": camera,
            "selected_tower_present": selected != "__MISSING__",
            "selected_tower": None if selected == "__MISSING__" else selected}


def validate_down_entry_identity(raw, before_state, *, extractor_time_origin, source_id):
    """Purely validate the buffered down observation before moving the pointer."""
    if not isinstance(raw, dict):
        raise ValueError("down entry raw visible sample is missing")
    if (raw.get("coverage") != "PLAYER_VISIBLE_COMPLETE" or
            raw.get("document_time_origin") != extractor_time_origin or
            raw.get("player_id") != before_state.player_id.value or
            raw.get("tick") is None or raw.get("camera_candidate") is None):
        raise ValueError("down entry identity, coverage, camera, or tick is unknown")
    if raw.get("root_candidate") is None or raw.get("root_slot_candidate") is None:
        raise ValueError("down entry normal extractor identity is missing")
    if "selected_tower" not in raw or raw["selected_tower"] is not None:
        raise ValueError("down entry did not preserve explicit deselected state")
    return True


def _adopted_pair(raw_result):
    if not isinstance(raw_result, tuple) or len(raw_result) != 2:
        raise ValueError("captured sample adoption returned no canonical state")
    return raw_result[0], raw_result[1]


async def perform_buffered_drag(*, page, extractor, source_point, destination_point,
                               expected, host_prerequisite, before_state, source_id,
                               stream, intent, endpoint_validator, deadline_monotonic):
    """Durably record intent, then capture/adopt down and up without re-reading memory."""
    from tools.v2_controlled_transition_capture import durable_before

    if time.monotonic() >= deadline_monotonic:
        raise TimeoutError("bounded deadline reached before observer arm")
    cdp = extractor.cdp
    if cdp is None or extractor.memories_id is None or extractor.owner_states_id is None:
        raise RuntimeError("attached extractor handles are unavailable")
    mouse_down = False
    destination_move_attempted = False
    down_state = up_state = None
    down_metadata = up_metadata = None
    arm_attempted = False
    observer_armed = False
    release_attempted = False
    observer_summary = None
    error = None
    durable_before(stream, intent)
    try:
        # Arm only after the durable intent, and before the trusted mouse event.
        arm_attempted = True
        arm_response = await cdp.send("Runtime.callFunctionOn", {
            "objectId": extractor.memories_id, "returnByValue": True,
            "arguments": [{"objectId": extractor.owner_states_id}],
            "functionDeclaration": make_arm_declaration(
                extractor.decoder_source, expected, host_prerequisite)})
        if "exceptionDetails" in arm_response:
            raise ValueError("observer arm failed: " + str(arm_response["exceptionDetails"]))
        observer_armed = True
        await page.mouse.move(*source_point)
        if time.monotonic() >= deadline_monotonic:
            raise TimeoutError("bounded deadline reached before mousedown")
        down_began = time.monotonic_ns() / 1_000_000
        mouse_down = True
        await page.mouse.down()
        down_received = time.monotonic_ns() / 1_000_000
        down_result = await call_observer(cdp, extractor.memories_id, "drain", "down")
        down_receipt = time.monotonic_ns() / 1_000_000
        if down_result.get("valid") is not True or not isinstance(down_result.get("entry"), dict):
            raise ValueError("buffered mousedown entry is invalid")
        down_entry = down_result["entry"]
        down_state, down_raw = _adopted_pair(extractor.adopt_captured_world(
            down_entry["raw"], began_monotonic_ms=down_began,
            received_monotonic_ms=down_receipt))
        down_metadata = public_entry_metadata(down_entry)
        down_metadata["host_clock"] = {"started_monotonic_ms": down_began,
            "mouse_call_completed_monotonic_ms": down_received,
            "drain_receipt_monotonic_ms": down_receipt}
        durable_before(stream, {"kind": "INPUT_ENTRY_DOWN_ADOPTED", "entry": down_metadata,
                                "state": down_state})
        validate_down_entry_identity(down_raw, before_state,
            extractor_time_origin=extractor.time_origin, source_id=source_id)
        down_certificate = endpoint_validator("down", before_state, down_state, down_entry)
        durable_before(stream, {"kind": "INPUT_ENTRY_DOWN_ENDPOINT_CHECK",
                                "certificate": down_certificate})

        if time.monotonic() >= deadline_monotonic:
            raise TimeoutError("bounded deadline reached before destination movement")
        destination_move_attempted = True
        await page.mouse.move(*destination_point, steps=6)
        if time.monotonic() >= deadline_monotonic:
            raise TimeoutError("bounded deadline reached after destination movement and before mouseup")
        up_began = time.monotonic_ns() / 1_000_000
        release_attempted = True
        await page.mouse.up()
        mouse_down = False
        up_received = time.monotonic_ns() / 1_000_000
        up_result = await call_observer(cdp, extractor.memories_id, "drain", "up")
        up_receipt = time.monotonic_ns() / 1_000_000
        if up_result.get("valid") is not True or not isinstance(up_result.get("entry"), dict):
            raise ValueError("buffered mouseup entry is invalid")
        up_entry = up_result["entry"]
        up_state, up_raw = _adopted_pair(extractor.adopt_captured_world(
            up_entry["raw"], began_monotonic_ms=up_began,
            received_monotonic_ms=up_receipt))
        up_metadata = public_entry_metadata(up_entry)
        up_metadata["host_clock"] = {"started_monotonic_ms": up_began,
            "mouse_call_completed_monotonic_ms": up_received,
            "drain_receipt_monotonic_ms": up_receipt}
        durable_before(stream, {"kind": "INPUT_ENTRY_UP_ADOPTED", "entry": up_metadata,
                                "state": up_state})
        endpoint_certificate = endpoint_validator("up", before_state, up_state, up_entry)
        durable_before(stream, {"kind": "INPUT_ENTRY_ENDPOINT_PAIR_CHECK",
                                "certificate": endpoint_certificate})
        final = await call_observer(cdp, extractor.memories_id, "take")
        if final.get("valid") is not True or len(final.get("entries", ())) != 2:
            raise ValueError("observer final two-entry proof is invalid")
        if (final.get("reset_free") is not True or final.get("reset_history") != [] or
                not isinstance(final.get("guard_evidence"), dict) or
                final["guard_evidence"].get("pointer_lock_element_is_null") is not True or
                final["guard_evidence"].get("visibility_state") != "visible"):
            raise ValueError("observer reset-sensitive history or document guards are not qualified")
        observer_summary = {key: final.get(key) for key in (
            "valid", "status", "drained_stages", "document_loading_at_install", "one_shot",
            "guard_evidence", "reset_free", "reset_history", "reset_history_truncated")}
        return {"valid": True, "down_state": down_state, "up_state": up_state,
                "down_entry": down_metadata, "up_entry": up_metadata,
                "endpoint_certificate": endpoint_certificate,
                "observer_summary": observer_summary,
                "mouse_release_attempted": True}
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if mouse_down:
            release_attempted = True
            try:
                await asyncio.wait_for(page.mouse.up(), timeout=2)
            except Exception as exc:
                error = (error + "; " if error else "") + f"cleanup mouse-up failed: {type(exc).__name__}: {exc}"
            mouse_down = False
        if arm_attempted:
            try:
                summary = (await call_observer(cdp, extractor.memories_id, "disarm")
                           if observer_armed else {"disarmed": False, "error": "observer did not arm"})
            except Exception as exc:
                summary = {"disarmed": False, "error": f"{type(exc).__name__}: {exc}"}
            disarm_failure = None
            if not isinstance(summary, dict) or summary.get("disarmed") is not True:
                detail = summary.get("error", "observer did not confirm disarm") if isinstance(summary, dict) else "malformed disarm result"
                disarm_failure = f"observer disarm failed: {detail}"
                error = (error + "; " if error else "") + disarm_failure
            durable_before(stream, {"kind": "INPUT_ENTRY_CAPTURE_RECEIPT",
                "status": "VALID" if error is None else "INVALID_OR_PARTIAL",
                "down_canonicalized": down_state is not None,
                "up_canonicalized": up_state is not None,
                "destination_move_attempted": destination_move_attempted,
                "mouse_release_attempted": release_attempted,
                "error": error, "disarm": summary,
                "observer_summary": observer_summary,
                "endpoint_certificate": locals().get("endpoint_certificate")})
            # Preserve a body exception already in flight, but never return a
            # successful capture when cleanup failed to prove the observer was
            # disarmed. The receipt above records that failure first.
            if disarm_failure is not None and error == disarm_failure:
                raise RuntimeError(disarm_failure)
