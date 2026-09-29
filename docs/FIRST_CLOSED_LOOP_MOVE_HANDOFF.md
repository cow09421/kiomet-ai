# 首次閉環調兵交接（2026-09-28 垂直切片長任務）

## VISIBLE MILESTONE REPORT（可見里程碑報告）

**FIRST_CLOSED_LOOP_MOVE_READY: YES（是）**

整條路完成，只差使用者明確說 EXECUTE（執行）。
本輪 sent_actions = 0、MOVE_FORCE = 0、Upgrade Actions = 0。

- Duration（時長）：約 4.2 小時（02:45→07:05）
- Commits（提交）：6（proposal 管線／Dashboard 區塊／升級採樣器輸出／國王逐塔語意＋2 前置）
- Tests（測試）：113 passed／0 failed（新增提案閘門 10 項，含最重要授權測試）
- Matches Dry-Run（乾跑對局）：5（m1-1790535667、m1-1790535911、m2-1790537230、m1-1790539798、m1-1790549068）
- Matches With Ready Proposal（有 READY 提案對局）：5（其中 1 局後期因鄰居易手轉 NO_SAFE_PROPOSAL，安全門正常作用）

## Current Match（目前對局）

- Current Match：m1-1790549068（以 first_move_candidate.json 為準；平台持續浸泡中）
- Current Proposal（目前提案）：見 `runtime/state/first_move_candidate.json`
- Source Tower（來源塔）：SELF Many（例：Runway／Mine／Cliff 系）
- Target Tower（目標塔）：NEUTRAL 直接鄰居（例：Ews／Mine／Radar 系）
- Source Units（來源兵力）：逐兵種現量（Many 完整解碼）
- Deployable Force（可派部隊）：DERIVED 逐兵種組成（非 Projector 不含 Shield）
- Path（路徑）：來源→目標直接邊（path_length=1）
- Neighbor（鄰居）：YES（邊圖驗證）
- Rank Score（排名分數）：heuristic_score（啟發式分數，非勝率）
- Rank Reasons（排名理由）：可派−防禦＋前線＋新增前線收益（逐項可解釋）
- World Freshness（世界新鮮度）：FRESH（同局＋30 秒門控）
- Camera Freshness（相機新鮮度）：每次預檢重算屏座標
- Coordinates（座標）：world／screen 雙座標＋畫布邊界檢查
- Preflight（執行前置）：PASS（11 項安全檢查＋座標重算）
- Executor（執行器）：READY（輸入完備；Page 層 Playwright／CDP 路徑預留，未接真執行）
- Verifier（驗證器）：READY（9 狀態機＋合成測試）
- ActionGate（行動閘門）：LOCKED（鎖定）
- Authorization（授權）：NO（否）
- Dashboard Preview（儀表板預覽）：YES（NEXT ACTION 區塊上線，顯示模式／來源／目標／可派／排名／預檢／授權狀態）
- Preview Evidence（預覽證據）：`runtime/research/preview/<match>/frame.jpg＋preview.json`（4 局）
- Vertical Slice Soak（垂直切片浸泡）：5 局乾閉環（4 READY＋1 誠實 NO_SAFE_PROPOSAL）
- Stale Leaks（過期洩漏）：0
- Cross-Match Bugs（跨局錯誤）：0
- Platform（平台）：RUNNING（恢復後實例；Win32 隔離＋靜音）
- Audio（音訊）：MUTED（靜音，0 違規）
- Crashes（崩潰）：2（crash-006／007，同舊特徵；皆在斷點錨點會話中；已存 incident＋恢復）
- Latest Commit（最新提交）：見 git log
- Working Tree（工作樹）：CLEAN（提交時）

## 本輪附帶突破

1. per-tower 國王語意確立（同玩家雙塔分歧 UI 驗證；Many 塔可駐王）。
2. Single(Nuke,1) 直接真值（首個非 Ruler 數字級驗證）。
3. 斷點活動↔崩潰關聯再獲 2 例（A/B 零斷點零崩潰 vs 錨點會話中 2 崩）。
4. 輕量錨點（16 樣本）同等有效，確立低侵入標準流程。

## Upgrade Round2 整合附註（§88，非里程碑條件）

- +47 Integration（+47 整合）：+47＝1 位元組通用暫停倒數（4 tick／秒，升級 160／EMP 240）——Muse 未驗證 Runtime 讀取路徑（callback root 未定位；按指示不深挖）。
- Player Tower Counts +592（玩家塔數）：27×u16 靜態確認；Runtime 接入 PARTIAL（未證明 Observer 握有 callback root）。
- Upgrade Mirror（升級鏡像）：GPT 77／77 來源規則通過；Muse 以 8 條 UI 驗證鏈＋解析器從 Production 側呼應（`docs/UPGRADE_SOURCE_EXPECTED_GRAPH.md`）。
- 结论：Upgrade Runtime 仍 PARTIAL，不阻塞首次閉環。

## 最終結論（§89）

「如果使用者現在輸入 EXECUTE，系統是否已經具備在目前最新對局中，
對一個安全的中立鄰塔完成第一次閉環 MoveForce 所需的全部技術前置？」

答案：**YES（是）**——以 first_move_candidate.json 的 READY 提案＋
READY_TO_EXECUTE 預檢＋LOCKED 閘門為證。但仍需使用者明確授權，
且授權當下必須重跑新鮮度（候選會過期）。
