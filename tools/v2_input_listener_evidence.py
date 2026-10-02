"""Read-only, same-document DOM listener inventory for the v2 input bridge.

This certifies only the observed listener topology.  It does not establish a
gesture, route, callback scheduling guarantee, or command acceptance.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any
from urllib.parse import urlsplit


CLIENT_SHA256 = "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c"
OBSERVER_STARTUP_SHA256 = "9465a5c3581d6659571fa83949b90d7cb13896e6acdbba3889f4c0dd7d78ecb6"
OBSERVER_LISTENER = ("7f70c845fa7f430271e6fa9f7d132470291a505fba10c1a489de92296da30ccf", 129, 20)
PLAYWRIGHT_LISTENER = ("1fa3e0fe90b287cb49f0e4b458356120c1da419f16017060562caa1184c09b8a", 7994, 21)
OFFICIAL_LISTENER = ("05b51675785a3f6568f4d80562dabb4f59a6130504c7a04c7de9cf777c33094e", 2270, 17)
RELEVANT_EVENTS = frozenset({
    "mousedown", "mouseup", "mousemove", "click", "dblclick",
    "pointerdown", "pointerup", "pointermove", "pointercancel",
    "touchstart", "touchend", "touchmove", "wheel",
})


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _fail(reason: str) -> dict[str, Any]:
    return {"qualified": False, "reason": reason, "certificate": None}


async def capture_owned_memory_type(
    cdp: Any, *, memories_id: str | None, expected_time_origin_ms: float,
) -> dict[str, Any]:
    """Prove only the runtime type of the extractor's already-discovered memory handle."""
    if not isinstance(memories_id, str) or not memories_id:
        return {"qualified": False, "reason": "MEMORY_HANDLE_UNAVAILABLE", "evidence": None}
    if not _finite_number(expected_time_origin_ms):
        return {"qualified": False, "reason": "EXPECTED_ORIGIN_INVALID", "evidence": None}
    function = """function () {
      const candidates = this.filter(m => m && m.buffer && m.buffer.byteLength > 1000000);
      const sharedAvailable = typeof SharedArrayBuffer === 'function';
      return {
        origin: performance.timeOrigin,
        count: candidates.length,
        memories: candidates.map(m => {
          const isMemory = typeof WebAssembly === 'object' && typeof WebAssembly.Memory === 'function' && m instanceof WebAssembly.Memory;
          const buffer = m.buffer;
          const isShared = sharedAvailable && buffer instanceof SharedArrayBuffer;
          return {is_memory: isMemory, buffer_type: isShared ? 'SharedArrayBuffer' : (buffer instanceof ArrayBuffer ? 'ArrayBuffer' : 'OTHER')};
        })
      };
    }"""
    try:
        response = await cdp.send("Runtime.callFunctionOn", {
            "objectId": memories_id,
            "functionDeclaration": function,
            "returnByValue": True,
            "awaitPromise": False,
            "userGesture": False,
        })
        if response.get("exceptionDetails"):
            return {"qualified": False, "reason": "MEMORY_TYPE_PROBE_FAILED", "evidence": None}
        remote = response.get("result")
        value = remote.get("value") if isinstance(remote, dict) else None
        if not isinstance(value, dict):
            return {"qualified": False, "reason": "MEMORY_TYPE_EVIDENCE_UNKNOWN", "evidence": None}
        evidence = {
            "document_time_origin_ms": value.get("origin"),
            "memory_count": value.get("count"),
            "memories": value.get("memories"),
            "shared_memory": None,
        }
        if not _finite_number(evidence["document_time_origin_ms"]) or float(evidence["document_time_origin_ms"]) != float(expected_time_origin_ms):
            return {"qualified": False, "reason": "DOCUMENT_ORIGIN_CHANGED", "evidence": evidence}
        rows = evidence["memories"]
        if (type(evidence["memory_count"]) is not int or evidence["memory_count"] != 1 or
                not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict)):
            return {"qualified": False, "reason": "MEMORY_COUNT_NOT_UNIQUE", "evidence": evidence}
        row = rows[0]
        if row.get("is_memory") is not True:
            return {"qualified": False, "reason": "MEMORY_TYPE_UNPROVEN", "evidence": evidence}
        if row.get("buffer_type") == "SharedArrayBuffer":
            evidence["shared_memory"] = True
            return {"qualified": False, "reason": "SHARED_MEMORY_UNSUPPORTED", "evidence": evidence}
        if row.get("buffer_type") != "ArrayBuffer":
            return {"qualified": False, "reason": "MEMORY_BUFFER_TYPE_UNKNOWN", "evidence": evidence}
        evidence["shared_memory"] = False
        return {"qualified": True, "reason": "UNIQUE_NON_SHARED_MEMORY_TYPE", "evidence": evidence}
    except Exception:
        return {"qualified": False, "reason": "MEMORY_TYPE_PROBE_FAILED", "evidence": None}


def validate_input_listener_inventory(
    evidence: dict[str, Any], *, expected_document_id: str, expected_time_origin_ms: float,
) -> dict[str, Any]:
    """Validate a pre-arm inventory.  Input is ordinary JSON-safe evidence."""
    if not isinstance(evidence, dict):
        return _fail("EVIDENCE_NOT_OBJECT")
    if not isinstance(expected_document_id, str) or not expected_document_id:
        return _fail("EXPECTED_DOCUMENT_UNKNOWN")
    if not _finite_number(expected_time_origin_ms):
        return _fail("EXPECTED_ORIGIN_INVALID")
    if evidence.get("document_id") != expected_document_id:
        return _fail("DOCUMENT_ID_CHANGED")
    if evidence.get("document_id_attestation") != "CALLER_SUPPLIED_EXTRACTOR_SESSION_ID":
        return _fail("DOCUMENT_ID_NOT_ATTESTED")
    if evidence.get("client_sha256") != CLIENT_SHA256:
        return _fail("CLIENT_SOURCE_UNPINNED")

    origin_fields = (evidence.get("time_origin_before_ms"), evidence.get("time_origin_after_ms"),
                     evidence.get("observer_install_time_origin_ms"))
    if any(not _finite_number(v) for v in origin_fields):
        return _fail("DOCUMENT_ORIGIN_UNKNOWN")
    if any(float(v) != float(expected_time_origin_ms) for v in origin_fields):
        return _fail("DOCUMENT_ORIGIN_CHANGED")
    frame_before = evidence.get("main_frame_before")
    frame_after = evidence.get("main_frame_after")
    if not isinstance(frame_before, dict) or not isinstance(frame_after, dict):
        return _fail("MAIN_FRAME_IDENTITY_UNKNOWN")
    for frame in (frame_before, frame_after):
        if (not isinstance(frame.get("frame_id"), str) or not frame["frame_id"] or
                not isinstance(frame.get("loader_id"), str) or not frame["loader_id"]):
            return _fail("MAIN_FRAME_IDENTITY_UNKNOWN")
        frame_url = frame.get("url")
        if not isinstance(frame_url, str) or not frame_url:
            return _fail("OFFICIAL_DOCUMENT_URL_REQUIRED")
        try:
            parsed_url = urlsplit(frame_url)
            port = parsed_url.port
            hostname = parsed_url.hostname
        except ValueError:
            return _fail("OFFICIAL_DOCUMENT_URL_REQUIRED")
        if (parsed_url.scheme != "https" or hostname != "kiomet.com" or
                parsed_url.username is not None or parsed_url.password is not None or
                port not in (None, 443)):
            return _fail("OFFICIAL_DOCUMENT_URL_REQUIRED")
    if frame_before != frame_after:
        return _fail("MAIN_FRAME_OR_LOADER_CHANGED")

    host = evidence.get("host_preregistration")
    status = evidence.get("observer_status")
    if not isinstance(host, dict) or not isinstance(status, dict):
        return _fail("OBSERVER_STARTUP_EVIDENCE_MISSING")
    if (host.get("observer_requested") is not True or
            host.get("registered_before_page_creation") is not True or
            host.get("startup_source_sha256") != OBSERVER_STARTUP_SHA256 or
            host.get("document_time_origin_ms") != expected_time_origin_ms):
        return _fail("OBSERVER_NOT_PREREGISTERED")
    if (status.get("installed") is not True or status.get("status") != "DISARMED" or
            status.get("armed_once") is not False or
            status.get("document_loading_at_install") is not True or
            status.get("ready_state_at_install") != "loading" or
            status.get("install_performance_time_origin_ms") != expected_time_origin_ms):
        return _fail("OBSERVER_STARTUP_STATUS_INVALID")
    status_after = evidence.get("observer_status_after")
    if (not isinstance(status_after, dict) or status_after.get("installed") is not True or
            status_after.get("status") != "DISARMED" or status_after.get("armed_once") is not False or
            status_after.get("document_loading_at_install") is not True or
            status_after.get("ready_state_at_install") != "loading" or
            status_after.get("install_performance_time_origin_ms") != expected_time_origin_ms):
        return _fail("OBSERVER_CHANGED_DURING_INVENTORY")

    transport = evidence.get("transport")
    if not isinstance(transport, dict):
        return _fail("TRANSPORT_EVIDENCE_MISSING")
    owned = transport.get("owned_transports")
    if (transport.get("client_sha256") != CLIENT_SHA256 or
            transport.get("mode") != "NETWORK" or
            transport.get("connected") is not True or
            transport.get("shared_memory") is not False or
            transport.get("metadata_provenance") != "CALLER_ATTESTED_FRESH_EXTRACTOR_SAMPLE" or
            not isinstance(owned, list) or len(owned) != 1 or
            not isinstance(owned[0], dict) or
            owned[0].get("kind") != "WEBSOCKET" or
            type(owned[0].get("state")) is not int or owned[0].get("state") != 1):
        return _fail("TRANSPORT_NOT_EXACT_CONNECTED_WEBSOCKET")

    inventory = evidence.get("inventory")
    if not isinstance(inventory, dict) or inventory.get("complete") is not True:
        return _fail("LISTENER_INVENTORY_INCOMPLETE")
    if type(inventory.get("canvas_count")) is not int or inventory.get("canvas_count") != 1:
        return _fail("CANVAS_COUNT_NOT_UNIQUE")
    nodes = inventory.get("nodes")
    chain = inventory.get("canvas_ancestor_backend_node_ids")
    if not isinstance(nodes, list) or not isinstance(chain, list) or not chain:
        return _fail("DOM_COVERAGE_MISSING")
    roles: set[str] = set()
    backend_ids: set[int] = set()
    by_role: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("roles"), list):
            return _fail("DOM_NODE_RECORD_INVALID")
        if any(not isinstance(role, str) for role in node["roles"]):
            return _fail("DOM_NODE_RECORD_INVALID")
        backend_id = node.get("backend_node_id")
        if backend_id is None:
            if set(node["roles"]) not in ({"window"}, {"document"}):
                return _fail("DOM_BACKEND_ID_MISSING")
        else:
            if not isinstance(backend_id, int) or isinstance(backend_id, bool) or backend_id <= 0:
                return _fail("DOM_BACKEND_ID_MISSING")
            if backend_id in backend_ids:
                return _fail("DOM_NODE_DUPLICATED")
            backend_ids.add(backend_id)
        for role in node["roles"]:
            if not isinstance(role, str) or role in roles:
                return _fail("DOM_ROLE_DUPLICATED")
            roles.add(role)
            by_role[role] = node
    if not {"html", "body", "canvas"}.issubset(roles):
        return _fail("DOM_REQUIRED_NODE_MISSING")
    if type(inventory.get("canvas_ancestor_count")) is not int:
        return _fail("CANVAS_ANCESTOR_COUNT_NOT_INTEGER")
    if (not all(isinstance(i, int) and not isinstance(i, bool) and i > 0 for i in chain) or
            len(chain) != len(set(chain)) or
            any(i not in backend_ids for i in chain) or
            by_role["canvas"].get("backend_node_id") != chain[0] or
            by_role["body"].get("backend_node_id") not in chain or
            by_role["html"].get("backend_node_id") not in chain):
        return _fail("CANVAS_ANCESTRY_NOT_FULLY_COVERED")
    ancestor_roles = sorted(
        (role for role in roles if role.startswith("canvas_ancestor_")),
        key=lambda role: int(role.rsplit("_", 1)[1]) if role.rsplit("_", 1)[1].isdigit() else -1,
    )
    expected_ancestor_roles = [f"canvas_ancestor_{i}" for i in range(1, len(chain))]
    if (ancestor_roles != expected_ancestor_roles or
            inventory.get("canvas_ancestor_count") != len(chain) - 1 or
            any(by_role[role].get("backend_node_id") != chain[index]
                for index, role in enumerate(expected_ancestor_roles, start=1)) or
            by_role["html"].get("backend_node_id") != chain[-1]):
        return _fail("CANVAS_ANCESTRY_NOT_CONTIGUOUS")
    if not {"window", "document"}.issubset(roles):
        return _fail("WINDOW_OR_DOCUMENT_NOT_COVERED")

    # The three expected callbacks must be the only relevant input callbacks.
    # A Playwright interceptor is optional but, if present, must be complete.
    playwright_present = False
    expected_window = [
        ("window", "mousedown", True, OBSERVER_LISTENER),
        ("window", "mousedown", True, PLAYWRIGHT_LISTENER),
        ("window", "mouseup", True, OBSERVER_LISTENER),
        ("window", "mouseup", True, PLAYWRIGHT_LISTENER),
        ("window", "mousemove", True, PLAYWRIGHT_LISTENER),
    ]
    expected_canvas = [
        ("canvas", "mousemove", False, OFFICIAL_LISTENER),
        ("canvas", "mousedown", False, OFFICIAL_LISTENER),
        ("canvas", "mouseup", False, OFFICIAL_LISTENER),
    ]

    observed: list[tuple[str, str, bool, tuple[str, int, int]]] = []
    for node in nodes:
        node_roles = node["roles"]
        listeners = node.get("listeners")
        if not isinstance(listeners, list):
            return _fail("LISTENER_ROWS_MISSING")
        for row in listeners:
            if not isinstance(row, dict):
                return _fail("LISTENER_ROW_INVALID")
            event = row.get("type")
            if event not in RELEVANT_EVENTS:
                continue
            # Listeners on window/document/html/body/canvas ancestors are all
            # inspected. Only the named window and actual canvas may own these.
            if "window" in node_roles:
                role = "window"
            elif "canvas" in node_roles:
                role = "canvas"
            else:
                return _fail("UNEXPECTED_ANCESTOR_INPUT_LISTENER")
            sha = row.get("source_sha256")
            line = row.get("line_number")
            column = row.get("column_number")
            source = (sha, line, column)
            capture = row.get("use_capture")
            if not isinstance(capture, bool):
                return _fail("LISTENER_PHASE_UNKNOWN")
            if role == "window" and sha == PLAYWRIGHT_LISTENER[0]:
                playwright_present = True
            observed.append((role, event, capture, source))

    # Ignore optional PW rows only if none were found; otherwise all three
    # mouse listeners must be present at their reviewed window-capture sites.
    wanted = [item for item in expected_window + expected_canvas
              if playwright_present or item[3] != PLAYWRIGHT_LISTENER]
    if observed != wanted:
        return _fail("INPUT_LISTENER_SET_OR_ORDER_MISMATCH")

    return {
        "qualified": True,
        "reason": "EXACT_PREARM_LISTENER_TOPOLOGY",
        "certificate": {
            "scope": "SAME_DOCUMENT_LISTENER_TOPOLOGY_ONLY",
            "document_id": expected_document_id,
            "document_id_binding": "CALLER_ATTESTED_EXTRACTOR_SESSION_ID; CDP_FRAME_AND_LOADER_OBSERVED",
            "document_time_origin_ms": expected_time_origin_ms,
            "client_sha256": CLIENT_SHA256,
            "observer_startup_source_sha256": OBSERVER_STARTUP_SHA256,
            "transport": "CONNECTED_WEBSOCKET_ONLY",
            "observer_listener_sha256": OBSERVER_LISTENER[0],
            "playwright_listener_present": playwright_present,
            "canvas_backend_node_id": by_role["canvas"]["backend_node_id"],
            "canvas_ancestor_backend_node_ids": list(chain),
            "gesture_continuity": "UNKNOWN",
            "route_continuity": "UNKNOWN",
        },
    }


async def capture_input_listener_inventory(
    cdp: Any, *, document_id: str, expected_time_origin_ms: float,
    host_preregistration: dict[str, Any], client_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Capture DOM listener metadata through CDP without reading game memory."""
    handles: list[str] = []
    debugger_enabled = False

    async def evaluate(expression: str, *, by_value: bool = False) -> dict[str, Any]:
        result = await cdp.send("Runtime.evaluate", {
            "expression": expression, "returnByValue": by_value,
            "awaitPromise": False, "userGesture": False,
        })
        if result.get("exceptionDetails"):
            raise RuntimeError("DOM metadata evaluation failed")
        remote = result.get("result") or {}
        if remote.get("subtype") == "error":
            raise RuntimeError("DOM metadata evaluation returned error")
        if not by_value:
            object_id = remote.get("objectId")
            if not isinstance(object_id, str):
                raise RuntimeError("DOM object handle unavailable")
            handles.append(object_id)
        return remote

    async def snapshot() -> dict[str, Any]:
        remote = await evaluate("({origin: performance.timeOrigin, ready: document.readyState, observer: window[Symbol.for('kiomet.inputEntryObserver.v1')]?.status?.() ?? null})", by_value=True)
        value = remote.get("value")
        if not isinstance(value, dict):
            raise RuntimeError("document snapshot unavailable")
        return value

    async def main_frame() -> dict[str, Any]:
        response = await cdp.send("Page.getFrameTree", {})
        frame = (response.get("frameTree") or {}).get("frame")
        if not isinstance(frame, dict):
            raise RuntimeError("main frame identity unavailable")
        return {"frame_id": frame.get("id"), "loader_id": frame.get("loaderId"), "url": frame.get("url")}

    async def current_canvas_chain() -> tuple[int, list[int]]:
        count_remote = await evaluate("document.querySelectorAll('canvas').length", by_value=True)
        canvas_count = count_remote.get("value")
        if type(canvas_count) is not int or canvas_count != 1:
            raise RuntimeError("canvas count is not unique")
        depth_remote = await evaluate("(() => { let n=document.querySelector('canvas'),p=0; while(n){p++;n=n.parentElement;} return p; })()", by_value=True)
        depth = depth_remote.get("value")
        if type(depth) is not int or depth <= 0 or depth > 64:
            raise RuntimeError("canvas ancestry invalid")
        chain_ids: list[int] = []
        for index in range(depth):
            if index == 0:
                expression = "document.querySelector('canvas')"
            else:
                expression = f"(() => {{ let n=document.querySelector('canvas'); for(let j=0;j<{index};j++) n=n?.parentElement; return n; }})()"
            node_remote = await evaluate(expression)
            description = await cdp.send("DOM.describeNode", {"objectId": node_remote["objectId"]})
            backend_id = (description.get("node") or {}).get("backendNodeId")
            if type(backend_id) is not int or backend_id <= 0:
                raise RuntimeError("canvas ancestry backend id unavailable")
            chain_ids.append(backend_id)
        if len(set(chain_ids)) != len(chain_ids):
            raise RuntimeError("canvas ancestry duplicated")
        return canvas_count, chain_ids

    try:
        await cdp.send("Debugger.enable")
        debugger_enabled = True
        frame_before = await main_frame()
        before = await snapshot()
        if not _finite_number(before.get("origin")) or float(before["origin"]) != float(expected_time_origin_ms):
            return _fail("DOCUMENT_ORIGIN_CHANGED")
        status = before.get("observer")
        if not isinstance(status, dict):
            return _fail("OBSERVER_STATUS_UNAVAILABLE")

        canvas_count_remote = await evaluate("document.querySelectorAll('canvas').length", by_value=True)
        canvas_count = canvas_count_remote.get("value")
        if type(canvas_count) is not int or canvas_count != 1:
            return _fail("CANVAS_COUNT_NOT_UNIQUE")
        depth_remote = await evaluate("(() => { const c=document.querySelector('canvas'); if(!c) return -1; let n=c,p=0; while(n){p++;n=n.parentElement;} return p; })()", by_value=True)
        depth = depth_remote.get("value")
        if not isinstance(depth, int) or isinstance(depth, bool) or depth <= 0 or depth > 64:
            return _fail("CANVAS_ANCESTRY_INVALID")

        targets: list[tuple[str, str]] = [
            ("window", "window"), ("document", "document"),
            ("html", "document.documentElement"), ("body", "document.body"),
            ("canvas", "document.querySelector('canvas')"),
        ]
        targets.extend((f"canvas_ancestor_{i}", f"(() => {{ let n=document.querySelector('canvas'); for(let j=0;j<{i};j++) n=n?.parentElement; return n; }})()") for i in range(1, depth))

        nodes_by_identity: dict[tuple[str, int], dict[str, Any]] = {}
        for role, expression in targets:
            remote = await evaluate(expression)
            backend_id = None
            if role not in ("window", "document"):
                described = await cdp.send("DOM.describeNode", {"objectId": remote["objectId"]})
                node_desc = described.get("node") or {}
                backend_id = node_desc.get("backendNodeId")
                if not isinstance(backend_id, int) or backend_id <= 0:
                    return _fail("DOM_BACKEND_ID_MISSING")
            key = ("backend", backend_id) if backend_id is not None else ("role", role)
            record = nodes_by_identity.setdefault(key, {"backend_node_id": backend_id, "roles": [], "listeners": [], "_object_id": remote["objectId"]})
            record["roles"].append(role)

        nodes = [{k: v for k, v in node.items() if k != "_object_id"} for node in nodes_by_identity.values()]
        for node in nodes:
            # Find any handle for the de-duplicated DOM backend node.
            handle = next(record["_object_id"] for record in nodes_by_identity.values()
                          if record["backend_node_id"] == node["backend_node_id"] and
                          set(record["roles"]) == set(node["roles"]))
            response = await cdp.send("DOMDebugger.getEventListeners", {
                "objectId": handle, "depth": 0, "pierce": False,
            })
            listeners = response.get("listeners")
            if not isinstance(listeners, list):
                return _fail("LISTENER_QUERY_FAILED")
            for listener in listeners:
                event = listener.get("type")
                if event not in RELEVANT_EVENTS:
                    continue
                script_id = listener.get("scriptId")
                if not isinstance(script_id, str):
                    return _fail("LISTENER_SCRIPT_UNKNOWN")
                source_result = await cdp.send("Debugger.getScriptSource", {"scriptId": script_id})
                source_text = source_result.get("scriptSource")
                if not isinstance(source_text, str):
                    return _fail("LISTENER_SOURCE_UNAVAILABLE")
                node["listeners"].append({
                    "type": event,
                    "use_capture": listener.get("useCapture"),
                    "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                    "line_number": listener.get("lineNumber"),
                    "column_number": listener.get("columnNumber"),
                })

        final_canvas_count, final_chain_ids = await current_canvas_chain()
        chain_roles = sorted(
            (role for node in nodes for role in node["roles"] if role == "canvas" or role.startswith("canvas_ancestor_")),
            key=lambda role: 0 if role == "canvas" else int(role.rsplit("_", 1)[1]),
        )
        role_map = {role: node["backend_node_id"] for node in nodes for role in node["roles"]}
        chain_ids = [role_map[role] for role in chain_roles]
        if final_canvas_count != canvas_count or final_chain_ids != chain_ids:
            return _fail("CANVAS_OR_ANCESTRY_CHANGED_DURING_INVENTORY")
        after = await snapshot()
        frame_after = await main_frame()
        if after.get("origin") != before.get("origin"):
            return _fail("DOCUMENT_ORIGIN_CHANGED")
        evidence = {
            "document_id": document_id,
            "document_id_attestation": "CALLER_SUPPLIED_EXTRACTOR_SESSION_ID",
            "client_sha256": client_metadata.get("client_sha256"),
            "time_origin_before_ms": before["origin"],
            "time_origin_after_ms": after["origin"],
            "observer_install_time_origin_ms": status.get("install_performance_time_origin_ms"),
            "host_preregistration": host_preregistration,
            "observer_status": status,
            "observer_status_after": after.get("observer"),
            "main_frame_before": frame_before,
            "main_frame_after": frame_after,
            "transport": {
                "client_sha256": client_metadata.get("client_sha256"),
                "mode": client_metadata.get("transport_mode"),
                "connected": client_metadata.get("transport_connected"),
                "shared_memory": client_metadata.get("shared_memory"),
                "owned_transports": client_metadata.get("owned_transports"),
                "metadata_provenance": client_metadata.get("metadata_provenance"),
            },
            "inventory": {
                "complete": True,
                "canvas_count": canvas_count,
                "canvas_ancestor_count": len(chain_ids) - 1,
                "nodes": nodes,
                "canvas_ancestor_backend_node_ids": chain_ids,
            },
        }
        return validate_input_listener_inventory(
            evidence, expected_document_id=document_id,
            expected_time_origin_ms=expected_time_origin_ms,
        ) | {"evidence": evidence}
    finally:
        for object_id in handles:
            try:
                await cdp.send("Runtime.releaseObject", {"objectId": object_id})
            except Exception:
                pass
        if debugger_enabled:
            try:
                await cdp.send("Debugger.disable")
            except Exception:
                pass
