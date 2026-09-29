# GPT ROUND 3 HARD-PROBLEM REPORT（第三輪高難題報告）

## P0 MOVING FORCE（移動部隊）

| 項目 | 結論 |
|---|---|
| Force Creation（部隊建立） | **PASS（通過）**：`1791 Tower::deploy_force`（塔派兵）→ `1963 Tower::send_force`（送出部隊）→ `2023` 出站事件／入站事件 → `1393` 插入 |
| 2031 → Force Units Copy（兵力複製） | **PASS**：`2031` 的 7 位元組結果 `sp+17..23`，在 `1791/0x10047B、0x100482` 複製至 Force `+14..+20` |
| Force Base（部隊起點） | **PASS**：建立時 `sp+24`，正式結構長 24 位元組 |
| Units Offset（兵力位移） | **PASS**：`Force+14..+20`，7 位元組**內嵌**，不是指標 |
| Collection（集合） | **PASS（靜態）**：每塔 `+0` 入站、`+12` 出站；兩個 `Vec<Force>`（部隊陣列）各 12 位元組；容量 `+0`、指標 `+4`、長度 `+8`；項目步長 24。`1539`、`1393`、`3241`、`448`、`1242` 互證 |
| Collection Root（集合根） | **PARTIAL（部分完成）**：從現有當局 `tower_ref`（塔位址）可直接取得；固定世界根鏈未證明，跨局絕對位址不可沿用 |
| Entry Representation（項目表示） | **PASS**：24 位元組 Force；欄位及證據見 `GPT_FORCE_STRUCT_CANDIDATES.json` |
| Owner（擁有者） | **PASS（位移）**：`Force+12` 2 位元組可空玩家編號；None（空值）編碼待實測 |
| Source（來源塔） | **PASS**：從倒序路徑最後一格導出；不單獨存於 Force |
| Target（目的塔） | **PASS**：當前目標為倒數第二格；最終目標為第一格；不單獨存於 Force |
| Path（路徑） | **PASS**：`Force+0..+11` 保存完整路徑陣列；每格 4 位元組塔編號，按倒序排列 |
| Progress（進度） | **PASS**：`Force+22` 為 1 位元組當前路段進度；`1845` 每節拍按速度增加，到段末縮短路徑 |
| World Position（世界座標） | **PASS（推導公式）**：`1861` 按來源塔與目的塔座標、進度、速度和所需進度內插；Force 無座標欄位 |
| ETA（預估抵達時間） | **PARTIAL**：可估單段 `ceil((required-progress)/speed)` 節拍，4 節拍／秒；戰鬥、續行及節拍內時間會變動 |
| Lifecycle（生命週期） | **PASS（主要路徑）**：建立事件、兩側鏡像插入、`448` 遍歷／更新／壓縮、抵達移除、戰鬥／合併／續行；戰鬥內部細節未完全拆解 |
| Render Path（渲染路徑） | **PASS**：`1242` 遍歷塔 `+0`／`+12` 的 24 位元組項目，`563→1861` 算座標並繪圖；出站受外部可見性判斷 |
| Arrival（抵達） | **PASS**：`1845` 比較 `+22` 與 `2689` 所需進度，彈出目前路徑末格；`448` 處理進站；`6128` 管理出站到達移除 |
| Battle Entry（戰鬥入口） | **PARTIAL**：來源及正式版 `448` 顯示進站後進入戰鬥分支；確切 `Combatants::fight`（交戰計算）內部函式對應未完成 |
| Observer Read Path（觀察器讀路） | **PASS（靜態配方）**：當局 `tower_ref` → 塔 `+0/+12` 陣列 → `pointer+24*i`；完整守衛與驗證方案見 `GPT_FORCE_OBSERVER_RECIPE.md` |

**STATIC_LAYOUT（靜態布局）: PASS（通過）**，限於 24 位元組欄位、塔集合與主要生命週期。特殊旗標名稱、可空玩家編號的空值編碼、世界根指標與戰鬥內部函式仍是 PARTIAL（部分完成）。

**RUNTIME_VALIDATION（執行期驗證）: NOT AVAILABLE（不可用）**；本輪依指示完全離線。Muse 的精確下一步：在既有唯讀通道上取至少 3 支自然出現的畫面部隊，對照路徑目前兩端、兵力、擁有者、位置，並跨兩個節拍檢查進度與抵達；另驗空集合。不得為此新增行動或附加偵錯器。

## P1 UPGRADE ROOT（升級根路徑）

Started（已開始）：**YES（是）**。`elem[438]→1242` 是間接回呼，`1242` 的第一參數為 callback root（回呼根）；`root+592` 起是 27×`u16`（16 位元無號整數），根也透過閉包 `+4` 交給 `3492→2425`。Callback Root Provenance（回呼根來源）：**PARTIAL（部分完成）**，因產生或持有首次傳入參數的物件仍未知。Stable Observer Path（穩定觀察器路徑）：**UNKNOWN（未知）**，未證明現有 `tower_ref` 可導到該根。Status（狀態）：**PARTIAL（部分完成）**；詳細證據及限制見 `GPT_UPGRADE_ROOT_ACCESS.md`／`GPT_UPGRADE_ROOT_PATH.json`。

## P2 BATTLE ENTRY（戰鬥入口）

Started（已開始）：**NO（否）**；Function（函式）：入口候選 `448`，未逐層對映；Status（狀態）：**NOT STARTED（未開始）**。

## 安全與檔案狀態

本輪 Runtime connections（執行期連線）=0、Chromium connections（瀏覽器連線）=0、sent_actions（送出行動）=0、MOVE_FORCE（移動部隊行動）=0、Upgrade Actions（升級行動）=0、Git commits（提交）=0。本工作流只新增 `runtime/research/gpt_concurrent/` 下的研究產物與靜態反組譯檔；正式追蹤檔修改=0。若儲存庫同時出現其他工作流改動，不能歸因於本輪。
