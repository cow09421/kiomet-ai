# 玩家淘汰與對局結束條件

## 已確認的淘汰條件

### Ruler（國王）死亡

保存的遊戲服務來源明確把 Info::LostRuler 轉成 DeathReason::RulerKilled，記錄擊殺 alias（玩家別名）及致命 Unit（單位），並排入 maybe_dead。有擊殺者時同時呼叫 tally_victory(killer, dead)。下一個服務更新邊界呼叫 kill_player：

1. PlayerData.alive = false。
2. 全地圖套用 ChunkMaintenance::KillPlayer。
3. 該玩家所有 Tower 移除 Ruler 與 Shield 並清除 owner；服務玩家塔集合透過 LostTower(PlayerKilled) 逐一移除。
4. 該玩家所有 inbound／outbound Force 移除。
5. 清理自己及盟友對自己的聯盟記錄。
6. 分數 API 對死亡者回傳 Score::None。已儲存的 score 欄位不是在 kill_player 歸零，而是在重新 Spawn 時歸零。

這是明確的玩家淘汰流程，不只是戰鬥兵力歸零。死亡原因在事件回呼時寫入，存活旗標在後續 post_update 寫入。

### 玩家離開

player_quit 也將玩家排入 maybe_dead，之後使用同一 kill_player 清理；這條路徑不一定產生 RulerKilled death_reason。它是離開／清理，不應與 Ruler 戰死混為一談。

## 未找到的候選條件

| 候選 | 靜態判定 |
|---|---|
| 0 座塔 | 沒有找到檢查 PlayerData.towers 為空後呼叫 kill_player 的路徑；塔集合會隨佔領變動，本身不是已證實淘汰條件。 |
| Headquarters（總部）失守 | 事件消費只按所有權更新 towers；沒找到 HQ 專屬淘汰分支。 |
| Timer（計時器） | 沒找到遊戲服務計時器直接排入玩家淘汰或全場結束的路徑。正常 lifetime 計數是存活時間，不等於淘汰計時。 |
| 特殊事件本身 | EMP／Nuke／Shell 事件消費不直接淘汰；若其戰鬥另殺 Ruler，才透過 LostRuler 間接淘汰。 |

「沒有找到」限於保存的遊戲專用參考來源；不能推導為正式伺服器所有版本都不存在。

## 淘汰後狀態與重新進場

沒有自動重生，但 Command::Spawn 可在 alive=false 時呼叫 spawn_player。成功 Spawn 會找新的安全塔、設定 lifetime 與 score 為 0、清除 death_reason 並重設 alerts；Spawn tower 的 GainedTower event 再把 alive 設回 true。這是玩家明確重新進場，故「該條 Ruler 永久消失」不等於「玩家 ID 永遠不能重新開局」。

## Match（對局）結果

- Ruler 死亡會呼叫引擎 tally_victory(killer, dead)，並把 alive=false 與死亡原因送給客戶端。
- 客戶端遊戲 UI 依 alive 顯示死亡面板；這能證明個別玩家進入死亡畫面。
- 遊戲專用 Info／CombatInfo 沒有 MatchEnded 事件；保存的 TowerService 沒有「最後存活玩家」或全場結束條件可供本輪確認。
- 因此可回答「何時淘汰單一玩家」，不能回答「整場何時結算／誰是全場最終勝者」。不要把客戶端個人死亡面板等同全場結果。

## 來源

- runtime/research/source-map/kiomet-local/server/src/service.rs:169-176：退出及移除玩家。
- runtime/research/source-map/kiomet-local/server/src/service.rs:274-293：存活與分數介面。
- runtime/research/source-map/kiomet-local/server/src/service.rs:436-462, 502-553：淘汰佇列、擊殺 tally、InfoEvent 消費。
- runtime/research/source-map/kiomet-local/server/src/world.rs:21-136, 347-404：Spawn 與全世界玩家清理。
- runtime/research/source-map/kiomet-local/common/src/chunk/maintenance.rs:34-58：逐塔／部隊清理。
- runtime/research/source-map/kiomet-local/client/src/ui/game_ui.rs:132-177：alive=false 時顯示死亡 UI。

## 判定

**淘汰條件：Ruler 死亡或退出所排程的清理。** 保存來源沒有證明 0 towers、HQ loss 或 timer 會淘汰玩家，也沒有證明遊戲專用的全場 MatchEnded 條件。伺服器參考來源的玩家淘汰鏈為 PASS（通過）；正式版伺服器版本及全場對局規則仍 PARTIAL（部分完成）。
