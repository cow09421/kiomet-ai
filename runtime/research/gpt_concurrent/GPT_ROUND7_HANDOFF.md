# GPT 第七輪：戰鬥解析器交接

## 結果摘要

| 項目 | 結果 | 狀態 |
|---|---|---|
| P0 初始累積值與傷害算術 | 單一 signed i32 累積值；士氣只在入口初始化；傷害、遠程減傷與 Nuke 溢位 guard 已追到指令 | **PARTIAL**；終端整理仍未全部映回 |
| P1 特殊單位 | Shell／EMP／Nuke 走一般選兵、傷害呼叫並由回呼消耗／設效果旗標；Ruler 是普通末順位兵及事件單位 | **PARTIAL**；事件側別與戰後處置未完 |
| P2 函式圖 | 30 個關鍵正式版函式，含位置、呼叫者／被呼叫者、source match（來源對應）與信心 | **PARTIAL**；`448`／`522` terminal result 的暫存欄位仍未全對映 |
| P3 戰鬥資料表 | 無獨立傷害矩陣；有 enum 順序與傷害公式；22 個容量資料列數值與參考碼 22/22 相符；5 個特殊塔型走專門分支 | **PARTIAL**；特殊塔型產生分支未全解 |
| P4 戰鬥鏡像 | `battle_mirror_partial.py` 已建立；只計算普通兵種 Force 對非空 Tower | **PARTIAL**；含特殊單位、國王、友軍分支、空塔捕獲或其他未確認輸入皆回 `UNSUPPORTED_CASE` |
| P5 靜態案例 | 29 個案例：20 個在支援子集、9 個預期拒絕；不呼叫正式版 WASM | **PARTIAL**；案例輸出與本地部分鏡像一致，不代表正式版執行差分 |
| P6 攻擊評估契約 | 只對支援子集輸出戰果；未支援時保持未知 | **PARTIAL** |
| P7 防守評估契約 | 定義無援軍、先到、後到與同節拍的輸入處理 | **PARTIAL** |

## P0 精確摘要

- `N = Shield + Fighter + Chopper + Bomber + Tank + Soldier + Ruler`，排除 Shell、EMP、Nuke；`M=min(3,floor(N/2))`。攻塔前先從 Force 移除 Shield，Tower Shield 保留；因此攻方 M 不計被清掉的盾，守方 M 可計塔盾。Force 對 Force 不適用攻塔盾清除。
- Tower `+45` 是 0/1 國王同塔／鄰塔光環；Force `+21` 是派出時複製的 0/1 快照。只有單側光環有效時，`damage0=+M(attacker)` 或 `−M(defender)`；旗標相同時 0。此值是整場戰鬥共享的 signed i32（有號 32 位元）初值，不是兩個獨立累積器，也不逐回合重算。
- Air（空中）後 Surface（地面），每次單側輪流用兵；優先序 Shield、Fighter、Chopper、Bomber、Tank、Soldier、Shell、EMP、Nuke、Ruler。累積為 0 且兩邊都能出兵時攻方先行。
- `2022` 用 u8（無號 8 位元）傷害；Bunker（碉堡）`floor(d/3)`、Headquarters（總部）`floor(2d/3)`。Nuke sentinel 31 轉成 `INT32_MAX`；只有反向累積值將跨過 signed half-range 時把該次傷害降為最多 1000。一般 WASM `i32.add/mul/sub` 以二補數環繞，不飽和。
- `BATTLE_DETERMINISM = PASS`（確定性靜態通過）：已見戰鬥函式呼叫圖無 RNG（隨機數）呼叫；這不替代正式版執行比對。

## Battle Mirror Ready Checklist（戰鬥鏡像就緒清單）

| 門檻 | 判定 |
|---|---|
| 士氣公式 | PASS（通過） |
| 初始累積值公式與型別 | PASS（通過） |
| 普通單位每回合順序 | PASS（通過） |
| signed／unsigned、floor、overflow 規則 | PASS（通過） |
| Shield 戰鬥語意 | PASS（通過） |
| Ruler 回呼及玩家死後狀態 | PARTIAL（部分完成） |
| 特殊單位回呼 | PARTIAL；子鏡像安全排除 |
| 最後存活兵力／winner（勝者）映射 | PARTIAL |
| owner transition（塔主轉換）入口 | PASS；所有特殊終端組合 PARTIAL |

清單尚未全過，所以只建立部分鏡像。它的勝負結果限於：已知玩家 ID（識別碼）、Neutral 或 Enemy 非空 Tower、普通兵種加 Shield、有效布林光環快照、非空攻方；含特殊單位／Ruler、直接佔領空塔、己方／盟友合併、特殊容量分支或不合規資料會拒絕。

## 主要未解 blocker（阻擋點）

目前阻止完整鏡像可靠輸出所有勝者與殘兵的單一主要區塊，是正式版 `448`／`522` 的 inline terminal cleanup（內嵌終端清理）與 scratch result（暫存結果）欄位，連同 `1347`／`1348` 特殊回呼，尚未逐條映回參考版 `Combatants::fight` 最後清理／勝者規則。士氣、傷害函式與普通單位優先序已不再是主要未知。這也是為何部分鏡像對未確認案例拒絕，而不輸出猜測勝負。

## Muse 整合佇列

### 可立即整合

1. 士氣入口公式、攻方先移除 Shield 的順序、塔旗標與部隊旗標的分別，以及 `damage0` 正負方向。
2. 部分鏡像的 `UNSUPPORTED_CASE` 介面可作為保守預測器範例；呼叫端應保留未知結果，不替換成兵力相減。
3. `GPT_BATTLE_FINAL_TABLES.json` 中普通容量列及公開傷害規則可作資料來源；Bunker、Artillery、Launcher、Rampart、Village 等特殊容量分支仍要拒絕。

### 需要執行期驗證

1. 用合法測試局比對普通兵種戰鬥的初值、各兵死亡順序、殘兵、勝者與塔主寫回。
2. 核實士氣旗標的更新延遲、Force 快照有效期，以及 EMP 延遲具體由哪一側觸發。
3. 特殊兵種與 Ruler 事件、正式伺服器玩家淘汰結果。

### 仍需 GPT 離線研究

1. 精確解出 `448`／`522` 終端狀態機與 `1347`／`1348` 回呼輸出欄位，逐一與公開參考碼收尾規則對照。
2. 解完五種特殊 TowerType（塔型）的容量分支，重新評估部分鏡像的塔型覆蓋範圍。

## 檔案與安全

本輪新增成果全部位於 `E:\SteamLibrary\kiomet\runtime\research\gpt_concurrent\`：算術分析、函式圖 JSON、戰鬥表 JSON、正式版差異、特殊單位說明、部分鏡像、29 個靜態案例、攻擊／防守評估契約與本交接檔。`GPT_BATTLE_STATIC_CASES.json` 的支援案例由本地部分鏡像輸出，未與執行中的 Production（正式版）差分。

Runtime connections（執行期連線） = 0；Browser connections（瀏覽器連線） = 0；Game actions（遊戲行動） = 0；Production WASM direct invoke（正式版 WASM 直接呼叫） = 0；本輪 GPT 修改的 tracked files（Git 追蹤檔） = 0；Git commits（Git 提交） = 0。
