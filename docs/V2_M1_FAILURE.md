# KIOMET AI v2 — M1 FAILURE

CURRENT MILESTONE: M1 Observation / State
STATUS: FAIL（約 18 工程小時上限）；核心開發停止。
START HEAD: 55ee71e
SOURCE HEAD: a21aeede1571eb2ca721b45a2ea5614d5d5bafd8
BRANCH: v2-rebuild；main 未修改。

停止觸發條件：依使用者設定的約 18 工程小時上限。不是宣稱所有合法方法
在技術上都不可能；最後目前版本十分鐘 cohort 已完成，必要來源仍未取得。
工程時間按首輪約 5 小時 52 分鐘，加 active goal 時間計算；配額暫停和
等使用者的空檔不計。原始計時不是逐分鐘工時帳，故保留「約」。
停止判定時間：2026-10-01T14:28:02+08:00。最近 active goal 計時 43,540 秒，
加首輪估計 21,120 秒，共 64,660 秒（17 小時 57 分 40 秒），
已達「18 小時左右」；未為湊整數繼續無資訊增益輪詢。

必要來源未取得：每份正式 Game 更新的伺服器生成時間，或與特定 Game
有可信因果對應、可證明 p95 ≤250 ms 的生成年齡上界。updated_at_ms 與
authoritative snapshot age p95 仍 UNKNOWN。M2／M3 未開始。

## 已完成且保留的能力

- immutable Canonical GameState、版本鎖定與正常事件回呼的 typed root 路徑。
- 正向 Visible.refs 門控；dirty、結果／選單、expanded visibility、離線模擬均拒絕實體資料。
- Many／Single 向量、可見部隊、保守 DERIVED ID、名義當前路段 ETA。
- Own 塔數／前置條件／永久解鎖與正常 UI lock 政策；未證明的命令資格保持 UNKNOWN。
- 超過連續性視窗撤銷對局 epoch 和部隊 ID；保留合法庫存並阻擋部分狀態就緒。
- 拒絕錯誤時域／未來／非有限時間，freshness 使用真正權威年齡。
- 36 項 v2 回歸通過；正常官方資訊框和純函式的獨立比較，沒有戰術命令。

## 真實證據與缺口

歷史三段獨立完整 600 秒：4,747／4,766／4,777 筆，7.911／7.943／7.961 Hz，
擷取 p95 5.90／6.43／6.98 ms。連續時間客戶端套用上界 p95 各 236 ms。
這些只能驗證頻率與客戶端套用區間，不能驗收伺服器生成年齡。

嚴格 UI inventory：1,373 eligible rows、1,365 unique selections；2,147/2,147
兵數與容量、1,356/1,356 關係、1,231/1,231 塔型、1,314/1,314 delay 進度、
554/554 前置數、554/554 前置 requirement flag、235/235 disabled、276/276 lock。
requirement flag 是歷史報告保留的布林比較，缺原數字，不能冒充完整需求數值。
1,248 rows 缺 scope/epoch，
6 rows 未確認 source/selection，排除；不 coherent 欄位逐項另計，重複衝突零。
這不是完整 GameState 的 100% 準確率。Single 分層只核對實際 DOM 顯示的
欄位；例如國王 icon 不能冒充 Ruler 兵數。ALLY（未出現）、Single 移動部隊、
部分 Shell/EMP 與真正 sensor hidden→visible 仍沒有足夠 live 覆蓋。

正常渲染的 positive Chopper 十兵種向量 300/300；路段所需 progress 30/30
去重版本，但後者均未加速且 required=72。debugger cohort 全部排除效能。
普通鏡頭 actor 缺席／恢復已見 14 組；sensor refs 全程正值，不能冒充 fog cycle。
本方 Satellite/Ews 場景 600 秒無 sensor loss/recovery；沒有延長相同靜態輪詢。

03d032d57e5b 全 600 秒有 4,767 筆、7.944 Hz、擷取 p95 7.745 ms，客戶端
套用保守上界 p95 205 ms。自然來源停滯 1.062 秒使 epoch UNKNOWN，不列
完整同局 PASS；14 支真實部隊撤銷 ID，後續 1,412 個部隊 facts 未復用 ID。
其中未知端點與 ETA 現在明確阻擋就緒。

最後目前版本 `f3f22dae0791`：600.073 秒、4,004 筆、6.673 Hz，擷取延遲
p95 6.998 ms，54,472 次來源 metadata 讀取、p95 2.301 ms。56 次拒讀／錯誤
保留，原摘要只列最前五項訊息。全程 NETWORK、同一文件；371 筆有 DERIVED
epoch，3,633 筆 UNKNOWN。世界序號 40092 停滯後，距最後觀察到的前進
1,062 ms 時撤銷 epoch。distinct_match_ids=2 是「原 epoch 與 None」，不是
兩場真實對局。只有 369 筆有客戶端套用區間，上界 p95 204 ms 只描述該
子集，不能代表全部 4,004 筆，更不能代表生成時間。

4,004 筆 coverage 均 PARTIAL，positive sensor slots 未全部對應當前已生成
actor，故完整覆蓋憑證未成立；沒有讀取隱藏 actors 補足。2,678 筆含部隊、
合計 4,179 個 force facts，ID 與 first-seen 全 UNKNOWN，追蹤數 0。
這不是穩定追蹤 PASS。有限離線核對未發現 unknown epoch 復用已知 ID、
未正向可見的 actor、已知端點指向未輸出塔、非 NETWORK 或逆序快照。
離線核對不是新增真實樣本。單一對局、完整覆蓋及權威年齡均不通過。

來源版本 manifest 全部與 SOURCE HEAD 的檔案吻合。可提交摘要與 UI inventory
在 `docs/V2_M1_FINAL_EVIDENCE.json`；原始 runtime JSONL 及研究檔留在本機、
gitignored。不能把推送摘要稱為推送全部原始紀錄。
最後 JSONL SHA-256：
`0ee08466bf5c9ae8ce127139960397741c7400677c4dd8a6e7691cd40314c1d1`。

## 時間來源假設的具體結論

共同 QUESTION：這條已定位的普通玩家來源，能否合法取得每份 Game 的
生成時間或具因果對應的可信年齡上界？下列 FAIL 限於各項具體假設。

| 支線 | EVIDENCE / CONCLUSION | STATUS |
|---|---|---|
| World.Singleton sequence | OBSERVED u16，正常更新／移動／換局／結果／reload／斷線已研究；非毫秒、非對局 ID，會 wrap。 | 世界版本語義 PASS；生成時鐘 FAIL |
| 客戶端套用區間 | DERIVED host clock bracket。不含未知排隊／傳輸前延遲。259d89778b11 持有已收到 Game 後才套用，得到生成至觀察的保守下界 ≥1,030 ms，而剛套用區間很小；debugger 樣本排除正常效能。 | 等同生成時鐘 FAIL |
| 插值／now_ms | 正式 Date/performance 來源與呼叫路徑是本機時間；不是每份 Game 的遠端時間。 | 直接生成時鐘 FAIL |
| bootstrap | 本機 nonce 來自 RNG；peer 值是未建立生成時鐘語義的 opaque marker。沒有輸出值或憑證。 | nonce 假設 FAIL；peer 語義 UNKNOWN |
| Game wrapper | 現行解碼為 checksum Option、九個 Vec descriptor 和 non-actor enum；沒有在這個布局證明生成時間。不是對所有可能編碼的不存在宣稱。 | 該布局的時鐘假設 FAIL |
| ACK | 序號／量化處理耗時供本機 RTT 修正，沒有特定 Game 的生成因果對應。 | 該 ACK 直接上界假設 FAIL |
| HTTP Date / x-held | Date 是回應日期；x-held 在正式程式扣除等待時間算 RTT。147 回應中 28 個有 x-held，缺席不填觀察零。生成／排隊／response wakeup 邊界未證明。 | 直接替代生成時鐘 FAIL；因果邊界 UNKNOWN |
| dateCreated | 正式 SessionCreated 保存路徑已定位；92 次正常讀取中世界 41 版本而日期不變。session metadata 不等於每份 Game 的生成時間。 | 每份 Game 時鐘假設 FAIL |

各支線的來源位址、正常呼叫路徑、版本與原 artifact 名稱詳見
`docs/V2_M1_TICK_EVIDENCE.md`；部隊純規則的有限分支證據詳見
`docs/V2_M1_FORCE_RULE_EVIDENCE.md`。無資訊增益的静態 sensor、鏡頭縮放與
零部隊等待已停止，没有以同樣輪詢消耗剩餘工時。

## UNKNOWN 與下一個唯一問題

UNKNOWN：權威生成時間／年齡、真正 server match ID、精確 launch time、
隱藏端點／未來路徑、歧義 force ID、部分升級／EMP 原因與最終命令合法性。
沒有把 first-seen、tick×250、RTT 或 HTTP header 直接填成權威時間。

下一個唯一最重要問題：官方每份 Game 更新，能否合法提供生成時間或
可驗證的因果年齡上界？未取得前，不能放行 M2／M3。

沒有證據表明只有違反 M0 才能解決。官方增加普通玩家可用的 metadata
或提供可核對的服務端語義，是合法但不在目前已取得來源內的可能方案。
讀 fog/private actors、改 heap 偽造時間、packet 注入或系統安全繞過均不符合
契約，而且沒有證明能補上可信生成來源；本次未採用。

## 程序與版本收尾

最後 sampler exit=0，專用 host 透過正常停止旗標完成 finally 並 exit=0。
專用 profile Chromium PID 清單空、host lease 已移除；清查無研究 Python
或 Playwright Node 殘留。核對工具的 Windows venv redirector 隨核對結束退出。
保留 Node PID 7552：Codex 管理的 `cua-repl.mjs` 工具服務，不是研究瀏覽器
或 probe；沒有停止應用程式的工具基礎設施或其他使用者程序。

main 檢查值為 `234cfad918381adfd2a48a183ca17d35b64970e0`，本輪未修改。
最後停止報告只提交及推送 `origin/v2-rebuild`。END HEAD 與 PUSHED 的實際
核對值由最終回報列出，避免文件自我引用尚未產生的 commit hash。
