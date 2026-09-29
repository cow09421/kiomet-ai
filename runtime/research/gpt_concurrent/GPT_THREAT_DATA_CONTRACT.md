# 入站威脅資料契約

此契約只提供客觀狀態，不設任意高／中／低分級。基礎布局由第三輪 `GPT_FORCE_STATIC_ANALYSIS.md` 證明；戰鬥投影受第五輪正式版士氣差異限制。

## `IncomingThreat`

| 欄位 | 型別與來源 | 規則 |
|---|---|---|
| `force_identity` | 本地衍生鍵 | 對局＋當前路段＋玩家＋兵力＋首次出現時間；不是遊戲內固定 ID，禁止用陣列位址當長期鍵 |
| `owner_id`, `owner_relation` | `Force+12` 與雙向盟友表 | 可空玩家值與當局映射須驗證；同玩家／雙空值為同隊，雙方同意才盟友；帶國王抵達盟友塔會改作敵對判斷 |
| `source_tower`, `target_tower`, `remaining_path` | `Force+4` 指標與 `+8` 長度 | 路徑倒序儲存：`len-1` 當前來源、`len-2` 當前目標、`0` 最終目的地；需要每節路段塔資料 |
| `target_owner` | 新鮮目標塔 `+36` | 與 `owner_relation` 同一快照世代 |
| `units` | `Force+14..+20` 7 位元組 | 另解碼為 10 兵種計數；保留原始位元組供校驗 |
| `progress` | `Force+22` | u8，目前路段進度 |
| `world_xy` | 推導 | `lerp(source.as_vec2,target.as_vec2,min(1,(progress+fractional_ticks*speed)/required))`；非獨立記憶體欄位 |
| `ETA_ticks`, `ETA_seconds` | 下式 | 對目前路段可給精確節拍估算；續段須預先假設兵力／路徑不變 |
| `battle_projection` | 可空物件 | 目前只能 `UNKNOWN`；禁止用公開版鏡像直接當正式版定論 |
| `confidence`, `freshness` | 證據 | 記錄 `match_id`、快照時間、遊戲節拍、塔集合世代、路徑有效性、配對歧義與觀察延遲 |

## 正式版 ETA（預估抵達時間）

`690 Force::speed` 與公開碼 `force.rs:289-329` 一致：普通單位以最慢兵種決定速度，Slow=1、Normal=2、Fast=3 進度／節拍。若有 `C` 架 Chopper，運載量 `4C`；全軍重量 `W=2*Tank+Soldier`。若 `W<=4C` 為 Fast；否則若慢速重量 `2*Tank<=4C` 為 Normal；其餘 Slow。一次性部隊仍以其單位速度決定。

對目前路段，`distance=TowerId::distance(source,target)`，以塔整數世界座標的歐氏距離取整數平方根（`tower/id.rs:157-173`）。`base=min(255,floor(distance*180/10))`。若 `Force+21==1`，`required=max(1,floor(base*4/5))`；否則 `required=base`（正式版 `2689:0x11ccbd..0x11cd15`）。`remaining=max(0,required-progress)`；`ETA_ticks=ceil(remaining/speed)`，`ETA_seconds=ETA_ticks/4`。本式假設快照在節拍邊界且路上不遭遇敵軍。若進度已達標但集合尚未移除，標記抵達待處理而非給負時間。

多段路徑的候選 ETA 可加總各段 `ceil(required_i/speed_i)`，首段扣既有 `progress`。但補給線、友軍續行、途中戰鬥、EMP、燃料、塔主變更與跨路徑國王轉移可能改變後續狀態；多段值必須附 `conditional`（有條件）標記。每次新快照重算，而非永久沿用派送時 ETA。

`battle_projection` 在正式版逐步規則未補齊前只能提供攻／守組成、護盾、塔型、玩家關係與 `UNKNOWN` 結果。若敵軍不是正在朝己方塔當前路段移動，資料仍可記錄但不列為「當前入站威脅」。雙集合鏡像須先去重。
