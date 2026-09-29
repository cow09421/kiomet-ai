# 攻擊可行性評估 v0

`evaluate_attack()`（攻擊評估）只檢查呼叫端提供的來源、目標與路徑，不會搜尋或選擇目標，也不會送出命令。

## 輸入條件

- 固定為 SELF（己方）來源塔到 ENEMY（敵方）相鄰塔。
- `deployable_force`（可派兵力）必須是來源塔實際可派出的完整普通 Many 兵力；本函式拒絕 Shield 和特殊兵種，也不允許自行挑選部分兵力。
- `battle_case.attacker_units` 必須和完整可派兵力一致。
- 命令證據必須確認來源屬於己方、來源兵力非空、目標為敵方且直接相鄰、路徑合法、世界與目標擁有者資料新鮮，以及命令類型為 `DeployForce`。
- `server_acceptance_validated`（伺服器接受驗證）須來自先前正式版驗證；未通過時不能成為可行攻擊。
- 戰鬥本身須通過安全評估器並達到 `SUPPORTED`（已支援）。

## 輸出

`legality`（合法性）為 `ILLEGAL`（不合法）、`UNKNOWN`（未知）或 `LEGAL_STATIC_SHAPE`（靜態命令形狀合法）。`projected_result`（預測結果）只會是 `ATTACK_WIN`、`ATTACK_LOSE`、`ATTACK_CONTESTED` 或 `UNSUPPORTED`。

勝利時，以攻方存活的普通移動兵數和 `marginal_survivor_max`（邊際殘兵上限）比較：不多於上限標記 `MARGINAL_WIN`（邊際勝利），超過上限標記 `ROBUST_WIN`（穩健勝利）。預設上限為 1，這是 `TUNABLE_POLICY`（可調政策），不是遊戲規則，也不是勝率估計。

只有命令條件、伺服器接受驗證、戰鬥差分驗證都通過且結果為 `ROBUST_WIN`，`safe_attack_candidate`（安全攻擊候選）才會為 true。未經執行期驗證時，輸出可供檢視，但不會交給仲裁器當作可行動攻擊。
