# GPT ROUND 5 HARD-PROBLEM REPORT（第五輪高難題交接）

分析方式：公開原始碼 → 本地編譯版 WASM（網頁組件）函式名稱 → 正式版 WASM（網頁組件）反組譯與資料段。未連線、未操作遊戲。正式版與公開原始碼有可證實差異，故每項分開標示靜態與執行期狀態。

## P0 BATTLE（戰鬥）

| 項目 | 結果 |
|---|---|
| Battle Entry（戰鬥入口） | **PASS（通過）**：正式版 `448` 到站後在函式內展開塔戰；路上對向部隊 `788→522`；`1845` 判抵達 |
| Friendly Merge（己方合併） | **PASS（靜態）**：關係友善、續行不成立時由 `2195` 加入塔；一次性兵種略過，超容量部分捨棄，玩家塔允許暫時超量 |
| Neutral Capture（中立佔領） | **PASS（分支靜態）**：空塔須有可佔塔活兵力才探索；有中立守軍先戰鬥；攻方勝且有玩家編號才轉塔主，僵持可能使塔失主 |
| Enemy Combat（敵方戰鬥） | **PARTIAL（部分）**：輸入、戰鬥核心、存活檢查、塔主更新與寫回定位完成；正式版士氣／完整逐步傷害尚未全部解碼 |
| Shield（護盾） | 攻塔部隊護盾由 `4969` 清掉；守塔護盾參與戰鬥；塔型與國王影響容量 |
| Ruler（國王） | 帶國王抵達盟友塔被視為不友善；最後上場，失去時發事件；國王給塔護盾容量加 10（來源碼） |
| Special Units（特殊單位） | Shell（砲彈）、Emp（電磁脈衝）、Nuke（核彈）一次性；正式版 `1347/1348` 處理消耗與事件，EMP 可寫塔延遲；精確逐兵種正式版結果仍待驗 |
| Production Functions（正式版函式） | `448,522,788,1845,690,2689,1778,2022,2408,2827,1347,1348,1888,2195,3571,732`；完整輸入／輸出／讀寫／呼叫圖見 `GPT_BATTLE_FUNCTION_MAP.json` |
| Combat Tables（戰鬥資料表） | **PASS（原始值）**：`732` 讀取 22 列 × 10 個 u32 容量，正式版靜態資料段位址 `1362240..1363119`，22／22 列對上來源容量；見 `GPT_COMBAT_TABLES.json`。塔型跳轉與五類特殊分支仍待逐支追完 |
| Offline Battle Mirror（離線戰鬥鏡像） | **PARTIAL（未建立）**：正式版多出 `1778` 士氣與 `+21/+45` 旗標條件。公開版確定性演算法不足以保證正式版預測，不提供假精確答案 |
| Static Validation（靜態驗證） | 函式呼叫圖、偏移與資料段抽取已驗；正式版演算法完整性仍 PARTIAL |
| Runtime Validation（執行期驗證） | **NOT AVAILABLE（無法取得）**：本輪禁止連線 |

關鍵證據：`vendor/kiomet-ref/common/src/chunk.rs:310-502`、`combatants.rs:105-366`、`units.rs:272-284`；正式版 `func-448.txt:0x01a9ae,0x01acc6..0x01b0ef,0x01b21d,0x01b458`；`func-1778.txt:0x0ffab8..0x0ffb52`。詳細見 `GPT_BATTLE_SOURCE_SEMANTICS.md` 與 `GPT_BATTLE_PRODUCTION_ANALYSIS.md`。

P0 等級：Level 1 Battle Entry（戰鬥入口）PASS（通過）；Level 2 Source Semantics（來源語意）PASS（通過）；Level 3 Production Mapping（正式版對照）PASS（主要路徑）；Level 4 Damage/Resolution（傷害與結果）PARTIAL（部分）；Level 5 Offline Mirror（離線鏡像）PARTIAL（未建立）。

**Muse 整合步驟**：先在既有真實觀察器提供同世代塔主、塔型、`+45`、守軍 Units（兵力）、入站部隊 `+21` 與兵力；用真實抵達前後案例校驗士氣造成的初始累積傷害偏移；依正式版順序完成鏡像後再讓規劃器使用。此之前，守軍中立塔的勝負預測回報 UNKNOWN（未知）。

## P1 THREAT（威脅）

- Force Speed Rule（部隊速度規則）：**PASS（靜態）**；普通組合取最慢；Chopper（直升機）用 `4*C` 運載量、Tank（坦克）重量 2、Soldier（士兵）重量 1，依總重量決定 3／2／1 進度每節拍。來源 `force.rs:289-329`，正式版 `690` 對應。
- ETA Formula（預估抵達公式）：**PASS（當前路段靜態）**；`required=min(255,floor(distance*180/10))`，`Force+21==1` 時改 `max(1,floor(required*4/5))`；`ETA_ticks=ceil(max(0,required-progress)/speed)`，`ETA_seconds=ETA_ticks/4`。多段需假設兵力、路徑與旗標不變。
- IncomingThreat Contract（入站威脅資料契約）：**PASS（規格）**；含識別、所有者與關係、路徑、兵力、進度、座標、ETA（預估抵達時間）、投影、信心及時效，見 `GPT_THREAT_DATA_CONTRACT.md`。
- Battle Projection（戰鬥投影）：**UNKNOWN（未知）**，受 P0 正式版差異所限。整體狀態 **PARTIAL（部分）**。
- **Muse 整合步驟**：先在同世代快照對入站／出站鏡像去重，計算當前路段 ETA（預估抵達時間），再附塔守軍與投影未知原因；不要臨時發明威脅等級。

## P2 DEFENSE（防守）

- SELF→SELF Reinforcement Legal（己方塔增援合法性）：**YES（來源碼命令語意可行）**；`DeployForce` 沒有中立目標限制，路徑搜尋可到己方塔，抵達後進入續行或合併。正式伺服端接受狀態 **UNKNOWN（未知）**；來源資料未含伺服端驗證實作。
- Defensive Action Types（防守行動類型）：己塔增援、國王轉移、己塔升級、反攻敵來源、設定補給線；各自前提與非立即效果見 `GPT_DEFENSIVE_ACTION_SPACE.md`。規格狀態 **PASS（通過）**，實行狀態尚未驗收。
- **Muse 整合步驟**：另增 `REINFORCE_SELF`（增援己方塔）提案類別；留著既有中立擴張的安全條件；送前核對拖曳未被選取塔狀態改成補給線命令，送後以部隊與塔兵力驗證。

## P3 FORCE DELTA CAPTURE（移動部隊差分捕捉）

- Before/After Algorithm（前後算法）：T0 保存同局完整兩側集合及路徑／兵力副本 → 記唯一行動識別與實際派送時間 → T1 立即再讀、T2 跨節拍再讀 → 多重集合差分 → 以來源、目標、完整入站路徑、所有者、兵力與進度一對一配對 → 對照來源塔兵力減少及畫面。詳見 `GPT_FORCE_DELTA_CAPTURE_RECIPE.md`。
- Expected Runtime Evidence（預期執行期證據）：唯一新入站 Force（移動部隊）、對應出站鏡像、進度沿路增加、來源兵力下降、相同對局／時間與同時刻畫面；有歧義一律不升級為已驗證自主操作。
- **Muse 精確整合步驟**：在下一筆已授權自主派兵的觀察器加 T0/T1/T2 只讀快照和差分紀錄，沿用 24 位元組 Force 與塔 `+0/+12` 集合布局；先收三組畫面／記憶體真值校正，再接強驗證。此輪實作狀態為**配方完成，執行期未測**。

## P4 UPGRADE ROOT（升級根路徑）

**NOT STARTED（未開始）**：依本輪 P0→P3 順序，保留既有 `GPT_UPGRADE_ROOT_ACCESS.md` 的 PARTIAL（部分）狀態，不重新研究升級規則。

## 至多五項突破

| BREAKTHROUGH（突破） | EVIDENCE（證據） | CONFIDENCE（信心） | WHY IT MATTERS FOR PVP（對玩家對戰的價值） |
|---|---|---|---|
| 戰鬥核心在正式版 `448` 內聯，路上交戰另在 `522` | 呼叫圖與 `448` 的選兵／傷害／塔主寫回指令 | 高 | 可在玩家對戰前後定位真實結果，避免誤用舊版函式 |
| 正式版增加士氣偏移，公開版鏡像不等價 | `1778` 計算 `min(3,floor(非一次性兵數/2))`；`448` 依 `+21/+45` 把初始累積傷害設為正、負或零 | 高（分支與數值）；中（旗標實體意義） | 阻止規劃器低估或高估有守軍塔 |
| 空中立塔與有守軍中立塔是兩條路 | `chunk.rs:310-430` 與正式版 `448:0x01ab59..0x01ac38` | 高 | 中立擴張能區分探索與攻塔 |
| 正式版容量原始值已抽出 | `732` 靜態資料段 22×10 u32 | 高（原值）；中（塔型標籤） | 增援與戰後合併可以避免把超量兵力當有效防守 |
| 己塔可作派兵目標 | `protocol.rs:18-39`、`world.rs:300-313`、`chunk.rs:433-479` | 高（來源碼）；正式伺服端未知 | 防守規劃器可增加增援而非只攻擊 |

## 安全結尾

Runtime connections（執行期連線）= **0**；Chromium connections（瀏覽器連線）= **0**；Actions sent by GPT（本工作流發送行動）= **0**；Tracked files modified（正式追蹤檔修改）= **0**；Git commits（版本提交）= **0**。所有本輪新檔案均在 `runtime/research/gpt_concurrent/`。歷史 Verified Autonomous Actions（已驗證自主行動）仍 **0**。
