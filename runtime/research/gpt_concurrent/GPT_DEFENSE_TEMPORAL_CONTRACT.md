# 防守時間序契約（Round 11）

## 結論

防守評估（DefenseEvaluator）核心比較必須使用整數伺服器 tick（更新節拍），不能以浮點秒數推定同節拍內的先後。

- `reinforcement_eta_tick < enemy_eta_tick`：只能標為 **SAFE / LIKELY SAFE（安全／很可能安全）**，而且必須同時具備精確援軍合併後狀態、來源塔安全檢查、完整已知威脅清單、合法路徑與有效行動權杖。此結論只代表援軍在第一支敵軍前至少早一個已確認 tick 抵達；不代表之後沒有第二支威脅。
- `reinforcement_eta_tick == enemy_eta_tick`：**ORDER_DEPENDENT（順序相依）**。伺服器參考來源依當下目標塔 `inbound_forces` Vec（向量）索引逐支處理，不保證援軍優先。Round 10 DefenseEvaluator（防守評估器）應 **ABSTAIN（暫不行動）**，除非未來取得已驗證的當下索引、完整中間狀態及正式版差分；Round 11 不建立此例外。
- `reinforcement_eta_tick > enemy_eta_tick`：**TOO_LATE（太晚）**，不能用來改寫第一場戰鬥結果。
- ETA（預估抵達時間）或 tick phase（節拍相位）未知：`UNKNOWN`（未知）→ **ABSTAIN**。不得補成 0。

因此，嚴格的援軍先到門檻是：

```text
enemy_eta_tick - reinforcement_eta_tick >= 1 confirmed tick
```

且每個 ETA 都要指向同一個、明確定義的「抵達處理 tick」，不能一個代表開始移動、另一個代表 tick 邊界前的畫面時間。

## ETA 量化

優先由完整、同一快照的 Force（部隊）路徑與進度計算整數 tick：

```text
remaining_progress = max(progress_required - path_progress, 0)
arrival_ticks = ceil(remaining_progress / progress_per_tick)
```

只有 `path_progress`、`progress_required`、`progress_per_tick`、路徑、速度與影響速度的光環快照都已知時才可採用。每次 world snapshot（世界快照）改變後重算。

若外部只給秒數，先把它轉成可能 tick 區間，不能單純比較秒數或四捨五入成單一 tick：

```text
high_tick = ceil(eta_seconds * 4)
low_tick  = max(0, high_tick - 1)
```

這是未知節拍相位下的保守區間；因觀測可能落在下一個 tick 邊界前，區間包含一個 tick 的相位不確定性。只有 `reinforcement_high_tick < enemy_low_tick` 才能證明援軍至少早一個 tick；區間重疊就標記 `ORDER_DEPENDENT` 並 ABSTAIN。例：1.99 秒區間為 `[7,8]`，2.01 秒為 `[8,9]`，兩者在 tick 8 重疊，不能宣稱援軍先到。

## 同節拍處理

伺服器參考來源在每個塔內以目前入站 Vec 順序逐支處理。沒有「SELF reinforcement（己方援軍）先合併」或「Enemy Force（敵方部隊）先戰鬥」的固定類別優先權。先處理者會立即改變塔兵力與塔主，後處理者再讀取已更新的狀態。

因此：

1. 不得把同 tick 敵軍合成一支，也不得把援軍先加進初始守軍後再一次算戰鬥。
2. 未保存當下 `inbound_index`（入站集合索引）與 `world_snapshot_id`（世界快照識別碼）時，一律視為順序未知。
3. 即使索引已知，正式版支援、每次戰鬥差分、合併容量及派兵前置檢查仍要各自通過；靜態順序證據不等於可安全派兵。
4. 援軍在敵軍之前抵達，也要檢查來源塔派兵後是否會被已知威脅攻下。

## 多威脅與已知事件

同一目標的敵軍依 `(arrival_tick, current_inbound_index)`（抵達節拍、當下入站索引）排序，逐場更新目標塔狀態。沒有 Force ID（部隊識別碼）；指紋只能作觀察快照內的去重輔助，不能替代版本或索引。

若第二支已知敵軍仍可能攻塔，第一場守住不代表威脅已解除。超出完整已知事件序列、遇到同節拍索引缺失、移動／合併狀態不完整或任何 `UNKNOWN`（未知）時，回 `UNSUPPORTED_TEMPORAL_CASE`（不支援的時間序案例）並 ABSTAIN。

## 範圍

本契約建立在保存伺服器來源的靜態順序上；本輪沒有連接執行期、沒有差分正式伺服器，也沒有驗證本地來源與正式伺服器二進位檔完全相同。正式版 PvP（玩家對玩家）行動仍需 Muse 完成獨立執行期驗證。
