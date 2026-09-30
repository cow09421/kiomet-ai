# Kiomet v2 — first construction session, 2026-09-30

CURRENT MILESTONE: M0 / M1

STATUS: PARTIAL（部分完成）；M1 未通過。

## 第二施工階段／長任務進度

`55ee71e` 已依使用者新指令推送到 `origin/v2-rebuild`；main 未動。
已接入正式 WASM 的 OBSERVED world_sequence（世界序號），並以正常更新、
可見兵力生產變化、結果畫面、短暫斷線／重連驗證。它在結果畫面仍更新，
因此不能作為對局 ID，也不能換算成時間戳。精確 source_updated_at 與
snapshot age p95 仍 UNKNOWN。

新增 DERIVED 更新時間區間，對來源年齡提供上下界；不把讀取時間冒充更新時間。
5 Hz 初測的保守來源年齡上界 p95 為 400–416 ms，尚未達 250 ms Gate。
已補官方 active／visibility-dirty／expanded-visibility 拒絕條件。
對局身分加入文件／玩家／官方加入與結果邊界的推導；完整真實切局、重載
驗證仍在進行，沒有提前宣稱通過。詳見 `V2_M1_TICK_EVIDENCE.md`。
本階段 v2 契約與生命週期測試 12 項通過；沒有處理 v1 測試失敗。

## 本輪完成

- 在原工作目錄恢復遺失的 Git 歷史；建立 `v2-rebuild`，基底與判決的
  `234cfad` 相符。未修改 v1 控制器、未推送 main。
- 寫下 v2 Observation Contract（觀察契約），明確替代 v1 的結構化讀取禁令。
- 新增不可變 Canonical GameState（標準化遊戲狀態），區分 OBSERVED（觀察）、
  DERIVED（推導）、UNKNOWN（未知）；未知集合不冒充空集合。
- 新增正式客戶端 SHA-256 鎖定的唯讀 State Extractor（狀態擷取器）。
  每次先檢查當下可見表，再讀塔；只輸出兩端已觀察的道路。
- 主動拒絕結果／選單畫面的資料；重啟後自動找資料根，不重用前局指標。
  這項根定位仍是 RESEARCH CANDIDATE（研究候選），不是已驗收來源。
- 分開瀏覽器與主機時鐘；絕不把記憶體輪詢時刻當成遊戲更新時刻。

## 實際證據與量化結果

正式官方客戶端 WASM 雜湊：
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`。

| 實驗 | 實際結果 | 限制 |
|---|---|---|
| 首次根定位 | 單次研究斷點定位後解除 | 不計入正常觀察樣本 |
| 結果畫面 30 秒輪詢 | 150 筆、約 4.98 Hz | 已排除；加入 active-match（對局中）門控 |
| 第二局 60 秒 | 299 筆、38 塔、約 4.97 Hz；1 次時鐘誤判 | 已修正時鐘分域 |
| 第二局修正後 15 秒 | 75 筆、約 4.96 Hz；擷取延遲 p95 約 9.12 ms；0 錯誤 | 更新年齡仍 UNKNOWN |
| 第二局官方資訊框 | 6 座塔點選 ID 全對；8 個 Many（多兵種）兵力欄位 8/8 一致 | 己方／中立；Single（單兵種）及敵方尚未覆蓋 |
| 全新瀏覽器文件／第三局 | 自動定位新根；玩家 51 → 55；根位址也改變 | 無手動重新錨定、無斷點 |
| 第三局塔圖與輪詢 | 29 塔、37 條可見無向道路；30 秒 150 筆、約 4.99 Hz；p95 約 9.54 ms；0 錯誤 | 道路反向一致；尚未獨立 UI 全量核對 |

上述延遲是 extraction latency（擷取延遲），**不是 snapshot update age（快照更新年齡）**。
不是三段各十分鐘，也不是一千個獨立 UI 核對樣本。不得宣稱 M1 PASS。
沒有派兵、拖曳、升級；只有官方 Play／Play Again 與資訊框點選。

真實原始記錄在忽略版控的 `runtime/research/v2/`；包含版本、最後一段
`snapshots*.jsonl`、`sampling*.json`、有限 `ui-comparison.json`。
沒有複製完整遊戲記憶體；解碼輸出僅含通過當下可見集合的塔。

## 驗證與已知限制

v2 契約測試通過。全專案測試在修正暫存路徑後：9 項失敗，無 setup errors
（測試準備錯誤）。7 項失敗是封存版本缺少未追蹤的研究 fixture（樣本）；
2 項是未修改 v1 的既有 reason taxonomy（原因分類）期望不一致。
完整診斷：`runtime/logs/v2-test-suite.log`。本輪不以修改封存架構來湊全綠。

## 真正剩餘 blocker（阻塞問題）

1. 尚未定位、驗證 authoritative update time / tick（權威更新時間／節拍）。
2. match lifecycle（對局生命週期）仍不能被獨立確認；標準狀態的 match_id 保留 UNKNOWN。
3. moving forces（移動部隊）與穩定身分、敵盟關係、Single 兵力尚未接入。
4. deployable / capacity / production（可派兵量／容量／生產）、國王與升級資源等
   決策必要欄位仍有 UNKNOWN。核心拒絕將這種局面標成可決策。
5. 可見性契約有正式來源對照，仍缺多場實際失去視野／重新可見的獨立核對。

## 下一步

依序補權威更新節拍與對局切換、部隊與欄位；對新文件／切局／死亡與霧邊界做
拒絕驗證；最後完成三段十分鐘、分層一千筆獨立 UI 比對。
M1 達不到前三個工作日／18 工程小時上限時，按指令判 FAIL 並停止。
M2–M5 尚未開始。

語意參考：[官方可見性實作](https://github.com/SoftbearStudios/kiomet/blob/main/client/src/visible.rs)、
[官方渲染與可見性邏輯](https://github.com/SoftbearStudios/kiomet/blob/main/client/src/game.rs)。
公開來源本身不證明正式版布局；本輪另以實際 WASM 版本與有限 UI 核對。
