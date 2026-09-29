# GPT CONCURRENT HARD-PROBLEM REPORT（並行高難題研究交接）

| 項目 | 結果 |
|---|---|
| 2031 Semantics（2031 語意） | PASS（沿用既有正式版語意及離線鏡像結論；本輪未重做） |
| 2031 Caller Count（呼叫者數） | 6 個直接函式，8 個直接呼叫位置；元素表未見 `ref.func:2031` 間接入口 |
| Best Caller（最佳呼叫者） | 1791 `Tower::deploy_force`（實際部署時的完整原始結果複製）；如只研究拖曳預覽，則 1242／`0x0D9D70` |
| Trigger（觸發） | 1791：自然或授權的實際部署；1242／`0x0D9D70`：拖曳預覽 |
| Result Pointer Origin（結果指標來源） | 1791 `local3+17`；1242 `local4+5104`。兩者皆為呼叫者堆疊等效暫存 |
| Output Lifetime（輸出生命週期） | 原始結果到呼叫者框架結束；1791 的複製品可進入 `Force`（移動兵力）事件及塔兵力集合 |
| Output Consumers（輸出消費者） | 空值、最大邊距、Ruler（國王）包含、兵種遍歷；1791 另扣除原塔單位並建立兵力事件 |
| Command Builder Relation（命令建構關係） | 拖曳釋放用輸出決定路徑及等待條件；`DeployForce`（派兵命令）僅保存塔編號與路徑，不保存兵種組成或總量 |
| Preview Relation（預覽關係） | 1242／`0x0D9D70` 的空值、距離、Ruler（國王）檢查對應 `draw_drag_path`（畫出拖曳路徑） |
| Passive Capture Point（被動擷取點） | NOT FOUND（未找到不部署、不掛鉤且可長期讀取的原始結果）；自然部署後的 `Force`（移動兵力）是條件式副本 |
| Passive Capture Risk（被動擷取風險） | MEDIUM（中），僅針對利用既有只讀事件通道觀察自然部署；暫存框架輪詢為 HIGH（高）且不建議 |
| Requires Breakpoint（需要中斷點） | NO（否），候選方案只使用既有只讀事件／狀態通道；目前未實作也未驗證該通道 |
| Exact Production Functions（正式版函式） | 448、488、864、1091、1242、1791、1963、2031；1690、6280、5440 是主要消費者 |
| Exact Offsets（精確位置） | `0x01A73C`、`0x057E3B`、`0x0B0043`、`0x0BFEC4`、`0x0D2E64`、`0x0D3327`、`0x0D9D70`、`0x10041C`；1791 複製在 `0x10047B`／`0x100482` |
| Source Mapping（原始碼對映） | `client/src/game.rs:227-268,1030-1105`；`common/src/tower.rs:107-128`；`common/src/chunk/event.rs:42-75,236-244`；`common/src/protocol.rs:13-40` |
| Local WASM Mapping（本地網頁組件對映） | 2997 `force_units`（可派兵單位計算）；2252 `peek_mouse`（滑鼠預看）；2189 `GameClient::tick`（遊戲更新）；2884 `Chunk::tick`（區塊更新）；2994 `take_force_units`（取出可派兵單位）；2993 `deploy_force`（部署兵力） |
| 2031 Output Dataflow（輸出資料流） | PASS（靜態）；8 處均已定位結果指標與後續主要消費，1791 複製鏈追至兵力事件 |
| Upgrade Static Analysis（升級狀態靜態分析） | PARTIAL（部分完成）；確認塔型 `tower_ref+46`、剩餘延遲 `+47`、前置條件的 27×2 位元組數量陣列參數；持久基底未解 |
| Next Muse Validation（Muse 後續驗證） | 只在自然部署已出現且現有觀察通道可讀時，對照事件兵種、來源塔與離線鏡像；不新增動作或重型偵錯 |
| Remaining Unknown（未解事項） | 1242 前兩處精確原始碼表達式、864 的精確源函式邊界、Muse 現有通道是否能唯讀讀到兵力事件、正式執行期直接輸出目前仍 0/5 |

## 交付檔案

- `GPT_2031_CALLERS.json`：8 個呼叫位置的機器可讀資料表。
- `GPT_2031_OUTPUT_DATAFLOW.md`：來源、本地版與正式版的資料流結論。
- `GPT_2031_CFG.txt`：呼叫與返回的控制流程摘要。
- `GPT_PASSIVE_CAPTURE_RECIPE.md`：可行條件、風險和停止條件。
- `GPT_UPGRADE_STATIC_ANALYSIS.md`、`GPT_UPGRADE_CANDIDATES.json`：升級狀態的有限靜態對映。
- `dumps/func-*.txt`：靜態反組譯原始證據。

本輪所有新檔案僅在 `runtime/research/gpt_concurrent/`；未修改正式程式、未提交、未連接 Muse 的執行期，也未觸發遊戲行動。
