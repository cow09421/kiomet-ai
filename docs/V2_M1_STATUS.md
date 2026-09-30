# KIOMET AI v2 — M1 STATUS

CURRENT MILESTONE: M1 Observation / State

STATUS: PARTIAL；M1 = NOT YET。2026-10-01 Asia/Taipei。

START HEAD: 55ee71e。重要研究檢查點只提交／推送 v2-rebuild；main 封存。
M2 / M3 尚未開始；本輪沒有派兵、拖曳、升級或語意遊戲命令。

## 目前狀態

| 必要來源 | 實際能力／限制 |
|---|---|
| 世界序號 | OBSERVED u16 World.Singleton sequence；NETWORK / OFFLINE 類別另存。已辨識第二條 tick 路徑屬 OfflineHarness，網路模式拒絕本機模擬。不是伺服器時間戳。 |
| 對局身分 | DERIVED 文件／玩家／加入／選單／結果 epoch；同一局穩定，Result → Menu → 新局與 reload 已實測；連線判定已改為 session 持有的 WS / WT / HTTP 傳輸。 |
| 資料根 | 正式 WASM 版本鎖定；正常事件回呼 → ClientBroker → context 的型別路徑；不再掃描遊戲記憶體。 |
| 可見塔 | 即時 Visible.refs 正值才解碼；dirty、非 active、擴張視野均拒絕。道路只輸出已觀察端點。 |
| 兵種 | Many / Single 的完整型別向量；正式 getter 證明 Single 布局，忽略 union padding。 |
| 部隊 | 正常渲染可見 inbound／必要 outbound；當前路段、兵種、兵數、進度、owner、關係、first-seen；唯一續接 DERIVED ID，歧義 UNKNOWN。 |
| ETA | DERIVED 當前路段剩餘模擬時間，包含加速規則；不是抵達時間戳，缺可見端點時 UNKNOWN。 |
| 容量／生產 | 正式純規則表與可見士氣；生產是潛在節拍間隔，不承諾容量或優先級阻擋時產出。 |
| 國王 | 看見自己的 Ruler 才標目前存活／位置；找不到不推論死亡。 |
| 可派兵量 | DERIVED force_units 可移動庫存；尚未證明路徑／命令合法性。 |
| 敵盟關係 | 正式正常顏色路徑的雙向盟友 membership；敵方已有限 UI 核對，真實盟友未覆蓋。 |
| 升級／特殊效果 | 自己的有效塔數是 OBSERVED 升級前置資源，候選前置需求 DERIVED；delay 與士氣已觀察。完整升級原因／解鎖／命令合法性、EMP 等仍 UNKNOWN。 |
| 可見性切換 | 正式門控與合成防洩漏檢查成立；真實 visible → hidden → visible 驗收尚未完成。 |

## 真實數據

官方 client SHA-256:
fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c。

| 實測 | 有效快照／Hz | 擷取延遲 p95 | DERIVED 來源年齡上界 p95 | 結論 |
|---|---:|---:|---:|---|
| 隔離有畫面，600.090 s | 1,849 / 3.081 | 10.44 ms | 415 ms | 頻率與上界不達標 |
| 無視窗、密集來源讀取，30.101 s | 149 / 4.950 | 6.90 ms | 235 ms，148 筆有區間 | 短測，不能驗收 |
| 無視窗、較大局面，600.086 s | 2,870 / 4.783 | 18.93 ms | 266 ms，2,868 筆有區間 | 頻率達標，上界不達標 |
| typed transport／200 ms 固定輪詢，600.058 s | 2,917 / 4.861 | 9.59 ms | 265 ms，2,917 筆有區間 | 完整單局，年齡上界仍不達標 |
| 新世界更新觸發＋200 ms 計時器，30.122 s | 238 / 7.901 | 7.15 ms | 235 ms，236 筆有區間 | 短測，尚未驗收 |
| 新世界更新觸發，600.086 s，c6a514114b2e | 4,747 / 7.911 | 5.90 ms | 235 ms，4,746 筆有區間 | 第一段完整單局達到頻率／客戶端套用年齡上界數值 |
| 不同玩家新局，600.167 s，a12a3a5d35c7 | 4,680 / 7.798 | 6.55 ms | 235 ms，4,677 筆有區間 | 有效跨度 589.050 s；最後進入 RESULT，不列完整單局通過 |

精確 authoritative snapshot age p95 = UNKNOWN，沒有用擷取延遲代替。
上述上界約束 NETWORK 模式下已觀察世界序號的客戶端套用區間，伺服器產生
時間與傳輸前延遲仍 UNKNOWN。e390ca4881ef 的舊年齡計算早於 receipt 移到
normalization 完成的修正；f413115a25e6、c6a514114b2e、a12a3a5d35c7
均已包含 normalization／tracking 成本。不能把 235 ms 宣稱為精確伺服器年齡。

第一段有 1,650 筆含部隊的快照、7,441 次進度變化。第二段有 2,870 筆含部隊
快照、34,570 次進度變化、1,114 個多次觀察的 DERIVED track，最多 36 支部隊。
這不是獨立部隊正確率；ID 續接本身使用進度規則，不能循環證明規則正確。

本批保留的四次有限官方資訊框比對：81 個 coherent 兵數欄位，81 個一致；
另 2 個變動區間已排除。容量有 22/22 的獨立介面分母比對。最新對局的
4 SELF、5 NEUTRAL、1 ENEMY 共 10 座塔顏色一致。舊首階段 8/8 留在歷史證據，
不重新計數。未達 1,000 個分層驗收樣本，也沒有完整關鍵欄位一致率。
最新 ui-comparison-7acdafd9b767 另有 22/22 兵數、22/22 容量、13/13
正常顏色與 8/8 自己的前置塔數／8/8 前置需求；各欄位分開計數，不混充
完整關鍵欄位正確率。其後三輪 345eee7264c9 為 45/45 兵數、45/45 容量、
30/30 顏色與 15/15 前置數量／需求。

50 輪正式資訊框讀取 ui-comparison-95dc42f35a60：717 次選取，
1,231 個依「epoch、塔 ID、世界序號、兵種」去重的兵數欄位，1,231/1,231
一致。分層為 SELF:SINGLE 50、SELF:MANY 450、NEUTRAL:MANY 331、
ENEMY:MANY 400。另有容量 1,231/1,231、顏色 717/717、自己的前置塔數
400/400、前置需求 400/400。各分母分開報告。這是 717 次塔選取，不把
1,231 個欄位誤寫成 1,231 個完整局面；移動部隊與視野轉換分層仍缺。
目前不存在完整關鍵欄位 >=99% 的 M1 驗收結論。

兩段十分鐘都沒有實際視野失去／重新取得；不得以合成測試代替此項驗收。
21 項 v2 Python 測試通過；Node 合成記憶體檢查也通過資料根、霧／dirty gate
與單向／雙向結盟邊界。未清理封存 v1 測試，也沒有把離線結果標成 live PASS。

## 目前最重要問題

重連疑點已找到具體原因：官方 session 會從 WebSocket 切換 HTTP 輪詢。
transport-research-e0ac23c469ab 的重連 30 秒中，兩個 WebSocket 都 CLOSED，
但 session 持有 HTTP_POLL state=1，108 次 Fetch 回應／完成，世界序號
53299 → 53439。舊的「任意 OPEN WebSocket」判定既漏掉 HTTP，也可能被
無關舊物件誤導；現已由正式型別 ownership 與 state getter 取代。
本次結果画面資料只算傳輸研究，不能算十分鐘有效對局或 UI 驗收樣本。

新世界更新觸發已完成第一段 600 秒單局，4,747 筆／7.911 Hz、套用年齡
上界 p95 235 ms。每個來源變更仍由實際序號觀察證明，不用插值或預設
250 ms 假造更新。下一個重點是補足三個獨立對局的完整證據，以及決策欄位、
真實可見性與部隊的獨立分層比對。不能只靠增加塔兵數欄位宣稱 M1 PASS。
reload-reacquisition-7b1063300c33 已證明舊 reader 拒絕、新 memory handle、
同 session／新文件／新觀察 epoch；同一個 Ruler 在重載前後仍存活，所以
這是文件隔離證據，不是另一局的證據。初始化空事件 owner 已改為重新附掛。
一次十分鐘嘗試 snapshots-0fa5e8439ec1 因瀏覽器期限中斷，明確排除；
新的測試會先驗證 host deadline，並保存觀察器程式碼雜湊。
f29371b41728 再次觀察自然 RESULT → MENU → JOINING → IN_MATCH；
同一 player=25／資料根仍建立新 epoch，重載拒絕舊文件，離線無可輸出身分，
重連恢復同一新文件 epoch。沒有把文件重載算成新遊戲生命。
部隊獨立正常執行核對 c567fea66f9c 速度原始讀取 20/20、c13b5b9fd217
位置 30/30 去重世界版本一致。所有除錯暫停均排除於效能驗收之外。
沒有降低 M1 Gate。尚未到 18 工程小時硬上限，也未證明技術不可行。

詳細可重現證據：V2_M1_TICK_EVIDENCE.md、V2_M1_FORCE_RULE_EVIDENCE.md。
原始研究資料在忽略版控的 runtime/research/v2/，不把大型 live 檔案推入 Git。
