# 兵力解碼交接（2026-09-27）

## STATUS（狀態）

**PASS（通過）：目前塔兵力數量的只讀解碼。** 同一場對局 `m1-1790487672` 的 10 座塔、3 個時點，共 30 筆「選塔資訊框讀數 ↔ 同塔記憶體」配對；`tools/decode_units.py` 對可見兵力數字核對 **30/30**。涵蓋己方、灰色中立、紅色其他玩家，並觀察到自然增減。這不代表已驗證可派出量：`force_units()` 會依塔種類過濾不能移動的兵種，也不代表已找到容量的執行期欄位。

## UI GROUND TRUTH（介面真值）

正式遊戲的塔資訊框把每種兵力顯示為 `current/capacity`（目前數量／容量）。例：塔 `17498402` 三次都是護盾 `15/15`、兩個兵種各 `4/4`，其原始結構後 7 位元組均為 `[0,4,0,0,0,4,15]`。塔 `17498403` 顯示 `20/20`、`12/12`，相同位置為 `[0,0,0,0,0,12,20]`。紅塔 `17432865` 的目前兵力由 `25,2` 變成 `24,4` 再到 `24,1`，對應值同步改變。所有取樣只點選塔；未拖曳、未派兵，`sent_actions=0`。

## SOURCE DATAFLOW（原始碼資料流）

伺服器狀態經 `vendor/kiomet-ref/client/src/state.rs` 的 `Update.actor_update` 進入世界塔狀態。`vendor/kiomet-ref/common/src/tower.rs` 的 `Tower.units: Units` 儲存目前數量，`Tower::force_units()` 根據 `Unit::is_mobile()` 產出可派兵力。`vendor/kiomet-ref/common/src/units.rs` 定義 `Units { always: [u8;1], either: Many([u8;5]) | Single(Unit,u8) }`，`available()` 取數。`vendor/kiomet-ref/client/src/ui/tower_overlay.rs` 用 `tower.units.iter_with_zeros()` 產生官方資訊框的 `current/capacity`。`vendor/kiomet-ref/client/src/layout.rs` 與 `game.rs` 也消費兵力來繪製與判斷操作。

## PRODUCTION FUNCTIONS（正式版函式）

- `Units::available`：函式 **1637**，WASM（網頁組件）偏移 `0xF9200`；反組譯顯示讀取結構位移 `+0/+1/+2/+5/+6`。
- `Tower::force_units`：函式 **2031**。本輪不直接呼叫任何正式版遊戲函式。
- 塔參照由已核對的渲染函式 **1242**，顏色讀取點 `0xDCC00` 取得。正式版 WASM 雜湊 `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`；版本不同時禁止沿用偏移。
- 本機可命名編譯版的 `Units::available` 函式 **2893**、`Tower::force_units` 函式 **2997**，供來源對照。

## TOWER_REF OFFSETS（塔參照位移）

每個塔參照是本場對局由渲染函式讀出的 WASM 記憶體位址。**重啟或換局後必須重取，不能重用數值。** 以 `tower_ref + 38` 為 `Units` 結構起點，所有欄位均為 **unsigned 8-bit（無號 8 位元）**、連續 1 位元組間距：

| 位移 | 內容 | 已驗證意義 |
| --- | --- | --- |
| `+38` | `UnitsEither` 標籤 | `0=Many`；`1=Single`（Single 的介面比對尚未獨立完成） |
| `+39` | `Many[0]` 或 Single 數量 | Fighter（戰鬥機）目前數量，或單一兵種數量 |
| `+40` | `Many[1]` 或 Single 兵種編號 | Chopper（直升機），或 Unit 列舉值 |
| `+41` | `Many[2]` | Bomber（轟炸機）目前數量 |
| `+42` | `Many[3]` | Tank（坦克）目前數量 |
| `+43` | `Many[4]` | Soldier（士兵）目前數量 |
| `+44` | `always[0]` | Shield（護盾）目前數量 |

`Unit` 列舉編號在 `vendor/kiomet-ref/common/src/unit.rs`：Shield=0、Fighter=1、Chopper=2、Bomber=3、Tank=4、Soldier=5、Shell=6、Emp=7、Nuke=8、Ruler=9。塔 `17563938` 的 `[1,1,9,0,0,0,30]` 符合 Single(Ruler,1) 加護盾 30，但正式介面此處只顯示 `30/30`，因此 **Ruler 的介面配對仍需另證**。

這些位元組是 **current（目前數量）**，不是 capacity（容量）。容量來自塔類型與規則，來源碼為 `Units::capacity(unit, tower_type)`；此處沒有聲稱找到容量欄位。

## CROSS-TOWER / TIME VALIDATION（跨塔／時間驗證）

配對記錄：`runtime/research/units/units_ground_truth.json`（含 match_id、時間、塔編號、塔參照、世界與畫面座標、每個 UI 原文數字、`tower_ref` 起 48 個原始位元組）；解碼結果：`decoded-units-m1-1790487672.json`。在 10 座塔 × 3 時點中，資訊框所有正數目前數量與上述 Shield + Many 解碼後的正數多重集合 **30/30 完全相等**。自然變化案例包含紅塔兵力減少、灰塔護盾由 0 增至 3。原始畫面與前六座塔的選取截圖也保留在 `runtime/research/units/`，數量有限。

重現：`python tools/decode_units.py runtime/research/units/units_ground_truth.json`，預期輸出 `tower_count=10, round_count=3, sample_count=30, matched=30`。新場次採樣：先取得**該場次**塔錨點，再執行 `python tools/unit_ui_samples.py --help`；讀取塔周邊完整位元組可用 `python tools/unit_struct_probe.py --help`。

## REJECTED HYPOTHESES（已排除方向）

先前三次全記憶體慢槽盲差分沒有得到可解釋的正式版行為。這次改用來源碼的兵力消費函式、已核對塔參照及官方資訊框；不應重新全記憶體掃描。

## NEXT EXACT EXPERIMENT（下一步精確實驗）

由 Muse 把已驗證的 `tower_ref +38..+44` 解碼加入持續觀察器，對每次新場次重新取得參照，並為每筆值標記新鮮度。加一個 Single 類型有明確介面數字的自然樣本；另依塔類型規則推導容量並獨立核對，**不要把 current 當 capacity 或直接當可派兵力**。若再次採樣前先確認對局仍相同、鏡頭未變、塔身份穩定。
