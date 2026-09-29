# 下一輪 GPT force_units 驗證難題（Muse 被動觀察後整理）

2031 本體（靜態語意＋離線鏡像）已 PASS，不重解。
以下只列 Muse 被動手段到達上限仍缺的兩件事。

---

## PROBLEM 1：2031 被動輸出直接捕捉

WHY MUSE IS STUCK（為何卡住）：
已知呼叫者（448 tick、488 peek_mouse、1091 supply、1242 render、
1791 deploy）全部需要拖曳狀態或真實派兵；單純選塔不呼叫 2031
（來源 `drag.start==current` 分支確認）。Muse 禁止製造拖曳／派兵，
故無法取得 `(result_ptr, tower_ref) → 7 位元組 Units` 的可讀輸出。

WHAT IS ALREADY KNOWN（已知）：
- 2 起自然下降事件（m1-1790523816，兩座敵方兵營 Soldier 4→0、
  護盾不動，間隔約 338 秒），下降向量與鏡像逐兵種一致。
  證據：`runtime/research/force_units/passive/drop-001-m1-1790523816.json`
- 工具：`tools/dispatch_diff.py`（探測差分＋鏡像比對）。
- 判讀：PARTIAL 旁證，非輸出捕捉；Many 保持 DERIVED（不降級）。

BEST NEXT EXPERIMENT（最佳下一步）：
反組譯 488 peek_mouse 的拖曳強度計算分支，找其讀取的
「已存在、可讀預覽結果結構」位址；或在自然補給線派兵瞬間
對同一塔做高頻前後快照＋Force 結構定位（Force 布局見難題 #5）。

---

## PROBLEM 2：Single 非 Ruler 單兵種真值

WHY MUSE IS STUCK（為何卡住）：
三局自然樣本（17563938、16515400、14745828）全為
Single(Ruler,1)＋護盾；Shell／Emp／Nuke 從未在自然對局出現。
Ruler 不以 N/M 顯示（UI_NOT_VISIBLE），故 count=1 缺獨立數字核對。

WHAT IS ALREADY KNOWN（已知）：
- Single 結構：+39 count、+40 enum（3 樣本一致）。
- Single 塔 +41..+43 可能帶轉換殘留（14745828 的 +43=5，
  UI 無士兵列），只讀 +39／+40／+44。
- 證據：`runtime/research/units/single-sample-*.json`（3 筆）。

BEST NEXT EXPERIMENT（最佳下一步）：
後期對局（火砲／發射器／筒倉建成後）cli 採樣，找 Shell／Emp／
Nuke 的 Single 塔；或反組譯 Single 分支的 UI 顯示路徑，
確認非 Ruler 單兵種是否有數字顯示。
