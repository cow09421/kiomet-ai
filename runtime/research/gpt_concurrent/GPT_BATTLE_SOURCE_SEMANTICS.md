# 戰鬥與抵達：公開原始碼語意

範圍：`vendor/kiomet-ref/common/src/`。這是參考版本的規則；正式版另有士氣與移動旗標，差異見 `GPT_BATTLE_PRODUCTION_ANALYSIS.md`。所有步驟為離線閱讀。

## 抵達完整鏈

1. `chunk.rs:310` 逐一處理入站集合。`Force::tick` → `raw_tick`（`force.rs:337-365`）把 `path_progress` 加上每節拍進度；達到 `progress_required` 後 `path.pop()`，回傳抵達。迴圈使用 `extract_if`，所以抵達的部隊從當前入站集合移除。
2. 目標塔就是此迴圈的 `tower_id`／`tower`。若塔已有玩家，或塔內兵力不空，先算關係。相同玩家（連同雙方皆無玩家）為 `Comrade`；兩個玩家雙向結盟為 `Ally`；其餘為 `Enemy`（`chunk.rs:128-139,511-537`）。盟友帶國王抵達會被當成不友善；其餘盟友友善。
3. 不友善者用 `Combatants::force(force.units)` 與 `Combatants::tower(tower.tower_type,tower.units)` 原地交戰（`chunk.rs:313-402`）。勝者非攻方會記錄 LostForce；勝者非守方則更新塔主。僵持（雙方皆不存活）使塔失主；攻方勝且有玩家編號才成為新塔主。失主的塔降級到底並清除延遲。`Tower::set_player_id_inner` 清掉原補給線（`tower.rs:185-209`）。
4. 塔無玩家、無兵力時不交戰；有玩家編號且 `force.units.is_alive()` 才探索取得塔主，並重整塔兵力（`chunk.rs:408-430`）。因此「中立塔」並非一律直接佔領：有中立守軍時先打；僅護盾或一次性兵種不算可佔塔活兵力。
5. 交戰或探索後重新計算關係。空部隊丟棄；`fuel=0` 到期；盟友／同隊可依路徑或補給線續行，成功則重建出站鏡像與入站項目，單類部隊同一目的地最多 8 支後擁擠丟失；其餘友善部隊併入塔兵；不友善且有國王的殘餘部隊記錄國王失去事件（`chunk.rs:433-502`）。
6. 出站鏡像由 `outbound_forces.retain_mut` 在 `raw_tick(None)` 回傳抵達時移除。路途中對向部隊可能先交戰，見 `chunk.rs:192-304`；不可把最初派出的兵力直接當作抵達兵力。

## 友軍合併、容量與特殊兵種

`Units::add_units_to_tower`（`units.rs:272-284`）逐兵種加入，跳過 `is_single_use()`，多於容量的部分因 `add_to_tower` 回傳較少而消失。塔主存在時允許暫時超量：Shield 15、Soldier 10、Tank 5、Fighter 4、Bomber／Chopper 各 2；其他 0（`unit.rs:137-151`）。正常容量由塔型決定，每類上限另受 `u8::MAX` 限制；國王在塔內額外給護盾容量 10（`units.rs:153-163`；`tower.rs:65`）。超量兵力後續在定期 `diminish_units_if_dead_or_overflow` 中逐種減 1，可觸發補給派兵（`chunk.rs:152-186`；`tower.rs:137-153`）。

`Units` 內只有 Shield 永遠可共存；`Many`（Fighter、Chopper、Bomber、Tank、Soldier）與 `Single`（Shell、Emp、Nuke、Ruler）互斥。加入 Single 可取代 Many 或較低優先的 Single；Many 無法覆蓋 Single（`units.rs:15-20,48-91,165-192`）。`Shield` 不能對塔進攻：戰鬥開始時塔的對手護盾被清空（`combatants.rs:117-126`）。國王不是一次性兵種，會最後上場；死亡觸發 LostRuler。一次性 Shell／Emp／Nuke 使用時即扣除，事件最多各一筆，EMP 可使塔延遲至少 60 秒（每秒 4 節拍，即 240 節拍），見 `combatants.rs:138-176`、`chunk.rs:330-351`。

## 戰鬥解析順序

`Combatants::fight`（`combatants.rs:105-366`）是確定性原地修改，沒有戰鬥用亂數。順序為 Air 後 Surface，單位按 `Unit` 枚舉優先序取用：Shield、Fighter、Chopper、Bomber、Tank、Soldier、Shell、Emp、Nuke、Ruler。它維持有號累積傷害；偏向某側時另一側取下一單位抵擋，傷害回到零時雙方各取下一單位。取新單位時前一已投入的單位被消耗；一次性單位立即消耗；最後依存活兵力與累積傷害決定勝者。塔在雙方皆死的零傷害僵持下保有所有權（`combatants.rs:352-366`）。這不是「總兵力相減」。

`Unit::damage`（`unit.rs:158-177`）：Tank 3；Air Fighter／Chopper 各 3；Air Bomber 對 Surface 5；Nuke 無限傷害哨兵 31；Shell 3；其餘 1。Bunker 對遠程傷害取 `floor(d/3)`；Headquarters 取 `floor(2d/3)`（`tower.rs:402-410`）。塔內空軍兵種若未超量屬 Surface；在移動部隊或塔內超量時屬 Air。Shield 若同組有空軍，也可算 Air（`unit.rs:190-202`）。核彈互毀條件有 1000 點上限保護（`combatants.rs:222-247`）。

## 各兵種實際作用

| 兵種 | 參考版本戰鬥作用 |
|---|---|
| Fighter | Air 時傷害 3，優先攔截 |
| Chopper | Air 時傷害 3，可運載慢速陸軍；運載影響速度，不改本文件戰鬥傷害 |
| Bomber | Air 對 Surface 傷害 5，其他情況 1 |
| Tank | 傷害 3 |
| Soldier | 傷害 1，常規兵種最後上場 |
| Shield | 一般傷害 1；進攻塔時被立即清掉；單獨盾牌不構成可佔領兵力 |
| Ruler | 傷害 1、優先序最後；在盟友塔抵達時使關係轉為不友善；被殺發事件 |
| Shell | 遠程、一次性、傷害 3、產生爆炸事件；不併入塔 |
| Emp | 遠程、一次性、傷害 1、產生 EMP 事件和塔延遲；不併入塔 |
| Nuke | 遠程、一次性、無限傷害哨兵 31、產生核爆事件；不併入塔 |

塔型會改變容量、空軍位階與遠程減傷；玩家關係先決定是否開戰。本表不聲稱正式版每個組合都已對齊。
