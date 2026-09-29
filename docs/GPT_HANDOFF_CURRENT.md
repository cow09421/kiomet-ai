# GPT 接手唯一入口（2026-09-27 13:04 之後）

LAST UPDATED: 2026-09-27 13:05（UTC+8）
AUTHOR: Muse
CURRENT LEVEL: **Level 4（Dry Run Semantic Move）**——7 閘 VALIDATED（禁發送）
SENT ACTIONS: **0**（零未授權行動；見 §2 核對）

## ONE-LINE STATUS
平台進程活著但停在 ERROR（渲染目標第 4 次崩潰，Dashboard 顯示舊 IN_MATCH；
詳見 PLATFORM HEALTH）；塔錨點＋命令邊界＋編碼真值＋乾跑俱全；派兵仍 0；
音訊多層靜音服役中；等你：重啟恢復＋目檢一票＋發送簽字。

## CURRENT LEVEL
Level 4（Dry Run Semantic Move）。Level 5 未開始（禁發送），Level 6 為 0。

## VERIFIED WORKING
- 隔離 Chromium（焦點違規 0；無 OS 輸入呼叫；grep 可證）
- Match Lifecycle 全狀態＋ENTER_MATCH（MENU→Play／RESULT→Play Again 同
  `#play_button`）＋match_id／index／start／end（RESULT→新局端到端實測多次）
- live 模式 Mock 全停（plans 恆 0）；Tower Anchor（16 塔三輪＋SELF＋43 無向邊）
- 命令邊界：`WebSocketTransport::send_unit`（正式 2386）參數刻畫＋1Hz 時序吻合
- 發送普查：4B 心跳 ground truth（`01 03 xx`＋通道位元組逐位元組對齊）＋7/8/13B 事件幀
- 本地編碼真值：Deploy／Upgrade／viewport／heartbeat＋roundtrip（`encode_probe`）
- Dry Run 7 閘 VALIDATED（當局有效；禁發送）
- 音訊：Chromium `--mute-audio`＋注入（AudioContext 出生暫停／resume 攔截／
  媒體靜音／MutationObserver）＋守衛（~4 秒＋違規轉換紀錄）＋Desired/Actual 分離

## PARTIAL
- WORLD_TO_SCREEN：公式＋鏡頭＋移植全 PASS；4 點環確認；缺目檢一票
 （`runtime/research/source-map/evidence-map.png`＋`evidence-towers.json`）。
- SELF：MEDIUM（連續塊＋內部邊＋新鮮 OWN 拖曳；无像素交叉）。
- Neighbor：43 邊（遮罩直讀，僅觀察塔）；視覺 0/10。
- Units：ref 差分靜態＋慢槽無生產特徵（渲染側記錄假說）。

## NOT STARTED
Real Planner、Defensive AI、KataKiomet 接線、Self-Play、Upgrade/Supply/King 執行、
Force 解碼（自然樣本未系統收集）、Rust 重寫。

## OBSERVER STATUS
- 每局：match_id＋16 塔＋world＋camera＋screen＋SELF＋邊＋新鮮度（`observe_match.py`；
  STALE 規則：舊局／超 30 秒拒絕）。
- 當局 m5 錨點＋快照俱全；MATCH_END 後舊檔自動失效（需重錨）。

## UNITS STATUS
FAIL（三次差分皆靜態；慢計數器 77 槽多為指標／旗標）。缺：生產中塔的可變槽。

## OWNER STATUS
SELF（MEDIUM，render_color 0＋連續＋邊）；OTHER／NEUTRAL 未分類；
UNKNOWN 28；灰色保守 UNKNOWN。

## TOWER TYPE STATUS
NOT STARTED（enum 已知，未映射到觀測塔）。

## UPGRADE STATUS
NOT STARTED；Upgrade 編碼形狀已有（`05 …` 6B）；Live Upgrade：NO（正常）。

## FORCE STATUS
NOT STARTED；自然樣本未收集（禁為測試送兵）。

## REAL WORLD MODEL
PARTIAL（MatchObservation 結構＋新鮮度門控就緒；units/type/force 欄位空）。

## EXPANSION PLANNER
NOT STARTED（units/owner 門檻未達）。

## SHADOW MODE
NOT STARTED。

## READY_FOR_FIRST_UI_MOVE
NO（差：目檢票、SELF HIGH、neighbor 目檢、新鮮 dry run）。EXECUTE：NO。

## EXECUTE GATE
 planner／shadow／dry-run／READY 皆不能使 sent_actions＞0（程式面未建
 強制門——**GPT 若建 Executor 必須先建此門**，見 §45 原始需求）。

## COMMAND OBSERVER
READY（被動包裝普查＋2386 參數＋心跳基線；真實 DeployForce 未見過——因零發送）。

## AUDIO
- Desired MUTED；硬靜音 YES；AudioContext 保護 YES；resume 攔截 YES；
  媒體保護 YES（document 級 observer）；新頁／新幀 YES（init 腳本）；
  導覽 YES；守衛 YES；Desired／Actual 已分離。
- 本輪漏音回報：**UNKNOWN**（Muse 在線期間零 VIOLATION 條目；使用者體感以使用者為準）。
- 回歸 7/8＋1 機制覆蓋（reload 舊式未重測）。

## PLATFORM HEALTH（13:04 實測）
- 進程活著（34180/34388，11:57 啟動）；主迴圈已停（ERROR）。
- 起因：第 4 次渲染目標崩潰（`Page.screenshot: Target crashed`），與前三次不同：
  **本次崩潰時無任何 CDP 偵錯活動**（Muse 近 1 小時只做 API 輪詢）→
  偵錯致崩假說削弱，記憶體壓力／廣告累積（10 個 kiomet chrome）升為首懷疑。
- Dashboard 顯示舊 IN_MATCH（m5）＋STOPPED 類殘留皆為陳舊快照；重啟即恢復
  （標準流程：stop→收容→pythonw 無重定向啟動→等 browser＋MUTED）。
- 焦點 0；鍵鼠 0；plans 0（live）；音訊 MUTED；Browser Profile 安全（未動）。

## TESTS
53 passed／0 failed（13:03 全綠）。契約含內（閘門／分類／偏好／新鮮度／模式）。

## GIT
最新：`21b6ff4 checkpoint: per match observer`；共 29 commits；
工作區 CLEAN（本輪只交接 docs，見下）。

## CURRENT HARD BLOCKER
發送二選一懸空：WASM 直接調用（§52 堆風險）vs UI 事件路徑（待目檢一票）——
技術到門口，缺風險簽字；簽字前禁發送。

## DO NOT REPEAT
f32/u16 盲掃／Yew DOM 選單／隨機像素放開／CDP Network 事件監聽／WebSocket
inbound（WebTransport＋加密，MITM 禁止）／SAME_TOWER_DUAL_READ／為靜音 resume
AI／Mock 回 live／vendor 入 Git／取樣命中當呼叫次數／憑單輪計數宣稱跨輪穩定／
在 CDP 偵錯會話中途殺進程（清理由 finally 做，殺掉即失）。

## NEXT 3 TASKS
1. **重啟恢復平台**（標準流程）→ 確認 browser＋MUTED＋0 錯 → 目檢
   `evidence-map.png` 5 點（30 秒）定 WORLD_TO_SCREEN。
2. **SELF 5 點像素＋neighbor 10 邊道路確認** → READY 門全開（仍禁發送）。
3. **發送二選一簽字後**：EXECUTE 首探（SELF→SELF 鄰居，單次，雙證據驗證）。
