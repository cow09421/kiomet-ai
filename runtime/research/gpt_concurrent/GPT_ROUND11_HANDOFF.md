# GPT Round 11 時間序與 PvP 紅隊交接

## 範圍與結論

本輪完全離線靜態分析。沒有連 Chromium（瀏覽器）、CDP（Chrome 開發者工具協定）或偵錯器，沒有讀執行期記憶體，沒有操作遊戲、派兵或升級，也沒有停止／重啟 Muse。所有新增檔案都在 `runtime/research/gpt_concurrent/`。

最高層順序已從保存的 Server Reference（伺服器參考來源）重建：

```text
伺服器 post_update 邊界清理／先前淘汰
→ world.tick_before_inputs：tick 遞增、halt/同盟標記處理
→ 依 ChunkMap 與固定 Tower 陣列順序逐塔：
   塔計時／生產／自動派兵
   → Force 對 Force 道路碰撞
   → inbound Force 進度與逐支 Tower 抵達／戰鬥／塔主寫回／合併或續行
   → outbound Force 進度與抵達移除
   → Vec 壓縮
→ Server tick 的玩家摘要更新
→ world.tick_after_inputs 套用排隊的 ChunkEvent
```

`TowerService::post_update` 在 `world.tick_before_inputs` 前先清 inbox、處理先前累積的 `maybe_dead`，再做週期性清理；`TowerService::tick` 在套用排隊 ChunkEvent 後更新玩家摘要。伺服器 `player_command` 會立即從來源塔取兵，但其出站／入站 ChunkEvent 要等 `tick_after_inputs` 才加入集合；該 Force 不會回頭參與已完成的本輪塔掃描。

## TEMPORAL ORDERING（時間順序）

**Top-Level Tick Order（最高層節拍順序）**：`TowerService::post_update` → `World::tick_before_inputs` → 玩家／命令週期 → `TowerService::tick` → `World::tick_after_inputs`。伺服器來源定義 4 ticks/s（每秒 4 節拍）。

**Force Movement Phase（部隊移動階段）**：部隊速度與路段進度以整數 tick 推進。入站 Force 的到達檢查在塔掃描時進行；出站鏡像在抵達／戰鬥處理後推進並於到點移除。

**Collision Phase（碰撞階段）**：每座塔先看 `inbound_forces`，再逐支遍歷 `outbound_forces`；用目前與下一 tick 的進度區間檢查反向道路重疊，並立即修改兩支部隊。這在塔抵達處理前。

**Arrival Phase（抵達階段）**：入站 Vec（向量）用 `extract_if` 逐支檢查進度；抵達 Force 按當下 collection index（集合索引）處理。

**Combat Phase（戰鬥階段）**：每一支敵對 Force 單獨對上前一事件留下的 Tower units（塔兵力）；不先合併多支敵軍。Tower owner（塔主）、兵力和戰鬥事件都在此分支內立即寫回。

**Owner Writeback Phase（塔主寫回階段）**：第一支 Force 完成 owner setter 後，下一支到達才重新讀塔主；第二支使用新塔主。這是 Server Reference 的靜態結論，正式伺服器尚未執行期差分。

**Deferred Events（延遲事件）**：`ChunkEvent`（區塊事件）先排入 inbox，等 `tick_after_inputs` 套用；`InfoEvent`（資訊事件）回呼同步執行。`LostRuler`（國王陣亡）會將玩家加入 `maybe_dead`，淘汰清理在後續 `post_update` 邊界執行。`maybe_dead` 是集合，不是 FIFO（先進先出）佇列。

- **Same-Tick Force Ordering（同節拍部隊排序）：PARTIAL**。來源證實按目標塔目前入站 Vec 順序處理；沒有 Force ID（部隊識別碼）、ETA、owner 或建立時間排序。索引只是當下快照位置，壓縮後會改變。生產版對映是靜態結構對映，未以正式伺服器執行期驗證。
- **Reinforcement vs Enemy Same Tick（援軍與敵軍同節拍）：ORDER_DEPENDENT（順序相依）**。沒有援軍優先規則。索引缺失或驗證未完成時，DefenseEvaluator（防守評估器）應 ABSTAIN（暫不行動）。
- **Multiple Enemy Forces（多支敵軍）：**依向量順序逐場戰鬥，每場沿用先前塔兵力／塔主寫回；不可把 A+B 合成一支再算。
- **Multiple Reinforcements（多支援軍）：**依向量順序逐支做移動、合併或後續分支；每一個中間容量結果都必須精確，不能把援軍批次加總。
- **Owner Flip + Arrival（塔主切換加後續抵達）：**後一支在事件執行時重讀新 owner；Neutral（中立）被第一支佔領後，第二玩家的 Force 會依新塔主進入友軍或敵軍分支。
- **Force Collision + Arrival（部隊碰撞加塔抵達）：**碰撞先處理；若入站 Force 在碰撞中被移除，同 tick 不再進塔戰；存活者才繼續到達處理。
- **Tower delay（塔延遲）：**每塔的 delay 會先遞減並跳過該 tick 生產／衰減。保存伺服器來源未找到全域遊戲暫停倒數；不可把 Tower.delay 當全域 Pause（暫停）。

**Temporal Model（時間序模型）：PARTIAL（部分完成；36/36 靜態案例通過）**。這是單塔、顯式集合索引和靜態戰鬥／合併 fixture（測試資料）的排序模型；不模擬連續移動、戰鬥算術、正式容量計算或網路排程，也不代表正式遊戲驗證。

## Source → Local → Production（來源→本地→正式版）對映

- **SERVER_REFERENCE（伺服器參考來源）**：`runtime/research/source-map/kiomet-local/server/src/service.rs` 與共用 `common/src/world.rs`、`common/src/chunk.rs`。本地保存來源來自 commit `d3f0956f27f48f6cac9ac9991f948fa7f90ba77c`。
- **CLIENT_PRODUCTION（正式客戶端）**：保存的 `production-client_bg.wasm` 與 page snapshot（頁面快照）SHA-256 相同；現有 R8 對映把函式 448 對到 `World::tick_before_inputs`，並把 1393 對到 `tick_after_inputs`／事件插入。保存本地重建 WASM（網頁組件）雜湊不同於正式版，因此只主張函式結構對映，不主張二進位相同。
- 官方伺服器二進位身分未從靜態資料確立，故 Server Reference 與 Client Production 沒有混為同一證據。

## PVP RED TEAM（玩家對玩家紅隊）

- 對抗性案例：**60**
- PASS（Round 10 契約已有該安全拒絕）：**15**
- FAIL（Round 10 契約仍缺安全保證）：**45**
- 嚴重度總案例：CRITICAL（嚴重）30、HIGH（高）24、MEDIUM（中）6、LOW（低）0。其中特定 FAIL 為 CRITICAL 24、HIGH 18、MEDIUM 3。

15 個 PASS 來自 Round 10 對未知兵力／擁有者／光環／護盾／塔型的嚴格拒絕、浮點 ETA 拒絕、邊際勝利不攻、Ruler（國王）和特殊兵種不支援。同節拍援軍的單一 ETA 案例也會安全拒絕；這不能解決多支援軍的組合順序。

**Critical Vulnerabilities（嚴重漏洞）**

1. 沒有派送前版本權杖與共用保留：世界／塔主／來源兵力／對局切換後，舊 Proposal（提案）可能被重用；不同 Planner（規劃器）也可能雙重花費同一支部隊。
2. 沒有來源塔派兵後安全閘門：增援或穩健攻擊可以救／打贏目標，卻讓來源塔被已知威脅攻下。
3. 同目標多敵軍尚未逐場串接：只守住第一場不能代表第二支敵軍已解除；若重用舊塔兵力或舊 owner，會誤報安全。

另有 VERIFY-IN-FLIGHT（驗證中）重送、同目標重複派送、光環或鏡頭座標版本過期及容量 fixture（測試資料）可信度等 HIGH／MEDIUM 缺口。詳見 `GPT_PVP_RED_TEAM_MATRIX.json`。

## 新增契約狀態

- **Source Safety Gate（來源塔安全閘門）：PARTIAL**；研究契約已完成，尚未整合到 Muse，也未做執行期驗證。
- **Multi-Threat Evaluation（多威脅評估）：PARTIAL**；定義逐支排序與寫回，正式版抵達索引與多事件分支仍待驗證。
- **Action Validity Token（行動有效性權杖）：PASS（契約完整）**；規定七個版本欄位、派送前逐一比對與原子保留；不是已上線的 Runtime（執行期）程式。
- **Temporal Support Matrix（時間序支援矩陣）：PASS**；未支援／順序相依情境都要求安全拒絕。

## Q1–Q6

**Q1：同節拍敵軍與 SELF reinforcement 誰先，能否可靠判斷？PARTIAL。** 保存伺服器來源可由目前入站 Vec index 判斷逐支順序，但沒有援軍類別優先權；Muse 現有輸入沒有可靠的正式版索引／差分證明，故同 tick 必須 ABSTAIN。

**Q2：兩支敵軍同 tick 打同一塔怎麼結算？PARTIAL。** Server Reference 是按向量索引逐場戰鬥，不預先合併；每場立即寫回塔兵力與 owner。若沒有確切集合順序和每場中間狀態，不可預測正式結果。

**Q3：第一支改變 owner 後第二支看舊還是新 owner？PARTIAL。** 靜態伺服器來源明確是新 owner；正式伺服器與保存客戶端對映仍待差分，且第二支戰鬥輸入要重算。

**Q4：Round 10 可能穩定做錯的 CRITICAL／HIGH 案例：**派兵後來源塔失守、攻擊後來源塔失守、同一來源雙重派兵、派送前目標／來源／對局已變、同目標重複救援／攻擊、第二支敵軍到達而首戰被錯當解除。HIGH 另含同節拍第二援軍、光環或鏡頭座標過期與容量合併依賴呼叫端不可信旗標。

**Q5：三個新契約能否避免已知最大送頭漏洞？PARTIAL。** 若真正接入執行器，可擋已知來源塔被抽空、過期提案和已知多威脅漏算；但還要取得新鮮的入站順序、完整觀測與正式版差分，並維持 R8–R10 的戰鬥支援閘門。

**Q6：Muse PvP v0 最需要的三個閘門：**(1) Source Safety Gate（來源塔安全閘門）；(2) Multi-Threat Defense（多威脅逐場防守）；(3) Action Validity Token（行動有效性權杖，包含單次原子花費與驗證中鎖定）。

## Runtime Validation Recipe（執行期驗證配方；本輪只列方案）

未連接或執行任何測項。Muse 日後應在與目標正式版相符的隔離測試環境做最少下列受控樣本，逐 tick 保存入站／出站 Vec 索引、完整 Force 欄位、Tower owner／units、Combat／GainedTower／LostTower InfoEvent（戰鬥／取得塔／失去塔資訊事件）與前後快照：

1. 同一非空 SELF Tower（己方塔）安排一支援軍與一支敵軍同 tick 到達，按「援軍先入 Vec」與「敵軍先入 Vec」各跑一次。確認兩次結果隨目前索引改變，第二事件讀到第一事件寫回後的 owner／units。
2. 同一塔安排兩支敵軍同 tick 抵達；記錄第一、第二場分別的守軍與塔主，確認是兩場 sequential combat（依序戰鬥），不是合併輸入。另一受控空中立塔案例安排兩個不同玩家同 tick 抵達，檢查第一支佔領後第二支的關係分支。
3. 同一塔安排兩支己方援軍同 tick 抵達，確認每支到達時的索引、合併容量與中間守軍；調換集合順序再比對。
4. 用反向道路 Force 碰撞安排一支 Force 在同 tick 抵達 Tower；觀察碰撞事件先後與碰撞失敗者是否完全跳過塔戰。
5. 驗證事件邊界：世界掃描中產生的新 ChunkEvent 何時加入集合，`tick_after_inputs` 新增 Force 是否到下一次世界掃描才移動；再用第二個 Ruler 案例單獨確認淘汰延遲邊界。Ruler 案例只確認事件次序，不啟用普通 PvP。

每個樣本只授權相同正式版雜湊、分支、塔型與順序規則；任一不符都保持 `RUNTIME_VALIDATION_NEEDED`（需要執行期驗證）或 `UNSUPPORTED_TEMPORAL_CASE`（不支援的時間序案例）。

## 驗證與安全結尾

- 時間序案例：**36/36 PASS**（排序模型與 fail-closed 拒絕測試）。
- Round 10 PvP 靜態案例：**25/25 PASS**；R8 包裝回歸：**51/51 PASS**。
- Round 11 PvP 紅隊矩陣：**60 案例，15 PASS／45 FAIL**；FAIL 表示 Round 10 契約缺口，不表示實際遊戲操作。
- Runtime connections（執行期連線）= **0**
- Browser connections（瀏覽器連線）= **0**
- Game actions（遊戲行動）= **0**
- Tracked files modified（Git 追蹤檔修改）= **0**
- Git commits（Git 提交）= **0**
