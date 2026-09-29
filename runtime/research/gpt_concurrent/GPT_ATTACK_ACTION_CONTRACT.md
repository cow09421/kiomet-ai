# 攻敵行動資料契約（離線）

## 已有命令與客戶端行為

公開參考碼 `common/src/protocol.rs:16-39` 的 `Command::DeployForce`（派兵命令）只帶來源 `tower_id`（塔識別碼）與 `path`（路徑），**沒有「目標必須中立」欄位**。`client/src/game.rs:225-273` 在拖曳時取來源塔可派兵力與最大跨邊距離，呼叫 `World::find_best_path`（尋找路徑），並在非補給線分支送出相同派兵命令；敵塔可作路徑終點。參考版 `common/src/chunk.rs:310-402` 對不友善且有守軍或塔主的目的塔啟動戰鬥。這證明客戶端與共同規則可表示己塔到敵塔的攻擊；**不證明正式版伺服器一定接受某個輸入**。

## 合法性分層

- `source`（來源）：須為己方有主塔，有可動員單位。`tower.rs:110-135` 的 `force_units`（可派兵力）按兵種可移動性過濾；空部隊不應送出。這是客戶端可構造行動的必要條件，伺服器權限仍待驗。
- `target`（目標）：敵方塔可作終點；若在拖曳當下來源塔已被選取且可生成移動單位，客戶端可能改送 `SetSupplyLine`（設定補給線），須記錄實際命令類型。
- `path`（路徑）：`common/src/force.rs:25-87` 的驗證要求至少兩塔、起點相符、塔存在且位於世界內、無連續重複；道路逐段相鄰、最多 16 塔（`world.rs:141`），遠程直達路徑恰兩塔且距離在該兵力／塔型上限內。`world.rs:300-390` 的客戶端尋路另要求目的可見，並避免穿過特定盟友塔；這是**尋路器限制**，不可與伺服器全部驗證條件混為一談。
- `ruler`（國王）：若來源兵力含國王且路徑包含非己方塔，客戶端需等待 1.2 秒拖曳警示（`game.rs:91,250-266,1008-1020`）。這是客戶端保護流程，不代表伺服器禁止國王攻敵。
- `alliance`（同盟）：路徑中繼、抵達戰鬥與國王攜帶狀態都可能改變關係判斷（`chunk.rs:511-537`）；不能僅看派出時目標顏色。

## 建議資料結構

```
AttackAction {
  source, target, path, command_kind,
  source_owner, target_owner, relationship_at_snapshot,
  available_force_by_unit, force_aura_snapshot,
  target_units_by_unit, target_aura_snapshot, tower_type,
  legal_conditions: {source_owned, nonempty_mobile_force,
                     path_valid, visibility, ruler_warning_handled,
                     server_acceptance},
  eta_ticks, battle_projection, expected_owner, evidence_time, confidence
}
```

`available_force_by_unit`（可派兵力）不得用塔總兵數替代；`battle_projection`（戰鬥預測）在正式版鏡像完成前為 `UNKNOWN`（未知）；`expected_owner`（預期塔主）也必須維持未知。`server_acceptance`（伺服器接受狀態）目前為 `PENDING`（待驗）。攻擊合法性狀態：客戶端命令語意 **PASS**，正式版伺服器完整驗證 **PARTIAL**，整體 `P2 = PARTIAL`。
