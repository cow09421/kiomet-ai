# 防守行動空間（靜態規格）

## 己方塔 → 己方塔增援

**來源碼語意：YES（可行）**。`common/src/protocol.rs:16-39` 的 `Command::DeployForce` 只有來源塔與路徑，沒有要求目標為中立塔；`common/src/world.rs:300-313` 可為己方目標回傳至少兩塔的路徑；`common/src/chunk/event.rs:42-57` 從來源塔取可動員兵力並建立部隊；`common/src/chunk.rs:433-479` 在同隊目標續行或合併，而不進入敵方戰鬥。客戶端拖曳在 `client/src/game.rs:225-273` 用同一 `find_best_path` 並送 `deploy_force_from_path`。若來源塔處於已選取且能生成兵力的狀態，該拖曳可能被解讀為 `SetSupplyLine`，須先確認命令種類。公開資料夾未包含伺服端命令驗證，正式線上接受狀態仍待 Muse 用可授權的測試確認；不把「源碼可表示」冒稱為正式版伺服端已驗收。

因此目前只會中立擴張的規劃器未來需要另一個 `REINFORCE_SELF`（增援己方塔）行動類別。不要直接移除其中立目標安全過濾；先由 Muse 另建防守行動資料流並驗證命令種類、對局擁有權、路徑與抵達合併。

## 有來源依據的候選行動

| 行動 | 條件與效果 | 證據 | 正式版驗證 |
|---|---|---|---|
| 其他己塔派兵增援 | 來源為自己、可取出移動兵力、有效路徑；抵達同隊塔後可能續行，否則併兵並受容量限制 | `protocol.rs:18-21`；`tower.rs:110-135`；`chunk.rs:433-479` | 命令完整性待驗 |
| 轉移國王 | 國王是可移動兵種；到自己塔按友軍合併，佔塔時提升護盾容量；途經盟友塔會視為不友善 | `unit.rs:232-248`；`chunk.rs:313-316,475`；`units.rs:153-163` | 路徑與實際存活待驗 |
| 升級受威脅己塔 | `Command::Upgrade` 存在；塔型可改容量並有升級延遲，不能假設升級立即增強防守 | `protocol.rs:26-29`；`chunk/event.rs:196-211` | 資源／合法性與時機待驗 |
| 由己塔反攻敵來源塔 | 同一 `DeployForce` 路徑指向敵塔；到達時敵對戰鬥 | `protocol.rs:18-21`；`chunk.rs:313-402` | 兵力、路徑、風險待驗 |
| 設定補給線 | `SetSupplyLine` 可自動沿路送生成兵力；不是立即增援 | `protocol.rs:22-25`；`chunk.rs:178-187` | 生效與到達時機待驗 |

## `DefensiveAction` 資料契約

`action_type`、`source`、`target`、`available_force`、`ETA_ticks`、`ETA_seconds`、`expected_battle_effect`、`legality`、`confidence`、`match_id`、`freshness`。`legality` 分為來源碼可表示、客戶端可發送、伺服端已接受、執行期已驗收四層。`expected_battle_effect` 目前只能含守塔兵力增量上限或 `UNKNOWN`，直到正式版戰鬥鏡像有對照案例。對同隊塔，先處理既有路徑／補給線續行條件，再計算真正會留在塔裡的援軍；「抵達」不保證「併入」。
