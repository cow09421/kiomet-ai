# GPT-6 接手唯一入口（先讀我，再讀 CURRENT_STATE.md）

LAST UPDATED: 2026-09-27 07:15（UTC+8）
AUTHOR: Muse
STATUS: 平台活著（live／RUNNING／IN_MATCH／MUTED／錯誤 0）， survey 版探針執行中（勿碰）

## 一句話專案狀態

平台骨架成熟、能進局能看能靜音；第一支真實派兵仍是 0，卡在「放開點必須是道路鄰居，但塔圖未知」；WASM 解出 0 個塔欄位，WebSocket 線已證偽收工。

## WORKING（確定能用）
- 隔離 Chromium（焦點違規 0、使用者桌面 0 視窗；實體鍵鼠零呼叫，grep 可證）
- LIVE VIEW（~1fps 真實畫面）、Dashboard、Control Center（唯讀小窗）
- Match Lifecycle：MENU／JOINING／IN_MATCH／RESULT_SCREEN／UNKNOWN／DISCONNECTED
  ＋ ENTER_MATCH（Play 與 Play Again 同一個 `#play_button`）＋ match_id／index／start／end
- live 模式：Mock 閉環全停（plans 恆 0）；Dashboard 顯示 REAL／UNKNOWN＋MOCK 折疊
- 音訊永久預設靜音（啟動／進局／reload／彈窗全覆蓋＋偏好檔＋~4 秒守衛）
- Git 14 個檢查點，單元測試 42 項全過（最後執行 07:0x）

## NOT WORKING（全 0 的東西）
- 真實塔位置／Owner／Type／Units／Neighbor／Force／King／Rank：全部 NO
- MOVE_FORCE VERIFIED SUCCESS = 0（7 輪探針；最新 survey 版執行中）
- Real Planner／Defensive AI／KataKiomet Search／Self-Play：0（按指示未啟動）

## LATEST BREAKTHROUGHS（最近突破）
1. RESULT_SCREEN 偵測：結算 overlay 蓋在首頁 DOM 上（`#play_button` 仍在），
   用 Play Again／Back to menu／Session Statistics 文字優先判定；國王死因
   可從 DOM 讀出（例：「國王被⚘XARS的護盾擊殺」）。
2. Path::validate 道路鄰居規則（vendor force.rs）：普通步兵放開必須
   `is_neighbor`，像素靠近≠合法；NEIGHBOR_TABLE 純幾何可算。
3. WASM：1 Memory（3,342,336 位元組／51 頁）＋主實例（wasm-bindgen）＋重複快照
   ＋全量傾印＋19 動頁地圖；玩家名表 stride-64 陣列定位。
4. 探針方法論：hunt 全 survey→選最近渲染點→按住 2.5 秒→質心吸附→放開；
   transition 證明放開零效果非量測盲點。

## FAILED / EXHAUSTED APPROACHES（勿重做，詳見 DO NOT REPEAT）
- f32 中心／u16 範圍盲掃（噪音海）；Yew DOM 選單通道（35 點擊零變化）；
  隨機像素放開（7 連敗）；CDP Network 事件監聽（機制性收不到事件）；
  WebSocket inbound（見下）。

## CURRENT BLOCKER
目前沒有任何可靠方法把官方 Runtime 裡的資料映射成一座已知 TowerId（塔圖未知→放開點合法性不可驗→MOVE_FORCE 卡死）。

## SELECTION DIFFERENTIAL STATUS：FAIL（有價值的 FAIL）
- 48 點擊網格→11 候選→徑向剖面剩 3 環（A(289,708) 三次同亮度 68.8 確認；
  B 存疑；C 中等）。
- A→B→A→C→A 全量差分：66 槽初篩，8 輪驗證全滅——清除穩定的永不響應，
  響應的永不重現（@0x1e0568 疑似慢速 churn／堆重定位）。
- 結論：選擇態可能根本不是持久 WASM 欄位（Yew 事件瞬態），或需同布局內
  即時重發現（spec §12），不值得再燒整輪。

## WASM STATUS
- modules 3／instances 3／memory 1／3,342,336 bytes／51 pages／動頁 19。
- 玩家名表：stride-64（u16 疑似 id＋u32 名指標＋u32 長度＋名），多處重複
  （聊天緩衝＋名表），是字串／名稱表，能否沿它到 player id 未驗證。
- Tower array／TowerId／position／owner／type／units／neighbors／Force／King：
  全部 NO（CANDIDATE 都沒有）。

## WEBSOCKET STATUS：FAIL（收工，勿重開）
- Playwright 原生 `page.on("websocket")` 75 秒 live 對局：0 事件。
- CDP Network.enable＋reload：0 事件；自建 echo socket 陽性對照：0 事件；
  fetch 觸發 requestWillBeSent：0 事件→**監聽機制本身收不到事件**（非無流量）。
- 引擎同時有 web_socket.rs＋web_transport.rs（kodiak-ref），部署版極可能走
  WebTransport（QUIC 加密，解碼需 MITM——禁止碰）。
- 結論：網路通道線終止；bitcode/Update 知識保留作 WASM 堆辨識參考。

## REAL ACTION STATUS
- JOIN_MATCH：反覆成功（Play／結果頁未端到端）。
- PLAY_AGAIN：selector 已知（同 `#play_button`），**未 live 驗證**。
- MOVE_FORCE：0／7（最新 survey 版 07:08 執行中，結果未定）。
- UPGRADE／SUPPLY／MOVE_KING：NO。

## MATCH LIFECYCLE
- 狀態：MENU／JOINING／IN_MATCH／RESULT_SCREEN／UNKNOWN／DISCONNECTED（程式碼）。
- Live 已驗：MENU、JOINING→IN_MATCH（多次，match 建號）、IN_MATCH 穩定、
  IN_MATCH→RESULT（MATCH_END 事件，今晨實測）。
- 未 live 驗：RESULT→Play Again→新 match（待自然死亡）。

## GIT STATUS
- 14 commits（見 log），工作區乾淨（本輪只動 docs，另有 2 個 docs commits）。
- 上次 11 個之後新增：`95bb6cd probe survey-then-nearest`、
  `3bd5d11 ignore kodiak vendor`（＋docs commits）。
- vendor/kiomet-ref、vendor/kodiak-ref：本地保留、不進 Git（AGPL 只讀參考，
  禁止複製進 src，禁止連官方服）。kodiak-ref 曾誤入索引，已 `rm --cached`。

## IMPORTANT FILES
- `src/kiomet_ai/browser.py`：隔離啟動／守衛／感測／進局／探針／音訊（真實能力全在此）。
- `src/kiomet_ai/app.py`：主迴圈＋戰術閘門／管理控制＋live/mock 分流。
- `src/kiomet_ai/imgutil.py`：標準庫像素比對（探針的眼睛）。
- `runtime/tmp/ws_native.py`：原生 ws 監聽（證偽工具）。
- `runtime/tmp/sel_*.py`：選擇差分全套（已證偽，留作反面教材）。
- `runtime/tmp/wasm_*.py, scan_*.py, score_*.py`：WASM 列舉／傾印／掃描／評分。
- `tests/`：42 項（分類／守衛／比對／偏好／模式）。
- `tools/control_center.py`：唯讀小窗。`docs/CURRENT_STATE.md`：5 分鐘版。

## IMPORTANT RUNTIME ARTIFACTS（實際存在）
- `runtime/wasm/mem-match1.bin`（3.3MB）、`mem-match2.bin`、`mem-menu1.bin`、
  `mvp1-enumeration.json`、`mvp2-change-map.json`。
- `runtime/research/seldiff/`：click-*.png（48 組）、sel-*.png、full-*.bin（6×3.3MB
  已剪枝？以現場 `ls` 為準）、phase2-seq.json、anchor-candidates.json、
  ring-candidates.json、rediscover.json。
- `runtime/research/websocket/ws-join-watch.json`（空事件紀錄）。
- `runtime/probe/`：最新兩輪探針 PNG＋證據（以現場為準）。
- `runtime/state/soak-report.json`：舊程式碼 30 分鐘 17/17（新程式碼未重跑）。
- `runtime/screenshots/match-live-*.jpg`：對局證據幀。

## DO NOT REPEAT（已證偽／浪費）
1. f32 k*5+2.5／u16 全堆盲掃（噪音海，無駐留特徵）。
2. Yew DOM 塔選單（部署版沒有，35 點擊零變化）。
3. 隨機像素／固定 hop 放開（7 連敗；必須先有塔圖）。
4. CDP Network 事件監聽（此環境收不到事件；陽性對照失敗）。
5. WebSocket inbound（傳輸疑為 WebTransport＋加密；MITM 禁止）。
6. 為靜音 resume AI（架構錯誤，已修為管理控制）。
7. MockPlanner 開回 live（污染，已用 --live 封死）。
8. 把 vendor 參考庫加進 Git（已 rm --cached＋ignore）。

## NEXT 3 TASKS（只三個）
1. **選擇環差分定位塔螢幕座標**（截圖差分找環心；A 點已驗證三重現；
   供探針放開點用，不建正式 CV Observer）。
2. **等自然死亡→RESULT→Play Again→新 match** 全鏈路驗證（補 P0-1 TEST C/D）。
3. **新程式碼 30 分鐘 Soak**（舊 PASS 是舊程式碼；重點看音訊守衛 CDP 負載）。

## 關於「平台 STOPPED」顯示問題（2026-09-27 07:11 調查）
- 進程：python shim 對（07:06:36 啟動）存活；chrome 42 個；API 當場回
  RUNNING／IN_MATCH（新鮮非 STALE）；final-status.json 是 07:05 舊實例殘留。
- 結論：**平台沒停**。STOPPED 畫面最可能是陳舊分頁／Control Center 快取／
  重啟空窗期看到的舊快照。Dashboard 每秒輪詢，.refresh 一次即恢復。
  GPT-6 若再看到 STOPPED：先調 `/api/status` 確認，勿直接重啟。
