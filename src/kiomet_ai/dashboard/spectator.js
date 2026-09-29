/* 誠實觀戰前端模組（P0）— 獨立檔，尚未掛進 index.html（GPT 施工中）。
 *
 * 原則：
 * - 絕不以 CSS 平移截圖冒充遊戲攝影機。
 * - 真攝影機可用時才呼叫 /api/spectator/*；不可用時誠實標示。
 * - 圖片縮放（IMAGE ZOOM ONLY）僅在 layer=IMAGE_ONLY 時允許，且必定標示。
 */
(function () {
  "use strict";
  const LABELS = {
    REAL_CAMERA: "REAL CAMERA（真實遊戲攝影機）",
    IMAGE_ONLY: "IMAGE ONLY（僅圖片縮放，非遊戲攝影機）",
    SPECTATOR_UNAVAILABLE: "SPECTATOR UNAVAILABLE（無法同局觀戰）",
    IMAGE_ZOOM_ONLY: "IMAGE ZOOM ONLY（僅圖片縮放）",
  };

  function layerLabel(st) {
    if (st && st.available) return LABELS.REAL_CAMERA;
    if (st && st.availability === "BLOCKED") return LABELS.SPECTATOR_UNAVAILABLE;
    return LABELS.IMAGE_ONLY;
  }

  function create(opts) {
    opts = opts || {};
    const token = opts.token || "";
    const status = { available: false, availability: "UNKNOWN", layer: "IMAGE_ONLY" };

    function setLabel(text) {
      if (opts.labelEl) opts.labelEl.textContent = text;
    }

    async function api(path, body) {
      const headers = { "X-Control-Token": token };
      if (body) headers["Content-Type"] = "application/json";
      const res = await fetch(path, {
        method: body ? "POST" : "GET",
        headers: headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      return res.json();
    }

    async function refresh() {
      const st = await api("/api/spectator/status");
      Object.assign(status, st || {});
      setLabel(layerLabel(st) + (st && st.reason ? " · " + st.reason : ""));
      return status;
    }

    async function pan(dx, dy) {
      if (!status.available) {
        setLabel(layerLabel(status));
        return { ok: false, code: "SPECTATOR_UNAVAILABLE", applied: false };
      }
      const r = await api("/api/spectator/pan", { dx: dx, dy: dy });
      if (r && r.ok && opts.onFrame) opts.onFrame();
      return r;
    }

    async function zoom(delta) {
      if (!status.available) {
        setLabel(layerLabel(status));
        return { ok: false, code: "SPECTATOR_UNAVAILABLE", applied: false };
      }
      const r = await api("/api/spectator/zoom", { delta: delta });
      if (r && r.ok && opts.onFrame) opts.onFrame();
      return r;
    }

    async function focus(worldX, worldY) {
      const r = await api("/api/spectator/focus",
        { world_x: worldX, world_y: worldY });
      if (r && r.ok && opts.onFrame) opts.onFrame();
      return r;
    }

    async function follow(mode) {
      return api("/api/spectator/follow", { mode: mode });
    }

    function imageZoom(factor) {
      if (status.layer !== "IMAGE_ONLY") return false;
      if (opts.img) {
        opts.img.style.transform = "scale(" + (factor || 1) + ")";
      }
      setLabel(LABELS.IMAGE_ONLY + " · " + LABELS.IMAGE_ZOOM_ONLY);
      return true;
    }

    return {
      refresh: refresh, pan: pan, zoom: zoom, focus: focus,
      follow: follow, imageZoom: imageZoom, status: status, LABELS: LABELS,
    };
  }

  if (typeof window !== "undefined") {
    window.KiometSpectator = { create: create, LABELS: LABELS,
                               layerLabel: layerLabel };
  }
})();
