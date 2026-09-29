# Kiomet GPT 第八輪：Battle Resolver 收尾交接

## 結果

本輪只檢查正式版函式 448、522、1347、1348 及其戰鬥尾端。沒有新增研究主題，沒有啟動遊戲、瀏覽器連線或 Production WASM（正式版網頁組件）呼叫。

| 項目 | 判定 | 摘要 |
|---|---|---|
| FUNC 448 | PASS（通過） | `World::tick_before_inputs`；塔光環、抵達分支、塔戰、塔主寫回及友軍續行／合併。 |
| FUNC 522 | PASS（通過） | `788` 呼叫的部隊相撞解析器；兵力就地更新並回報勝方／入站存活旗標，不寫塔主。 |
| FUNC 1347 | PASS（通過） | `448` 塔戰的通用替換／消耗回呼；處理普通兵、Shell、EMP、Nuke、Ruler 的局部狀態。 |
| FUNC 1348 | PASS（通過） | `522` 部隊相撞的同構回呼；差異是事件橋接器 2561，而非攻／守或成功／失敗配對。 |
| Battle Tail（戰鬥尾端） | PASS（通過） | 已由選兵尾端接到勝者、存活者、Tower owner（塔主）、容量與 Force（部隊）移除／續行。 |
| Owner Transition（塔主轉換） | PASS（通過） | 攻方勝換主；守方勝保留；無勝者清空。空主塔降級並清除延遲。 |
| Survivor Writeback（存活兵力寫回） | PASS（通過） | 448／522 就地修改 Units（兵力）；788／448 外層完成 Force 集合保留、移除、續行或合併。 |
| Capacity Handling（容量處理） | PARTIAL（部分完成） | 戰鬥欄位分類支援 22/22 塔型；中立空塔 reconcile 與友軍合併路徑不由戰鬥鏡像推算。 |
| Shell（砲彈） | PARTIAL（部分完成） | damage 3、一次性消耗、單場事件去重已對上；支援矩陣仍拒絕含 Shell 的輸入。 |
| EMP（電磁脈衝） | PARTIAL（部分完成） | damage 1、一次性消耗；448 只在攻方 EMP 時寫 Tower `+47=max(old,240)`。延遲倒數時暫停塔兵力生產／衰減與中立塔降級，不改 Force 移動進度；鏡像仍拒絕含 EMP 的輸入。 |
| Nuke（核彈） | PARTIAL（部分完成） | sentinel 31、Bunker 10、Headquarters 20、INT32_MAX 及 1000 guard 已對上；鏡像仍拒絕含 Nuke 的輸入。 |
| Ruler（國王） | PARTIAL（部分完成） | 非一次性、damage 1、計入士氣；離場事件已對上，外部玩家淘汰後續不在支援範圍。 |
| Determinism（確定性） | PASS（通過） | 448／522 戰鬥呼叫圖沒有 RNG／PRNG（隨機數產生器）呼叫；同一輸入按固定順序計算。 |
| Integer Rules（整數規則） | PASS（通過） | u8、u16、u32 與 signed i32、除法、clamp（封頂）、環繞規則已列在 JSON。 |
| Battle Mirror（戰鬥鏡像） | PARTIAL（部分完成） | 普通 Force 對非空 Tower、普通 Force 對 Force、Shield 與明確 aura snapshot（光環快照）可算；特殊／外層抵達分支回 `UNSUPPORTED_CASE`。 |

## 448 與 522

```text
448 World::tick_before_inputs（世界節拍）
├─ Tower arrival（部隊抵達塔）→ 448 內嵌 Force-vs-Tower 戰鬥 → 1347
└─ Force collision（部隊相撞）→ 788 路徑／重疊檢查 → 522 → 1348
```

448 不直接呼叫 522。兩者是同一世界節拍中的不同交戰分支。522 只處理兩支 Force，不處理 Tower owner；788 根據 522 的結果保留勝方並移除敗方。

## 鏡像支援範圍

`battle_mirror_partial.py` 仍保留 partial（部分）名稱，拒絕任何未知輸入，不升成泛用 `battle_mirror.py`。

- 普通 Force 對非空 Tower：攻方 Shield 先移除、Tower Shield 保留；可用明確攻守光環布林值與 22 列容量表。
- 普通 Force 對 Force：兩側 Shield 都保留；路徑是否相撞由呼叫端先決定。
- 可輸出攻方勝、守方勝或雙方皆敗，以及兩側普通兵殘量；塔戰另輸出新塔主關係。
- 51 個靜態案例：32 個支援子集案例、19 個預期拒絕；51/51 本地鏡像一致性檢查通過。這是本地一致性檢查，**不是** Production WASM 差分驗證。

## 三個答案

1. **Q1 普通 Many vs Many（多兵種對多兵種）：YES（是）**。在普通六種兵、Shield、有效塔型及明確光環快照的支援輸入內，可靜態預測勝者與殘兵；沒有與執行中的正式版做差分驗證。
2. **Q2 Shield + ruler aura（護盾加國王光環）：YES（是，限輸入已含正確光環快照）**。鏡像使用已計算的布林旗標，不自行從國王位置推導旗標；攻塔時攻方 Shield 會先移除。
3. **Q3 Shell / EMP / Nuke（砲彈／電磁脈衝／核彈）是否全部支援：NO（否）**。局部算術已靜態追到，但鏡像有意拒絕這些案例。

## 最主要的唯一剩餘 blocker（阻擋點）

特殊單位與 Ruler 的戰鬥事件已可由 1347／1348 經 `1943 CombatInfo::into_info_event`（戰鬥事件轉資訊事件）確認；唯一主要阻擋是事件送出後由外層消費器造成的玩家全域狀態，尤其 Ruler 陣亡後的淘汰寫回，不屬於這四個戰鬥函式的已閉合狀態。為避免把局部戰鬥結果誤報成完整玩家結果，鏡像仍拒絕所有特殊單位與 Ruler 輸入；普通 PvP（玩家對玩家）支援子集不依賴這些分支。

其他未支援的中立空塔、友軍合併、移動續行、燃料與同節拍排程是不同的外層抵達功能，不是阻止普通戰鬥計算的 blocker（阻擋點）。

## 給 Muse 的最小介面

`GPT_BATTLE_MIRROR_SUPPORT_MATRIX.json` 已定義 `BattleEvaluationInput`（戰鬥評估輸入）與 `BattleEvaluationResult`（戰鬥評估結果）。

- IMMEDIATE（可立即工程化）：只將六種普通兵、Shield、已知 owner、TowerType 及明確攻守 aura snapshot 傳給部分鏡像；保留 `supported` 與 `unsupported_reason`。
- RUNTIME VALIDATION（執行期驗證）：日後在另行核准的隔離測試中比較正式版勝者、殘兵、owner 與 EMP 延遲。本輪依指示沒有執行。
- DO NOT USE YET（目前不可進規劃器）：Shell／EMP／Nuke／Ruler、友軍合併與續行、中立空塔完整抵達結果、未映射塔型及同節拍排程。
- Planner（規劃器）只有在 `supported=true` 才可依 BattleEvaluator（戰鬥評估器）結果決定攻擊／防守；未支援結果禁止冒險，不能改用兵力相減猜測。

## 安全與檔案

所有 Round 8 新成果都在 `E:\SteamLibrary\kiomet\runtime\research\gpt_concurrent\`。未修改 `src/`、`tests/`、`docs/`、`tools/` 或 `run.ps1`；未操作 Muse 平台。

Runtime connections（執行期連線） = 0；Chromium connections（瀏覽器連線） = 0；Game actions（遊戲行動） = 0；Production WASM direct invoke（正式版 WASM 直接呼叫） = 0；Tracked files modified（Git 追蹤檔修改） = 0；Git commits（Git 提交） = 0。
