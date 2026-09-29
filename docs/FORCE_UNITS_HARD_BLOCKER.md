# 可派兵力剩餘驗證缺口

## WHAT IS PROVEN（已證明）

公開來源 `Tower::force_units` 的規則完整；正式版函式 2031 的所有主要分支都能對應：由 `tower_ref+38` 迭代非零兵力，讀 `tower_ref+46` 是否 Projector（投射器），只有非 Projector 的 Shield（護盾）略過，其他兵種包含 Ruler（國王）原量加入新的 `Units`。離線鏡像 `src/kiomet_ai/force_units.py` 與此靜態規則一致，10 座塔 × 3 時點的歷史輸入均可計算。正式版沒有讀 `+45` 國王旗標。

## WHAT IS NOT PROVEN（未證明）

沒有正式 Client（客戶端）在**正常呼叫** 2031 時的可讀結果樣本，故離線鏡像尚不能標 RUNTIME_VALIDATED（執行期核驗）。Single（單兵種）目前只有兩個自然的 `Single(Ruler,1)` 結構例，缺官方資訊框直接顯示該特殊兵種數量的對照；持續觀察器因此只把完整 Many（多兵種）狀態的逐兵種可派量標 DERIVED（推導）。

## PRODUCTION 2031 CFG（正式版控制流程）

`result_ptr, tower_ref → zero result → iter_with_zeros(tower_ref+38) → is_projector=(tower_ref[46]==15) → loop { next nonzero(unit,count); if unit==10 break; if unit==0 and !is_projector continue; Units::add(result,unit,count) } → copy 7-byte result`。完整指令與逐分支表見 `docs/FORCE_UNITS_PRODUCTION_ANALYSIS.md`。

## KNOWN LOADS / BRANCHES（已知讀取／分支）

- 2031 讀 `tower_ref+46`，傳 `tower_ref+38`；未讀 `+45`。
- `2031 → 3825 → 5444 → 1637` 取得每兵種目前數量。1637 依 `Units+0` 標籤讀 Many `+1..+5`、Single `+1/+2`、Shield `+6`。
- `unit==10` 終止，`unit==0 && !Projector` 才略過。Ruler=9 沒有特別分支。

## SOURCE MATCHES / MISMATCHES（來源吻合／差異）

`Tower::force_units` 的過濾、輸出型別與無策略預留語意吻合。這個函式內**沒有找到來源／正式版差異**；其他模組的盾容量 `+45` 差異不進入 2031。

## BEST NEXT EXPERIMENT（最有價值的下一實驗）

只等待自然遊戲流程出現補給線自動派兵或找到已存在、可讀的拖曳預覽結果結構；以同一新鮮塔的派兵前後原始 `Units` 與自然部隊組成對照鏡像。若需要主動拖曳才能看見 2031 輸出，本輪保持不做；沒有 `EXECUTE`（執行）授權，不得派兵或直接呼叫正式版 WASM（網頁組件）函式。
