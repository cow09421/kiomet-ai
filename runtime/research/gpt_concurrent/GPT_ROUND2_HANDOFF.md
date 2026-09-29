# GPT ROUND 2 HARD-PROBLEM REPORT（第二輪高難題交接）

## P0 UPGRADE STATE（升級狀態）

| 項目 | 結果 |
|---|---|
| Source Semantics（來源語意） | **PASS（通過）**：玩家塔數量為 `NonActor.tower_counts: TowerArray<u16>`（非演員更新中的固定塔型數量陣列），伺服器更新時替換，封頂 65535，**不計正在升級的塔**；候選由目前塔型的直升關係、己方擁有權與延遲共同決定 |
| Production Mapping（正式版對映） | **PASS（靜態）**：573 寫塔型／延遲；448 遞減與電磁脈衝設定；6044 查塔型延遲；2425／789 比前置條件；460 驗證升級命令；3492／1242 用戶端候選及數量讀路 |
| `tower_ref+47` type（型別） | 1 位元組 `Option<NonZeroU8>`（可為空的非零 8 位元整數）：0＝無延遲，1..255＝剩餘節拍 |
| `tower_ref+47` unit（單位） | tick（更新節拍）；每秒 4 tick，1 tick＝0.25 秒 |
| `tower_ref+47` semantic（語意） | 塔的通用暫停倒數：升級建造延遲或電磁脈衝暫停，非單一用途的升級冷卻 |
| `tower_ref+47` readers（讀取者） | 448／`0x01A619`；460／`0x02E2E6-0x02E2EE`；3492／`0x139D34`；另有複製／比較用途 |
| `tower_ref+47` writers（寫入者） | 573／`0x07D4E8` 從 6044 塔型延遲表設定，正式表最大 160 tick；448／`0x01A627` 每 tick 減 1，`0x01B10C` 電磁脈衝寫 `max(old,240)`，`0x01B257` 清 0；1539 僅複製塔結構 |
| Player Tower Counts（玩家塔數量） | **PARTIAL（部分完成）**：27 格、每格 `u16`（16 位元無號數）、索引 `base+2*TowerType enum`（基底＋塔型列舉值乘二）已確定；用戶端根指標的非偵錯器取得方式未確定 |
| Count Structure（數量結構） | 用戶端回呼 1242 第一參數 `root+592..+645`；命令驗證函式 460 在 `root+45092` 指向的 184 位元組玩家記錄中讀 `record+128..+181`；兩路都傳給 2425 |
| Count Index Rule（索引規則） | `TowerType`（塔型）為 `repr(u8)`（8 位元列舉），有效值 0..26；第 `i` 格位於 `base+2*i`；27 是迭代哨兵。完整名稱與索引見 `GPT_UPGRADE_LAYOUT.json` |
| Persistent Read Path（持久讀路） | **根相對路徑已找到**：1242 的 `root+592`；3492 透過閉包中的 `root` 傳給 2425，1242 亦複製同 54 位元組給介面。缺少現有觀察器能安全取得 `root` 的證據；不可沿用跨局絕對位址 |
| Upgrade Mirror（升級離線鏡像） | **PASS（來源規則）**：`upgrade_state_mirror.py` 對 19 條來源升級邊完成 77/77 檢查；輸出候選、缺額、按鈕顯示／啟用狀態。等級／解鎖資料缺席時，直接送命令結論為未知 |
| Can Observer derive upgrade state without UI?（觀察器能否免介面推算） | **PARTIAL（部分完成）**：資料及規則足夠，但現有安全通道尚未證明能取得當局的 `root+592` 數量陣列；若可讀，無須反覆點塔 |
| Remaining Unknown（未解事項） | 安全取得用戶端根指標的方式；460 玩家記錄 `+128` 的完整寫入鏈；玩家／對局切換後指標重錨；真實執行期的數量對照 |

### P0 成功級別

- Level 1 `UPGRADE_SOURCE_SEMANTICS = PASS`（來源語意通過）。
- Level 2 `UPGRADE_PRODUCTION_MAPPING = PASS`（正式版靜態對映通過）。
- Level 3 `PLAYER_TOWER_COUNTS_LAYOUT = PARTIAL`（數量布局部分完成：相對偏移、寬度、索引確定，根指標取得未解）。
- Level 4 `UPGRADE_OFFLINE_MIRROR = PASS`（來源規則離線鏡像通過）。
- Level 5 `RUNTIME_GROUND_TRUTH = NOT VALIDATED`（真實執行期未驗證；本輪明令禁止接觸）。

## P1 MOVING FORCE（移動兵力）

| 項目 | 結果 |
|---|---|
| Started（是否開始） | **NO（否）**。P0 的安全根指標仍未解，依本輪優先順序未展開 P1 新研究 |
| 2031 → Force Copy（2031 到兵力複製） | 沿用第一輪靜態結果：1791／`0x10041C` 把 7 位元組寫在暫存 `sp+17..23`；`0x10047B`／`0x100482` 複製到由 `sp+24` 開始的 `Force`（移動兵力）結構 `+14..20` |
| Force Collection（兵力集合） | 來源碼 `Tower.inbound_forces`／`outbound_forces`（塔的入站／出站兵力集合），正式版持久集合的指標路徑未展開 |
| Force Entry（兵力項目） | 來源碼 `Force`（移動兵力），正式版完整布局未展開 |
| Units Offset（兵種偏移） | `Force+14..20`，**靜態已確認** |
| Owner / Source / Target / Path / Progress / World Position（擁有者／起點／終點／路徑／進度／世界位置） | 本輪未展開；不可把來源碼型別直接宣稱為正式版布局 |
| Static Layout（靜態布局） | **NOT STARTED（未開始完整 P1；僅保留第一輪已知的兵種偏移）** |
| Runtime Validation（執行期驗證） | **NOT AVAILABLE（不可用）** |

## Muse Exact Next Validation（Muse 下個精確驗證）

若 Muse 的**既有**唯讀狀態通道能取得當前用戶端回呼根指標，在同一個對局與更新世代讀 `root+592` 起的 54 位元組，按 27 個小端序 `u16`（16 位元無號數）解碼，並選擇一筆**自然出現**的官方升級介面進度（例如工廠 `0/2` 或村莊 `1/3`）逐格對照；同時核對塔 `+46` 塔型、`+47` 延遲與自我擁有權。若現有通道無法取得根指標，保留 Level 3 為 PARTIAL（部分完成），不為此研究附加偵錯器或操控遊戲。

## 交付檔案與安全狀態

第二輪產物：`GPT_UPGRADE_SOURCE_SEMANTICS.md`、`GPT_UPGRADE_PRODUCTION_ANALYSIS.md`、`GPT_UPGRADE_LAYOUT.json`、`GPT_UPGRADE_MIRROR_REPORT.md`、`upgrade_state_mirror.py`、`inputs/source_expected_graph.snapshot.json`、`tools/read_wasm_data.py`。靜態反組譯證據在 `dumps/` 與 `dumps/local/`。所有新檔案均位於 `runtime/research/gpt_concurrent/`。

本 GPT 工作流的 `sent_actions=0`、`MOVE_FORCE=0`、升級行動 0；未連接執行期／瀏覽器、未修改正式追蹤檔、未提交。Muse 的同步工作狀態不由本輪靜態研究推斷。
