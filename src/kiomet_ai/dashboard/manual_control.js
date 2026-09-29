/* 真實遊戲遠端控制前端模組（P0）— 獨立檔，尚未掛進 index.html（GPT 施工中）。
 *
 * 模式：[AI VIEW] [MANUAL CONTROL] [RETURN TO AI]
 * MANUAL CONTROL：把使用者的 pointer/wheel/click 轉成 /api/control/input
 * 送給真正的 AI game_page（真遊戲攝影機會改變）。
 * 禁止以 CSS transform 平移冒充攝影機。
 */
(function () {
  "use strict";
  const MODES = { AI_VIEW: "AI VIEW", MANUAL: "MANUAL CONTROL",
                  RETURN: "RETURN TO AI" };
  const LABELS = {
    REACQUIRING_CAMERA: "REACQUIRING CAMERA（重新取得攝影機）",
    REACQUIRING_WORLD: "REACQUIRING WORLD（重新取得世界）",
    READY: "READY（就緒）",
    AUTONOMY_RESUMED: "AUTONOMY RESUMED（自主已恢復）",
    HUMAN: "Control owner: HUMAN（真人控制中）",
    AI: "Control owner: AI（AI 控制中）",
  };

  function create(opts) {
    opts = opts || {};
    const token = opts.token || "";
    const img = opts.img || null;
    const state = { owner: "NONE", mode: MODES.AI_VIEW, dragging: false };
    let last = null;

    function setLabel(text) {
      if (opts.labelEl) opts.labelEl.textContent = text;
    }
    function setMode(mode) {
      state.mode = mode;
      setLabel(mode);
    }
    async function api(path, body) {
      const headers = { "X-Control-Token": token };
      if (body) headers["Content-Type"] = "application/json";
      const res = await fetch(path, {
        method: body ? "POST" : "GET", headers: headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return res.json();
    }

    async function refresh() {
      const st = await api("/api/control/status");
      state.owner = (st && st.owner) || "NONE";
      setLabel(state.mode + " · " + (state.owner === "HUMAN"
        ? LABELS.HUMAN : LABELS.AI));
      return st;
    }
    async function engageManual() {
      const r = await api("/api/control/manual", {});
      if (r && r.owner === "HUMAN") setMode(MODES.MANUAL);
      return r;
    }
    async function returnToAI() {
      setMode(MODES.RETURN);
      setLabel(LABELS.REACQUIRING_CAMERA);
      const r = await api("/api/control/return-to-ai", {});
      if (r && r.code === "AUTONOMY_RESUMED") setLabel(LABELS.AUTONOMY_RESUMED);
      else setLabel(LABELS.REACQUIRING_WORLD);
      return r;
    }
    function imageCoords(ev) {
      if (!img) return { x: ev.clientX, y: ev.clientY };
      const rect = img.getBoundingClientRect();
      const sx = img.naturalWidth ? img.naturalWidth / rect.width : 1;
      const sy = img.naturalHeight ? img.naturalHeight / rect.height : 1;
      return { x: (ev.clientX - rect.left) * sx,
               y: (ev.clientY - rect.top) * sy };
    }
    function canInput() {
      return state.owner === "HUMAN" && state.mode === MODES.MANUAL;
    }
    async function send(action, params) {
      if (!canInput()) return { ok: false, code: "MANUAL_NOT_ALLOWED" };
      return api("/api/control/input", { action: action, params: params });
    }
    async function onPointerDown(ev) {
      if (!canInput()) return;
      state.dragging = true;
      last = imageCoords(ev);
      await send("move", last);
      await send("down", {});
    }
    async function onPointerMove(ev) {
      if (!canInput() || !state.dragging) return;
      last = imageCoords(ev);
      await send("move", last);
    }
    async function onPointerUp() {
      if (!state.dragging) return;
      state.dragging = false;
      await send("up", {});
    }
    async function onWheel(ev) {
      if (!canInput()) return;
      ev.preventDefault && ev.preventDefault();
      await send("wheel", { dx: ev.deltaX, dy: ev.deltaY });
    }
    function fullscreen() {
      const el = opts.container || (img && img.parentElement);
      if (document.fullscreenElement) document.exitFullscreen();
      else if (el && el.requestFullscreen) el.requestFullscreen();
    }

    return { refresh: refresh, engageManual: engageManual,
             returnToAI: returnToAI, send: send, onPointerDown: onPointerDown,
             onPointerMove: onPointerMove, onPointerUp: onPointerUp,
             onWheel: onWheel, fullscreen: fullscreen, state: state,
             MODES: MODES, LABELS: LABELS };
  }

  if (typeof window !== "undefined") {
    window.KiometManual = { create: create, MODES: MODES, LABELS: LABELS };
  }
})();
