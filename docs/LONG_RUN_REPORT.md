# LONG_RUN_REPORT（長任務報告）

時間：2026-09-27 03:25 → 06:00（Muse Spark 自主長任務）。
Git：master 共 13 個檢查點（0dc7850 → … → 最新見 `git log`）。
單元測試：39 passed。平台現況：RUNNING／IN_MATCH／MUTED／錯誤 0。

## REALITY

### 目前 REAL
- 隔離 Chromium＋零鍵鼠干擾（focus_viol 0，原始碼無 OS 輸入呼叫）。
- LIVE VIEW 真實對局約 1fps；Dashboard 真實控制台（對局雙證據＋來源時效、
  音訊全分頁＋守衛＋偏好持久、探針結果）。
- 真實進局（Play＋雙證據驗證，多次成功）；預設永久靜音（8 項回歸全過）。
- 參考源操作語意完整解碼（game.rs 輸入／Path::validate／TowerId 座標系／
  TowerType 表／Command／Update 形狀）。
- WASM：列舉成功（1 Memory 51 頁／3 實例／wasm-bindgen）、重複快照成功、
  全量傾印 3.3MB、變化地圖（19 動頁）、逐頁剖面（靜零／堆／密／渲染區）。
- 探針：hunt-then-release＋ruler-hold＋質心吸附＋嚴格四指標分類器；
  路徑渲染可重現；transition 證明放開零效果非盲點。

### 目前 MOCK
- 主迴圈 MockGame 閉環（分數／塔／WAIT／SUCCESS 全部假世界；Dashboard 已標示）。
- KataKiomet 離線 heuristic（policy／value／ownership／safety／simulator，未接線）。

### 目前 UNKNOWN
- 全部塔／兵／擁有者／鄰接／兵力／排名（觀察器未建）。
- 放開無派兵的最終一跳（首懷疑：非道路鄰居，見下）。

## RUNTIME MVP
- WASM：PASS（列舉＋重複快照＋全量傾印＋變化圖）。
- Memory：51 頁；動頁 [15,20-26,29,30,34,40,41,43-46,48,49]；
  靜密頁 31-33（192KiB 疑似壓縮/序列化緩衝，未辨）、渲染稀疏頁 39-49。
- 解出的結構：TowerId(u16×2, CONVERSION=5, 世界 0~2565)、TowerType u8 枚舉
  （~27 種）、Tower／Force／Path／Command／Update 欄位順序（參考源）、
  Path::validate 道路鄰居規則（普通步兵須 is_neighbor）。
- 玩家名表：步長 64 位元組陣列（u16 id?＋u32 名指標＋u32 長度＋名），
  URE-VIH／Beguest 等多處（聊天緩衝＋名表），證結構化陣列可讀。
- 塔陣列：未定位。f32 中心掃描僅渲染拷貝；u16 範圍掃描 12 萬命中多為噪音；
  候選評分器（步長＋範圍＋枚舉）最高分群為計數器/渲染 u16 序列，非塔。
- 傳輸層：客戶端無 WebSocket 字串（kodiak 外部 crate 未取）；CDP 封包監聽
  5 分鐘零幀（監聽本身存疑，勿解讀）。
- Yew 選單通道：證偽（35 點擊零 DOM 變化）。
- 塔中心 f32 掃描：177 命中但僅 1 組相鄰對（渲染拷貝），非常駐塔陣列特徵。

## REAL OBSERVATION
- Tower／Owner／Units／Neighbor：UNKNOWN（Yew 選單通道已證偽：35 點擊零 DOM
  變化，部署版選單非 Yew 或點空）。
- 可用：GAME STATE、截圖、音訊狀態、探針統計。

## EXECUTOR
- MOVE_FORCE：7 輪探針，0 成功。最好成績：路徑渲染 116 倍背景後放開零效果。
- 成功率：0/7（未達 9/10 門檻，不准接 AI）。
- 根因排序見 GPT6_HANDOFF_0700 F1（道路鄰居規則為首）。

## LIVE BOT
- 模式：OBSERVE_ONLY（探針外零真實輸入；每進程 1 次 Play）。
- 存活：多場對局存活至主動重啟；06:00 前一場在探針中自然結束回 MENU
  （join_done=True 後 sense 回 MENU，無重連，符合設計），後一次手動重進
  曾短暫 IN_MATCH 又迅速回 MENU（疑似秒踢／秒死，待觀察）。
- 領土／Rank／Peak：UNKNOWN（未讀）。

## FAILURES
- F1 放開不派兵（見交接文件，附完整診斷資產路徑）。
- F2 ws 零封包（量測存疑；傳輸層在外部 kodiak crate，未取）。
- F3 彈窗增生（已緩解：全分頁靜音；頁數指標作廢）。
- F4 背景程序回收（緩解：pythonw 無重定向啟動；雙 PID 釐清為 shim）。

## NEXT（3～5 項，同交接文件）
1. 塔圖讀取器（CV 環檢／選擇環差分二選一）→ 探針放相鄰塔中心。
2. 合法目標推導：NEIGHBOR_TABLE 純幾何可計算，塔座標＋鏡頭一解即可推導。
3. 新程式碼 30 分鐘 Soak。
4. match-obs.jsonl 落盤。
5. 首 SUCCESS 後 Stage 1→2 漸進（WAIT＋觀察→後方增援）。
