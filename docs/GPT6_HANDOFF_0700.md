# MORNING STATUS（早上狀態）— GPT-6 交接 07:00

版本：master `ae8fb0d`（2026-09-27 ~05:00）。共 6 個檢查點，38 項單元測試全過。
目前 Phase（階段）：Real Match Bootstrap 完成＋OBSERVE_ONLY；RealMoveProbe
基礎設施完成但首次 SUCCESS 尚未拿到；Stability Bot 離線核心（未接線）。

- 平台現況（05:01 實測）：RUNNING，GAME STATE=IN_MATCH（雙證據），
  音訊 MUTED，錯誤 0，平台/對局點擊 1（僅 Play），焦點違規 0。
- Soak Test（30 分鐘）：OVERALL=PASS（17/17，見 runtime/state/soak-report.json，
  但該次運行是舊程式碼；新程式碼尚未跑完整 30 分鐘）。

## LIVE（真正實戰完成了什麼）

- 隔離 Chromium 進 Kiomet 首頁 → 點 Play → IN_MATCH，全程頁面級操作，
  實體滑鼠鍵盤零干擾（focus_violations=0）。
- GAME STATE 雙證據感測（menu_absent＋match_markers）＋來源/時效/STALE 顯示。
- 音訊永久預設靜音：啟動／進局／reload／新分頁全部自動補靜音；
  偏好 `config/runtime-preferences.json`（game_audio_enabled=false）；
  PAUSED 下可靜音/開聲（管理控制，不經戰術閘門）。
- RealMoveProbe 跑過 6 輪真機：路徑渲染可重現（走廊 0.04~0.11 vs 背景 0.001~0.03），
  按住 2.5 秒＋渲染質心吸附後放開，仍無部隊（transition 證明非量測盲點，
  見 KNOWN FAILURES）。第 6 輪掃描起點強反應但 hunt 零渲染：
  掃描 elongation 量尺會把選擇環誤判，下一版掃描應改用走廊渲染量尺。
- LIVE VIEW 全程顯示真實對局（非首頁），約 1fps。

## SIMULATED（模擬完成了什麼）

- KataKiomet 離線核心：graph／belief／ownership／value／policy／safety／
  opponents／simulate（前向模擬器），單元測試覆蓋，未接真實對局。
- Beam Search／MCTS／Self-Play：未開始（按指示暫停，等首個真實 MoveForce）。

## MOCK（仍然假的部分）

- 主迴圈分數／兵力／決策仍是 MockGame；Dashboard「最新行動（模擬）」與真實對局無關。
- MockExecutor／MockVerifier 只動本機模擬世界，未送任何真實遊戲命令。

# ARCHITECTURE（真實架構圖）

```
Kiomet 官方伺服器
  ↕（官方 WASM 客戶端，唯讀研究 vendor/kiomet-ref，不自建客戶端）
隔離 Chromium（Win32 獨立桌面，6+ 分頁含廣告彈窗）
  ├─ game_page：對局頁（Play 點擊、探針拖曳、LIVE 截圖、音訊 suspend 對象）
  ├─ probe_page：本機 /probe 輸入隔離驗收（不碰遊戲）
  └─ 廣告彈出分頁（只靜音，不關閉、不操作）
  ↓ Playwright 頁面級事件＋CDP Runtime（無 OS 輸入、無 SwitchDesktop）
BrowserHost：guard（焦點/桌面檢查）＋ sense（雙證據）＋ join（一次）＋
            probe_move（探針）＋ audio（全分頁 suspend／resume）
  ↓ Tactical Gate（戰術閘門：join／probe／遊戲輸入，需 RUNNING）
  ↓ Management Control（管理控制：靜音／感測，不看 RUNNING）
Application：mock 閉環＋monitor（守衛/感測/音訊守衛）＋capture＋dashboard
  ↓ Dashboard（本機）：平台狀態／GAME STATE＋來源時效／音訊／REAL ACTION STATUS
  ↓ Control Center（tools／桌面小窗，唯讀）
```

# KATAKIOMET STATUS

- Policy：HeuristicPolicy 完成（候選＋先驗排序，Amount 離散化），未接線。
- Value：HeuristicValue 完成（穩定權重），未接線。
- Ownership：啟發式控制權＋戰線梯度完成，未接線。
- Uncertainty：belief 信心衰減＋staleness 完成；safety 懲罰完成，未接線。
- Search：未開始（beam/MCTS 暫停中）。
- Self-Play：未開始（本地模擬器未建）。

# STABILITY BOT

- 它現在會：什麼都不會（保持 OBSERVE_ONLY；探針外零真實輸入）。
- King Safety／Reserve／Defense／Expansion／Upgrade／Supply：只有離線 Heuristic，
  未在真實對局執行過任何一次。
- 解鎖條件（按指示）：首個真實 MoveForce SUCCESS＋Verify 後才恢復。

# BENCHMARK（數字）

- 單元測試：38 passed（test_core 8＋test_live 6＋test_bootstrap 9＋
  test_katakiomet 8＋test_probe 7），~1.6 秒。
- Soak（舊程式碼）：17/17 PASS，1802 秒，0 錯誤，focus_viol 0，
  暖機後記憶體斜率 5.39 MB/min（<10 告警線）。
- 探針真機 4 輪：結果皆 FAILED_NO_FORCE_CREATED；路徑渲染 in 0.04~0.11；
  放開後走廊變化 in 0.0~0.02、motion 0.0、shift (0,0)；
  ws 封包：發 0／收 0（見下：量測方式待確認）。
- 音訊回歸 8 項：T1✓T2✓T4✓T5✓T6✓T7✓T8✓，T3 機制驗證（單元測試＋程式碼）。

# LIVE TEST（2026-09-27 凌晨多場對局）

- 多次進局（每次重啟後重新 Play），每場存活至主動重啟（未被殲滅記錄）。
- 塔數變化／最大回撤／King：未量測（觀察器未建）。
- 操作錯誤：0；焦點違規：0；實體鍵鼠干擾：0（程式碼無此類呼叫，grep 可證）。
- 真實遊戲輸入總數：每進程 1 次 Play 點擊＋探針拖曳（研究用，有紀錄）。

# KNOWN FAILURES（重要失敗）

## F1. 放開拖曳不派兵（最高優先，阻塞 Stability Bot）
- 現象：路徑渲染出現（in≈0.06，背景 20~100 倍），按住 2.5 秒＋質心吸附，
  放開後路徑消失、無部隊、無位移、motion 0（transition 證明非量測盲點）。
- 已排除：Camera Pan（shift 恆 0,0）、量測盲點、國王 1.2 秒延遲、
  放開點偏離（質心吸附後仍失敗）。
- 首要懷疑：`find_best_path` 在可見塔子圖上無完整路徑（參考源放開要
  complete 路徑，中間塔在霧中即失敗；只畫 incomplete 路徑會誤導）。
  2026-09-27 ~05:45 深挖確認更精確規則（common/src/force.rs Path::validate）：
  普通步兵 max_edge_distance=None，放開走 `is_neighbor` 道路圖分支——
  目標必須是道路鄰居，不是「螢幕上靠近」！盲目 130px 放開極易命中非鄰居。
  好消息：NEIGHBOR_TABLE 是純幾何可計算的（tower/id.rs），只要解出塔座標
  ＋鏡頭變換，合法目標可推導，無需猜。
  次要懷疑：supply-line 分支誤觸（需確認 selected 狀態）、伺服器靜默拒絕。
- 診斷資產：runtime/probe/（每輪 PNG＋證據 JSON）、transition_analysis.py、
  hunt-then-release＋ruler-hold 已在程式碼中。
- 建議：見 NEXT FOR GPT-6 第 1 項。

## F2. WebSocket 封包零紀錄（量測方式存疑）
- 現象：Network.enable＋webSocketFrameSent/Received 監聽 5 分鐘，發 0 收 0。
- `CDPSession.on` 存在（已驗證），事件名正確；但不排除遊戲用 WebTransport
  或監聽附著時機問題。結論：ws 證據不可用，勿解讀為「無流量」。
- 建議：下一次用 `Network.webTransportCreated`＋`Target.getTargets` 變化監看；
  或直接放棄網路通道，專注像素＋遊戲狀態通道。

## F3. 廣告彈窗分頁增生（已緩解）
- 現象：kiomet.com 分頁從 2 個增生到 6 個（廣告彈窗），各自放音。
- 已處理：音訊改全分頁掃描＋守衛補靜音；不關閉彈窗（保守）。
- 注意：owned_page_count=2 的舊假設已失效；別用頁數當健康指標。

## F4. 背景程序曾被執行環境回收（已緩解，未根除）
- 現象：用 shell 管線重定向啟動的平台約數分鐘後被回收（Unknown: ChildProcess.kill）。
- 緩解：改 pythonw＋無重定向分離啟動後存活數小時；但機制不明，仍需觀察。
- 雙 PID 現象已釐清：venv python 是轉發 shim（CPU≈0），codex python 才是本體；
  單一有效實例，無雙寫問題（control.json pid 為準）。

## F5. 官方音量鍵不存在（已接受）
- localStorage 無音量鍵、DOM 無喇叭按鈕、設定在外部 kodiak crate。
  採用 FALLBACK_MUTE（AudioContext suspend）＋如實標示；自動播放旗標
  `--autoplay-policy=no-user-gesture-required` 保證 resume 可用。

# NEXT FOR GPT-6（只列 5 項，按順序）

1. **最小塔圖讀取器＋餵給探針**：先讀出可見塔的 화면座標／擁有者／相鄰
   （Canvas CV 或遊戲狀態暴露二選一，做最小可行），探針改放「相鄰可見塔中心」
   再驗證 F1 是否消失。這是 Stability Bot 的唯一門鎖。
   補充（WASM 衝刺約 80 分鐘結論）：堆逆向未定位塔陣列；但玩家名表已證結構化陣列可讀（stride 64）；u16 掃描噪音大；建議下一波主攻選擇環差分定位（截圖差分找環心＝塔螢幕座標，供探針用）＋渲染實例緩衝辨識，WASM 並行但不擋路。
2. **探針結果分流**：supply-line 誤觸排查（放開前讀 selected 狀態；必要時
   每次探針前強制清選擇）＋mid-vs-after 轉移量作為正式 SUCCESS 輔證。
3. **新程式碼跑一次完整 30 分鐘 Soak**：舊 PASS 是舊程式碼；重點看音訊守衛
   CDP 負載＋探針程式碼常駐（不執行時）的穩定性。
4. **OfficialClientObserver 最小閉環**：match-obs.jsonl 落盤（10 秒快照：
   text_len／markers／live seq），為第 1 項鋪路；仍只觀察。
5. **Stability Bot 接線（僅在首個 MoveForce SUCCESS 後）**：按 Stage 1→2
   漸進（WAIT＋觀察→後方增援），每類 Action→Verify→Logger 完整。

# 給 GPT-6 的操作提醒

- 唯一工作區 E:\SteamLibrary\kiomet；git 用 GitHubDesktop 內附 git.exe
 （系統 PATH 無 git）；.venv 的 python.exe 是轉發 shim，屬正常。
- 平台啟停：Dashboard /api/stop（憑證在 runtime/state/control.json）→
  進程會駐留顯示最終狀態（by design）→ 再 Stop-Process；啟動用
  pythonw 無重定向分離啟動（詳見本輪紀錄）。
- 禁止：搶鍵鼠、視野作弊、隱匿／反偵測、多帳號官方 Self-Play、
  開源客戶端連官方服、AGPL 碼複製進 src、Windows 音量。
- 音訊預設永靜音是永久規則（config/runtime-preferences.json）。
- 真實對局除明確單次探針外保持 OBSERVE_ONLY；join／probe 全經戰術閘門。
