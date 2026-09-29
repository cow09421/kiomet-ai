# Kiomet AI 現況

更新：2026-09-27 交接收尾。先讀 `docs/GPT_HARD_PROBLEM_HANDOFF.md`。

## 平台（本輪最後狀態）
- 第五次同型渲染崩潰後已安全重啟；最後檢查為 `RUNNING`、專用瀏覽器已連線、`IN_MATCH`（`m1-1790487672`）、觀戰持續更新、音訊 `MUTED`、錯誤 0、已送行動 0。這些是取樣當刻狀態，下次使用前仍須重查。
- 五次渲染崩潰特徵一致，但上游原因尚未確認；另有一次重啟階段的 GPU 權限故障，已以一般主機權限啟動恢復。詳見 `docs/RENDER_CRASH_FORENSICS.md`。
- 本輪取得 `tower_ref +38..+44` 兵力解碼：10 座塔 × 3 時點，介面數字 30/30 對上；詳見 `docs/UNITS_DECODE_CURRENT.md`。

## 結論

- `WORLD_TO_SCREEN = PASS`：m3 同局五座己方塔以原始畫面與選取圈核對，5/5；m4 新局四座可見己方塔再次核對，4/4。
- `SELF confidence = HIGH`：m3 的 5/5、m4 的 4/4 均為畫面可見的藍色己方塔。
- `Neighbor Visual Validation = PASS`：m3 與 m4 各自抽查 12 條圖上相鄰邊，兩端與可見道路逐條核對，兩局皆 12/12。
- `Final Dry Run = PASS`：在同一有效對局，來源與目標均為己方、相鄰、有可見道路；鏡頭與視窗未變，行動數前後皆為 0。
- `READY_FOR_FIRST_UI_MOVE = YES`：僅表示已通過首次 UI 路徑的準備門檻。**真正 MOVE_FORCE 仍為 0；必須等使用者明確說出 `EXECUTE`。** 屆時須重新確認目前對局、鏡頭、所有權及畫面座標，不可沿用已過期數值。

## 可核對的證據

- m4 塔與相鄰邊資料：原驗證圖及逐項記錄仍在 `runtime/research/source-map/human-verification/`；**`verified-anchor-current.json` 已由本輪新對局覆寫，不再是 m4**。新檔是 `m1-1790487672`，26 塔、4 座 SELF、32 條無向邊。不可用它重建舊局 m4 的畫面座標。
- m4 塔選取圖：`runtime/research/source-map/human-verification/tower_1_before.png` 至 `tower_4_selected.png`，及 `verification.json`。
- m4 道路圖：同資料夾 `neighbor_01.png` 至 `neighbor_12.png`，逐邊記錄在 `neighbor-verification.json`。
- m4 最終只讀演練：同資料夾 `final-dry-run.png`、`final-dry-run.json`。
- m3 的五塔及十二條道路證據保留在 `runtime/research/source-map/human-verification/m3-1790482935/`。
- m4 演練路徑：來源塔 `14418149`，世界 `(1147,1104)`，畫面約 `(615,524)`；目標塔 `14483685`，世界 `(1148,1108)`，畫面約 `(650,385)`。兩端都是 SELF，圖與畫面都證實直接相鄰。

## 鏡頭修正

遊戲公式的 y 從畫面底部起算，頁面點選的 y 從頂部起算；換算為 `page_y = canvas_top + canvas_height - client_y`。先前只加上畫布偏移，會讓 x 正確但 y 上下顛倒。現已修正 `tools/camera_transform.py`，並以五個實際塔中心加入測試。此輪只驗證 1264×805、DPR 1、滿版畫布；其他顯示條件需重新驗證。

## 平台與限制

- 專用 Chromium 位於 **Win32 Desktop Object（Windows 桌面物件）**，不是一般 Windows Virtual Desktop（Windows 虛擬桌面）。觀戰由專用頁面擷取，未切換使用者前景。
- 最終演練時平台 `RUNNING`、`live`、`IN_MATCH`、音訊 `MUTED`，錯誤 0；使用者桌面視窗數 0，已送行動數 0。
- 觀戰約每秒一張，最新畫面保存在記憶體；沒有連續截圖檔累積。研究截圖是有限的證據檔。
- 目前未接入真正的戰術規劃或持續觀察器；`plan_count` 與 `sent_actions` 為 0。

## 執行界線

使用者已選定 Option B（介面事件路徑）。在明確 `EXECUTE` 前，禁止真實拖曳或派兵；不得改走 WASM 直接呼叫、封包注入或記憶體修改。研究程式僅讀取鏡頭、點選塔以驗證選取圈、擷取專用 Chromium 畫面，最終演練不執行任何遊戲操作。
