# 觀戰攝影機技術阻塞報告（REAL SPECTATOR CAMERA）

日期：2026-09-29
狀態：**SPECTATOR_SAME_MATCH = BLOCKED / REAL CAMERA = UNAVAILABLE**

## 問題

LIVE VIEW（即時觀戰）的 Pan／Zoom 目前只是對單張 game frame（遊戲截圖）
做 CSS transform（畫面轉換），拖曳後只把截圖移離原位，並非真正的
Kiomet camera movement（遊戲攝影機移動）。目標是改用獨立觀戰頁
（SPECTATOR_PAGE）真正移動遊戲 renderer（渲染器）的相機。

## 探測方法（唯讀，未送任何遊戲命令、未以第二玩家加入）

以 CDP（Chrome 開發者工具協定）唯讀讀取專用 Chromium 的 Kiomet 頁面：

- CDP `Runtime.evaluate`（唯讀表達式）：`location.href/search/hash`、
  `Object.keys(window)`、`document.querySelector('canvas')`、按鈕文字。
- 無點擊、無指標事件、無 `MoveForce`/`Upgrade`/`Deploy`。

## 證據

| 項目 | 觀測值 | 意涵 |
|---|---|---|
| 頁面位址 | `https://kiomet.com/` | 無 match-id 片段 |
| `location.hash` | `""` | 無 `#match=...` |
| `location.search` | `""` | 無 `?match_id=...` |
| 觀戰／join 全域 | 無（僅 `matchMedia`、音訊標記、廣告 SDK） | 無 `spectate`/`replay`/`watch`/`joinMatch` |
| 畫布 | 單一 `#canvas`（1264×805） | 遊戲渲染器 |
| 進局按鈕 | `#play_button`（文字 `Play Again`） | 進局＝伺服器配對，非指定對局 |
| 傳輸 | WebSocket 連線存在 | 對局由伺服器配對 |

`tools/spectator_feasibility.py` 的唯讀判定器在無機制時回
`same_match=BLOCKED`、`real_camera=UNAVAILABLE`，且**永不自動標
`VERIFIED`**（有 `join-by-id` 也只回 `UNKNOWN`，需第二頁實測）。

後續一次對執行期瀏覽器的 CDP 連線被拒（`WinError 10061`，平台當時未運行）；
此為環境狀態，已誠實記錄，不以靜態推測冒充實測。

## 結論

Kiomet 官方客戶端**沒有暴露**「以 match-id 加入同一對局」或「觀戰」的
客戶端能力；對局由伺服器即時配對。因此：

- **無法建立真正同局的 SPECTATOR_PAGE**：第二頁會是另一個玩家／另一場
  對局，不能保證與 AI_PAGE 同 match。
- 若以第二頁點 `Play` 強行加入，可能新增玩家／影響配對，且無法保證同局
  → 不採用（不得偽造成功）。
- 使用 AI_PAGE 當自由攝影機則會改動 AI 相機／座標映射 → 明確禁止。

### 對兩個關鍵問題的直接回答

- **Q1：拖到原 screenshot 外面，現在是否真的能看到新的 Kiomet 世界區域？**
  **NO**。真實同局觀戰頁不可得；真攝影機標記為 `SPECTATOR_UNAVAILABLE`。
  已移除「以 CSS 平移冒充真攝影機」的語意（前端契約禁止）。
- **Q2：使用者改變觀戰 camera，AI 的 camera / coordinate mapping 是否完全不變？**
  **YES**。隔離測試證明觀戰操作只改觀戰狀態，AI 相機／世界座標映射／
  行動計數完全不變。

因未達 Q1=YES 且 Q2=YES，**本任務不宣稱完成**，改以誠實降級交付。

## 誠實降級架構（依 §18）

| 視圖 | 內容 | 標示 | 可操作 |
|---|---|---|---|
| GAME FRAME | AI 目前真實看到的畫面 | `IMAGE ONLY` | 僅圖片縮放（`IMAGE ZOOM ONLY`），禁拖曳平移 |
| TACTICAL WORLD | 已知世界全局 | 自由 | Pan／Zoom／Fit／Follow（世界圖，非遊戲相機） |
| 真攝影機 | 不可得 | `SPECTATOR UNAVAILABLE` | 無 |

## 若未來官方新增能力

`tools/spectator_feasibility.py` 會偵測到 `join-by-id`／`spectate` 機制
並回報 `UNKNOWN`（而非 VERIFIED），提示需以第二頁實測同局；
`src/kiomet_ai/spectator.py` 只需接上真正的 camera driver 與
`note_same_match("VERIFIED", id)` 即可啟用真攝影機。

## 已交付（本輪）

- `src/kiomet_ai/spectator.py`：誠實觀戰相機服務（與 AI 隔離）。
- `src/kiomet_ai/spectator_api.py` + `dashboard/__init__.py`：觀戰 API 契約與路由。
- `src/kiomet_ai/dashboard/spectator.js`：獨立誠實前端模組（無假平移）。
- `tests/test_spectator_*.py`：50 個測試（服務／隔離／API／UI 契約／可行性）。
- `tools/spectator_feasibility.py`：唯讀可行性判定器。
