import copy
import gzip
import asyncio
import hashlib
import json
from pathlib import Path

import tools.v2_input_listener_evidence as listener_evidence
from tools.v2_input_listener_evidence import (
    CLIENT_SHA256,
    OBSERVER_STARTUP_SHA256,
    validate_input_listener_inventory,
)


FIXTURE = Path(__file__).parent / "fixtures/v2/friendly-scene-preview-A-20261002.json.gz"
ORIGIN = 1790901054004.9
DOC_ID = "1fecb541790d476b91074b1079b3c779"


def _synthetic_evidence_from_historical_mouse_rows():
    fixture = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    listener_rows = fixture["listeners"]
    nodes = [
        {"backend_node_id": None, "roles": ["window"], "listeners": []},
        {"backend_node_id": None, "roles": ["document"], "listeners": []},
        {"backend_node_id": 101, "roles": ["html", "canvas_ancestor_2"], "listeners": []},
        {"backend_node_id": 102, "roles": ["body", "canvas_ancestor_1"], "listeners": []},
        {"backend_node_id": 103, "roles": ["canvas"], "listeners": []},
    ]
    by_role = {role: node for node in nodes for role in node["roles"]}
    for row in listener_rows:
        key = "window" if row["node"] == "window" else "canvas"
        by_role[key]["listeners"].append({
            "type": row["type"],
            "use_capture": row["useCapture"],
            "source_sha256": row["source_sha256"],
            "line_number": row["lineNumber"],
            "column_number": row["columnNumber"],
        })
    before = fixture["BEFORE"]
    return {
        "document_id": before["document_id"],
        "document_id_attestation": "CALLER_SUPPLIED_EXTRACTOR_SESSION_ID",
        "client_sha256": before["client_sha256"],
        "time_origin_before_ms": before["document_time_origin_ms"]["value"],
        "time_origin_after_ms": ORIGIN,
        "observer_install_time_origin_ms": ORIGIN,
        "host_preregistration": {
            "observer_requested": True,
            "registered_before_page_creation": True,
            "startup_source_sha256": OBSERVER_STARTUP_SHA256,
            "document_time_origin_ms": ORIGIN,
        },
        "observer_status": {
            "installed": True,
            "status": "DISARMED",
            "armed_once": False,
            "document_loading_at_install": True,
            "ready_state_at_install": "loading",
            "install_performance_time_origin_ms": ORIGIN,
        },
        "observer_status_after": {
            "installed": True,
            "status": "DISARMED",
            "armed_once": False,
            "document_loading_at_install": True,
            "ready_state_at_install": "loading",
            "install_performance_time_origin_ms": ORIGIN,
        },
        "main_frame_before": {"frame_id": "main-frame", "loader_id": "loader-1", "url": "https://kiomet.com/"},
        "main_frame_after": {"frame_id": "main-frame", "loader_id": "loader-1", "url": "https://kiomet.com/"},
        "transport": {
            "client_sha256": CLIENT_SHA256,
            "mode": "NETWORK",
            "connected": True,
            "shared_memory": False,
            "metadata_provenance": "CALLER_ATTESTED_FRESH_EXTRACTOR_SAMPLE",
            "owned_transports": [{"kind": "WEBSOCKET", "state": 1}],
        },
        "inventory": {
            "complete": True,
            "canvas_count": 1,
            "canvas_ancestor_count": 2,
            "nodes": nodes,
            "canvas_ancestor_backend_node_ids": [103, 102, 101],
        },
    }


def _validate(evidence):
    return validate_input_listener_inventory(
        evidence, expected_document_id=DOC_ID, expected_time_origin_ms=ORIGIN,
    )


def test_synthetic_adapter_of_historical_mouse_rows_qualifies_only_as_topology():
    # This constructs synthetic backend IDs, frame/transport/status metadata,
    # and a filtered mouse-only node inventory. It is not a retained complete
    # topology receipt and earns no live gesture or route credit.
    result = _validate(_synthetic_evidence_from_historical_mouse_rows())
    assert result["qualified"] is True
    cert = result["certificate"]
    assert cert["scope"] == "SAME_DOCUMENT_LISTENER_TOPOLOGY_ONLY"
    assert cert["gesture_continuity"] == "UNKNOWN"
    assert cert["route_continuity"] == "UNKNOWN"
    assert cert["canvas_ancestor_backend_node_ids"] == [103, 102, 101]


def test_unverified_script_hash_or_location_is_rejected():
    evidence = _synthetic_evidence_from_historical_mouse_rows()
    tampered = copy.deepcopy(evidence)
    tampered["inventory"]["nodes"][0]["listeners"][0]["source_sha256"] = "f" * 64
    assert _validate(tampered)["reason"] == "INPUT_LISTENER_SET_OR_ORDER_MISMATCH"
    tampered = copy.deepcopy(evidence)
    tampered["inventory"]["nodes"][0]["listeners"][0]["line_number"] += 1
    assert _validate(tampered)["qualified"] is False


def test_injected_ancestor_listener_and_missing_dom_coverage_are_rejected():
    evidence = _synthetic_evidence_from_historical_mouse_rows()
    injected = copy.deepcopy(evidence)
    injected["inventory"]["nodes"][1]["listeners"].append({
        "type": "mouseup", "use_capture": True,
        "source_sha256": "f" * 64, "line_number": 1, "column_number": 1,
    })
    assert _validate(injected)["reason"] == "UNEXPECTED_ANCESTOR_INPUT_LISTENER"

    missing_document = copy.deepcopy(evidence)
    missing_document["inventory"]["nodes"] = [n for n in missing_document["inventory"]["nodes"]
                                                 if "document" not in n["roles"]]
    assert _validate(missing_document)["reason"] == "WINDOW_OR_DOCUMENT_NOT_COVERED"

    missing_canvas = copy.deepcopy(evidence)
    missing_canvas["inventory"]["nodes"] = [n for n in missing_canvas["inventory"]["nodes"]
                                               if "canvas" not in n["roles"]]
    assert _validate(missing_canvas)["reason"] == "DOM_REQUIRED_NODE_MISSING"


def test_identity_transport_and_startup_contract_are_fail_closed():
    evidence = _synthetic_evidence_from_historical_mouse_rows()
    changed = copy.deepcopy(evidence)
    changed["document_id"] = "other-document"
    assert _validate(changed)["reason"] == "DOCUMENT_ID_CHANGED"
    changed = copy.deepcopy(evidence)
    changed["time_origin_after_ms"] += 1
    assert _validate(changed)["reason"] == "DOCUMENT_ORIGIN_CHANGED"
    changed = copy.deepcopy(evidence)
    changed["transport"]["owned_transports"].append({"kind": "WEBTRANSPORT", "state": "CONNECTED"})
    assert _validate(changed)["reason"] == "TRANSPORT_NOT_EXACT_CONNECTED_WEBSOCKET"
    changed = copy.deepcopy(evidence)
    changed["transport"]["owned_transports"][0]["state"] = 99
    assert _validate(changed)["qualified"] is False
    changed = copy.deepcopy(evidence)
    changed["transport"]["shared_memory"] = True
    assert _validate(changed)["reason"] == "TRANSPORT_NOT_EXACT_CONNECTED_WEBSOCKET"
    changed = copy.deepcopy(evidence)
    changed["host_preregistration"]["registered_before_page_creation"] = False
    assert _validate(changed)["reason"] == "OBSERVER_NOT_PREREGISTERED"


def test_wrong_capture_phase_and_incomplete_ancestry_are_rejected():
    evidence = _synthetic_evidence_from_historical_mouse_rows()
    changed = copy.deepcopy(evidence)
    changed["inventory"]["nodes"][0]["listeners"][0]["use_capture"] = False
    assert _validate(changed)["qualified"] is False
    changed = copy.deepcopy(evidence)
    changed["inventory"]["canvas_ancestor_backend_node_ids"] = [103, 101]
    assert _validate(changed)["reason"] == "CANVAS_ANCESTRY_NOT_FULLY_COVERED"

    changed = copy.deepcopy(evidence)
    window_rows = changed["inventory"]["nodes"][0]["listeners"]
    window_rows[0], window_rows[1] = window_rows[1], window_rows[0]
    assert _validate(changed)["reason"] == "INPUT_LISTENER_SET_OR_ORDER_MISMATCH"

    changed = copy.deepcopy(evidence)
    changed["inventory"]["nodes"][0]["listeners"].pop(1)
    assert _validate(changed)["reason"] == "INPUT_LISTENER_SET_OR_ORDER_MISMATCH"

    changed = copy.deepcopy(evidence)
    changed["inventory"]["canvas_ancestor_count"] = 1
    assert _validate(changed)["reason"] == "CANVAS_ANCESTRY_NOT_CONTIGUOUS"


def test_frame_canvas_and_pristine_observer_identity_must_remain_stable():
    evidence = _synthetic_evidence_from_historical_mouse_rows()
    changed = copy.deepcopy(evidence)
    changed["main_frame_after"]["loader_id"] = "new-loader"
    assert _validate(changed)["reason"] == "MAIN_FRAME_OR_LOADER_CHANGED"
    changed = copy.deepcopy(evidence)
    changed["inventory"]["canvas_count"] = 2
    assert _validate(changed)["reason"] == "CANVAS_COUNT_NOT_UNIQUE"
    changed = copy.deepcopy(evidence)
    changed["observer_status_after"]["armed_once"] = True
    assert _validate(changed)["reason"] == "OBSERVER_CHANGED_DURING_INVENTORY"


def test_boolean_counts_and_transport_states_are_not_integer_evidence():
    evidence = _synthetic_evidence_from_historical_mouse_rows()
    changed = copy.deepcopy(evidence)
    changed["transport"]["owned_transports"][0]["state"] = True
    assert _validate(changed)["reason"] == "TRANSPORT_NOT_EXACT_CONNECTED_WEBSOCKET"

    changed = copy.deepcopy(evidence)
    changed["inventory"]["canvas_count"] = True
    assert _validate(changed)["reason"] == "CANVAS_COUNT_NOT_UNIQUE"

    # Construct a valid two-node synthetic ancestry so True would otherwise
    # compare equal to the expected integer ancestor count of one.
    changed = _synthetic_evidence_from_historical_mouse_rows()
    window, document, html, body, canvas = changed["inventory"]["nodes"]
    body["roles"].append("html")
    changed["inventory"]["nodes"] = [window, document, body, canvas]
    changed["inventory"]["canvas_ancestor_backend_node_ids"] = [103, 102]
    changed["inventory"]["canvas_ancestor_count"] = True
    assert _validate(changed)["reason"] == "CANVAS_ANCESTOR_COUNT_NOT_INTEGER"


def test_malformed_json_roles_and_noncanonical_frame_urls_fail_closed():
    evidence = _synthetic_evidence_from_historical_mouse_rows()
    changed = copy.deepcopy(evidence)
    changed["inventory"]["nodes"][0]["roles"] = ["window", {}]
    assert _validate(changed)["reason"] == "DOM_NODE_RECORD_INVALID"

    for bad_url in (None, {}, "https://kiomet.com:444/", "https://user@kiomet.com/"):
        changed = _synthetic_evidence_from_historical_mouse_rows()
        changed["main_frame_before"]["url"] = bad_url
        assert _validate(changed)["qualified"] is False
        assert _validate(changed)["reason"] == "OFFICIAL_DOCUMENT_URL_REQUIRED"


def test_async_cdp_collector_uses_dom_protocol_shapes_and_releases_handles(monkeypatch):
    fixture = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    sources = {"3": "observer-source", "36": "pw-source", "8": "official-source"}
    hashes = {key: hashlib.sha256(value.encode()).hexdigest() for key, value in sources.items()}
    monkeypatch.setattr(listener_evidence, "OBSERVER_LISTENER", (hashes["3"], 129, 20))
    monkeypatch.setattr(listener_evidence, "PLAYWRIGHT_LISTENER", (hashes["36"], 7994, 21))
    monkeypatch.setattr(listener_evidence, "OFFICIAL_LISTENER", (hashes["8"], 2270, 17))

    role_handles = {
        "window": "w", "document": "d", "document.documentElement": "h",
        "document.body": "b", "document.querySelector('canvas')": "c",
    }
    object_backend = {"h": 101, "b": 102, "c": 103, "c2": 104, "b2": 105}
    by_handle_rows = {"w": [], "d": [], "h": [], "b": [], "c": []}
    for row in fixture["listeners"]:
        handle = "w" if row["node"] == "window" else "c"
        by_handle_rows[handle].append({
            "type": row["type"], "useCapture": row["useCapture"],
            "scriptId": row["scriptId"], "lineNumber": row["lineNumber"],
            "columnNumber": row["columnNumber"],
        })

    class FakeCDP:
        def __init__(self, change=None):
            self.released = []
            self.listener_queries = []
            self.change = change
            self.canvas_queries = 0
            self.parent_queries = 0
            self.html_queries = 0
            self.timeline = []

        async def send(self, method, params=None):
            params = params or {}
            if method in ("Debugger.enable", "Debugger.disable"):
                return {}
            if method == "Page.getFrameTree":
                self.timeline.append("frame")
                return {"frameTree": {"frame": {"id": "main-frame", "loaderId": "loader-1", "url": "https://kiomet.com/"}}}
            if method == "Runtime.evaluate":
                expr = params["expression"]
                if "origin: performance.timeOrigin" in expr:
                    self.timeline.append("snapshot")
                    value = {"origin": ORIGIN, "ready": "loading", "observer": {
                        "installed": True, "status": "DISARMED", "armed_once": False,
                        "document_loading_at_install": True, "ready_state_at_install": "loading",
                        "install_performance_time_origin_ms": ORIGIN,
                    }}
                    return {"result": {"type": "object", "value": value}}
                if "querySelectorAll('canvas').length" in expr:
                    self.timeline.append("canvas_count")
                    return {"result": {"type": "number", "value": 2 if self.change == "extra_canvas" else 1}}
                if "let n=c,p=0" in expr or "p=0; while(n)" in expr:
                    self.timeline.append("canvas_depth")
                    return {"result": {"type": "number", "value": 3}}
                if expr.startswith("(() => { let n=document.querySelector('canvas'); for(let j=0;j<1"):
                    self.parent_queries += 1
                    if self.change == "reparent" and self.parent_queries > 1:
                        return {"result": {"type": "object", "objectId": "b2"}}
                    return {"result": {"type": "object", "objectId": "b"}}
                if expr.startswith("(() => { let n=document.querySelector('canvas'); for(let j=0;j<2"):
                    self.html_queries += 1
                    return {"result": {"type": "object", "objectId": "h"}}
                if expr == "document.querySelector('canvas')":
                    self.canvas_queries += 1
                    if self.change == "replace_canvas" and self.canvas_queries > 1:
                        return {"result": {"type": "object", "objectId": "c2"}}
                    return {"result": {"type": "object", "objectId": "c"}}
                return {"result": {"type": "object", "objectId": role_handles[expr]}}
            if method == "DOM.describeNode":
                self.timeline.append("describe")
                return {"node": {"backendNodeId": object_backend[params["objectId"]]}}
            if method == "DOMDebugger.getEventListeners":
                handle = params["objectId"]
                self.listener_queries.append(handle)
                return {"listeners": by_handle_rows[handle]}
            if method == "Debugger.getScriptSource":
                return {"scriptSource": sources[params["scriptId"]]}
            if method == "Runtime.releaseObject":
                self.released.append(params["objectId"])
                return {}
            raise AssertionError(f"unexpected CDP method {method}")

    cdp = FakeCDP()
    host = {
        "observer_requested": True,
        "registered_before_page_creation": True,
        "startup_source_sha256": OBSERVER_STARTUP_SHA256,
        "document_time_origin_ms": ORIGIN,
    }
    client = {
        "client_sha256": CLIENT_SHA256,
        "transport_mode": "NETWORK", "transport_connected": True,
        "shared_memory": False, "metadata_provenance": "CALLER_ATTESTED_FRESH_EXTRACTOR_SAMPLE",
        "owned_transports": [{"kind": "WEBSOCKET", "state": 1}],
    }
    result = asyncio.run(listener_evidence.capture_input_listener_inventory(
        cdp, document_id=DOC_ID, expected_time_origin_ms=ORIGIN,
        host_preregistration=host, client_metadata=client,
    ))
    assert result["qualified"] is True
    assert result["certificate"]["scope"] == "SAME_DOCUMENT_LISTENER_TOPOLOGY_ONLY"
    assert set(cdp.listener_queries) == {"w", "d", "h", "b", "c"}
    assert len(cdp.released) == 10
    assert result["evidence"]["inventory"]["canvas_ancestor_backend_node_ids"] == [103, 102, 101]
    assert cdp.timeline[-3:] == ["describe", "snapshot", "frame"]

    for change in ("replace_canvas", "reparent", "extra_canvas"):
        changed_cdp = FakeCDP(change=change)
        changed = asyncio.run(listener_evidence.capture_input_listener_inventory(
            changed_cdp, document_id=DOC_ID, expected_time_origin_ms=ORIGIN,
            host_preregistration=host, client_metadata=client,
        ))
        assert changed["qualified"] is False
        assert changed["reason"] in {
            "CANVAS_OR_ANCESTRY_CHANGED_DURING_INVENTORY", "CANVAS_COUNT_NOT_UNIQUE",
        }


def test_owned_memory_type_probe_requires_unique_nonshared_arraybuffer_and_same_origin():
    class FakeCDP:
        def __init__(self, value=None, *, error=False, malformed=False):
            self.value = value
            self.error = error
            self.malformed = malformed
            self.calls = []

        async def send(self, method, params=None):
            params = params or {}
            self.calls.append((method, params))
            assert method == "Runtime.callFunctionOn"
            assert params["objectId"] == "extractor-memory-handle"
            assert "WebAssembly.Memory" in params["functionDeclaration"]
            assert "SharedArrayBuffer" in params["functionDeclaration"]
            assert "root" not in params["functionDeclaration"].lower()
            if self.error:
                return {"exceptionDetails": {"text": "probe failed"}}
            if self.malformed:
                return {"result": {"type": "undefined"}}
            return {"result": {"type": "object", "value": self.value}}

    async def probe(value=None, **kwargs):
        cdp = FakeCDP(value, **kwargs)
        result = await listener_evidence.capture_owned_memory_type(
            cdp, memories_id="extractor-memory-handle", expected_time_origin_ms=ORIGIN,
        )
        return result, cdp

    good = {"origin": ORIGIN, "count": 1,
            "memories": [{"is_memory": True, "buffer_type": "ArrayBuffer"}]}
    result, cdp = asyncio.run(probe(good))
    assert result["qualified"] is True
    assert result["reason"] == "UNIQUE_NON_SHARED_MEMORY_TYPE"
    assert len(cdp.calls) == 1

    shared = copy.deepcopy(good)
    shared["memories"][0]["buffer_type"] = "SharedArrayBuffer"
    result, _ = asyncio.run(probe(shared))
    assert result["reason"] == "SHARED_MEMORY_UNSUPPORTED"

    multiple = copy.deepcopy(good)
    multiple["count"] = 2
    multiple["memories"].append({"is_memory": True, "buffer_type": "ArrayBuffer"})
    result, _ = asyncio.run(probe(multiple))
    assert result["reason"] == "MEMORY_COUNT_NOT_UNIQUE"

    changed_origin = copy.deepcopy(good)
    changed_origin["origin"] += 10
    result, _ = asyncio.run(probe(changed_origin))
    assert result["reason"] == "DOCUMENT_ORIGIN_CHANGED"

    unknown = copy.deepcopy(good)
    unknown["memories"][0]["buffer_type"] = "OTHER"
    result, _ = asyncio.run(probe(unknown))
    assert result["reason"] == "MEMORY_BUFFER_TYPE_UNKNOWN"

    result, _ = asyncio.run(probe(error=True))
    assert result["reason"] == "MEMORY_TYPE_PROBE_FAILED"
    result, _ = asyncio.run(probe(malformed=True))
    assert result["reason"] == "MEMORY_TYPE_EVIDENCE_UNKNOWN"
