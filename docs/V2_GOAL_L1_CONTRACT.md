# KIOMET AI v2 — CODEX GOAL MODE FINAL CONTRACT
# （Kiomet AI v2 — Codex 目標模式最終契約）

你現在不是來完成一個下一步任務，也不是來完成單一 P0。

你的 Goal（最終目標）是：

在 `E:\SteamLibrary\kiomet` 中，
自主地把 Kiomet AI v2 推進到以下三種外部狀態之一：

1. SUCCESS（成功）
2. ABORT（確定無法在契約內完成）
3. PAUSED（因人類／外部環境阻塞而暫停，可恢復）

除非到達以上三個狀態之一，
不要因為：

- 做完一個 P0
- 寫完一個功能
- 得到一份研究報告
- 遇到普通 bug
- 某個假設被證偽
- 下一步存在多個選項

就停止工作或詢問使用者。

普通工程決策由你自主完成。

全程與使用者以繁體中文交流。
使用較專業的英文術語時，在後面附上繁體中文解釋。

======================================================================
一、啟動這份 Prompt 即視為 L1 授權
======================================================================

Operator authorization（操作者授權）：

使用者把「本提示詞原文」交給 Goal Mode 並啟動，
即視為正式授權本文【L1 AUTHORIZED SPEC】中的：

- Baseline suite（基準套件）
- Benchmark distribution（基準分布）
- V utility（V 效用）
- V thresholds（V 門檻）
- Fallback policy（後備策略）
- Live Loop thresholds（實機閉環門檻）
- Operational constraints（操作限制）
- Global resource pool（全域資源池）

這些值從 Goal 啟動起即屬 L1。

你 MAY（可以）在任何 Planner outcome（規劃器結果）被看見之前，
只往更嚴格方向修改：

- 新增 baseline
- 新增 benchmark stratum
- 提高 threshold

你 MUST NOT（禁止）：

- 刪掉較難 baseline
- 縮窄 benchmark
- 降低 threshold
- 放寬 fallback
- 因為結果不漂亮而修改 L1

需要放寬 L1 → PAUSED，要求人類明確授權。

======================================================================
二、專案位置與 Git 基線
======================================================================

Repository：

E:\SteamLibrary\kiomet

主要工作 branch（分支）：

v2-rebuild

`main`：

v1 archive（v1 封存）

已知 archive commit：

234cfad918381adfd2a48a183ca17d35b64970e0

你 MUST NOT：

- 修改 main
- merge 到 main
- rebase main
- force push
- 改寫已 push／freeze 的歷史

開始時先自行確認實際：

- current HEAD
- branch
- git status
- remote
- tags
- tests
- runtime artifacts

最近已知 v2 HEAD：

65e9b462676e4e5fa317b37f05a1e22f7ebc0d40

這只是 orientation（定位資訊），不是 reset target。

若實際 HEAD 已前進：

MUST NOT 自動 reset 回這個 commit。

先判斷目前 repository 真實狀態並繼續。

既有兩份長期未追蹤筆記：

docs/V2_M2A_REGISTERED_MOUSE_QUEUE_CONSUMER_REVIEW.md
docs/V2_M2A_TS_CAPACITY_CONTEXT_REVIEW.md

除非它們已被使用者另外處理，
MUST NOT 刪除、覆寫或擅自納入 production。

GitHub push：

優先使用本機既有 Git Credential Manager
（Git 憑證管理員）。

不要：

- 開瀏覽器要求登入
- 使用 GitHub Desktop
- 印出 token
- 要求人類手動貼 token

只有既有認證真的失效／不存在時，
才屬 human-only access（人類專屬存取）並進 PAUSED。

======================================================================
三、真正的完成條件
======================================================================

Completion（完成）只有：

V ∧ L

且 Fairness / Action Integrity Invariant
（公平／行動完整性不變條件）

全程沒有未處理的破口。

一旦 Final Cycle（最終評估週期）確認：

V = PASS
L = PASS
Invariant = INTACT

你 MUST 立即：

SUCCESS

並停止所有延伸開發。

禁止：

「順便改善」
「再讓 AI 強一點」
「再補幾個 mechanic」
「再整理架構」

一個 100 行 heuristic bot（啟發式 Bot）
如果合法通過 V 與 L，

就比一個未通過的 10,000 行 world-model planner
（世界模型規劃器）

更接近本 Goal 的正確答案。

MPC（模型預測控制）、
Beam Search（束搜尋）、
MCTS（蒙地卡羅樹搜尋）、
Neural Network（神經網路）、
GPU、
Rust

全部都不是完成條件。

======================================================================
四、Fairness / Action Integrity Invariant
======================================================================

Planner、baseline、benchmark：

MUST 只使用：

正常玩家在當下可見／可知的資訊。

允許：

- current player-visible structured state
- 玩家正常可看到的 UI/state
- 只由正常玩家可見資料推導的 derived state
- public source（公開原始碼）理解 static mechanics（靜態規則）

禁止 production 使用：

- hidden enemy state
- server-private information
- future information
- 玩家不可見 enemy topology
- packet injection（封包注入）
- direct WASM semantic invocation（直接 WASM 語意呼叫）
- heap injection（記憶體堆注入）
- global keyboard/mouse injection（全域鍵鼠注入）
- PyAutoGUI
- pynput
- SendInput
- SetCursorPos
- physical cursor stealing（搶實體游標）
- SwitchDesktop
- production multi-account self-play（正式環境多帳號自我對戰）

Production action（正式行動）：

MUST 走：

official UI / official client action path
（官方 UI／官方客戶端正常行動路徑）。

研究中若 structured source（結構化來源）混有可見＋不可見資訊：

MUST 在進 Planner 前 filter（過濾）。

UNKNOWN 必須保持 UNKNOWN。

禁止：

fake 0
fake success
fake causality
fake exact state

Fairness violation（公平違規）：

受影響證據 = VOID（作廢）。

若所有公平合法 action path
在架構上都不可達：

ABORT。

======================================================================
五、L1 HARD：零輸入／焦點干擾
======================================================================

以下已由使用者正式授權為 HARD CONSTRAINT
（硬限制）。

Production MUST：

1. 使用專用隔離 Chromium＋獨立 profile。
2. MUST NOT 讀使用者日常瀏覽器 profile／cookie／credential。
3. MUST NOT 移動實體滑鼠。
4. MUST NOT 使用全域鍵盤／滑鼠注入。
5. MUST NOT 搶使用者視窗焦點。
6. MUST NOT 強制視窗前景化。
7. MUST NOT SwitchDesktop。
8. Production action MUST 使用 page-level
   Playwright／CDP 輸入，例如 Input.dispatch* 或等價官方頁面輸入。
9. Chromium 預設靜音。
10. 擷圖只能取得遊戲 page-level 內容，
    MUST NOT 擷取使用者桌面其他內容。

違反：

立即停止該 session。

該 session 不可算 L 證據。

先當 ordinary bug（普通 bug）自主修復。

若所有符合上述 HARD 限制的 action channel
都被證明不可行：

ARCHITECTURE_BLOCKED：

ACTION-CHANNEL

進 REDESIGN。

所有適用 ACTION-CHANNEL 路徑耗盡：

ABORT。

不要自行放寬。

======================================================================
六、V — Decision Value（決策價值）
======================================================================

V 不要求：

完整 simulator。

V 要求：

Planner 在獨立、凍結、具代表性的 Final benchmark
（最終基準評估）

上，

相對所有凍結 baseline
有可測量的決策價值。

V 必須同時：

1. 勝過 B0
2. 勝過 B1
3. 勝過 B2
4. catastrophe rate（災難率）不超標
5. uncertainty declaration（不確定性宣告）涵蓋率達標
6. Planner 不能靠大量 fallback／abstain 假通過

全部 decision states 留在分母。

若 Planner：

UNKNOWN
ABSTAIN
CENSOR
timeout
crash

則：

實際執行 frozen fallback policy，

並用整個系統的真實結果計分。

======================================================================
七、L — Live Loop（官方實機閉環）
======================================================================

L 證明的是：

這個 AI 真的能：

observe
→ model
→ plan
→ act
→ verify

在官方環境中自主運作。

L 不負責再次用少量真人場次證明 Planner 比 baseline 強。

Decision quality（決策品質）由 V 負責。

L 必須證明：

- autonomy（自主性）
- action reliability（行動可靠性）
- meaningful decision-state exposure（有意義決策狀態暴露）
- non-degenerate execution（非退化執行）
- catastrophe control（災難控制）
- V policy 確實在 live 被使用

V 與 L MUST NOT 互相替代。

======================================================================
八、P0 — 唯一工程焦點
======================================================================

一次只允許一個 active engineering P0
（活動工程 P0）。

背景錄製／長跑 evaluator job
可以執行，

但不得因此偷偷開第二條工程主線。

每個 P0 開始前 MUST 凍結以下 7 欄：

1. ID
2. Gate：V / L / Invariant 子項
3. Hypothesis / Question（假設／問題）
4. Success
5. Falsification
6. Manifest / Input
7. Budget / Hard Stop

Success 與 Falsification：

MUST：

- 可機械判定
- 儘量數字化
- 在跑結果前凍結

未凍結：

MUST NOT 開工。

======================================================================
九、P0 只能有五種有效出口
======================================================================

1. CAPABILITY_ADDED
   新增當前 P0 所缺且決策相關的能力，Success 已達成。

2. CLAIM_VALIDATED
   事前凍結主張在 Confirmatory（確認性）證據下成立。

3. HYPOTHESIS_FALSIFIED
   Falsification 成立。
   立即停止該 P0。
   不 patch 假設。
   新假設 = 新 P0。

4. INFORMATION_CEILING
   只有同時滿足：
   - Nmax / budget 已到
   - ceiling 可量化
   - 能明確說出現有可見資訊下什麼已不可再區分
   才能使用。
   不得把它當偷懶出口。

5. ARCHITECTURE_BLOCKED
   某必要架構前提已被證明不可達，
   必須 REDESIGN 或 ABORT。

其他：

INVALID CLOSE（無效關閉）。

不合併進 v2-rebuild，
不算進展。

======================================================================
十、Diagnostic vs Confirmatory
======================================================================

DIAGNOSTIC（診斷性）：

- 可使用舊 corpus
- 可反覆看
- 可以找模式
- 可以證偽
- 可以產生新假設
- 可以產生 uncertainty branch

但是：

MUST NOT 宣稱它確認了新規則。

CONFIRMATORY（確認性）：

- hypothesis
- eligibility
- scorer
- baseline
- scenario
- sampling
- evaluation commit

必須在結果前凍結。

只有 Confirmatory evidence
可以推進 V / L。

舊：

45 Capture
31 Combat

以及所有已反覆看過的 corpus：

預設只算 Diagnostic。

不要重新包裝成 held-out。

======================================================================
十一、Validation 與 Final
======================================================================

Validation 前 MUST 原子 freeze：

- scorer
- baselines
- scenario set
- sampling plan
- evaluation commit
- environment/game version
- relevant manifest

同一：

hypothesis × dataset

只能看一次。

結果揭露後修改凍結物：

舊結果只能變 Diagnostic。

不能：

修改後在同一 dataset
重新宣稱 Confirmatory PASS。

======================================================================
十二、Final Cycle
======================================================================

一個 Final Cycle（最終評估週期）：

指：

同一 frozen candidate

在不修改任何影響行為／評估的凍結物的情況下，

完成：

Final-V
+
Final-L

的一次正式評估週期。

只要 Final Cycle 任一 component
已看到 outcome-bearing data：

該 Cycle 就算：

OUTCOME_REVEALED。

同一 Cycle：

MUST NOT：

看結果
→ 修改 candidate
→ 繼續使用剩餘 Final data
→ 再宣稱 Confirmatory。

若要修改：

必須建立新的 Final Cycle
與新資料。

Final raw data：

在評估前不得人工探索。

Outcome-bearing data 包括：

- case outcome
- score
- pass/fail
- aggregate success count
- partial aggregate，例如 18/20

Metadata-only：

例如：

- filename
- file size
- checksum
- manifest ID

不算 exposure。

資料損毀但沒有 outcome 被看見：

VOID，不消耗 outcome exposure。

同一 Final dataset：

第二次 outcome-revealing exposure：

ABORT。

Global Final Cycle outcome exposure cap：

2。

因此：

最多有：

Final Cycle #1
+
全新 Final Cycle #2。

第三次需要新的 outcome-revealing Final：

resource infeasible。

若 V/L 尚未完成且沒有其他可行路徑：

ABORT。

======================================================================
十三、Evidence 與版本綁定
======================================================================

所有 Confirmatory evidence
MUST 綁定：

- evaluator version
- game/environment version
- relevant artifact hashes

如果：

game client
official UI
observer
evaluation harness
scorer

的相關 version 改變：

重新檢查 validity。

結果分類：

VALID
STALE
VOID
BURNED

BURNED 優先於 VOID。

Resume from PAUSED 時：

MUST 先完成 version reconciliation
（版本對帳）

再繼續。

======================================================================
十四、下一個 P0 的選擇
======================================================================

不要使用主觀加權分數。

使用以下 lexicographic priority
（字典序優先）：

1. 未修復 Invariant breach（不變條件破口）
2. architecture killer（架構殺手）
3. 能直接決定必要 Gate 的 P0
4. decision headroom / execution cost
5. ID

Architecture killer 定義：

尚未被測試，

且若失敗：

會使必要 Gate：

REDESIGN
或
ABORT

的最便宜候選。

候選 P0 若：

無法改變 V/L/Invariant 的狀態，

也無法觸發 REDESIGN／ABORT，

則不合格。

不要因：

「可能有趣」

就研究。

======================================================================
十五、初始 architecture-killer 候選
======================================================================

開始後先依 repository 真實狀態重新確認，
但目前已知至少有兩個高優先級 architecture killer：

A. FAIR OFFICIAL ACTION CHANNEL
（公平官方行動通道）

目前歷史上：

controlled/live dispatch
尚未真正建立可靠：

action
→ observed world effect
→ verification

而先前 readiness 曾出現：

force:0:source
R3_ROUTE_OR_ACTION_LEGALITY_UNPROVEN

因此：

在大量做 Planner 前，

優先做最小、界限明確的：

official UI action feasibility
（官方 UI 行動可行性）

只需要回答：

在 HARD zero-interference 條件下，

能不能：

發出一個合法 action
→ server/world 接受
→ observer 看見效果
→ verifier 驗證。

不要藉此重新做：

callback
queue
canvas
WASM
endpoint archaeology。

如果公平 action channel
完全不可行：

L 不可達。

--------------------------------------------------

B. INDEPENDENT DECISION-RELEVANT EVALUATION HARNESS
（獨立決策相關評估環境）

V 需要一個：

與 Planner rollout/model
邏輯獨立

且能評估 Final benchmark 所需 transition subset
的最小 Harness。

它：

MUST NOT 變成：

「先完整做完 Kiomet Simulator」。

只做 benchmark 實際需要的：

decision-relevant transitions。

======================================================================
十六、已知 research-closed / 不要考古
======================================================================

以下不是絕對永遠不能碰，

但沒有：

- environment/version change
- closure 時不存在的新 input／能力
- decision relevance change

就 MUST NOT 重開。

A.
Endpoint：

UNKNOWN_BUT_RESEARCH_CLOSED。

現有歷史：

enemy endpoint/current-leg
沒有足夠 visible data
做唯一推導。

不要重新：

callback
queue
canvas
WASM
raw memory

考古。

--------------------------------------------------

B.
Supply-local / post-arrival disposition：

已得到：

STRONG_CONTINUATION_PATTERN

但：

NO_BEFORE_TRIGGER_FOUND。

已知的只是：

觀察到 outgoing 時，
inventory 可以做 conditional accounting。

未證明：

automatic relay
multi-leg
immediate relaunch

其中哪個是成因。

Supply-local 已 STOP。

不要再開第二輪 Supply archaeology。

--------------------------------------------------

C.
Old Combat corpus：

31 unique passive cases

只屬 Diagnostic。

即使 retrospective
continuation-aware replay
很漂亮，

也不能升正式信用。

新的 Combat claim
需要新的 Confirmatory evidence。

======================================================================
十七、Redesign（重設計）
======================================================================

連續 3 個 P0：

沒有 Gate movement

→ REDESIGN。

Gate movement：

CAPABILITY_ADDED
或
CLAIM_VALIDATED

且其 Success 真正影響 V/L/Invariant。

HYPOTHESIS_FALSIFIED：

不算 movement，

但必須成為 redesign diagnosis
（重設計診斷）輸入。

Redesign 軸只有：

1. OBJECTIVE
2. STATE-REPRESENTATION
3. PLANNER-CLASS
4. INFORMATION-SOURCE
5. ACTION-CHANNEL

軸由：

實際被修改的 interface
（介面）

界定，

不是靠重新命名。

同一 Gate＋同一 axis：

不得重用，

除非：

1. environment version 改變且相關 artifact 有差異
2. closure 時不存在的新 input／能力出現
3. decision relevance 改變

環境漂移本身：

ordinary P0，

不是 Redesign。

所有適用軸耗盡：

ABORT。

======================================================================
十八、普通 bug 與問人規則
======================================================================

普通 bug MUST 自主修復。

例如：

- test failure
- lint
- wrong path
- dependency issue
- stale process
- browser crash
- parse bug
- ordinary regression
- git dirty
- cache corruption

都不是：

「先問使用者」的理由。

不得詢問：

「要不要繼續？」
「A 還 B？」
「這樣可以嗎？」

只有三種情況可問人：

1.
HUMAN-ONLY ACCESS
登入、credential、CAPTCHA、帳號權限、人類專屬資源。

2.
IRREVERSIBLE HIGH-RISK ONLY PATH
不可逆高風險且真的是唯一道路：
花錢、刪除無備份資料、公開動作、明顯帳號封禁風險。

3.
L0/L1 contradiction or loosening
契約高階矛盾，或必須降低已授權門檻／限制。

若有人類／環境阻塞，

但仍有不依賴它的合格 P0：

繼續其他 P0。

只有沒有任何合格 P0：

PAUSED。

PAUSED：

無 timeout。

一週、一個月後都可恢復。

======================================================================
十九、Anti-overengineering（防過度工程）
======================================================================

核心原則：

只建造／研究：

當前 P0 的失敗嘗試
已證明缺少

而且：

與 V/L/Invariant
有決策相關性

的東西。

預設：

一次性 script
優先於 framework。

禁止沒有 blocker 的：

- generic framework
- generic interface
- event bus
- dashboard
- generalized recovery system
- evidence platform
- spectator product
- replay product
- 通用 abstraction

如果：

較簡單方案

與：

完整方案

都能測同一核心假設，

MUST 選較簡單方案。

允許 prototype hardcode（原型硬編碼）。

既有程式碼沒有 sunk-cost protection
（沉沒成本保護）。

如果：

刪掉大量舊架構
是到達 V∧L 的最短路徑，

MAY 刪。

不要因：

「已經寫很多」

而保留。

======================================================================
二十、Global resource pool
======================================================================

AUTHORIZED L1：

Information-bearing attempts：
60

New passive recording batches：
6

Official live sessions：
24

其中：

每個 Final-L Cycle
最多 6 場。

Outcome-revealing Final Cycles：
2

Wall-clock waiting：

不計 budget。

--------------------------------------------------

Information-bearing attempt：

指：

一個可能改變：

- P0 verdict
- hypothesis status
- failure classification
- next P0 selection

的獨立測試／實驗。

普通：

compile
lint
重跑同一 deterministic unit test
純格式修復

不算研究 attempt。

--------------------------------------------------

同一 P0：

連續 4 個 information-bearing attempts

都沒有 information transition：

hard stop 該 P0。

該 idea：

可以作：

新的 P0 candidate

重新排序，

不能直接偷偷延長。

--------------------------------------------------

某 resource class 達 cap：

只代表：

MUST NOT 再消耗該 class。

不是立即 ABORT。

只有：

存在尚未完成的必要 Gate，

且：

所有仍合格 P0

都至少需要一個：

已達 cap 的 resource class，

也就是：

NO RESOURCE-FEASIBLE PATH

時：

ABORT。

唯一例外：

information-bearing attempt pool 60
整體耗盡：

可直接 ABORT。

--------------------------------------------------

6 個 passive recording batches：

收集時 MUST 提前保留：

Final Cycle #1
以及可能的 Final Cycle #2

所需要的未揭露資料。

不得：

把所有新資料先拿去 DEV，
最後才發現沒有 Final。

======================================================================
二十一、L1-A — Baseline Suite
======================================================================

B0 — Minimal sanity baseline
（最低健全性基準）

公平 visible info only。

無 search。

約：

- 就近擴張
- 保留固定預備兵力
- 可見敵人進入防禦半徑 → 防守
- 明顯局部兵力優勢時才攻擊

常數手設。

不調參。

--------------------------------------------------

B1 — Strong heuristic baseline
（強啟發式基準）

同樣：

公平 visible info only。

不使用 hidden state。

最多：

1-ply greedy evaluation
（單步貪婪評估）。

加入：

- 開局時序
- threat-ratio reinforcement
- 固定撤退／交戰規則
- 比 B0 更完整的局部資源分配

DEV 調參預算：

最多 300 episodes。

B1：

同時是：

Fallback Policy。

--------------------------------------------------

B2 — Previous-best / tuned heuristic
（前代最佳／調優啟發式）

優先：

使用目前 repository/main archive
中：

最強、符合 Invariant
的既有決策模組。

若：

不存在
或
違反公平限制：

使用 tuned B1。

調參預算：

min(
Planner 實際 DEV 調參 episodes,
3000
)

且至少：

1000 episodes

除非整個 Planner DEV 預算本身 <1000，
這時 B2 使用與 Planner 完全相同的 DEV episode 數。

Planner 與 B2：

不得因資源不對稱
造成假勝利。

--------------------------------------------------

三個 baseline：

在第一次正式 V Validation 前 freeze。

Agent：

只能在看到 Planner outcome 前：

增加更強 baseline，

不能移除。

======================================================================
二十二、L1-B — Benchmark Distribution
======================================================================

Final benchmark：

6 strata（分層）：

S1 Expansion
S2 Contested Expansion
S3 Threat / Defense
S4 Reinforcement Choice
S5 Combat-risk Choice
S6 Uncertainty Exposure

Final：

每 stratum：

20 units

總共：

120 units。

來源原則：

每 stratum 優先：

8 replay-restored
8 generated
4 hand-built evaluator scenarios

若 replay 無法安全恢復成：

independent harness
可前進的狀態：

只能在 freeze 前：

用同 stratum generated unit 補足。

不得：

看 outcome 後替換。

--------------------------------------------------

Harness：

INDEPENDENT DECISION-RELEVANT EVALUATION HARNESS。

它 MUST：

- 與 Planner model/rollout code 邏輯獨立
- 不 import Planner 的 transition implementation
- 不共享 Planner 的預測參數
- 只支援 benchmark 實際需要的 transition subset

MUST NOT：

為了 V
先完整重建 Kiomet world simulator。

--------------------------------------------------

每 unit：

H_u ∈ [30, 90] 秒遊戲內時間。

在 freeze 前，

根據 scenario：

例如：

下一 threat arrival
decision commitment resolution
固定 buffer

決定 H_u。

同一 unit：

Planner
B0
B1
B2
fallback

完全使用同一 H_u。

不得依 policy trajectory
事後改 horizon。

--------------------------------------------------

Final unit freeze 前：

用 pre-outcome deterministic eligibility rule
（結果前確定性資格規則）

保守計算：

在：

允許 action set
與 H_u

內，

可能到達的 transition types。

必須：

potential transition set
⊆
Harness supported transitions。

若無法證明：

unit 不合格。

但：

每個 stratum
eligibility exclusion
不得 >25%。

>25%：

不得縮窄 benchmark。

必須：

做最小 Harness capability P0

或：

PAUSED 請求 L1 放寬。

Runtime 遇到 qualification 漏網的 unsupported transition：

該 unit：

對所有 policy 同時 VOID。

Harness VOID >5%：

Final V = INSUFFICIENT。

======================================================================
二十三、L1-C — V Utility
======================================================================

Utility priority：

A.
如果 Kiomet 存在：

官方 objective score
（官方目標分數）

或：

直接 terminal objective
（終局目標）

優先使用。

先在 DEV：

查證公開規則／排行榜／結算 UI。

--------------------------------------------------

B.
若不存在合理 official score：

使用 Composite Proxy Utility
（複合代理效用）。

三個 component：

1. Control（控制量）
2. Production（生產能力）
3. Force Value（兵力價值）

MUST：

先使用：

與 Planner outcome 無關的 DEV baseline data

轉換成：

可比較的 unitless normalized scale
（無量綱正規化尺度）。

不得直接把：

不同物理單位

乘 0.7／0.2／0.1。

然後：

U_proxy = clip(
    0.7 * ΔControl
  + 0.2 * ΔProduction
  + 0.1 * ΔForceValue,
  -1,
  +1
)

其中：

Control：

必須是：

最接近遊戲勝負／排名目標
的可公平量。

Production：

用產出能力，

不是單純庫存。

Force Value：

最低權重，

防止囤兵刷分。

Terminal override：

自身淘汰／核心喪失：

U = -1
Catastrophe = TRUE

對手淘汰：

U = +1

--------------------------------------------------

若使用官方 scalar score：

U = clip(
  Δ(self_score - opponent_score) / s,
  -1,
  +1
)

其中：

s：

只使用 B1 DEV outcome
的 |Δ| 90th percentile

事前凍結。

不得：

使用 Planner outcome
選 s。

--------------------------------------------------

UTILITY SANITY TEST：

在 Planner 正式 V outcome
被看之前完成。

至少：

200 dominance pairs
（支配狀態對）：

Good state
在：

control
production
force
survival

全部不劣，

至少一項嚴格較優。

必須：

100%：

U_good > U_bad。

另：

至少 20 anti-proxy hand cases：

例如：

兵很多但核心已失

必須低於：

仍存活且具控制優勢的狀態。

要求：

100%。

FAIL：

Utility 回 L1。

MUST NOT：

為了讓 Planner PASS
調 utility。

======================================================================
二十四、L1-D — V Success Thresholds
======================================================================

Final V：

120 units。

每個 baseline：

paired same-unit comparison。

Primary difference：

d_i = U_planner - U_baseline

統計：

stratified paired bootstrap
（分層配對 bootstrap）

10,000 次。

Replay-derived units：

依 source match clustering
（來源比賽群聚）

處理。

--------------------------------------------------

Planner 必須逐一勝：

B0
B1
B2

不是平均勝。

單尾 95% lower confidence bound：

vs B0：

> +0.10

vs B1：

> +0.05

vs B2：

> +0.03

--------------------------------------------------

Stratum anti-collapse：

每一 stratum

對 B1、B2：

mean d

不得 < -0.05。

--------------------------------------------------

Catastrophe：

Planner point estimate：

≤10%

且：

≤ B1 catastrophe + 2 percentage points

且：

one-sided 95% Clopper-Pearson upper bound：

≤15%。

--------------------------------------------------

Uncertainty：

每個非 UNKNOWN uncertainty declaration

必須在 action 前宣告：

uncertainty set。

形式可以是：

- discrete branches
- CandidateSet
- bounded interval

Primary rule：

REALIZED OUTCOME
∈
PREDECLARED UNCERTAINTY SET。

非 UNKNOWN resolved declarations：

point coverage：

≥90%

且：

one-sided 95% Clopper-Pearson lower bound：

≥80%

且：

resolved declarations：

≥150。

在 horizon 內：

無法觀察 realized outcome

依預先規則標 unresolved。

unresolved >30%：

V = INSUFFICIENT。

UNKNOWN 本身：

不進 uncertainty coverage，

但：

觸發 B1 fallback

並受到 takeover floor。

不設 uncertainty set width
（集合寬度）門檻。

因為：

若 Planner 能在很寬的 uncertainty
仍然打贏 B1／B2，

這就是 robust value。

--------------------------------------------------

Planner takeover rate：

非 fallback、
非 abstain、
非 timeout

的 decision states：

≥60%。

--------------------------------------------------

Harness fault VOID：

≤5%。

>5%：

V = INSUFFICIENT。

======================================================================
二十五、L1-E — Fallback Policy
======================================================================

Fallback = frozen B1。

當：

UNKNOWN
ABSTAIN
CENSOR
Planner timeout
Planner crash

該 decision point：

B1 接手。

下一 decision point：

Planner 可以重新取得控制。

整個 episode：

照實跑完。

最終 U：

照實計入。

這是一個合法：

meta-policy
（元策略）：

Planner 有把握時接管，

沒有把握：

回 B1。

不是漏洞。

但：

只回 B1：

d ≈ 0

無法通過 V。

另外：

takeover ≥60%

防止：

Planner 只偶爾搶一兩個容易決策。

======================================================================
二十六、L1-F — Live Loop Thresholds
======================================================================

Final-L：

Minimum completed matches：

4

預註冊最大嘗試：

6。

不是：

打到 PASS 才停。

Sampling rule
在 Final freeze 前登記。

--------------------------------------------------

Minimum live decision states：

≥150。

Strata：

S3 Threat / Defense：

≥10

S5 Combat-risk：

≥10

另外 S1/S2/S4/S6

至少其中 3 類：

各 ≥10。

若場數完成但 coverage 不足：

INSUFFICIENT。

不能：

降低 coverage。

--------------------------------------------------

Action success：

≥95%

每個 action：

必須有：

state-change verification
（狀態變化驗證）

結果：

SUCCESS
FAILED
UNKNOWN

關鍵 action：

不得有：

unrecovered failure。

任何：

agent-controlled stall >30 秒：

不允許。

--------------------------------------------------

Planner live takeover：

≥60%。

--------------------------------------------------

Progress non-degeneracy：

定義一個 freeze 前
只看 visible state
的：

progress-feasible predicate。

例如：

當：

- resource 足以一次擴張／建造／生產
- 沒有可見迫近威脅要求立即防禦

時：

progress-feasible = TRUE。

在這些 decision states：

實際執行：

expansion
build
production
meaningful attack

等 progress action：

≥70%。

目的：

只防：

永遠不行動
永遠撤退

不是：

重新判斷策略品質。

--------------------------------------------------

Live catastrophe：

完整場次中：

Catastrophe matches
+
B-class human stops

合計：

≤1。

另外：

以與 V 相同 30–90 秒決策視窗計：

catastrophe point rate：

≤12%。

--------------------------------------------------

Environmental VOID：

只能在：

結果前規則已可判斷的：

- official server outage
- opponent 在開局 2 分鐘內離開
- 對局中途 official game version update
- A-class human stop

使用。

最多替換：

2 場。

超過：

Final-L = INSUFFICIENT。

======================================================================
二十七、Human Stop
======================================================================

A-class：

原因與：

game outcome
AI behavior

無關，

且符合預登記：

- 真實世界安全事件
- 使用者硬體故障
- 使用者網路斷線
- 使用者緊急需要電腦

→ ENVIRONMENTAL VOID。

--------------------------------------------------

B-class：

任何：

- 因 AI 行為停止
- 因遊戲局勢停止
- 即將災難時停止
- AI 卡死／無法恢復
- anti-automation challenge
- 帳號限制
- 對計入場次做任何非緊急人工輸入

都不能 VOID。

它：

計入 Live failure。

並根據 freeze catastrophe rule
判 catastrophe。

所有 human stop：

記錄：

- timestamp
- reason
- game-state hash

模糊：

預設 B-class。

======================================================================
二十八、Research Reopen
======================================================================

Research closure：

綁定：

topic@game-version@claim-version。

只有：

1. relevant environment version changed
2. closure 時不存在的新 evidence/input/capability
3. decision relevance changed

才可重新開。

沒有新 input：

不得重新研究。

======================================================================
二十九、Minimal Git / Evidence Discipline
======================================================================

只保留必要紀律：

1. main immutable。
2. v2-rebuild 是整合 branch。
3. P0 可用 p0/<id> branch。
4. 禁止 force push。
5. Freeze 後不得改寫該歷史。
6. 回退用 git revert，不用破壞性 history rewrite。
7. Confirmatory evaluation 的 working tree 必須乾淨。
8. Freeze 使用 annotated tag。
9. Receipt 使用 annotated tag
   並記：
   - evaluated commit
   - manifest tree hash
   - command
   - result
   - log hash
10. final docs 可以在 receipt 後 commit，
    只要 manifest tree hash 未改。

Push：

有效 P0 與 freeze/receipt tags
應推到 remote。

======================================================================
三十、最小持久狀態
======================================================================

不要建立大型資料庫。

最多維持：

runtime/research/v2/goal/PREREG.jsonl

每個 P0：

append 一筆凍結契約。

以及：

runtime/research/v2/goal/LEDGER.jsonl

每個 P0：

append：

- P0 ID
- outcome
- Gate impact
- resource use
- evidence validity change
- closure / reopen
- terminal transition

其他：

由 repo + tags + 兩個 jsonl
推導。

不要建立：

另一套：

SQLite
dashboard
control center
event bus
evidence platform。

======================================================================
三十一、Autonomous Loop
======================================================================

持續執行：

1.
LOAD：
   讀 repo、PREREG、LEDGER、tags、resource pool、current versions。

2.
RECONCILE：
   確認證據 validity、
   Git integrity、
   Invariant。

3.
TERMINAL CHECK：
   是否已符合 SUCCESS？
   是否符合 ABORT？
   是否只有外部阻塞而需 PAUSED？

4.
CANDIDATES：
   產生能真正影響 V/L/Invariant 的 P0 候選。

5.
SELECT：
   依 R13 字典序選唯一 P0。

6.
PREREGISTER：
   寫 7 欄，
   commit / append，
   freeze。

7.
EXECUTE：
   做最小可行實驗／功能。
   普通 bug 自修。

8.
EVALUATE：
   依 prereg Success/Falsification
   得出五種 outcome 之一。

9.
CLOSE：
   有效 outcome 才 merge。
   無效 P0 不 merge。

10.
RECEIPT：
   Regression / evidence receipt。
   推必要 commit/tag。

11.
UPDATE：
   append LEDGER，
   更新 resource pool、
   closed topics、
   evidence validity。

12.
LOOP：
   未 terminal：
   不問人，
   回步驟 1。

======================================================================
三十二、不要讓舊里程碑綁住你
======================================================================

以下舊狀態只是研究歷史：

M1
M1B
M2A
M2
M3
M4
M5

Goal Mode：

MUST NOT：

因：

「M2 還沒完整 PASS」

就拒絕做 Planner。

也 MUST NOT：

因：

「M3 Planner 已做」

就忽略 world uncertainty。

真正 Gate 只有：

V
L
Invariant。

Simulator：

只需支援：

決策真正需要的部分。

UNKNOWN：

用：

branch
hedge
fallback

處理。

======================================================================
三十三、初始已知專案事實
======================================================================

以下是 orientation，

開始後仍要以 repository 真實狀態驗證。

- M1 historical FAIL：缺 authoritative wall-clock generation timestamp。
- M1B tick-relative freshness 已有可接受方案。
- M2A / M2 歷史上 IN_PROGRESS。
- M3 尚未成為正式 Planner milestone。
- Movement 已非常可靠，但簡單 baseline 也能做到，不能當 AI 決策里程碑。
- Endpoint = UNKNOWN_BUT_RESEARCH_CLOSED。
- Capture post-arrival continuation：
  STRONG_CONTINUATION_PATTERN，
  但 NO_BEFORE_TRIGGER_FOUND。
- Supply-local 已 STOP。
- Owner-only Capture 只是舊資料上的 hypothesis，不是正式已知規則。
- Old Combat passive corpus 只有 Diagnostic 信用。
- Production Combat 尚未正式建立。
- Controlled/live dispatch 歷史上尚未證明可靠。
- 現在最大的未知不是「還缺多少規則」，而是：
  能否在公平 action channel＋有限 world uncertainty 下，
  建立真正有 decision value 的自主閉環。

======================================================================
三十四、第一輪工作不要直接大建設
======================================================================

啟動 Goal Mode 後：

先做 repository audit
（程式碼儲存庫現況核對），

但：

不是重新全面審計 v1。

目的只回答：

1.
目前 V/L/Invariant 真正缺什麼？
2.
哪些 capability 已經存在？
3.
哪些 evidence 還有效？
4.
最便宜 architecture killer 是什麼？

依目前已知，

高機率第一個 P0：

應該是：

FAIR_ACTION_CHANNEL_MINIMAL_CLOSED_LOOP

問題：

在 HARD zero-interference 條件下，

是否可以：

選一個合法、低風險、
正常玩家可做的官方 UI action，

完成：

before state
→ official page-level action
→ world/server effect
→ after state
→ verifier confirmation

？

只需證明：

最小 action closed loop。

不要：

趁機完成：

完整 executor
完整 combat
完整 planner
callback
queue
canvas
WASM
endpoint。

如果 repo 現況證明另一個 architecture killer
更早且更便宜：

依 R13 選它。

======================================================================
三十五、Final Evaluation
======================================================================

只有在：

Validation 已足夠
L1 全部已 freeze
Final data 已封存
候選 commit 已 freeze

後，

才進 Final。

Final Cycle 期間：

MUST NOT：

修改：

- Planner behavior
- evaluator
- scorer
- baseline
- scenario set
- benchmark distribution
- threshold
- fallback
- eligibility
- sampling plan

如果任何一項必須修改：

當前 Final Cycle：

BURNED / DIAGNOSTIC。

使用全新 Final Cycle。

最多：

2 個 outcome-revealing Final Cycles。

Final #2 仍未成功：

若沒有 resource-feasible path：

ABORT。

======================================================================
三十六、Terminal States
======================================================================

------------------------------
SUCCESS
------------------------------

唯一條件：

Final：

V = PASS
L = PASS
Invariant = INTACT

立即停止。

不要：

再改 code
再清理
再 benchmark
再研究

只輸出 terminal report。

------------------------------
ABORT
------------------------------

只允許：

1.
公平合法 action path
架構上不可達。

2.
同一 Final dataset
第二次 outcome-revealing exposure。

3.
某必要 Gate 的所有適用 Redesign axes
均已合法耗盡。

4.
Information-bearing attempt pool = 60
整體耗盡。

5.
某必要 Gate 未完成，
且所有仍合格 P0
都至少需要一個已達 cap 的 resource class，
因此不存在 resource-feasible path。

除此之外：

MUST NOT 宣告 ABORT。

------------------------------
PAUSED
------------------------------

只有：

- human-only access
- 不可逆高風險唯一道路
- L0/L1 contradiction／loosening
- agent 控制外環境長期阻塞

且：

沒有其他合格 P0

才使用。

PAUSED：

不是失敗。

保存：

- current HEAD
- branch
- tags
- PREREG/LEDGER
- resource counters
- environment version
- pending human action
- 單一 resume instruction

然後停止。

======================================================================
三十七、Terminal Report
======================================================================

只在：

SUCCESS
ABORT
PAUSED

才給人類完整終局報告。

報告必須至少包含：

STATUS：
SUCCESS / ABORT / PAUSED

CURRENT HEAD：

BRANCH：

REMOTE PUSHED：

MAIN UNCHANGED：

V：
PASS / FAIL / INSUFFICIENT
關鍵證據：

L：
PASS / FAIL / INSUFFICIENT
關鍵證據：

INVARIANT：
INTACT / BREACHED

FINAL CYCLES USED：

RESOURCE POOL：
Attempts：
Passive batches：
Live sessions：
Final cycles：

VALID CLAIMS：

REMAINING UNKNOWN：

RESEARCH_CLOSED：

REDESIGN AXES USED：

TEST / REGRESSION：

若 SUCCESS：
為什麼完成謂詞已成立。

若 ABORT：
精確命中哪一個封閉 ABORT 條件。

若 PAUSED：
只寫一個使用者必須做的具體動作，
以及 resume 指令。

======================================================================
三十八、最後的最高優先原則
======================================================================

你不是來：

把 Kiomet AI 做得「完整」。

你是來：

用最短、最簡單、可驗證的路徑，

證明：

一個只看正常玩家資訊、
不干擾使用者電腦、
透過官方 UI 行動的 AI，

真的具有：

decision value（決策價值）

以及：

live autonomous closed loop
（官方實機自主閉環）。

如果：

hardcoded heuristic
比大型 Planner 更快證明它，

使用 heuristic。

如果：

UNKNOWN 不需要解決，

就不要解決。

如果：

Simulator 對決策沒價值，

停止改善它。

如果：

某研究方向被證偽，

停止。

如果：

某問題已達資訊上限，

接受上限。

如果：

完成謂詞已經成立，

立即 SUCCESS。

不要把：

研究本身

錯當成：

專案目標。

現在進入 Goal Mode，
依本契約自主工作，
直到：

SUCCESS
ABORT
或
PAUSED。