"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {install, key} = require("../src/kiomet_ai/v2/observe/input_entry.js");

class FakeWindow {
  constructor(readyState = "loading") {
    this.document = {readyState, pointerLockElement: null, visibilityState: "visible",
      listeners: new Map(),
      addEventListener(type, listener, capture) {
        const rows = this.listeners.get(type) || [];
        rows.push({listener, capture: !!capture});
        this.listeners.set(type, rows);
      },
      removeEventListener(type, listener, capture) {
        const rows = this.listeners.get(type) || [];
        this.listeners.set(type, rows.filter(row => row.listener !== listener || row.capture !== !!capture));
      }};
    this.devicePixelRatio = 1;
    this.performance = {timeOrigin: 1234, now: () => 56};
    this.listeners = new Map();
  }
  addEventListener(type, listener, capture) {
    const rows = this.listeners.get(type) || [];
    rows.push({listener, capture: !!capture});
    this.listeners.set(type, rows);
  }
  removeEventListener(type, listener, capture) {
    const rows = this.listeners.get(type) || [];
    this.listeners.set(type, rows.filter(row => row.listener !== listener || row.capture !== !!capture));
  }
  dispatch(event) {
    event.target ||= event.canvas;
    event.composedPath ||= () => [event.canvas, this.document, this];
    const rows = this.listeners.get(event.type) || [];
    for (const row of rows.filter(item => item.capture)) row.listener(event);
    for (const row of rows.filter(item => !item.capture)) row.listener(event);
  }
  dispatchDocument(type) {
    const event = {type, target: this.document};
    for (const row of this.document.listeners.get(type) || []) row.listener(event);
  }
}

function fixture({decode = null} = {}) {
  const win = new FakeWindow();
  const canvas = {tagName: "CANVAS", width: 800, height: 600,
    getBoundingClientRect: () => ({left: 0, top: 0, width: 800, height: 600})};
  const memory = new WebAssembly.Memory({initial: 1});
  const memories = [memory];
  const owners = [{normal: true}];
  const calls = [];
  const raws = [];
  const decoder = decode || function (mode, watchedIds, eventOwners) {
    assert.equal(this, memories);
    assert.equal(mode, "world");
    assert.deepEqual(watchedIds, []);
    assert.equal(eventOwners, owners);
    calls.push("decode");
    const raw = {sampled_at_ms: 10, document_time_origin: 1234,
      camera_candidate: [1, 2, 3], coverage: "PLAYER_VISIBLE_COMPLETE",
      towers: [{id: 7, position: [5, 6], research_ref: 888}], forces: [],
      root_candidate: 999, root_slot_candidate: 2};
    raws.push(raw);
    return raw;
  };
  const api = install(win);
  const arm = () => api.arm({decoder, memories, owners,
    hostPrerequisite: {init_script_registered_before_page: true, page_created_after_registration: true},
    expectedCanvas: canvas,
    expected: {down: {x: 10, y: 20}, up: {x: 30, y: 40}, tolerancePx: 0.25}});
  const dispatch = (type, {x, y, trusted = true, canvasTarget = canvas} = {}) => {
    win.dispatch({type, isTrusted: trusted, button: 0, buttons: type === "mousedown" ? 1 : 0,
      clientX: x, clientY: y, pageX: x, pageY: y, screenX: x, screenY: y,
      timeStamp: 77, ctrlKey: false, shiftKey: false, altKey: false, metaKey: false,
      canvas: canvasTarget, composedPath: () => [canvasTarget, win.document, win]});
  };
  return {win, canvas, api, arm, dispatch, calls, raws};
}

test("bootstrap is idempotent and installs disabled capture listeners before app handlers", () => {
  const f = fixture();
  assert.equal(f.win[key], f.api);
  assert.equal(install(f.win), f.api);
  assert.equal(f.api.status().document_loading_at_install, true);
  assert.equal(f.calls.length, 0);
  f.dispatch("mousedown", {x: 10, y: 20});
  assert.equal(f.calls.length, 0);
  f.arm();
  assert.throws(() => f.arm(), /one bounded drag per document/);
});

test("trusted down/up snapshots are immutable, pointer-matched, bounded to two and precede broker", () => {
  const f = fixture();
  const order = [];
  f.arm();
  f.win.addEventListener("mousedown", () => order.push("broker-down"), false);
  f.win.addEventListener("mouseup", () => order.push("broker-up"), false);
  f.dispatch("mousedown", {x: 10, y: 20});
  const down = f.api.drainEntry("down");
  assert.equal(down.valid, true);
  assert.equal(down.entry.raw.root_candidate, 999);
  assert.equal(down.entry.raw.root_slot_candidate, 2);
  assert.equal(down.entry.raw.towers[0].research_ref, undefined);
  f.raws[0].camera_candidate[0] = 999;
  assert.equal(down.entry.raw.camera_candidate[0], 1);
  f.dispatch("mouseup", {x: 30, y: 40});
  const up = f.api.drainEntry("up");
  assert.equal(up.valid, true);
  assert.deepEqual(f.calls, ["decode", "decode"]);
  assert.deepEqual(order, ["broker-down", "broker-up"]);
  const result = f.api.take();
  assert.equal(result.valid, true);
  assert.equal(result.entries.length, 2);
  assert.equal(result.entries[0].stage, "MOUSEDOWN_ENTRY");
  assert.equal(result.entries[1].stage, "MOUSEUP_ENTRY");
  assert.equal(result.entries[0].raw.towers[0].research_ref, undefined);
  assert.equal(result.entries[0].raw.root_candidate, 999);
  assert.equal(Object.isFrozen(result.entries[0]), true);
  assert.equal(Object.isFrozen(result.entries[0].raw.towers[0]), true);
  assert.throws(() => { result.entries[0].raw.towers[0].id = 3; }, TypeError);
});

test("untrusted, off-coordinate, wrong-canvas and duplicate events invalidate without extra decode", () => {
  for (const invalid of [
    f => f.dispatch("mousedown", {x: 10, y: 20, trusted: false}),
    f => f.dispatch("mousedown", {x: 10.5, y: 20}),
    f => f.dispatch("mousedown", {x: 10, y: 20, canvasTarget: {tagName: "DIV"}}),
    f => { f.dispatch("mousedown", {x: 10, y: 20}); f.dispatch("mousedown", {x: 10, y: 20}); }
  ]) {
    const f = fixture();
    f.arm();
    invalid(f);
    const result = f.api.take();
    assert.equal(result.valid, false);
    assert.equal(result.status, "INVALID");
    assert.ok(result.errors.length > 0);
    assert.ok(f.calls.length <= 1);
  }
});

test("mouseup-first, duplicate mouseup and post-completion event invalidate the proof", () => {
  for (const dispatch of [
    f => f.dispatch("mouseup", {x: 30, y: 40}),
    f => { f.dispatch("mousedown", {x: 10, y: 20}); f.dispatch("mouseup", {x: 30, y: 40});
      f.dispatch("mouseup", {x: 30, y: 40}); }
  ]) {
    const f = fixture();
    f.arm();
    dispatch(f);
    assert.equal(f.api.take().valid, false);
    assert.ok(f.calls.length <= 2);
  }
});

test("taking an incomplete drag marks the missing boundary as an invalid gap", () => {
  const f = fixture();
  f.arm();
  f.dispatch("mousedown", {x: 10, y: 20});
  const result = f.api.take();
  assert.equal(result.valid, false);
  assert.equal(result.status, "INVALID");
  assert.ok(result.errors.includes("mouseup entry was not captured"));
});

test("wrong-stage and duplicate drains invalidate the bounded entry proof", () => {
  const early = fixture();
  early.arm();
  assert.equal(early.api.drainEntry("up").valid, false);
  assert.equal(early.api.take().valid, false);

  const duplicate = fixture();
  duplicate.arm();
  duplicate.dispatch("mousedown", {x: 10, y: 20});
  assert.equal(duplicate.api.drainEntry("down").valid, true);
  assert.equal(duplicate.api.drainEntry("down").valid, false);
  assert.equal(duplicate.api.take().valid, false);
});

test("decoder failure never blocks the ordinary broker handler", () => {
  const f = fixture({decode() { throw new Error("visibility cache pending"); }});
  const broker = [];
  f.arm();
  f.win.addEventListener("mousedown", () => broker.push("normal-handler"), false);
  f.dispatch("mousedown", {x: 10, y: 20});
  assert.deepEqual(broker, ["normal-handler"]);
  assert.equal(f.api.take().valid, false);
});

test("disarm clears the queue and prevents all actor reads", () => {
  const f = fixture();
  f.arm();
  f.dispatch("mousedown", {x: 10, y: 20});
  f.api.disarm();
  f.dispatch("mouseup", {x: 30, y: 40});
  assert.deepEqual(f.calls, ["decode"]);
  assert.deepEqual(f.api.take().entries, []);
});

test("late bootstrap, shared memory and malformed endpoint bounds cannot arm", () => {
  const late = fixture();
  const lateApi = install(new FakeWindow("complete"));
  assert.equal(lateApi.status().document_loading_at_install, false);
  assert.throws(() => lateApi.arm({}), /while document was loading/);

  const f = fixture();
  assert.throws(() => f.api.arm({decoder() {}, memories: [new WebAssembly.Memory({initial: 1, maximum: 1, shared: true})],
    owners: [{}], hostPrerequisite: {init_script_registered_before_page: true,
      page_created_after_registration: true}}), /shared WebAssembly memory/);
  assert.throws(() => f.api.arm({decoder() {}, memories: [new WebAssembly.Memory({initial: 1})],
    owners: [{}], hostPrerequisite: {init_script_registered_before_page: true,
      page_created_after_registration: true},
    expected: {down: {x: 1, y: 1}, up: {x: 2, y: 2}, tolerancePx: 3}}), /tolerance/);
});

test("pointer lock and hidden documents fail closed at arm without inventing missing visibility", () => {
  const locked = fixture();
  locked.win.document.pointerLockElement = {};
  assert.throws(() => locked.arm(), /pointer lock/);

  const hidden = fixture();
  hidden.win.document.visibilityState = "hidden";
  assert.throws(() => hidden.arm(), /visible/);

  const absentVisibility = fixture();
  delete absentVisibility.win.document.visibilityState;
  const armed = absentVisibility.arm();
  assert.equal(armed.guard_evidence.visibility_api_available, false);
  assert.equal(armed.guard_evidence.visibility_state, null);
  assert.equal(absentVisibility.api.status().guard_evidence.visibility_state, null);
  absentVisibility.api.disarm();
});

test("reset-sensitive events invalidate armed capture passively with bounded history", () => {
  const events = [
    ["window", "blur"], ["window", "mouseleave"], ["window", "keydown"],
    ["window", "keyup"], ["window", "touchstart"],
    ["window", "touchmove"], ["window", "touchend"], ["window", "touchcancel"],
    ["document", "pointerlockchange"], ["window", "pointercancel"],
    ["document", "visibilitychange"]
  ];
  for (const [owner, type] of events) {
    const f = fixture();
    f.arm();
    if (owner === "document") f.win.dispatchDocument(type);
    else f.win.dispatch({type});
    const status = f.api.status();
    assert.equal(status.status, "INVALID", type);
    assert.equal(status.reset_free, false, type);
    assert.deepEqual(status.reset_history, [type], type);
    const result = f.api.take();
    assert.equal(result.valid, false, type);
    assert.equal(result.reset_free, false, type);
    assert.deepEqual(result.reset_history, [type], type);
    assert.equal(f.calls.length, 0, type);
  }
});

test("reset-sensitive events after down retain bounded evidence and never take a second sample", () => {
  const f = fixture();
  f.arm();
  f.dispatch("mousedown", {x: 10, y: 20});
  f.win.dispatch({type: "blur"});
  f.win.dispatch({type: "touchcancel"});
  const result = f.api.take();
  assert.equal(result.valid, false);
  assert.equal(result.status, "INVALID");
  assert.equal(result.reset_free, false);
  assert.deepEqual(result.reset_history, ["blur"]);
  assert.deepEqual(f.calls, ["decode"]);
});
