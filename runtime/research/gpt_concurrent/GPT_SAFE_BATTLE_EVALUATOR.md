# 安全戰鬥評估器 v0

## 目的與狀態

`safe_battle_evaluator.py`（安全戰鬥評估器）是離線包裝層。它先檢查輸入是否完全落在 `battle_mirror_partial.py`（部分戰鬥鏡像）的靜態支援範圍，再決定是否呼叫鏡像。它不連接遊戲、瀏覽器、CDP（Chrome 開發者工具協定）或正式版 WASM（WebAssembly 執行模組）。

本輪沒有正式版差分結果。程式使用三種狀態：

- `UNSUPPORTED`（不支援）：必要事實缺失、互相衝突或超出鏡像範圍。絕不呼叫鏡像，也不輸出勝負。
- `RUNTIME_VALIDATION_NEEDED`（需要執行期驗證）：輸入在靜態子集內，可取得條件式鏡像結果，但正式版尚未差分。
- `SUPPORTED`（已支援）：靜態支援且呼叫端的驗證登錄明確標記此案例差分通過。Round 10 沒有任何真實案例達到此狀態；靜態情境中的旗標只用來測試閘門行為。

`supported=true` 只表示靜態鏡像可計算；規劃器能否採取行動還要看 `support_status`。`RUNTIME_VALIDATION_NEEDED` 永遠不能當成安全行動依據。`battle_differential_validated=true` 只能由未來 Muse 驗證登錄提供，不能由即時策略輸入自行宣稱。

`evaluation_status`（評估狀態）另外保留 `SUPPORTED`、`UNKNOWN`（未知）和 `UNSUPPORTED`（不支援）的介面三態。戰鬥尚未通過正式版差分時，靜態勝負可供診斷，但狀態仍是 `UNKNOWN`；未知／不支援都會被仲裁器擋下。

## 必要輸入

每個案例至少要包含：

- `attacker_units`、`defender_units`：完整且精確的兵種數量；只接受 Shield、Fighter、Chopper、Bomber、Tank、Soldier。
- `attacker_owner_relation`、`defender_owner_relation`、`self_owner_id`、攻守 owner ID（擁有者識別碼）：關係必須與識別碼一致。
- `battle_kind`、`target_branch`：只接受非空塔戰，或呼叫端已確認相撞的 Force 對 Force（部隊對部隊）。
- `tower_type`、`tower_capacity`：塔戰必須使用驗證表中完全相符的容量列。
- `attacker_aura_snapshot`、`defender_aura_snapshot`（攻守光環快照）：必須是已觀測的布林值，不能由舊地圖推導。
- `shield_state`（護盾狀態）：護盾數量必須和兩側單位向量相符。
- `special_unit_flags`（特殊兵種旗標）：Ruler、Shell、EMP、Nuke 必須明確為 false。
- `ruler_aura_state`（國王光環狀態）：兩側都要明確表示沒有國王參戰，並和光環快照一致。
- `world_context_required`（需要完整世界狀態）：必須是 false。
- `observed_tick`（觀測節拍）：非負整數。

## 支援閘門

閘門拒絕未知擁有者或光環、特殊兵種、未知塔型、完整玩家／世界狀態需求、空塔直接佔領、友軍合併推算、未確認的 Force 相撞，以及無法辨認的分支。拒絕時輸出 `supported=false`、`support_status=UNSUPPORTED`、`winner=null`，並填入原因。

只有閘門通過後才會呼叫 `predict_battle()`。輸出包含勝方、攻守殘兵、新塔主、可信度、支援原因及 `runtime_validation_required`（仍需執行期驗證）。沒有勝率百分比。

## 驗證旗標的責任

`battle_differential_validated` 是驗證整合層的輸入，不是本模組的推論結果。整合層只有在同一支援範圍的正式版結果與鏡像結果完成逐項比對後才能設為 true。靜態情境測試會以合成旗標測試「通過閘門後才能行動」的控制流；這不構成任何正式版驗證證據。

## 不支援範圍

Ruler 參戰或死亡後的全域淘汰、Shell、EMP、Nuke、特殊兵種、空塔直佔、援軍容量合併推導、燃料／擁塞／移動續行、同節拍事件順序、未確認的 Force 相撞，以及完整玩家／世界狀態。特殊兵種一律 `DO NOT USE`（禁止使用）。
