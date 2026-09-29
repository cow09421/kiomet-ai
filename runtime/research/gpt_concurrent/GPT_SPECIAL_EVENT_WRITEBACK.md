# Shell（砲彈）、EMP（電磁脈衝）、Nuke（核彈）事件寫回

## 事件通路與通用消費者

1347（塔戰）／1348（部隊碰撞）的特殊單位回呼消耗一次性單位並產生至多一筆同類 CombatInfo。1347 經 2193、1348 經 2561；兩者最後呼叫 1943 轉 InfoEvent，再交給上層事件閉包。第八輪已確認這些是事件轉換出口，而不是最後的玩家狀態處理器。

保存參考伺服器的 TowerService::on_info_event 只對三類事件寫玩家集合／死亡欄位：GainedTower、LostTower、LostRuler。其他事件走 wildcard（萬用分支），所以 Emp、NuclearExplosion、ShellExplosion、LostForce 不直接寫 PlayerData。客戶端 TowerState 只把資訊事件放入最多 128 筆的向量；畫面消費 EMP／核爆／砲彈事件建立動畫。這不是無限累積的伺服器事件帳本。

## EMP（電磁脈衝）

### 實際寫回

- 單位消耗及 EMP 事件去重發生在戰鬥回呼。
- 塔戰 wrapper 只在收到 CombatInfo::Emp(CombatSide::Attacker) 時標記 tower_emped。
- 戰鬥後把塔的 delay 設成 max(existing_delay, 240 ticks)；防守方 EMP 不走這個塔延遲寫回。
- 每次塔 tick 若 delay 存在，就只將它減 1；該 tick 不做塔兵生產／衰減，也不讓中立塔降級。Force 移動在另一段流程，不因這個延遲停止。

### 沒有發現的玩家寫回

on_info_event 對 Info::Emp 不修改 PlayerData、score、tower_counts、cooldown 或統計。事件會送到客戶端資訊動畫。直接的全域效果是目標 Tower.delay，不是施放玩家旗標。若 EMP 戰鬥同時殺死 Ruler，淘汰來自另一個 LostRuler 事件。

## Nuke（核彈）

- 戰鬥回呼消耗 Nuke，並以 NuclearExplosion 發一筆位置事件；塔型減傷、特殊 damage、兵力／owner 終局處理屬第八輪已映射局部 resolver。
- 保存伺服器資訊處理器忽略 NuclearExplosion，客戶端建立核爆動畫。沒有直接玩家計數、冷卻、統計或分數寫入。
- 若局部戰鬥另殺死 Ruler，LostRuler 事件走淘汰鏈；若塔主變動，則由 LostTower／GainedTower 事件更新玩家塔集合，分數於後續每秒掃描重算。

## Shell（砲彈）

- 戰鬥回呼消耗 Shell，並以 ShellExplosion 發一筆位置事件；傷害、單場事件去重和局部塔結果依第八輪映射。
- 保存伺服器資訊處理器忽略 ShellExplosion，客戶端建立砲彈動畫。沒有直接玩家計數、冷卻、統計或分數寫入。
- Ruler 被殺或塔主改變時仍走一般 LostRuler／LostTower／GainedTower 狀態鏈。

## 事件與玩家狀態矩陣

| 事件 | 戰鬥物件寫回 | Tower 寫回 | PlayerData 直接寫回 | 間接狀態路徑 |
|---|---|---|---|---|
| EMP | 消耗 EMP；發 Emp 資訊事件 | 攻方 EMP：delay 至少 240 ticks | 無 | Ruler 死亡或塔主變動時，分別走淘汰或塔集合更新 |
| Nuke | 消耗 Nuke；發 NuclearExplosion | 一般戰鬥終局，可能改塔主 | 無 | Ruler 死亡或塔主變動時走一般事件鏈 |
| Shell | 消耗 Shell；發 ShellExplosion | 一般戰鬥終局，可能改塔主 | 無 | Ruler 死亡或塔主變動時走一般事件鏈 |

## 支援界線

事件消費在保存伺服器來源中已閉合，不代表目前 Python Battle Mirror（戰鬥鏡像）能預測特殊戰鬥。鏡像尚不輸出 Tower.delay 差分、特殊事件或 Ruler death／player elimination 事件；Shell、EMP、Nuke 及含 Ruler 輸入仍應回 UNSUPPORTED_CASE。

## 證據

- runtime/research/source-map/kiomet-local/common/src/combatants.rs:135-202
- runtime/research/source-map/kiomet-local/common/src/chunk.rs:321-344, 355-405
- runtime/research/source-map/kiomet-local/common/src/chunk.rs:160-177
- runtime/research/source-map/kiomet-local/server/src/service.rs:502-553
- runtime/research/source-map/kiomet-local/client/src/state.rs:14-49
- runtime/research/source-map/kiomet-local/client/src/game.rs:908-927
- 第八輪 GPT_FUNC1347_ANALYSIS.md、GPT_FUNC1348_ANALYSIS.md、GPT_BATTLE_INTEGER_RULES.json
