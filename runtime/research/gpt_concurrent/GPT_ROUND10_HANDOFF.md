# GPT Round 10 安全 PvP 規劃器交接

## 本輪結果

已將 Round 8／9 的普通戰鬥子集包成先檢查、後計算的離線評估層，並加入防守、攻擊、最低救援候選比較和確定性仲裁契約。`safe_battle_evaluator.py`（安全戰鬥評估器）只有通過輸入閘門才會呼叫 `battle_mirror_partial.py`（部分戰鬥鏡像）。未知或不支援案例不會得到勝負。

目前只完成靜態驗證。Round 10 沒有任何正式版 Runtime（執行期）差分，也沒有實際的 `SUPPORTED` PvP 案例。情境檔中的 `battle_differential_validated` 旗標是合成測試資料，用來確認閘門控制流，不能當作 Muse 驗證紀錄。

## Muse 最小工程介面

| 層 | 輸入 | 輸出與安全條件 |
|---|---|---|
| `BattleEvaluator.evaluate(case)`（戰鬥評估器） | 精確兩側單位、owner relation（擁有者關係）、塔型與容量、Shield（護盾）、aura snapshot（光環快照）、特殊兵種旗標、世界狀態需求 | `SUPPORTED`、`RUNTIME_VALIDATION_NEEDED` 或 `UNSUPPORTED`；不輸出機率。 |
| `ThreatEvaluator.evaluate(world)`（威脅評估器） | SELF towers（己方塔）、新鮮的入站 Force（部隊）、路徑與 ETA | `SUPPORTED`、`UNKNOWN` 或 `UNSUPPORTED`；未知威脅阻止攻擊與擴張。 |
| `DefenseEvaluator.evaluate(threat, candidates)`（防守評估器） | 已知敵軍、現有守軍、ETA、完整 SELF 候選兵力及精確合併後狀態 | 塔存活／失守、殘兵、完整候選救援；不拼造兵種。 |
| `AttackEvaluator.evaluate(source, target)`（攻擊評估器） | 單一 SELF→ENEMY 相鄰候選、完整可派兵力、路徑與新鮮度證據 | 合法性、戰鬥支援、勝負和離散安全餘裕；UNKNOWN／UNSUPPORTED 不會安全。 |
| `ActionArbitrator.select(...)`（行動仲裁器） | 以上已評估的候選與既有中立擴張候選 | 失守防守優先，其次穩健攻擊，再中立擴張，否則不動。 |

各介面遇缺少或過期資料時回 `UNKNOWN`（未知），已知超出支援範圍時回 `UNSUPPORTED`（不支援），正式差分通過後才回 `SUPPORTED`（已支援）。評估器用 `evaluation_status` 保留這三態，並以 `support_status` 額外標記是否仍需執行期驗證。任何 `UNKNOWN`／`UNSUPPORTED` 都不能當成安全攻擊。

## 支援邊界

- 靜態支援：普通 Shield、Fighter、Chopper、Bomber、Tank、Soldier 的 Force 對非空塔、Force 對 Force、非空中立塔戰。Force 相撞必須先由呼叫端確認；攻守光環必須明確輸入；塔戰容量必須匹配來源確認的 22 種塔型容量表。
- 尚需 Runtime Validation（執行期驗證）：所有正式版戰鬥差分、兩種 `DeployForce`（部署部隊）命令接受、光環快照來源、移動 ETA、SELF→SELF 合併結果及行動時世界新鮮度。
- 不支援：Ruler 參戰或死亡的全域後果、Shell、EMP、Nuke、其他特殊兵種、空塔直接佔領、未計算的合併／容量／移動續行、晚到援軍的後續事件、同節拍順序、完整玩家／世界狀態。特殊兵種 `DO NOT USE`（禁止使用）。
- 安全攻擊目前要有戰鬥差分閘門、正式版攻擊命令接受、世界和目標擁有者新鮮、合法相鄰路徑，以及 `ROBUST_WIN`（穩健勝利）。閾值是可調政策，不是遊戲規則。
- 最低救援比較只使用呼叫端提供的完整可派兵力和已確認合併後狀態；總兵數只作候選排序，不代表資源價值。

## 離線驗證

`GPT_PVP_PLANNER_STATIC_SCENARIOS.json`（PvP 規劃器靜態情境）包含 25 案例，並逐案列出其 Round 8 案例依據；`run_pvp_static_scenarios.py`（靜態情境執行器）會檢查案例 ID（識別碼）存在，再呼叫實際評估器與仲裁器。本輪結果為 **25/25 策略情境 PASS、51/51 Round 8 包裝回歸 PASS**；其中 32 個已支援結果一致，19 個不支援案例都在呼叫鏡像前拒絕。這驗證的是本地契約、鏡像包裝與確定性決策，不是正式版正確性或執行期安全證明。

## 執行期計畫最短摘要

SELF→SELF 部署接受和 SELF→ENEMY 部署接受各至少一個成功樣本；戰鬥鏡像、塔容量、光環及援軍抵達／合併都要多樣本。只啟用正式差分實際覆蓋的分支與塔型。詳見 `GPT_PVP_RUNTIME_VALIDATION_PLAN.md`（PvP 執行期驗證計畫）。

## 安全結尾

- Runtime connections（執行期連線）：0
- Browser connections（瀏覽器連線）：0
- Game actions（遊戲行動）：0
- 本輪 GPT 修改的 tracked files（已追蹤檔案）：0；最終檢查時工作樹另有 3 個研究範圍外的追蹤檔案變更，已保留原樣，未檢視或覆寫。
- Git commits（版本提交）：0
