# Ruler（國王）事件流程與光環更新

## Ruler 死亡資料流

Combatants::fight（戰鬥解析）
→ 1347（塔戰）／1348（部隊碰撞）的 Ruler 離場回呼
→ CombatInfo::AttackerLostRuler(unit) 或 DefenderLostRuler(unit)
→ 2193／2561（事件橋接）
→ 1943（CombatInfo::into_info_event，戰鬥事件轉資訊事件）
→ Info::LostRuler { player_id, KilledBy(opponent, unit) }
→ TowerService::on_info_event（塔服務資訊事件處理器）
→ 寫 PlayerData.death_reason = RulerKilled，並把玩家排入 maybe_dead
→ 若有擊殺者，同一處理呼叫 tally_victory(killer, dead)
→ 下一個 post_update 邊界呼叫 kill_player（玩家淘汰清理）
→ alive=false、清除全部所屬塔／Ruler／Shield／入出部隊／聯盟
→ 各塔發出 LostTower(PlayerKilled)，更新玩家塔集合

資料流證據：保存伺服器參考來源 common/src/combatants.rs:14-49, 135-202、server/src/service.rs:436-462, 502-553、server/src/world.rs:347-404、common/src/chunk/maintenance.rs:34-58。正式版戰鬥端 1347／1348／2193／2561／1943 的對應已在第八輪映射；最終伺服器事件目標由傳入閉包提供，不能從 1347 本身判定。

### 時序上的「立即」

LostRuler 消費回呼立即記錄死亡原因並排入 maybe_dead，也在該處呼叫擊殺統計；它本身不直接寫 alive=false。post_update 先處理上一輪 maybe_dead，再呼叫 tick_before_inputs。若 Ruler 死亡是在本次 tick 的戰鬥中發生，清理會在下一個 post_update 邊界執行。因此狀態是「死亡事件後排程淘汰」，不是回呼內同步改存活旗標。

### 重新 Spawn

沒有自動 Ruler respawn（重生）。但 Command::Spawn 在 alive=false 時允許呼叫 spawn_player；成功生成新塔時發出 GainedTower(Spawned)，消費者將 alive 設 true。新 Spawn 同時清掉 death_reason 並把 score、lifetime 歸零。

## Ruler aura（國王光環）語意

| 項目 | 靜態證據與判定 |
|---|---|
| 來源 | 正式版 World player record +0：可選 TowerId 的 8-byte 打包位置。func448 以塔 owner 找 Player record。 |
| 範圍 | 同塔或鄰接塔；檢查的是 TowerId 相同／鄰接，不是玩家全域或一般距離場。 |
| Tower 快照 | Tower+45，u8 布林值。每塔依 (tower_index XOR tick) & 15 == 0 輪流更新。 |
| Force 快照 | 派兵時 func1791 複製來源 Tower+45 到 Force+21；現有 Force 保留派遣時值。 |
| 戰鬥讀取 | func448 塔戰讀攻方 Force+21 與守方 Tower+45；func522 部隊碰撞讀雙方 Force+21。 |
| 移動 A→B | Player+0 更新後，塔旗標由 func448 在後續各自排程重算；新派 Force 讀更新後來源塔旗標。移動中 Force+21 不由目前位置重算。 |
| 死亡清除 | 伺服器參考清理移除玩家全部塔與 Force；無主 Tower 在 func448 無主分支中將 Tower+45 設為 0，各塔在下一次排程更新時清除，最長約 16 ticks。此結論不依賴 Player+0 清除時序。 |

Round6 的正式版函式／布局證據：GPT_MORALE_ANALYSIS.md、GPT_MORALE_LAYOUT.json、GPT_MORALE_FUNCTION_MAP.json。其信心水準為客戶端靜態高信心；伺服器端位置更新語意仍部分確認。

## 邊界

- 不將 PlayerData.alerts.ruler_position（約略警示位置）視為正式版 Player+0 的權威伺服器欄位；保存服務來源每秒掃描自有塔，可能不含在途 Force。正常移動的 Player+0 更新端仍待核對。
- 不將 Ruler death event 等同當下同步 alive=false；兩者之間有 maybe_dead 隊列與更新邊界。
- 不因靜態結果而把含 Ruler 的戰鬥加入鏡像；完整玩家／世界狀態尚非鏡像輸入。
