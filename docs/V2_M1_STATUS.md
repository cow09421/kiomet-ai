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

| 實測 | 有效快照／Hz | 擷取延遲 p95 | 原報告整數上界 p95（連續時間須 +1 ms） | 結論 |
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

camera-visibility-84402eb3385c 以普通左右鏡頭鍵向右並返回，正常畫面截圖
證明鏡頭移動；201 個 coherent 世界／sensor brackets 中 loss=0、recovery=0。
此場景鏡頭位置不能改變 sensor coverage，因此這條支線沒有補上 fog cycle，
不重複延長相同實驗。這是當時工具版本的結果；後續新增 lease、文件／player／
root bracket 與 source manifest 檢查，不回填為舊程序已測欄位。

新場景的 fca86e13b9ad 已取得加強 pause guard 的 live 控制證據：10 個去重
世界版本完整十兵種向量，100/100 欄位一致；實際是四士兵（enum 5），不擴張為 Single
覆蓋。來源端不可見仍不輸出其 ID／幾何。87214e834f0e 正常資訊框另有
59/59 兵數／容量、42/42 顏色／塔型／delay 進度條，18/18 本方前置需求。

同一新場景的 visibility-research-5a57cbbd3018：600.078 秒、2,627 次
合法快照、2,447 次 coherent sensor brackets，33 個歷史已見 ID，仍沒有
loss／recovery。不能將新場景有部隊等同於本方視野必然變化。

delayed-apply-259d89778b11 取得因果反例：已解碼正常 Game 更新在暫停後
照常套用，tick 32818→32819，但該更新在套用時至少存在 1,030 ms
（原始整數端點差 1,031 ms，扣除 1 ms 取整不確定性）。
session-clock-71082f680622 另核對 receive context 與本機／peer bootstrap
範圍；兩者均非一般 Unix 時間範圍。仍未建立正式 server-generation clock。
上述 debugger 研究均排除於效能分母，不宣稱 snapshot age p95 或 M1 PASS。

年齡區間已擴張 ±1 ms，以涵蓋整數 host clock 端點的量化誤差。歷史報告的
原值仍保留；三段主要完整單局的連續時間上界 p95 應保守讀作 236 ms，
不是原先的 235 ms。005d91726c30 原報告 250 ms 應讀作 251 ms，因此這一
新版負載場景的上界不通過 250 ms 門檻。真正 authoritative age 仍 UNKNOWN。

sampling-bffad6e038a2 的 60 秒修正診斷：470 筆、7.829 Hz、p95 擷取
10.273 ms、套用年齡上界 p95 251 ms。完整保留尾部，不將它列為通過。
備援固定取樣間隔改為可明確配置並寫入報告／工具雜湊；150 ms 不依年齡
選樣或刷新停滯來源。sampling-a63088d2539c 的 60 秒為 477 筆、7.932 Hz、
p95 擷取 11.694 ms、含量化誤差的套用年齡上界 p95 205 ms；只是短診斷。

可見集合 coverage 不再固定 PARTIAL。正式 sensor 正值數與目前 generated
actor 解碼數完全相等，且正常 active／NETWORK／連線／非 expanded／非 dirty
門控成立，才有 DERIVED coverage_evidence 與 PLAYER_VISIBLE_COMPLETE。
缺任一目前 actor 仍 PARTIAL；這不是全世界完整性，也不清除 UNKNOWN 欄位
或 freshness。真實短測有 41/41 sensor slots，已移除固定 coverage 缺口。
26 項 v2 測試與 Node 隱私邊界通過。d4a9b156ae26 坦克（enum 4）分層取得
10 個完整十兵種向量、100/100 欄位一致；除錯暫停排除於效能驗收。

直接 getter 的 83d3f2a9f42b 遇到自然終局，沒有有效案例；356d561ee6e5
雖在真正坦克場景命中正式 entry 0xf9203，但 bounded caller／address seek
未找到可核對目標，仍為零案例。已新增有限 caller 名稱／地址是否吻合的布林
診斷；後續靜態 proof 已確認 iterator 呼叫 Units::clone，getter 参数地址無法
回推原 Force 指標，因此已退役未驗證直接模式，保留已成功的 captured
Force::speed nested getter 方法。失敗嘗試仍保留，沒有成功案例回填。

sampling-fe678ebb30ce 是新版 150 ms 備援計時器的完整 600.120 秒單局：
4,797 筆／7.993 Hz，有效跨度 599.571 秒，擷取 p95 8.248 ms，已含量化誤差
的客戶端套用年齡上界 p95 189 ms（4,795 筆有區間）。一文件／一 epoch／
NETWORK，1 次 dirty 拒絕；無除錯暫停或資訊框操作。4,797/4,797 筆皆有
29 個正值 sensor slots 與 29 個 generated actors，coverage evidence 數量全符。
來源 manifest 含當次 sampler 雜湊；authoritative age 仍 UNKNOWN，不能列為
M1 PASS 或把這些集合一致性檢查當成獨立 UI 正確率。

本方正常 UI 的 ad／rank／level／永久解鎖 AND 政策已加入 upgrade_locks。
只在必要條件均成立或存在已證明的 false 條件時推導；直接 rank tag=0 的
claims 路徑維持 UNKNOWN，不讀 account claims。正常 UI root clone 與
4 個目前本方資訊框計算吻合；44f67d1ba854 有 6/6 獨立 DOM 鎖头比較，
全為 ad 不可用場景的未鎖定。locked=true／廣告可用的 live 分層尚未取得。
前置條件、鎖定與最終命令資格仍分開，沒有升級或降級動作。

新版 sampling-c1448a90cbb2 為 60.025 秒、480 筆／7.997 Hz、擷取 p95
9.096 ms、客戶端套用年齡上界 p95 204 ms；只是短診斷。1,920 個本方塔
列有 DERIVED upgrade_locks，13,440 個非本方塔列維持 UNKNOWN，零越權
推導。28 項 v2 測試及 Node 隱私檢查通過。先前 fca／d4a 的兵種名稱已
依原始 enum 更正；數值比較不變，不再宣稱尚未取得的直升機分層。

新增正常部隊 glyph layout 核對，先以合法原 Force invocation 定位，再觀察
其正常十兵種 getter，不以 iterator clone 地址倒推原部隊。控制 ae28d4ab333d
有 10 組完整向量、100/100 欄位；positive Chopper(enum 2) 的 5189c3d1eabf
有 30 組完整向量、300/300 欄位。兩次 visibility pending 在讀取門控時拒絕。
第一批 de94e037b79e 的查詢上限不足，零有效案例，沒有納入一致率。
這補上直升機真實分層；不等同 Single 移動部隊或效能驗收。

已完成傳輸 ACK 假設的型別編碼檢查：資料 frame 只有 length/kind 與 payload，
ACK 另有送出序號及量化處理耗時，沒有已證明的特定 Game 生成因果關聯。
因此無法用這條支線建立 per-Game snapshot age；仍維持 UNKNOWN。

本方 Satellite(23)／Ews(8) 的新場景，visibility-research-652eee1871f2
跑足 600.235 秒：2,630 個快照、2,385 coherent sensor brackets、110 個
已知 ID，224 次 dirty 門控拒絕；sensor loss／recovery 仍為零。
不延長這個靜態場景的相同輪詢。

8 秒正常鏡頭遠移並反向移動的 87dd5b4a80ea 有 329 coherent rows，17 次
dirty 拒絕，截圖證明移動畫面。actor 數量 110→96→110，原始 sensor refs
全程仍為正值。從保留的 live rows 離線推導，14 個 actor 缺席並在同 scope
新 tick 恢復，最短缺席 8,781 ms。截圖顯示反向移動後並未精確回到原鏡頭
中心；actor 集合恢復不能證明鏡頭原點恢復。這驗證 viewport actor availability 的
缺席／恢復，並非 fog sensor cycle；後續工具會分開記錄兩種轉換。

正常 HTTP 時間標頭另有新證據：375a9c52106e 的 147 回應中 28 個有
x-held=1..238（中位數 16.5）；官方程式用它扣除 request 等待耗時以算 RTT。
Date 是一般回應日期，Game association 仍 UNKNOWN。缺 x-held 的回應沒有
被填為已觀察零，沒有 packet／body／URL／credential 匯出。公開旧版 socket
的 Game queue 也不能證明現行 HTTP 的生成時點；真正 server age 仍 UNKNOWN。

0a2e70d05651 的有限資訊框比對有 100 次選取、157/157 兵數與容量欄位、
100/100 顏色／塔型／delay 進度條。當時鏡頭中只選到 ENEMY:MANY；
未取得新的本方 Single 或升級政策分層，不能把這批擴張為全面正確率。

### 修正 metadata 輪詢誤延長對局連續性的缺口

舊 tracker 只計算兩次 observe 呼叫的間隔：若斷線或 UNKNOWN 期間持續
輪詢，間隔一直小於一秒，可能沿用失去來源前的對局 epoch。現在另追蹤
實際在線世界序號的變更；metadata 輪詢、連線仍開啟但世界停滯、未知狀態
均不能延長來源連續性。超過原本的一秒保守視窗就使舊 epoch 失效。
同 scope 後續恢復更新仍維持 UNKNOWN，直到正常 Menu／Result／Join
或新文件／玩家來源證據可建立新 observation epoch。這不是毫秒世界時鐘。

identity-gap-ed2336d158aa 在傳輸過渡 enum 被原門控拒絕後中斷，零完整
回歸案例；没有放寬傳輸解碼。工具改成固定 phase 期限內重試拒絕結果。
identity-gap-5aad71227572 實測 baseline 3 秒、offline 3 秒、reconnect
15 秒：正常 baseline 身分穩定，重連後同文件／玩家且世界繼續更新，舊
epoch 不復用；Canonical match_id UNKNOWN 且 readiness 留下 match_id
缺口。正常 reload 取得新文件 epoch 與新 memory handle。當時移動部隊
為零，因此其 force ID 布林檢查沒有提供非空 live 案例，不能宣稱部隊 ID
實測通過；新的工具會明確輸出該項 UNKNOWN。非空部隊在 match UNKNOWN
時清除 ID／first-seen 而保留合法庫存，由回歸測試驗證。

source 改動後 sampling-b192f03bc401 的 60.014 秒診斷：479 筆、7.981 Hz、
擷取 p95 8.659 ms、客戶端套用年齡上界 p95 204 ms，5,465 metadata reads、
零錯誤，一文件／一 epoch／NETWORK。沒有移動部隊，不列完整 M1 驗收。
31 項 v2 回歸與 Node 隱私門控通過；authoritative age 仍 UNKNOWN。

### 完整 UI cohort 與自然來源缺口

ui-comparison-9f8a743e9d1d 完成 1,000 次普通資訊框選取，零戰術命令。
994 次 coherent 塔型／關係／進度條均吻合；1,558 個 coherent 兵數與容量
欄位均吻合。涵蓋 SELF:SINGLE、SELF:MANY、NEUTRAL:MANY、ENEMY:MANY。
完整 observer source manifest 保存在原始報告；Single 分層不等同每一個
Single 兵種都在 DOM 顯示並已核對，例如國王 icon 不能當成國王兵數。

tools/v2_validation_inventory.py 對全部有獨立檔名的歷史 UI 報告做一次有限
統計：必須有文件、玩家、非空 epoch、正式 SHA、NETWORK、確認選取及
世界版本 bracket；跨 observer 按文件／玩家／版本／塔／欄位去重。
重複失敗不會被第一次成功遮蔽。1,248 rows 缺 scope/epoch、6 rows 未能
確認 source/selection，明確排除；每個不 coherent 的欄位另計，不混入分母。
1,353 eligible rows、1,345 unique selections；兵數 2,117/2,117、容量
2,117/2,117、關係 1,336/1,336、塔型 1,211/1,211、delay 進度條
1,294/1,294、前置數 536/536、disabled 229/229、lock 270/270，重複衝突零。
兵數分層：ENEMY:MANY 897、SELF:SINGLE 102、SELF:MANY 525、NEUTRAL:MANY
589、ENEMY:SINGLE 4。缺完整 moving/fog/lifecycle、部分特殊兵種及 true-lock
分層；這些欄位結果不能合併成「完整 GameState 關鍵欄位準確率」。

既存 live DOM rows 的有限士氣分析 morale-ui-9f8a743e9d1d，有 264/264
明確「士氣高昂」提示與 visible morale=1 相符。736 rows 沒有正向提示或
不 coherent，未將提示缺席推論為 false；不是 264 個新採集案例。

sampling-03d032d57e5b 在 lifecycle 修正後跑足 600.088 s：4,767 筆、
7.944 Hz、擷取 p95 7.745 ms；客戶端套用年齡的連續時間保守上界 p95
205 ms（原整數 204，4,622 bounds）、55,039 metadata reads，7 次拒絕。
初段同時有正常資訊框比對負載，没有 debugger pause。有效跨度 599.535 s。
一文件／NETWORK，但舊 epoch 後變 UNKNOWN，不能列完整同局 PASS。

序號 4618 首見 tick=23078，至 4624 仍未改；4625 在 1,062 ms 後讀到
23081，因此失效原本的一秒連續性視窗；不是 metadata 呼叫間隔超時。
當時 14 個部隊 ID 均原為 DERIVED；失效後 14 個 ID/first-seen 均 UNKNOWN。
後續 143 快照共 1,412 個合法部隊 facts 都未復用 ID。證據保存為
natural-force-gap-03d032d57e5b，來自原始快照（SHA 隨報告）；是非空
自然來源缺口驗證，不能宣稱受控斷線或真正伺服器換局。停滯原因 UNKNOWN。

### Session 日期、ETA 核對與部隊就緒修正

現行 WASM 的 dateCreated 已找到正常 SessionCreated 保存路徑。十秒中
92 次讀取均為有效 Unix ms 類別，世界有 41 個版本，日期不變；直接用於
Game 生成時間的假設 FAIL。數字只在工具內暫存，未寫入證據檔或讀憑證。
沒有每份 Game 的因果對應，伺服器快照年齡仍 UNKNOWN。

正常 Force::progress_required 的 30 個去重版本，30/30 與所需節拍公式吻合；
這批全為未加速、required=72，同距離分層。加速／255 cap／最小值沒有
新的 live 覆蓋，不代表抵達時刻驗收。13 次 visibility pending 拒絕；排除
全部 debugger 暫停，不混入頻率或年齡資料。

已修正 readiness 只檢查 OBSERVED 部隊集合、卻忽略集合內 UNKNOWN 欄位
的漏檢。原始 03d032d57e5b 的 14 支部隊，在身分失效前已有 2 個未知來源、
5 個未知目的地、7 個未知 ETA；現在明確阻擋這些缺口。失效後另阻擋 14
個未知 ID。資料仍合法保留、未知值仍為未知。完整 v2 回歸 33 項通過。

普通縮放的 966c9efabdb6 發生在自然淘汰後，零有效 Game rows；原門控
拒絕全部實體讀取，不列驗證樣本。工具補上各 phase 的 active 判定後，
普通 Play Again 新局的 bfc0d4968952 有 132 rows、8 次 dirty 拒絕，畫面
縮放 18.125→22.836→18.125，actor 數全程 23，沒有特殊 Single 或新的
sensor cycle。這條支線沒有增加所需覆蓋，不再延長同場景輪詢。

### 拒絕錯誤時域，並用真正權威年齡決定 freshness

原 age_ms 的 max(0, now-update) 可把未來時間／錯誤 epoch 截成新鮮的零。
現在 Canonical 只接受 host_monotonic_ms；已知更新點必須是非負整數且不
晚於 receipt。未來、bool、NaN／Infinity、錯誤時域均拒絕；receipt 前或
無效數值的年齡查詢回 UNKNOWN。正常欄位沒有被填入假的新時間來源。

另修正 freshness 在更新點已知時，仍可能優先採用近期客戶端套用 bounds
的缺口：現在直接用權威 point age。回歸案例的 application bound 0..12 ms，
但 generation age 901 ms，必須拒絕就緒。案例時間全部是合成隔離資料，
不算 live 年齡證據。完整 v2 回歸 36 項通過；真實 updated_at_ms 與年齡
p95 仍 UNKNOWN。既有 application bound 指標仍分開記錄。
