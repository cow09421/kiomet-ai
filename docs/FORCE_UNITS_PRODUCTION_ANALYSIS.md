# 正式版函式 2031：可派兵力逐分支重建

更新：2026-09-27。只做本機靜態反組譯，**沒有呼叫正式版 WASM（網頁組件）函式**。輸入檔 `runtime/research/source-map/production-client_bg.wasm` 的 SHA-256（檔案雜湊）為 `fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c`。使用 `tools/extract_wasm_functions.py` 產生的有限指令節錄在 `runtime/research/force_units/production/func-*.txt`。

## 介面與資料流

`Tower::force_units` 是 **func[2031]**、偏移 `0x1096F9`、簽章 `(i32 result_ptr, i32 tower_ref) -> nil`。回傳值由呼叫方提供的 7 位元組 `Units` 儲存位置承接，並非一個整數。函式起始把本地結果清零，接著：

```text
tower_ref+38 （Units 結構）
  → func[5440] Units::iter_with_zeros（複製結構並設置 0..9 兵種迭代）
  → func[3825]（取下一個非零的兵種與數量）
     → func[5444] → func[1637] Units::available（該兵種目前數量）
  → unit=10 結束；unit=0 且 tower_ref+46!=15 則略過
  → 其餘 func[5906] Units::add（把原數量加入結果）
  → 把本地 7 位元組 Units 複製到 result_ptr
```

`tower_ref+46=15` 對應 Projector（投射器），已由既有塔類型觀察器對照正式列舉。**函式沒有讀 `tower_ref+45`**：國王存活旗標及盾容量加成不是此過濾器的輸入。函式也不讀所有權、路徑、目的地或容量欄位。

## 主要分支與證據

| 指令偏移 | 條件／動作 | 來源對應 | 信心 |
| --- | --- | --- | --- |
| `0x109718..0x10971D` | 傳 `tower_ref+38` 給 func[5440] | `self.units.iter()`；迭代器複製 `Units` | HIGH（高） |
| `0x109720..0x109728` | 讀 `tower_ref+46`，與 15 比較，設 `is_projector` | `unit.is_mobile(Some(self.tower_type))` 中 Shield 的 Projector 例外 | HIGH（高） |
| `0x109735` | func[3825] 取得下一個非零 `(unit,count)` | `self.units.iter()`（零數量被排除） | HIGH（高） |
| `0x10973A..0x109742` | `unit == 10` 則跳到終止 | Unit 列舉 0..9，10 是迭代結束哨兵 | HIGH（高） |
| `0x109744..0x109751` | 若 `(unit OR is_projector)==0`，跳過加入 | 只有 `unit=Shield(0)` 且非 Projector 被略過 | HIGH（高） |
| `0x109753..0x10975F` | `Units::add(result,unit,count)` | 把其餘兵種原數量加入新的 Units | HIGH（高） |
| `0x109764..0x109775` | 複製本地 7 位元組結果到 result_ptr | 回傳 `Units` 結構 | HIGH（高） |

這些是函式內的所有主要分支。`unit=9` 的 Ruler（國王）通過非零檢查，因此此函式**不自動保留國王**。非 Projector 的 Shield（護盾）留在塔內；Projector 的 Shield 被納入。Many（多兵種）與 Single（單兵種）分支實際在 `Units::available` 的布局解碼中；2031 本身不用兩種不同過濾規則。

## 1637 的正確角色

`Units::available` **不是「可派兵量」**，而是取得某一兵種在原始 `Units` 的**目前數量**。2031 不直接呼叫它；呼叫鏈是 `2031 → 3825 → 5444 → 1637`。1637 讀 `Units+0` 標籤；Many 變體用 `Units+1..+5`，Single 變體用 `Units+1` 數量、`Units+2` 兵種編號；Shield 由 `Units+6` 取得。這與已驗證 `tower_ref+38..+44` 位元組布局一致。`5444` 把 1637 結果寫到迭代項的 `count` 欄位；3825 略過零數量項。

`func[5906]` 是 `Units::add` 的包裝，呼叫 `func[902] Units::add_inner`；來源的輸出 `Units` 不是塔，故 `add` 不施加原塔的容量規則。正式版函式輸入的目前數量均是 `u8`（無號 8 位元），逐項加入不會因戰略預留而扣減。

## Local Source ↔ WASM（本機來源與編譯版對照）

公開來源 `vendor/kiomet-ref/common/src/tower.rs` 的同名函式在本機編譯版為 **func[2997]**，簽章同為 `(i32,i32)->nil`；`Units::available` 是 **func[2893]**，簽章 `(i32,i32)->i32`。本機反組譯 `runtime/research/force_units/local/func-2997.txt` 可見對塔欄位的直接位元組讀取，及多次呼叫 `Units::add_inner`（func[2892]）。本機與正式版的優化及結構配置不同，**不可把本機位移套到正式執行期**。來源與正式版在「逐兵種複製且只有一般塔 Shield 被排除」的語意上對齊。

## SOURCE vs PRODUCTION DELTA（來源與正式版差異）

在 **force_units 這個函式** 的主要分支沒有發現差異。既有 `+45` 盾容量規則的來源／正式版差異不進入 2031，故對本離線鏡像沒有影響。正式版正常路徑的實際**輸出**尚無被動觀察樣本；此處的 `PRODUCTION SEMANTICS（正式版語意）= PASS（通過）` 是靜態等價證據，**不等於執行期輸出已驗證**。

## 正常呼叫者與唯讀輸出限制

既有正式函式索引列出 2031 的呼叫者：448 `World::tick_before_inputs`（輸入前世界更新）、488 `KiometGame::peek_mouse`（滑鼠狀態處理）、864（未命名）、1091 `filter_supply_src`（補給線來源過濾）、1242（渲染主流程）、1791 `Tower::deploy_force`（實際部署）。公開來源的**單純點選塔**走 `drag.start == current` 分支，只切換選取，不呼叫 `force_units`；`peek_mouse` 在拖曳終點與起點不同時才算 `strength`（可派兵力），渲染預覽也要求已有拖曳狀態。塔資訊框展示的是原始 `tower.units`，不是 2031 的輸出。故目前沒有一個已證明安全的選塔唯讀輸出可作正式結果真值。本輪不啟動拖曳或攔截正式命令，`FORCE_UNITS_RUNTIME_VALIDATION（正式執行期輸出核驗）= NOT AVAILABLE（目前不可取得）`。
