# Kiomet GPT 並行高難題攻關第九輪交接

## 範圍與證據

本輪只做離線靜態追蹤，未連接瀏覽器、CDP（Chrome 開發者工具協定）或偵錯器，未呼叫正式版 WASM（網頁組件），未操作遊戲，也未停止或重啟 Muse。

追蹤起點是第八輪的 1347／1348 戰鬥回呼與 2193／2561 事件橋接。新閉合的伺服器事件消費流程來自保存於 runtime/research/source-map/kiomet-local/ 的參考來源：common/src/info.rs、server/src/service.rs、server/src/world.rs、common/src/chunk/maintenance.rs。正式版客戶端靜態映射仍使用 SHA-256 fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c。伺服器參考來源與正式版伺服器產物的版本一致性，不能由本輪證據確認。

## GPT ROUND 9 GLOBAL COMBAT STATE REPORT

### RULER DEATH（國王死亡）

- **Event Producer（事件產生者）**：1347（塔戰）／1348（部隊相撞）的 Ruler（國王）離場分支；CombatInfo::AttackerLostRuler 或 DefenderLostRuler 攜帶致命單位。2193／2561 轉成 Info::LostRuler。
- **Event Consumer（事件消費者）**：TowerService::on_info_event（塔服務資訊事件處理器）。
- **Player State Writes（玩家狀態寫入）**：先寫 death_reason = RulerKilled { killer alias, unit }，並排入 maybe_dead；同一處理回呼會呼叫 tally_victory(killer, dead)。下一個 post_update 邊界才執行 kill_player，寫 alive = false。
- **Elimination（淘汰）**：YES（是），在保存的伺服器參考來源中，Ruler 死亡會排程淘汰；alive=false 不是在 LostRuler 回呼內同步寫入，而是在下一個更新邊界寫入。
- **Cleanup（清理）**：清除該玩家所有塔上的 Ruler 與 Shield（護盾）、塔主權、所有入／出部隊及盟友關係；各塔發出 LostTower(PlayerKilled)。清理不再發出第二個 LostRuler。
- **Respawn（重生）**：沒有自動重生；玩家死亡後仍可透過 Spawn 命令重新進場。這會重設死亡原因、分數與存活時間，並由生成事件重新設 alive=true。Ruler 在該次生命中消失，但玩家可以明確重新進場。
- **Aura Cleanup（光環清除）**：清理使該玩家所有塔變成無主。正式版 func448（函式 448）的無主分支將 Tower+45 寫 0；因此各塔在自己的下一次排程更新後清除，最長約 16 ticks（節拍），不是死亡回呼內同步清除。這不依賴 Player+0 位置欄位是否即時清零。
- **Status（狀態）**：參考伺服器事件到淘汰清理鏈 PASS（通過）；正式版伺服器版本一致性及 Ruler 位置欄位寫入仍 PARTIAL（部分完成）。

### RULER AURA（國王光環）

- **Scope（範圍）**：同塔或鄰塔；不是全玩家、任意距離或路徑光環。
- **Storage / Derivation（儲存／推導）**：玩家位置紀錄 +0 保存可選 TowerId（塔識別碼）；Tower+45 是依位置推導的一位元組布林快照。func448 以 (tower_index XOR tick) & 15 == 0 分散排程更新。持有 Ruler 的 Tower 若屬於該玩家，且其位置與 Ruler 同塔或鄰接，寫 1，否則寫 0。
- **Movement Update（移動更新）**：玩家位置資料由正式版客戶端 func460 從伺服器 PlayerInput（玩家輸入更新）複製或清除；伺服器端確切寫入端未定位。塔光環不是全表即時重算，而是各塔輪流更新。部署部隊時，Tower+45 複製到 Force+21；在途 Force（部隊）的值是快照，Ruler 後來移動不會回溯更新這個已部署 Force。
- **Battle Input（戰鬥輸入）**：塔戰讀 Force+21 與 Tower+45；部隊碰撞讀雙方 Force+21。Battle Mirror（戰鬥鏡像）可安全使用已提供的布林快照，但不應只靠目前 Ruler 位置推估一支在途部隊的旗標。
- **Status（狀態）**：光環作用範圍、衍生欄位及淘汰後清除語意 PASS（通過）；正常移動時正式版伺服器位置欄位來源與跨版本一致性 PARTIAL（部分完成）。

### EMP（電磁脈衝）

- **Local Effect（局部效果）**：一次性消耗 EMP；只有攻方 EMP 事件令目標 Tower.delay（塔延遲）成為 max(原值, 240 ticks)。倒數期間暫停該塔的生產／衰減及中立塔降級，不停止 Force 移動。
- **Global Effect（全域效果）**：伺服器 on_info_event 對 Info::Emp 落入忽略分支；沒有已見的 PlayerData（玩家資料）、冷卻、分數或統計寫入。資訊事件另供客戶端動畫。若同一戰鬥另殺死 Ruler，則獨立的 LostRuler 事件仍會導致淘汰。
- **Status（狀態）**：參考來源事件消費與塔延遲 PASS（通過）；鏡像尚未回傳此效果，故 EMP 戰鬥仍 UNSUPPORTED（不支援）。

### NUKE（核彈）

- **Local Effect（局部效果）**：一次性消耗；傷害、塔型減傷、塔主／兵力終局處理依第八輪映射。核爆資訊事件沒有獨立玩家資料寫回。
- **Global Effect（全域效果）**：伺服器資訊處理器忽略 Info::NuclearExplosion；客戶端將有限長度資訊事件轉為核爆動畫。若核彈戰鬥造成 Ruler 死亡，另走 Ruler 淘汰鏈。
- **Status（狀態）**：直接全域事件處理 PASS（通過）；核彈戰鬥仍 UNSUPPORTED（不支援），因鏡像未實作特殊兵傷害／事件及其條件式淘汰。

### SHELL（砲彈）

- **Local Effect（局部效果）**：一次性消耗；傷害及塔戰終局依第八輪映射。砲彈爆炸資訊事件本身不寫玩家資料。
- **Global Effect（全域效果）**：伺服器資訊處理器忽略 Info::ShellExplosion；客戶端只建立動畫。若砲彈戰鬥造成 Ruler 死亡，另走 Ruler 淘汰鏈。
- **Status（狀態）**：直接全域事件處理 PASS（通過）；砲彈戰鬥仍 UNSUPPORTED（不支援），因鏡像未實作特殊兵戰鬥回呼。

### PLAYER ELIMINATION（玩家淘汰）

- **Condition（條件）**：Ruler 死亡；玩家離開也會排入同一清理程序，但不是 Ruler 死亡。沒有找到 0 座塔、HQ（總部）失守或計時器直接淘汰的程式路徑。
- **State Transition（狀態轉換）**：LostRuler 寫死亡原因並排程；下一個 post_update 寫 alive=false，清空塔主權、塔內 Ruler／Shield、行軍部隊和盟友。分數查詢對死亡玩家回傳無分數；原分數欄位不在死亡路徑清零，只在下次 Spawn 重設。
- **Match Effect（對局影響）**：呼叫引擎 tally_victory(killer, dead) 並送出 alive=false／death_reason；客戶端顯示死亡面板。遊戲專用來源中沒有全場 MatchEnded 事件或「最後一名玩家存活」處理器，因此全局對局是否結束不作推論。
- **Status（狀態）**：保存參考伺服器淘汰流程 PASS（通過）；正式版伺服器版本核對與全場結束規則 PARTIAL（部分完成）。

### BATTLE MIRROR（戰鬥鏡像）

- **Previous（先前）**：PARTIAL（部分完成）。
- **Current（目前）**：PARTIAL（部分完成）。
- **New Supported Cases（新增支援案例）**：無。已閉合的 Ruler 事件消費鏈可以描述，但現有鏡像沒有 PlayerData／整張世界狀態輸入，不能安全回報淘汰後的完整玩家狀態。battle_mirror_partial.py 保持不變。
- **Remaining Unsupported（仍不支援）**：任何參戰兵力含 Ruler、Shell、EMP、Nuke；特殊事件戰鬥輸出；完整玩家塔集合／分數寫回；中立空塔佔領、友軍合併、續行、燃料與同節拍排程。

## 最重要三題

1. **Q1：Ruler 死亡後玩家全域狀態發生什麼？**  
   事件回呼先寫 RulerKilled 死亡原因並排程淘汰；下一個更新邊界設 alive=false，再清除其所有塔、Ruler／Shield、在途部隊及盟友。所有塔變無主後，各塔在至多 16 ticks 內的下一次光環更新將 Tower+45 清零。該局生命不自動重生，但死亡玩家可透過 Spawn 命令重新進場。
2. **Q2：普通 PvP（玩家對玩家）＋Shield＋Ruler aura 能否完整預測戰果與玩家全域後果？**  
   **PARTIAL（部分完成）**。戰鬥勝者、殘兵、塔主結果在已映射普通子集及明確光環快照下可預測；鏡像沒有完整世界／玩家集合，不能回報事件後的完整玩家資料與分數。
3. **Q3：哪些情況仍必須 UNSUPPORTED_CASE（不支援案例）？**  
   Ruler 參戰或陣亡、Shell／EMP／Nuke、需要完整玩家資料的事件寫回、空中立塔直接佔領，以及戰後移動／合併／燃料與同節拍部隊排程。

## 唯一主要 blocker（阻塞）

Battle Mirror（戰鬥鏡像）沒有 PlayerData（玩家資料）與全世界塔／部隊狀態輸入，因此不能從單場戰鬥安全產出完整玩家全域狀態差分；保存伺服器參考來源與正式版伺服器版本也未核對。不要把局部勝負結果標成完整 PvP 後果。

## Muse Integration Queue（Muse 整合佇列）

- **IMMEDIATE（可立即工程化）**：沿用第八輪普通戰鬥輸入限制；傳入明確 Aura（光環）快照；只在支援子集讀勝者、殘兵與塔主結果；Ruler／特殊兵種存在時拒絕決策。
- **RUNTIME VALIDATION（執行期核驗）**：在另行安排的隔離驗證中核對正式版伺服器事件到 alive、死亡原因、塔清理及 Player+0 清除時間。這輪未做。
- **DO NOT USE（不可進入規劃器）**：Ruler 戰鬥／淘汰結果、Shell／EMP／Nuke 戰果與副作用、完整分數／塔集合預測、未映射的移動合併路徑。

## 完成邊界

- Runtime connections（執行期連線）= 0
- Browser connections（瀏覽器連線）= 0
- Game actions（遊戲操作）= 0
- Tracked files modified（追蹤檔案修改）= 0
- Git commits（Git 提交）= 0
- battle_mirror_partial.py 未修改；未新增正式 Planner（規劃器）或 PvP 決策契約。
