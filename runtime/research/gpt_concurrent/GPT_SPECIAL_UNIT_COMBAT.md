# 特殊單位戰鬥分支：Round 8 靜態結論

正式版函式 `448`（塔抵達）與 `522`（部隊相撞）都會進入一般選兵／傷害迴圈。`448` 使用 `1347`、`522` 使用 `1348` 處理每次替換。兩個回呼會扣除一次性單位、更新投入中的 last-unit（上一個投入單位），並把 `CombatInfo`（戰鬥事件）轉成 `InfoEvent`（資訊事件）。它們不是勝負判定器。

| 單位 | 列舉值／戰鬥順序 | 傷害、欄位與消耗 | 可確認的戰後效果 |
|---|---|---|---|
| Shell（砲彈） | 6；普通六種之後、EMP 之前 | u8（無號 8 位元）傷害 3；一次性，出手時立刻扣 1。作為 ranged（遠程）單位；Force（部隊）中在 Air（空中），Tower（塔）中只有容量 overflow（超容量）時才是 Air。 | 每場戰鬥最多送一次 ShellExplosion（砲彈爆炸）事件；傷害仍進一般累積器。沒有直接 owner（所有權）寫入。 |
| EMP（電磁脈衝） | 7；Shell 之後、Nuke 之前 | u8 傷害 1；一次性，出手時立刻扣 1；事件帶攻／守側。 | `448` 只有攻方 EMP 時將 Tower `+47` 設成 `max(現值,240)`。`Tower.delay` 倒數期間，塔兵力生產／衰減與中立塔降級跳過該節拍；不改 Force 移動進度。`522` 部隊相撞沒有 Tower 寫入。 |
| Nuke（核彈） | 8；EMP 之後、Ruler 之前 | damage sentinel（傷害哨兵值）31；先按目標 TowerType（塔型）遠程減傷：Bunker 為 `floor(31/3)=10`，Headquarters 為 `floor(2×31/3)=20`，其餘為 31；31 再轉為 `INT32_MAX`。一次性，出手時扣 1。 | `2022` 在 `prev_damage × -direction > INT32_MAX/2` 時把該次傷害限制為 `min(d,1000)`。每場戰鬥最多送一次 NuclearExplosion（核爆）事件。Nuke 透過一般 winner（勝者）與 Tower owner 分支生效，不直接設塔主。 |
| Ruler（國王） | 9；最後順位 | damage 1；不是 `is_single_use`（一次性判定），不在第一次出手時扣除；計入士氣。 | 上一投入 Ruler 被替換／尾端清理時扣除，事件帶對側 last-unit 作為擊殺原因。玩家淘汰等 InfoEvent 消費後果在戰鬥 wrapper 外。 |

## 去重、資料型別與目標規則

- Shell、EMP、Nuke 的 1347／1348 每戰旗標會使事件最多發出一次；每個一次性單位仍各自進入戰鬥並消耗。這與來源 `Combatants::fight` 的 `shelled`／`emped`／`nuked` 去重布林值相符。
- 這三種遠程單位不計入士氣 N；Ruler 計入。Force 對 Force 使用兩側 Force 光環快照；Force 對 Tower 在士氣前清除攻方 Shield、保留守方 Tower Shield。
- 遠程傷害減傷只在目標有 TowerType 時套用；Force 對 Force 不使用 TowerType 減傷。
- `1943 CombatInfo::into_info_event` 把事件種類、側別、位置及玩家欄位轉為 InfoEvent，再由呼叫者閉包送出。此事件派送不替代傷害、存活或 owner 分支。
- Shell 與 Nuke 的傷害／消耗本身不檢查玩家 ID；最後是否換塔主仍由普通勝者公式決定。EMP 的塔延遲對「攻方側」敏感：只有攻方 EMP 設 Tower delay，不以塔主 ID 判斷。Ruler 陣亡事件帶入其所屬玩家與擊殺者側資料；玩家淘汰寫回在事件消費器外。

## 鏡像支援界線

局部傷害、一次性扣除、事件種類與 EMP 塔延遲均已靜態對應；Ruler 離場事件也可對應到擊殺者單位。但 `battle_mirror_partial.py` 仍回 `UNSUPPORTED_CASE`（不支援案例）於 Shell、EMP、Nuke、Ruler 輸入，避免把戰鬥事件與外層玩家狀態後果混成同一份保證。這不是把特殊單位從算術中略掉。
