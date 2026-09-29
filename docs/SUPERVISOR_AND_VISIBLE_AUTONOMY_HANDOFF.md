# 監督器與可見自主交接（2026-09-29）

## Supervisor（監督器）

- `src/kiomet_ai/supervisor.py`：生命週期唯一權威（啟動／停止／重啟／修復／健康分層／恢復階梯／單實例保護）。
- Control Center 已升級：啟動／停止／重啟／暫停自主／恢復自主／修復遊戲頁＋健康列＋版本列＋按鈕狀態。
- 健康分層：Backend／Dashboard／Browser／Page／Game／Observer／Planner／Executor／Verifier／Controller／Authorization。
- 恢復階梯：LEVEL 1 Page → LEVEL 2 Chromium → LEVEL 3 全平台；10 分鐘 3 次上限。
- 後端命令：pause-autonomy／resume-autonomy／recover-page／recover-chromium（Dashboard 路由已加）。
- BrowserHost.recover_page／recover_chromium 已實作（含 live token 重標記）。
- 測試：8 項合成（啟停／重啟／恢復上限／健康分層／防雙啟）。

## Visible Autonomy（可見自主）最終統計

- sent_actions：39（全平台日誌累計；自主＋歷史，不含測試）
- verified_moves：30（TARGET_CONTESTED＋判定）
- verified_expansions：10（待確認追蹤自動確認 NEUTRAL→SELF）
- failed_actions：0（連續失敗保護未觸發）
- Force bundles：13＋（8 束雙 VERIFIED 路徑相關）
- Tests：148 passed／0 failed

## Dashboard／Control Center 真實性

- NEXT ACTION 讀控制器實時態（無 stale DRY）。
- 三卡片讀真實後端；WORLD STATUS 上線；建置識別上線。
- Control Center 按鈕直連 Supervisor（不經 Dashboard 也可操作）。

## Crashes（崩潰）

- 本輪新增：第 9 起（45e95d87，renderer；恢復中）。
- 9/9 關聯斷點／重研究活動；A/B 零斷點零崩潰維持。
- 不開新研究線；incident 已存。

## 授權與安全

- EXECUTE authorization = YES（LIVE_NEUTRAL_EXPANSION，會話級）。
- sent_actions／MOVE_FORCE／Upgrade Actions 全程政策內。
- ENEMY／ALLY／SELF 目標／Single／Upgrade／跨多跳全拒絕（門控＋測試）。
