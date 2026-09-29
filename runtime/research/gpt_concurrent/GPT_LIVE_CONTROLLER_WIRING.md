# 真實控制器接線稽核與修復藍圖

## 啟動與呼叫圖

`run.ps1:14-16` 把 `-Live`／`-LiveAuthorize`（真實模式／真實操作授權）轉成 `--live`／`--live-authorize`。`src/kiomet_ai/app.py:538-541` 只設定 `config.mode`（運行模式）；`app.py:563-568` 建立 `Application`（平台物件）、設定授權並等待 `app.run()`。

`Application.__init__`（`app.py:27-35`）**無條件建立** MockGame、MockObserver、MockPlanner、MockExecutor、MockVerifier（模擬遊戲、觀察器、規劃器、執行器、驗證器）。`Application.run`（`app.py:375` 附近）建立 Dashboard（儀表板）、監控、瀏覽器與觀戰截圖任務；主迴圈 `app.py:445-450` 遇到 `mode=live` 時**只更新狀態**，不呼叫 `cycle()`。`app.py:451-452` 的 Observe→Plan→Execute→Verify（觀察、規劃、執行、驗證）是模擬分支。

真正的自主閉環寫在**另一支可直接執行的腳本** `tools/live_controller.py`：`__main__`（結尾）→ `asyncio.run(main())` → `main:282-314` 每回合 `await cycle` → `cycle:176-279` 取得 `/api/status`、錨點、唯讀塔探測、排名、提案、畫面座標、預檢 → `:242-246` POST `/api/execute-move` → 等八秒、再探測、`verify_post_action`（行動後驗證）。平台的 `app.py`、`run.ps1` **沒有匯入、建立、啟動或等待這支腳本**。

| 問題 | 結論 |
|---|---|
| LiveController class（真實控制器類別）是否存在 | **NO（沒有類別）**；現有的是 `tools/live_controller.py` 的函式式獨立腳本 |
| 在平台內是否建立 | **NO（沒有）** |
| `run()` 是否呼叫／等待 | 平台 **NO**；僅手動啟動獨立腳本時 `asyncio.run(main())` 才執行 |
| 平台是否建立背景控制任務 | **NO**；現有背景任務只有監控、瀏覽器啟動及觀戰截圖 |
| 作用域或垃圾回收是否讓已建立控制器結束 | **非主因**；平台根本沒有建立它。獨立腳本若啟動，自己持有事件迴圈及 `while True` |
| 已記錄的獨立腳本狀況 | `runtime/state/live_controller_log.jsonl` 共 30 個 ERROR（錯誤）週期，送出 0、驗證 0；最新錯誤為 `未知 UnitsEither 標籤：55`，最終 `live_controller.json` 為 ERROR，更新於 2026-09-28 11:57:37 |

## 精確斷點與模擬資料洩漏

第一個斷點是 `app.py:446-449`：真實模式只做心跳，沒有銜接外部控制器，也沒有狀態活性檢查。第二個是 `tools/live_controller.py:150-161` 的觀察解碼；歷史日誌顯示它在本輪樣本中讀到不合法 `UnitsEither`（兵力聯合型態）標記。`unit_struct_probe.py:36` 實際讀取 `tower_ref-32..+160`，`live_controller.py:155` 切出 `[32:80]` 作塔 48 位元組，此偏移本身相符；更可能是錨點品質、記憶體世代不一致或假塔參照，需以同一快照與多塔欄位守衛查明，**不能直接判定切片錯 32 位元組**。歷史 `anchor_quality_ok`（錨點品質檢查）僅抽首三塔，`build_states` 對全部塔解碼，後續假錨點可穿過抽檢。

Mock（模擬）物件雖在真實模式建立，但 `app.py:446-450` 不執行模擬閉環；它們仍使頂層 `sent_actions`／`last_action`／`last_verification` 表示模擬資料。儀表板 `app.py:93-112` 無條件從舊 `first_move_candidate.json` 建立 `next_action.mode="DRY / LOCKED"`；即使對局已換，也顯示舊提案。`app.py:85-88` 的 `real_action` 專指探針結果，因此有兩筆定向拖曳時仍可顯示「無紀錄」。`dashboard/index.html:36` 用存在 `live_controller.phase` 判斷已連線，沒有檢查更新時效；`live_sent_actions` 只計當前平台程序記憶體中的拖曳，重啟後歸零。

## Muse 可直接採用的修復點（不在本輪套用）

1. 在平台啟動時選擇**一個**真實控制器所有權模型：由 `Application.run` 在真實模式建立並持有受監督的控制任務，或明確以獨立程序啟動並持續監督。現有 `run.ps1` 未做第二件事。啟動完成前記錄控制器 PID（程序編號）、啟動時間與唯一實例鍵；終止與重新啟動應受同一生命週期管理。
2. 真實模式不要把模擬欄位當真實狀態；以當局、當次觀察世代與控制器心跳發布 Planner（規劃器）／Executor（執行器）／Verifier（驗證器）連線狀態。過期 `first_move_candidate.json` 不得顯示為目前待執行提案；`real_action` 應讀真實行動日誌而非探針欄位。
3. 先修 `tools/live_controller.py:123-165` 的全體塔有效性與快照一致性：每塔 `tower_ref`、48 位元組範圍、兵力標記、塔型、對局與時間都合格才產生狀態。解碼失敗回到 OBSERVING（觀察中）並重新錨定，不得默默產生提案，更不能送操作。
4. 控制器 POST（網頁請求）必須帶唯一 `action_id` 與 `origin=AUTONOMOUS_CONTROLLER`（自主控制器來源），平台在 `app.py:153-200` 記錄發起者、程序、授權、派送與驗證。未有可稽核來源時，不能把平台歷史計數當作自主操作數。
5. 將 `tools/live_controller.py:253-275` 的固定八秒與弱判準改為事件／節拍驅動的強驗證。至少一個行動獲確認或明確失敗後，重新觀察並重排，再考慮下一個行動。

## 同步工作樹更新（尚未驗收）

以上是本輪開始時、提交 `ee1e9cf` 的稽核。Muse 在本輪同步新增 `src/kiomet_ai/live_controller.py`，其中已有 `class LiveController`（真實控制器類別）；`src/kiomet_ai/app.py` 已在 `Application.__init__` 建立它，並在 `run` 建立 `asyncio.create_task(self.live_controller.run_loop())`（非同步背景任務）。Muse 隨後以 `e4d371f` 提交這批修補。故**目前程式的靜態接線缺口已有修補**；尚無本輪可讀的新進程心跳或成功驗證，不能宣稱新接線已跑通。本 GPT 工作流沒有修改或提交那些正式檔案。

工作樹仍需處理的具體靜態風險：`src/kiomet_ai/live_controller.py:96-102` 沿用五分鐘內的舊錨點時，沒有強制取得當局新探測資料；`cycle_once:212-218` 可直接讀既存 `unit-struct-probe`（單位結構探測）檔，時間新鮮度未守衛，且 `build_states:178-189` 對全部塔解碼而品質閘只抽首三塔。`cycle_once:249-275` 仍固定八秒後單次取樣、把 `force_observed` 設為 False（否），並把來源任意變化列為已驗證；`run_loop:294-306` 把一般例外記為 ERROR（錯誤）後繼續每 90 秒重試，連續失敗閘只計驗證不明，不計這類例外。這些都是**靜態風險候選**，待 Muse 自己完成修補與測試。

舊提交 `ee1e9cf` 的 `--live` 只接真實觀察；新提交 `e4d371f` 已把真實控制器接入平台。最終是否常駐與能否安全操作，必須以 Muse 的新進程心跳、閉環測試及真實世界證據判定。
