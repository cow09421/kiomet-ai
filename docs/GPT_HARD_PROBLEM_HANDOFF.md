# GPT → Muse 高難題交接

LAST UPDATED（最後更新）：2026-09-27（臺灣時間）  
AUTHOR（作者）：GPT  
HIGH-REASONING SPRINT STATUS（高推理衝刺狀態）：HANDOFF（交接）  
SENT ACTIONS（已送行動）：**0**  
MOVE_FORCE VERIFIED SUCCESS（已驗證派兵成功）：**0**  
EXECUTE AUTHORIZATION（執行授權）：**NO（無）**

**先讀 `docs/UNITS_DECODE_CURRENT.md` 與 `docs/RENDER_CRASH_FORENSICS.md`，再讀本文件後續。不要從舊 Muse 狀態回退已完成的視覺驗證。**

## HIGHEST BREAKTHROUGH（最高價值突破）

`tower_ref +38..+44` 是正式遊戲塔的 7 位元組兵力結構：`+38` 標籤，`+39..+43` 五種 Many（多種類）兵力，`+44` Shield（護盾）。官方塔資訊框與同塔記憶體即時配對，在 `m1-1790487672` 的 **10 座塔 × 3 時點 = 30/30 筆**目前數量吻合。`Units::available` 的正式版函式 **1637**（偏移 `0xF9200`）反組譯也符合此配置。**UNITS STATUS（兵力狀態）= PASS（目前數量通過）**。容量與可派出量另算，Single（單一種類）特殊兵種尚需獨立介面例子。詳見專用文件與 `runtime/research/units/units_ground_truth.json`。

## STATE RECONCILIATION（真實狀態校正）

- `WORLD_TO_SCREEN = PASS`；頁面 y 座標公式 `page_y = canvas_top + canvas_height - client_y`。離線換算 20/20 通過。
- `SELF = HIGH`：m3 視覺 5/5；m4 視覺 4/4。道路視覺 m3 12/12、m4 12/12；最終只讀演練 PASS。
- `READY_FOR_FIRST_UI_MOVE = YES` 僅是流程資格；使用者本輪**沒有**說 `EXECUTE`。真實 `MOVE_FORCE=0`，`sent_actions=0`，不得派兵、拖曳、直接呼叫 WASM（網頁組件）函式、注入封包或記憶體。
- 舊 Muse 文件若寫 WORLD_TO_SCREEN（世界到畫面座標）PARTIAL（部分）、SELF（己方）MEDIUM（中）、道路 0/10 或 READY（準備）NO（否），以 `docs/STATE_RECONCILIATION.md` 和原始圖像證據為準。`verified-anchor-current.json` 已是本輪新對局，**不是舊 m4**。

## RENDER CRASH（渲染崩潰）

- **DUMPS（傾印）=5；SIGNATURE（特徵）=SAME（相同）。** 五次皆渲染程序讀取存取違規 `0xC0000005`，`chrome.dll+0x710E1A7`（本機絕對位址 `0x00007FF8AD45E1A7`），讀取每次不同基址之 64 KiB 保留不可讀區域起點。前 18 個程式碼堆疊偏移相同。
- **MEMORY-PRESSURE HYPOTHESIS（記憶體壓力假說）=DOWNRANKED（降低優先）**。第五次故障前渲染 RSS（常駐記憶體）276.2 MiB、JS 堆 40.4 MB、WASM 記憶體 3.21 MB；第四次最後總 RSS 約 1655 MiB，無單調逼近峰值證據。局部洩漏仍不能完全排除。
- **UPSTREAM ROOT CAUSE（上游根因）=UNKNOWN（未知）；分類為 NARROWED BUT UNCONFIRMED（範圍縮小但未確認）。** `Page.screenshot: Target crashed` 是偵測點，不可當成因果。第五次有研究斷點活動；第四次 Muse 報告無活動，故斷點不是共同必要條件。
- **NEXT CRASH EXPERIMENT（唯一下一步）**：保持隔離桌面、版本、靜音、遊戲流程一致，對照週期性頁面截圖開啟 1 FPS（每秒畫面數）與關閉，各 60 分鐘；兩組均不附著研究偵錯器，每 20 秒記錄資源與頁面崩潰事件。若只一組崩潰須重複確認。**不要再從頭逆五份傾印。** 完整逐份索引在 `docs/RENDER_CRASH_FORENSICS.md`。

## GPU STARTUP ISSUE（圖形處理器啟動問題）

受限執行環境啟動專用 Chromium（瀏覽器）時，GPU 子程序以 `0xC0000022`（存取被拒）反覆退出，瀏覽器主程序另留下三份 `0x80000003` 傾印。**這和五次對局中渲染讀取違規不是同一故障。** 改用一般主機權限啟動，仍保留 Win32 Desktop Object（Windows 桌面物件）及隱藏視窗，已恢復正常；啟動前後使用者前景程序與游標相同。啟動記錄位於 `runtime/logs/chromium-startup.log`。

## UNITS DECODE（兵力解碼）

- **BEST RUNTIME CANDIDATE（最佳執行期欄位）已提升為已驗證：** `tower_ref +38..+44`，各 1 byte（位元組）、unsigned（無號）。`+38` 為 `UnitsEither` 標籤：0=Many（五兵種），1=Single（單一兵種）；`+39..+43` 依序 Fighter（戰鬥機）、Chopper（直升機）、Bomber（轟炸機）、Tank（坦克）、Soldier（士兵）；`+44` 為 Shield（護盾）。標籤 1 時 `+39` 是數量、`+40` 是單一兵種列舉編號。
- **UI GROUND TRUTH（介面真值）：** `current/capacity`（目前數量／容量），例如 `15/15、4/4、4/4、0/2、0/1`；`20/20、12/12` 的當前數量分別對上 `+44=20、+43=12`。此結構存 current（目前數量），**不是 capacity（容量）**。`force_units()` 還會過濾不能移動的單位，不能把全部目前數量直接當可派兵量。
- **VALIDATED TOWERS（已驗證塔數）=10；TIMEPOINTS（時點）=每塔 3；UI MATCH（介面吻合）=30/30；CONFIDENCE（信心）=HIGH（高，限 Shield + Many 的目前數量）。** 正式版函式號碼 `Units::available=1637`、`Tower::force_units=2031`；來源與本機編譯版號碼見 `docs/UNITS_DECODE_CURRENT.md`。
- 原始有限樣本 `runtime/research/units/units_ground_truth.json`；解碼報告 `decoded-units-m1-1790487672.json`；原始塔周邊位元組 `unit-struct-probe-m1-1790487672.json`。工具 `tools/unit_ui_samples.py`、`tools/unit_struct_probe.py`、`tools/decode_units.py`。只讀，沒有派兵。
- **NEXT EXACT EXPERIMENT（下一步精確實驗）：** Muse 把此解碼放進持續觀察器，換局與重啟後重新取得塔參照，標記每筆資料新鮮度；找一個有介面數字的自然 Single（單一兵種）例子，並從塔類型規則另行求容量。不要重做全記憶體 `u8/u16`（8／16 位元無號整數）盲掃或先前三次慢槽差分。

## OWNER / TYPE / UPGRADE / FORCE（所有權／塔種類／升級／移動軍隊）

依最新交接指示，本輪**不再開新研究**。兵力聯合驗證時附帶記錄到顏色值 `0=SELF`、`1=NEUTRAL`、`3=OTHER`，本場 26 座可見塔分布為己方 4、中立 15、其他玩家 7；與公開 `client/src/color.rs` 的列舉和當前畫面藍／灰／紅相符。顏色 2 的盟友尚無本場樣本。這是附帶證據，**未工程化持續分類器**。塔種類、升級狀態、移動軍隊均留下一棒，禁止把未知值寫成 0。

## CURRENT PLATFORM HEALTH（當前平台健康）

最後取樣：程序 PID 27440 活著，平台 `RUNNING`，專用瀏覽器連線，隔離桌面啟用，`IN_MATCH` `m1-1790487672`，觀戰持續更新且無錯誤，音訊 `MUTED`，平台錯誤 0、`sent_actions=0`。啟動前後使用者前景 PID 均 40088，游標均 `(1381,690)`；之前使用者回報在其他程式打字、移滑鼠正常。沒有獨立持續的焦點違規計數，不能以啟動快照證明整段時間零干擾。研究腳本已結束並執行偵錯停用與會話脫離；目前全域活動斷點數 **UNKNOWN（未知）**，沒有再附著偵錯器去測。平台狀態是時間點快照，下一棒開始須重新讀取。

## TOOLS / FIXTURES / TESTS（工具／樣本／測試）

- 傾印解析 `tools/analyze_crash_dumps.py`；短連線只讀 CDP（開發者工具協定）`tools/cdp_probe.py`；低成本資源遙測 `tools/resource_telemetry.py`，資料在 `runtime/research/crash/resource-telemetry.jsonl`。不可量測的會話、偵錯及產物佇列欄位為 `null`，不是 0。
- 正式來源 `vendor/kiomet-ref/`（僅研究引用）；函式清單 `runtime/research/source-map/local-functions.json` 與 `production-functions.json`；正式 WASM 雜湊在兵力專用文件。
- `python tools/decode_units.py runtime/research/units/units_ground_truth.json`：30/30 配對；`python -m pytest -q`：**55 passed（55 項通過）**，有 1 則既有快取目錄存取權警告，未影響測試。
- `tools/unit_consumer_probe.py` 是**未執行的實驗性斷點腳本**；近期渲染崩潰仍未解，不要在長跑期間執行。

## FAILED APPROACHES / HARD BLOCKER（失敗方法／目前阻礙）

全記憶體兵力盲差分三輪未找到可靠欄位，已由局部塔結構解碼取代。崩潰直接故障位置已定，上游觸發未定，影響長跑可靠性；須以單一 A/B（對照）實驗區分週期性截圖是否必要觸發。重啟後塔參照與鏡頭位址會變，舊 `match_id`、塔指標和畫面座標一律失效。

## MUSE NEXT 3 TASKS（Muse 後續三項任務）

1. 把已驗證兵力結構加入只讀觀察器：換局重新取塔參照，輸出目前數量與新鮮度，並保存一個自然 Single（單一兵種）樣本；不要重新盲掃。
2. 加入 `RealTowerState.units`（真實塔狀態兵力）資料契約與 `UNKNOWN`（未知）處理，容量及可派兵量分開驗證；同時按上方唯一 A/B（對照）方案安排兩組各 60 分鐘渲染穩定性測試。
3. 兵力穩定後依序工程化所有權分類、塔種類、升級狀態、自然移動軍隊；不做首次派兵，除非使用者之後明確授權 `EXECUTE`（執行）。

## GIT STATUS（版本控制狀態）

交接前基底提交為 `7d05c27`。本輪測試已通過；最新交接提交與工作樹狀態見最終回覆。研究原始資料與 Crashpad（崩潰傾印）保留在專案 `runtime/` 下；其中多數為忽略的本機資料，**不能因工作樹看似乾淨就刪除**。
