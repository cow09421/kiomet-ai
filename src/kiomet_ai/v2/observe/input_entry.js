// Disabled-at-bootstrap observer for one ordinary trusted left drag.
// It samples only through the caller-supplied normal visible-world decoder.
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root && root.document && root.addEventListener) api.install(root);
})(typeof window === "object" ? window : null, function () {
  "use strict";

  const KEY = Symbol.for("kiomet.inputEntryObserver.v1");

  function deepFreeze(value) {
    if (value && typeof value === "object" && !Object.isFrozen(value)) {
      for (const child of Object.values(value)) deepFreeze(child);
      Object.freeze(value);
    }
    return value;
  }

  function copyVisibleRaw(raw) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      throw new Error("normal world decoder returned no object");
    }
    // Keep root candidates only in this private handoff for the existing
    // extractor identity/source-clock path. Actor pointers are never needed.
    const copy = structuredClone(raw);
    const strip = value => {
      if (!value || typeof value !== "object") return;
      delete value.research_ref;
      for (const child of Object.values(value)) strip(child);
    };
    strip(copy);
    return deepFreeze(copy);
  }

  function validExpected(expected) {
    if (expected == null) return null;
    if (typeof expected !== "object") throw new TypeError("expected endpoints must be an object");
    const tolerance = expected.tolerancePx == null ? 0 : expected.tolerancePx;
    if (typeof tolerance !== "number" || !Number.isFinite(tolerance) || tolerance < 0 || tolerance > 2) {
      throw new TypeError("endpoint tolerance must be between 0 and 2 CSS pixels");
    }
    for (const key of ["down", "up"]) {
      const point = expected[key];
      if (!point || typeof point !== "object" ||
          typeof point.x !== "number" || !Number.isFinite(point.x) ||
          typeof point.y !== "number" || !Number.isFinite(point.y)) {
        throw new TypeError(`expected ${key} coordinate is required`);
      }
    }
    return {down: {x: expected.down.x, y: expected.down.y},
      up: {x: expected.up.x, y: expected.up.y}, tolerancePx: tolerance};
  }

  function checkMemories(memories) {
    if (!Array.isArray(memories) || memories.length !== 1 ||
        typeof WebAssembly !== "object" || typeof WebAssembly.Memory !== "function") {
      throw new TypeError("one already-discovered WebAssembly memory is required");
    }
    for (const memory of memories) {
      if (!(memory instanceof WebAssembly.Memory)) throw new TypeError("invalid WebAssembly memory handle");
      if (typeof SharedArrayBuffer === "function" && memory.buffer instanceof SharedArrayBuffer) {
        throw new Error("shared WebAssembly memory is unsupported");
      }
    }
  }

  function install(target) {
    if (!target || !target.document || typeof target.addEventListener !== "function") {
      throw new TypeError("a browser window is required");
    }
    if (target[KEY]) return target[KEY];
    const document = target.document;
    const readyStateAtInstall = document.readyState;
    const loadingAtInstall = readyStateAtInstall === "loading";
    const installPerformanceOrigin = target.performance.timeOrigin;
    const installPerformanceNow = target.performance.now();
    let capture = null;
    let armedOnce = false;
    let removed = false;

    function metrics(canvas) {
      if (!canvas || typeof canvas.getBoundingClientRect !== "function") return null;
      const rect = canvas.getBoundingClientRect();
      const values = [rect.left, rect.top, rect.width, rect.height,
        canvas.width, canvas.height, target.devicePixelRatio];
      if (values.some(value => typeof value !== "number" || !Number.isFinite(value))) return null;
      return {left: rect.left, top: rect.top, css_width: rect.width, css_height: rect.height,
        width: canvas.width, height: canvas.height, dpr: target.devicePixelRatio};
    }

    function invalidate(reason) {
      if (capture && capture.status !== "INVALID") {
        capture.status = "INVALID";
        capture.errors.push(reason);
      }
    }

    function eventPoint(event) {
      return {client_x: event.clientX, client_y: event.clientY,
        page_x: event.pageX, page_y: event.pageY,
        screen_x: event.screenX, screen_y: event.screenY};
    }

    function eventIsForCanvas(event, canvas) {
      if (!canvas) return true;
      if (typeof event.composedPath === "function") return event.composedPath().includes(canvas);
      return event.target === canvas;
    }

    function matchesExpected(point, expected, stage) {
      if (!expected) return true;
      const targetPoint = expected[stage];
      return Math.abs(point.client_x - targetPoint.x) <= expected.tolerancePx &&
        Math.abs(point.client_y - targetPoint.y) <= expected.tolerancePx;
    }

    function onMouse(event) {
      const active = capture;
      if (!active) return;
      if (active.status === "INVALID") return;
      const stage = event.type === "mousedown" ? "down" : "up";
      if (active.status === "COMPLETE") {
        invalidate("duplicate mouse event after the bounded drag");
        return;
      }
      if (event.isTrusted !== true) return invalidate("untrusted mouse event");
      if (event.button !== 0 ||
          (stage === "down" && event.buttons !== 1) ||
          (stage === "up" && event.buttons !== 0) ||
          event.ctrlKey || event.shiftKey || event.altKey || event.metaKey) {
        return invalidate("event was not an unmodified left-button drag endpoint");
      }
      if (!eventIsForCanvas(event, active.canvas)) return invalidate("event target was not the expected canvas");
      const point = eventPoint(event);
      if (![point.client_x, point.client_y].every(value => typeof value === "number" && Number.isFinite(value))) {
        return invalidate("event coordinates are unavailable");
      }
      if (!matchesExpected(point, active.expected, stage)) return invalidate(`unexpected ${stage} coordinates`);
      if ((stage === "down" && active.status !== "ARMED") ||
          (stage === "up" && active.status !== "DOWN_CAPTURED")) {
        return invalidate("mouse event order was incomplete or duplicated");
      }
      if (stage === "up" && !active.drained.has("down")) {
        return invalidate("mousedown entry was not drained before mouseup");
      }
      const canvasMetrics = metrics(active.canvas);
      if (active.canvas && !canvasMetrics) return invalidate("canvas geometry is unavailable");
      try {
        const sampledPerformanceNow = target.performance.now();
        const decoderRaw = active.decoder.call(active.memories, "world", [], active.owners);
        const raw = copyVisibleRaw(decoderRaw);
        const entry = deepFreeze({stage: stage === "down" ? "MOUSEDOWN_ENTRY" : "MOUSEUP_ENTRY",
          event: {type: event.type, isTrusted: event.isTrusted, button: event.button,
            buttons: event.buttons, ...point, timeStamp: event.timeStamp,
            ctrlKey: !!event.ctrlKey, shiftKey: !!event.shiftKey,
            altKey: !!event.altKey, metaKey: !!event.metaKey},
          browser_clock: {date_now_ms: Date.now(), performance_time_origin_ms: target.performance.timeOrigin,
            performance_now_ms: sampledPerformanceNow},
          canvas: canvasMetrics, raw});
        active.entries.push(entry);
        active.status = stage === "down" ? "DOWN_CAPTURED" : "COMPLETE";
      } catch (error) {
        invalidate(`entry sample failed: ${String(error && error.message || error)}`);
      }
    }

    target.addEventListener("mousedown", onMouse, true);
    target.addEventListener("mouseup", onMouse, true);

    const api = {
      status() {
        return deepFreeze({installed: true, ready_state_at_install: readyStateAtInstall,
          document_loading_at_install: loadingAtInstall,
          startup_claim: "page cue only; host must attest init-script registration before page creation",
          install_performance_time_origin_ms: installPerformanceOrigin,
          install_performance_now_ms: installPerformanceNow,
          armed_once: armedOnce, armed: !!capture,
          status: capture ? capture.status : (removed ? "REMOVED" : "DISARMED")});
      },
      arm(options) {
        if (removed) throw new Error("observer was removed");
        if (!loadingAtInstall) throw new Error("observer bootstrap was not installed while document was loading");
        if (armedOnce) throw new Error("observer permits one bounded drag per document");
        if (!options || typeof options.decoder !== "function") throw new TypeError("normal decoder function is required");
        const hostProof = options.hostPrerequisite;
        if (!hostProof || hostProof.init_script_registered_before_page !== true ||
            hostProof.page_created_after_registration !== true) {
          throw new Error("host pre-start registration evidence is required; loading state alone is insufficient");
        }
        checkMemories(options.memories);
        if (!Array.isArray(options.owners) || options.owners.length === 0) {
          throw new TypeError("already-discovered normal event-owner handles are required");
        }
        const expected = validExpected(options.expected);
        const canvas = options.expectedCanvas || null;
        if (canvas && (String(canvas.tagName).toLowerCase() !== "canvas" || !metrics(canvas))) {
          throw new TypeError("expected canvas is invalid");
        }
        armedOnce = true;
        capture = {decoder: options.decoder, memories: options.memories, owners: options.owners,
          canvas, expected, status: "ARMED", entries: [], errors: [], drained: new Set()};
        return deepFreeze({armed: true, one_shot: true,
          document_loading_at_install: loadingAtInstall,
          host_prestart_evidence: structuredClone(hostProof)});
      },
      drainEntry(stage) {
        if (!capture) return deepFreeze({valid: false, status: removed ? "REMOVED" : "DISARMED",
          entry: null, errors: []});
        const active = capture;
        if (active.status === "INVALID") return deepFreeze({valid: false,
          status: active.status, entry: null, errors: active.errors.slice()});
        if (stage !== "down" && stage !== "up") {
          invalidate("invalid entry drain stage");
          return deepFreeze({valid: false, status: active.status, entry: null, errors: active.errors.slice()});
        }
        if (active.drained.has(stage)) {
          invalidate(`duplicate ${stage} entry drain`);
          return deepFreeze({valid: false, status: active.status, entry: null, errors: active.errors.slice()});
        }
        const entry = active.entries.find(row => row.stage ===
          (stage === "down" ? "MOUSEDOWN_ENTRY" : "MOUSEUP_ENTRY"));
        if (!entry || (stage === "up" && (!active.drained.has("down") || active.status !== "COMPLETE"))) {
          invalidate(`wrong-stage or unavailable ${stage} entry drain`);
          return deepFreeze({valid: false, status: active.status, entry: null, errors: active.errors.slice()});
        }
        active.drained.add(stage);
        return deepFreeze({valid: true, status: active.status, stage, entry});
      },
      take() {
        if (!capture) return deepFreeze({valid: false, status: removed ? "REMOVED" : "DISARMED",
          entries: [], errors: []});
        const active = capture;
        if (active.status !== "COMPLETE" && active.status !== "INVALID") {
          active.errors.push(active.status === "ARMED" ? "mousedown and mouseup entries were not captured" :
            "mouseup entry was not captured");
          active.status = "INVALID";
        }
        if (active.status === "COMPLETE" &&
            (!active.drained.has("down") || !active.drained.has("up"))) {
          active.errors.push("both entry stages must be drained in order before final take");
          active.status = "INVALID";
        }
        const result = deepFreeze({valid: active.status === "COMPLETE" && active.entries.length === 2,
          status: active.status, entries: active.entries.slice(), errors: active.errors.slice(),
          drained_stages: [...active.drained],
          document_loading_at_install: loadingAtInstall,
          one_shot: true});
        capture = null;
        return result;
      },
      disarm() {
        capture = null;
        return deepFreeze({disarmed: true, queue_cleared: true});
      },
      teardown() {
        capture = null;
        if (!removed) {
          target.removeEventListener("mousedown", onMouse, true);
          target.removeEventListener("mouseup", onMouse, true);
          removed = true;
        }
        return deepFreeze({removed: true, queue_cleared: true});
      }
    };
    Object.defineProperty(target, KEY, {value: api, configurable: false, enumerable: false});
    return api;
  }

  return {install, key: KEY};
});
