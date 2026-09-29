# CAMERA TRANSFORM GROUND TRUTH（鏡頭轉換真值）

> 來源：公開原始碼逐行轉錄，未改數學。AGPL 參考，只讀學習。

## Source
- `vendor/kodiak-ref/client/src/renderer2d/camera_2d.rs`：`Camera2d`、
  `View::new`、`to_view_position`、`to_client_position`。
- `vendor/kodiak-ref/client/src/renderer/renderer.rs:681`：`viewport_to_aspect`。
- `vendor/kodiak-ref/client/src/io/pan_zoom.rs`：`PanZoom::{get_center,
  get_zoom, get_zooms, pan, multiply_zoom}`。
- `vendor/kiomet-ref/client/src/game.rs:947-960`：每幀 `camera.update(center,
  zoom, canvas_size)`；`1156`：`to_client_position` 定義。

## Exact formula
```
aspect   = viewport.x / viewport.y                      # viewport: UVec2
view     = ((world - center) * (1, aspect)) / zoom      # View::new 矩陣等價
zero_to_one = (view + 1.0) * (0.5 / device_pixel_ratio)
client   = zero_to_one * viewport_px
```
其中 `viewport`（Camera2d.viewport）來自 `renderer.canvas_size()`；
`center`/`zoom` 來自 `pan_zoom.get_center()`/`get_zoom()`。

## Required runtime parameters（缺一不可）
| 參數 | 來源 | 取得方式 |
|---|---|---|
| camera center x/y | WASM Runtime | 待逆（PanZoom 或 Camera2d center） |
| zoom | WASM Runtime | 待逆 |
| viewport w/h | JS | canvas_size 語意待確認（見下） |
| devicePixelRatio | JS | `window.devicePixelRatio` 直接讀 |
| canvas rect | JS | `getBoundingClientRect` 直接讀 |

## 2026-09-27 視覺核驗：頁面座標需翻轉 y

目前 viewport 1264×805、DPR 1、canvas rect (0,0,1264,805)。
`to_client_position` 公式的 y 從畫面**底部**起算，Playwright 點選的 y 從**頂部**起算。
因此 `page_y = canvas_top + canvas_height - client_y`，x 則加 `canvas_left`。
同局五個塔中心在翻轉前偏移 35–453 px；翻轉後與畫面塔中心相差約 0–1 px。
`tools/camera_transform.py` 保留原公式，新增 `world_to_page` 供頁面操作使用。
跨 DPR 或非滿版 canvas 尚需獨立驗證。

## PanZoom 補充
- `get_zooms() = (zoom, zoom / aspect)`；`pan(delta)` 做 `center -= delta`；
  `multiply_zoom` 繞 origin 縮放；`clamp_center` 限制範圍。
- tight_viewport 由 center±zooms 推導（SetViewport 交叉驗證可用，但精度只到 chunk）。
