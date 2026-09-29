# 第七輪：正式版戰鬥算術收尾

範圍：正式版樣本 `production-client_bg.wasm`，SHA-256 `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`；以離線反組譯及公開參考碼交叉閱讀。未執行 WASM（網頁組件），未連線遊戲。

## 士氣與初始累積值

正式版函式 `1778 Combatants::morale_advantage` 遍歷 `Units`（兵力集合）的全部兵種計數，排除 `Unit::is_single_use` 為真的單位，將剩餘數量相加，再做無號右移 1 位及上限 3：

```
N = Shield + Fighter + Chopper + Bomber + Tank + Soldier + Ruler
M = min(3, floor(N / 2))
```

Shell（砲彈）、EMP（電磁脈衝）、Nuke（核彈）屬一次性／遠程單位，不計入 N。Ruler（國王）會計入。Shield（護盾）也會計入**戰鬥入口當下仍存在的數量**：攻塔前 `4969` 以塔型 sentinel（哨兵值）27 對 `Tower.units` 呼叫時保留塔盾；再以實際塔型對攻方 `Force.units` 呼叫時移除攻方盾。因此塔戰的攻方 M 不含其派兵盾，守方 M 可含塔盾。Force 對 Force 遭遇沒有 Tower 型別，這個攻塔護盾清除包裝不適用，兩側盾都可計入。N 是整份 `Units` 中的計數總和，不只當回合被選為作戰單位的兵，也不按兵種加權。

士氣只在戰鬥入口初始化一次，並不每回合重算：

```
A = 攻方 Force+21 != 0
D = 守方 Tower+45 & 1 != 0       # 力量遭遇則 D = 對方 Force+21 != 0
damage0 =  A && !D ? +M(攻方 Units)
        : !A &&  D ? -M(守方 Units)
        : 0
```

兩側旗標都為真時不是相減，而是抵銷為 0。這是一個**共用的有號 i32 累積傷害初值**，沒有分開存放的 attacker／defender accumulator（攻守累積器）。正值表示累積方向偏攻方，負值偏守方。`448:0x01acd4..0x01ad06` 與 `522:0x068fa4..0x068fd6` 分別把該值交給攻塔與對向部隊戰鬥。光環旗標是布林值，不是層數：Tower+45 依塔主玩家記錄中的國王 TowerId 與該塔相同或相鄰設為 1；Force+21 是派出時複製的光環快照。故可精確描述為國王位置**同塔／鄰接塔條件**，不是玩家全域兵數或路徑距離加成。

## 傷害整數規則

`2022` 呼叫 `2970 Unit::damage`，後者回傳 u8（無號 8 位整數）：Shield／Soldier 為 1；Tank 為 3；Fighter／Chopper 在 Air（空中）欄位為 3、否則 1；Bomber 在 Air 對 Surface（地面）為 5、否則 1；Shell 為 3、EMP 為 1；Nuke 回傳 31 作為無限傷害 sentinel。一次性兵種若攻擊 Tower，先過 TowerType 遠程傷害：Bunker（碉堡）`floor(d/3)`，Headquarters（總部）`floor((2*d)/3)`，其他塔保持 d。這些是無號整數除法，向下取整；HQ 先乘 2 再除 3。

`2022` 以 `d==31` 將 sentinel 映成 `INT32_MAX`。通常保留此值；只有會把方向相反的累積值推過 signed half-range（有號半範圍）時，才將此 hit（命中）降到 1000。公開碼 predicate（條件）是：

```
if previous_damage * -direction > INT32_MAX / 2:
    d = min(d, 1000)
```

其中 `direction=+1` 為攻方打守方，`-1` 為守方打攻方；正式碼以 `i32.mul`、`i32.sub`、signed `i32.lt_s` 實作等價 guard。一般 Rust／WASM `i32.add`、`i32.mul`、`i32.sub` 是二補數 32 位元環繞運算，不是 saturating add（飽和加法）；`Unit::damage_to_finite` 先處理 Nuke sentinel。士氣是無號兵數的 `shr_u 1`，等同整除 2 向下取整，接著 `min(3,…)`；無浮點數、ceil（向上取整）或定點算術。

## 逐回合順序與兵種

正式 `1185`／`2408`／`2827` 的下一兵種查找配合 `448`／`522` 迴圈，與參考 `combatants.rs` 一致採**循序**而非雙方同時扣兵：Air 優先於 Surface；同一欄位按 enum（列舉）優先序：Shield、Fighter、Chopper、Bomber、Tank、Soldier、Shell、EMP、Nuke、Ruler。每次選一個攻擊單位，依累積值選攻方或守方；累積為 0 且雙側均有候選時，參考碼 `next_defender.and(next_attacker)` 選攻方先行。先選上場的單位保留為 `last`；該側下次再選單位時，上一個非一次性單位扣除一個，表示它戰死。一次性單位在選中時立即消耗。欄位處理結束後另有最後清理／剩餘單位結算；本輪已確認存在於 `448`／`522`，但其 inline（內嵌）分支與正式版結果欄位逐值對映仍需完成。

| 兵種 | 已確認的戰鬥角色 | 限制／邊界 |
|---|---|---|
| Fighter | 空中傷害 3，地面傷害 1； enum 次序在 Shield 後 | 空軍塔 stack 是否空中取決於兵數超容量 |
| Chopper | 空中傷害 3，其他 1；在 Fighter 後 | 同上 |
| Bomber | Air 對 Surface 傷害 5，其他 1 | 同上 |
| Tank | 固定傷害 3 | 地面欄位 |
| Soldier | 固定傷害 1；普通 Many（多數型）兵種最後上場 | 地面欄位 |
| Shield | 普通、非一次性、傷害 1；enum 最先 | 不吸收傷害；上場後下一個同側單位上場時被消耗；攻塔時 Force 盾先清除，塔盾保留 |
| Ruler | 普通最後順位單位、傷害 1、計入士氣 | 死亡回呼與正式伺服器淘汰結果未完全對映，部分鏡像排除此單位 |
| Shell／EMP／Nuke | 被相同 enum 迴圈選中；上場即由 `1347` 消耗並設事件旗標，然後仍呼叫 `2022` 計傷 | 回呼側別、特殊效果應用及最後存活組合未全部重建，部分鏡像排除 |

Tower 中空軍單位若數量**大於**該兵種容量則計 Air；Force 中 Fighter／Chopper／Bomber 計 Air。Shield 的欄位取該作戰群組中最高欄位。`Units::is_alive` 不把 Shield 或一次性兵種視為可佔塔的存活單位。

## 分支語意與確定性

- 中立且守軍集合空：在 `448` 直接探索／設塔主，不進戰鬥迴圈；後續仍要按友軍抵達路徑併兵及容量／溢出規則結算，不能把原攻方兵力無條件原樣當塔兵。
- 中立且有守軍、敵塔：都會從 `448` Force-vs-Tower 同一內嵌戰鬥體處理。獲勝後塔主更新走 `3571`，敵塔失主再依分支降級；完整塔內兵種 reconcile（重整）與特殊單位組合尚未涵蓋。
- 己方／友盟友軍到塔：由抵達關係分支續行或 `2195` 併兵，完全不呼叫士氣 `1778` 或傷害 `2022`；這是 resolver（解析器）外的合併分支。
- 對向 Force 戰鬥：`522` 是另一個抵達／出站 wrapper（包裝層），但內聯選兵、士氣、傷害函式與塔戰共用；塔型遠程傷害沒有敵塔目標。
- `448`／`522` 戰鬥呼叫圖未見 RNG（隨機數產生器）或 PRNG（偽隨機數產生器）呼叫；配合參考碼確定性迴圈，`BATTLE_DETERMINISM = PASS`（戰鬥確定性通過，靜態）。

## 狀態與最後阻擋點

`P0 BATTLE ARITHMETIC = PARTIAL`。初值、整數傷害函式、排序與 Shield 語意已有具體證據；但 `448`／`522` 內嵌的 terminal（終端）清理、`1347` 的 Ruler／單次事件回呼與最後勝者欄位尚未全逐項映回參考演算法。這是目前阻止完整 Battle Mirror（戰鬥鏡像）安全輸出勝者與殘兵的**主要單一 blocker（阻擋點）**。因此另附 `battle_mirror_partial.py`，只接受普通兵種 Force 對非空 Tower；其餘分支回傳 `UNSUPPORTED_CASE`。靜態子集結果仍未經執行期驗證。
