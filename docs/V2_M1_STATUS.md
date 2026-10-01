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
| 升級／特殊效果 | 自己的有效塔數是 OBSERVED 升級前置資源，候選前置需求 DERIVED；delay 與士氣已觀察。本方永久 keys／解鎖種類已觀察；delay=0 可推導無進行中延遲式升級。連續可見直接升級轉型＋正式 delay 倒數可保守追蹤進行中升級；未見起始原因、EMP 中斷、有效 UI 解鎖政策／命令合法性仍 UNKNOWN。 |
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
| 另一新局，600.052 s，dbd474eb11d0 | 4,766 / 7.943 | 6.43 ms | 235 ms，4,764 筆有區間 | 第二段完整單局達到頻率／客戶端套用年齡上界數值 |
| 第三新局，600.020 s，12f8a3edfab7 | 4,777 / 7.961 | 6.98 ms | 235 ms，4,775 筆有區間 | 第三段完整單局；有效跨度 599.541 s，NETWORK、同文件／同 epoch |
| 自然淘汰，600.105 s，7029917c4bc8 | 3,281 / 5.467 | 5.91 ms | 235 ms，3,278 筆有區間 | 只有 412.244 s 有效跨度；不列完整十分鐘 |

精確 authoritative snapshot age p95 = UNKNOWN，沒有用擷取延遲代替。
上述上界約束 NETWORK 模式下已觀察世界序號的客戶端套用區間，伺服器產生
時間與傳輸前延遲仍 UNKNOWN。e390ca4881ef 的舊年齡計算早於 receipt 移到
normalization 完成的修正；f413115a25e6、c6a514114b2e、a12a3a5d35c7
以及 dbd474eb11d0、12f8a3edfab7 均已包含 normalization／tracking 成本。不能把 235 ms 宣稱為精確伺服器年齡。

第一段有 1,650 筆含部隊的快照、7,441 次進度變化。第二段有 2,870 筆含部隊
快照、34,570 次進度變化、1,114 個多次觀察的 DERIVED track，最多 36 支部隊。
這不是獨立部隊正確率；ID 續接本身使用進度規則，不能循環證明規則正確。

本批保留的四次有限官方資訊框比對：81 個 coherent 兵數欄位，81 個一致；
另 2 個變動區間已排除。容量有 22/22 的獨立介面分母比對。最新對局的
4 SELF、5 NEUTRAL、1 ENEMY 共 10 座塔顏色一致。舊首階段 8/8 留在歷史證據，
不重新計數。當時尚未達 1,000 個分層驗收樣本；完整關鍵欄位一致率仍未建立。
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

三段完整十分鐘都沒有實際視野失去／重新取得；不得以合成測試代替此項驗收。
25 項 v2 Python 測試通過；Node 合成記憶體檢查也通過資料根、霧／dirty gate
與單向／雙向結盟邊界。未清理封存 v1 測試，也沒有把離線結果標成 live PASS。

## 目前最重要問題

重連疑點已找到具體原因：官方 session 會從 WebSocket 切換 HTTP 輪詢。
transport-research-e0ac23c469ab 的重連 30 秒中，兩個 WebSocket 都 CLOSED，
但 session 持有 HTTP_POLL state=1，108 次 Fetch 回應／完成，世界序號
53299 → 53439。舊的「任意 OPEN WebSocket」判定既漏掉 HTTP，也可能被
無關舊物件誤導；現已由正式型別 ownership 與 state getter 取代。
本次結果画面資料只算傳輸研究，不能算十分鐘有效對局或 UI 驗收樣本。

新世界更新觸發已完成三段 600 秒單局，分別 4,747／4,766／4,777 筆，7.911／7.943／7.961 Hz、
套用年齡上界 p95 均 235 ms。每個來源變更仍由實際序號觀察證明，不用插值或預設
250 ms 假造更新。三段頻率數值證據已齊；下一個重點是來源時間、決策欄位、
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
a9d60c91270f 另直接讀取官方正常 Units::available 回傳值：30 個去重世界版本，
每個均取得完整十兵種向量，300/300 欄位一致。實際組成全部是五輛坦克，
不宣稱涵蓋所有組成。可派兵量已區分「已知非本方來源的本方兵量為零」
與「本方身分未知」；後者仍 UNKNOWN，不靠零代替未知。
沒有降低 M1 Gate。尚未到 18 工程小時硬上限，也未證明技術不可行。

詳細可重現證據：V2_M1_TICK_EVIDENCE.md、V2_M1_FORCE_RULE_EVIDENCE.md。
原始研究資料在忽略版控的 runtime/research/v2/，不把大型 live 檔案推入 Git。

### 後續獨立比對與本方資源

ui-comparison-b64690264b9c：40 輪，632/632 coherent 去重兵數、632/632
容量、432/432 coherent 顏色、360/360 本方前置數量／需求。與 95dc42f35a60
合計 1,149 次 coherent 塔選取、1,863 個兵數欄位；各分母仍分開，不是
完整狀態正確率。8a52e26a523b 另有 6/6 前置不足的按鈕 disabled 比對、
6 次可觀察未鎖定圖示；尚無啟用與鎖定的完整矩陣。

本方 Unlocks 的 typed 路徑 root+46240 由 pinned 正常 UI props clone 使用；
keys 在 +32，解鎖 enum set 經 ctrl/mask/len/範圍／唯一性驗證。只輸出本方
資源，不讀 hash seeds。412e589d030d 真實短測讀到 keys=3、unlocked_types=()
（兩者 OBSERVED）；無效 storage 為 UNKNOWN。這不等於有效 UI lock policy。

visibility-research-498d23c31a2b：120.079 秒，474 coherent sensor brackets，
11,208 次去重「歷史已見 ID 現在不覆蓋且無目前 actor」檢查，零洩漏。
24 次 loss 全是匯入舊局歷史，0 recovery，不能當成同局 fog cycle。
7029917c4bc8 有 24 次 canonical 塔列消失，但沒有同步直接 sensor 證據；
不把全局淘汰或新局的歷史 ID 不覆蓋冒充 visible→hidden→visible。

決策 readiness 現在拒絕用客戶端 application age 清除 authoritative freshness
缺口；updated_at_ms UNKNOWN 時 freshness 必留。RTT、frame 時間與輪詢時間
均未拿來填造伺服器 snapshot age。

### 連續可見升級與新版實測

UpgradeTracker 只接受同 epoch、同正值 owner、相鄰一次 source tick、
prior delay=0、正式 direct-upgrade 塔型轉換及新型 nominal delay。只在倒數
精確吻合時續接；EMP 式延遲跳變、owner／epoch 改變、可見性失去、
未觀察更新或超過 1 秒間隔均失去原因證據，回到 UNKNOWN。

upgrade-history-79047ae0c5ea 對原始合法 live 紀錄離線重新處理：15 個
升級起始、2,868 筆倒數、333 筆仍未知的 delay。這不是新增 live 驗收。
新的 ui-comparison-a84933df9cb7 則有真實 Village→Headquarters 起始，
52/52 coherent 正常進度條一致；32f3180246b6 另有 Reactor 29/29 delay
進度條一致，但未見其起始，不能只憑進度條判定原因。

e68f3686914c：獨立塔型標籤 25/25，兵數／容量 47/47，顏色 27/27；
其中 ENEMY:SINGLE 有 4 個兵種欄位，實際 Silo 的 Single Nuke=1、Shield=20
與正式資訊框一致。沒有把未支持的中文標籤放進塔型分母。
正常 force getter 新 strata：9ac718c8fdb9 30 個十二士兵完整向量，300/300；
06d675aad308 30 個四轟炸機完整向量，300/300。除錯暫停仍不計效能。

新版完整單局 sampling-005d91726c30：600.067 秒、4,748 快照、7.912 Hz、
有效跨度 599.364 秒、p95 擷取 14.602 ms、客戶端 application age 上界
p95 250 ms（4,747 筆有區間）。一文件／一 epoch／NETWORK，18 次 dirty
拒絕，含普通資訊框操作的實際負載；全部保留，不刪慢樣本。來源 manifest
包含 UpgradeTracker 與本方 Unlocks。後加 document_time_origin_ms 僅供
跨 observer 文件核對，不用於 game age，這一舊程序的輸出尚不含該新增欄位。

visibility-research-0662272c4f3f：450.078 秒、1,812 coherent sensor brackets；
f5ec73cea14a：600.109 秒、2,438 coherent brackets。兩次都無 loss／recovery，
不能宣稱同局 fog cycle 通過。相同靜態視野的重複輪詢已停止。

部隊除錯核對的 pause guard 現在重驗 owned transport、當前 sensor 及正常
renderer 的 inbound/outbound vector membership；合法 anchor 通過前不讀
force payload，也不讀 path pointer 或隱藏端點資料。合成邊界檢查已通過。
ea293294b9f0 額外控制未取得有效部隊樣本，0 個獨立核對；不能當成新 guard
的 live 成功證據。之後的合法短讀當時有 36 座可見塔、沒有移動部隊。
