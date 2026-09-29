# Muse 接棒起始指令

你現在接手 `E:\SteamLibrary\kiomet` 的 Kiomet AI（Kiomet 人工智慧玩家）專案。全程使用繁體中文；英文專業術語後立即附上繁體中文說明。所有程式、文件、截圖及暫存資料只留在這個專案根目錄內。

開始前依序讀：

1. `docs/GPT_HARD_PROBLEM_HANDOFF.md`
2. `docs/UNITS_DECODE_CURRENT.md`
3. `docs/RENDER_CRASH_FORENSICS.md`
4. `docs/CURRENT_STATE.md`

然後執行 `git status` 並讀取當前平台健康狀態。前一棒已把 `tower_ref +38..+44` 的目前兵力解碼驗證至 10 座塔 × 3 時點、30/30 官方介面數字吻合；第一任務是把它工程化為只讀、每局重新錨定且有新鮮度的觀察資料。容量、可派兵量、Single（單一兵種）仍需分開處理。研究原始資料位於 `runtime/research/units/`，有限機器可讀樣本是 `units_ground_truth.json`，解碼工具是 `tools/decode_units.py`。

五份對局中渲染崩潰傾印有完全相同的 `chrome.dll+0x710E1A7` 讀取違規特徵，但上游根因未確認。另一組三份瀏覽器啟動傾印是 GPU（圖形處理器）存取被拒，兩個故障必須分開。按 `docs/RENDER_CRASH_FORENSICS.md` 中**唯一**的觀戰截圖開／關 A/B（對照）長時間實驗推進，不要再從頭解析同一批傾印。

保留先前直接視覺證據：世界到畫面座標 PASS（通過）、己方塔 m3 5/5 與 m4 4/4、道路兩局各 12/12、最終只讀演練 PASS（通過）。`READY_FOR_FIRST_UI_MOVE = YES` 僅表示資格；使用者本輪沒有說 `EXECUTE`（執行），真實派兵和已送行動仍為 0。不得執行拖曳派兵、直接呼叫 WASM（網頁組件）遊戲函式、封包／記憶體注入或系統級鍵鼠。

不要重推鏡頭、重做塔錨點與道路人工驗證、重做己方塔目檢、重做全記憶體兵力盲掃、從頭逆渲染崩潰傾印，或改走直接送指令方案。平台重啟後只做新局必要的安全重新錨定；舊 `match_id`、塔指標、鏡頭與畫面座標全部作廢。
