# 國王死亡與玩家全域狀態

## 結論

保存的伺服器參考來源有完整的 Ruler death → death reason → deferred player elimination → world cleanup（國王死亡 → 死亡原因 → 延後淘汰 → 世界清理）鏈。這個死亡不是「只少一個兵」：alive 最終變成 false，玩家所有塔與行軍部隊被清除，死亡分數不再提供。沒有自動重生，但死亡玩家仍能透過 Spawn 重新進場。

正式版客戶端已靜態映射 Player record（玩家紀錄）+0 的可選 Ruler 位置，以及 Tower+45／Force+21 光環欄位。伺服器參考來源沒有對應的 authoritative ruler-location 欄位；正式版伺服器是否逐位元相同，仍未證實。

## 完整事件鏈

1. combatants.rs 的 Ruler 單位在最後投入後被替換／移除時產生 CombatInfo::AttackerLostRuler(Unit) 或 DefenderLostRuler(Unit)。事件帶致命單位，側別決定被殺玩家。
2. CombatInfo::into_info_event 將它轉為 Info::LostRuler { player_id, reason: KilledBy(opponent, unit) }。正式版 func1347／1348 呼叫事件橋接 2193／2561，再由 1943 轉成資訊事件；函式閉包目標由上層提供。
3. 保存伺服器 TowerService::on_info_event 收到 LostRuler 後，寫 PlayerData.death_reason = Some(RulerKilled { alias, unit })，並呼叫提供的 maybe_dead 回呼。
4. post_update 內的回呼把死亡玩家放進 maybe_dead，同時對已知擊殺者呼叫 context.tally_victory(killer, dead)。玩家不在這個回呼中立刻寫成 dead。
5. 下一個 post_update 邊界取出前一輪的 maybe_dead，呼叫 kill_player：先寫 alive=false，再對所有 Chunk（區塊）套用 ChunkMaintenance::KillPlayer。
6. 每座屬於玩家的塔移除 Ruler 與 Shield，呼叫塔主權 setter 設為無主，並送出 LostTower { reason: PlayerKilled }。所有該玩家的 inbound／outbound Force 被過濾移除；不再發 LostRuler。玩家本身的聯盟集合及其盟友對玩家的關係也被清理。
7. LostTower 消費者從玩家塔集合移除塔。死者的 get_score 回傳 Score::None；原始 score 欄位不在 kill_player 內歸零。重新 Spawn 時才清零 score、lifetime（存活時間）、death_reason（死亡原因）與 alerts（警示）。

## 玩家是否能重生

保存來源的 Command::Spawn 直接呼叫 spawn_player。它只拒絕 alive=true 的玩家，所以已死亡玩家可再次發出 Spawn。成功生成時，生成塔事件以 GainedTowerReason::Spawned 令 alive=true 並插入新塔。這是明確重新進場，不是 Ruler 自動復活；每次重生會建立新的 Ruler 和新起始塔。

## Ruler 位置與光環

### 正式版客戶端中已映射的欄位

- World player record 步幅 64 bytes；+0 為 8-byte packed optional TowerId。低 32 位最低位是存在旗標，高 32 位是 TowerId。
- func460 讀伺服器 PlayerInput 的 8-byte 值寫入 Player+0；另一分支會把 Player+0 清為 0。這只能證明客戶端寫入與清除路徑，不能確定伺服器何時發送兩種更新。
- func448 在 (tower_index XOR tick) & 15 == 0 時，檢查持有塔的 owner、Player+0 位置與當前 TowerId。Ruler 位於該塔或鄰塔時 Tower+45 寫 1；否則寫 0。每塔分散重算，並非移動當刻全局即時清除。
- 部隊派遣時 func1791 將 Tower+45 複製到 Force+21。Force+21 同時影響部隊移動進度與戰鬥士氣初值；已在路上的 Force 保留當時快照。

### A → B 移動／死亡的已知與未知部分

- 已知：位置紀錄變更後，各 Tower+45 由 func448 輪流更新；新派 Force 複製當時來源塔的 +45。Ruler 死亡清理會刪除全部持有 Ruler 的塔狀態與該玩家 Force。
- 未知：正式版伺服器寫入 Player+0 的函式、該欄位代表 Ruler 在塔上或移動中的位置、死亡時清除更新的精確時序、已存在 Force+21 的後續更新規則。現有客戶端靜態證據不能補出伺服器事件來源。

保存服務來源另有 PlayerData.alerts.ruler_position，它是每秒掃描自有塔並重設的近似警示資料，不等同已證實的正式版 Player+0 欄位。

## 對生產、移動、士氣、分數與對局的影響

- **塔主權**：淘汰清理對所有塔設無主，供應路徑也由塔主 setter 清除。
- **生產**：所有原屬玩家的塔失主，之後依中立塔規則運作；EMP delay 另有獨立倒數。
- **移動**：玩家名下入／出部隊被移除；不能視作只有 Ruler 單位被扣除。
- **士氣／光環**：死亡清理把該玩家所有塔設為無主；正式版 func448 的無主分支把 Tower+45 寫 0。各塔在下一次自己的更新時清除，最長約 16 ticks。這條淘汰後清理不依賴 Player+0 是否立即清零；Player+0 的正常移動更新來源仍未知。
- **分數**：存活者每秒以活動塔的 score_weight 加總；死亡後 get_score 回傳 None。死亡路徑不直接把內存 score 寫 0，重新 Spawn 才歸零。
- **對局結果**：擊殺者可獲 tally_victory；自己的客戶端收到 alive=false 與 death_reason 後顯示死亡面板。遊戲專用事件列舉沒有全場 MatchEnded 事件；沒有證據可判斷整場何時結束。

## 證據位置

- runtime/research/source-map/kiomet-local/common/src/combatants.rs:14-49, 135-202：戰鬥事件、Ruler 移除和轉資訊事件。
- runtime/research/source-map/kiomet-local/common/src/info.rs:21-69：資訊事件及死亡原因。
- runtime/research/source-map/kiomet-local/server/src/service.rs:41-55, 274-293, 342-426, 436-462, 502-553：PlayerData、分數、tower counts、排程與 LostRuler 消費者。
- runtime/research/source-map/kiomet-local/server/src/world.rs:21-136, 347-404：重新 Spawn 與 kill_player 清理。
- runtime/research/source-map/kiomet-local/common/src/chunk/maintenance.rs:16-58：塔、部隊及 LostTower 清理。
- runtime/research/source-map/kiomet-local/common/src/chunk.rs:147-185, 310-405：塔更新、戰鬥事件與 owner 寫回。
- GPT_MORALE_LAYOUT.json、GPT_MORALE_ANALYSIS.md：正式版客戶端 Player+0、Tower+45、Force+21 靜態映射。

## 判定

保存伺服器參考來源中的「Ruler 死亡導致玩家淘汰」是明確規則，不是猜測。淘汰寫入延後到下一個 post_update 邊界；之後可透過 Spawn 明確重新進場。正式版伺服器位址及 Player+0 更新時序仍未對上，因此此文件不是正式版執行期差異驗證。
