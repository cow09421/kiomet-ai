# 防守可行性評估 v0

`evaluate_defense()`（防守評估）將已知入站敵軍對上 SELF（己方）非空塔的目前守軍，輸出條件式鏡像勝負、塔是否保住及守方殘兵。敵軍 ETA（預估抵達時間）由呼叫端提供；本函式不推算道路、移動進度或同節拍先後。

## 不增援

若戰鬥子集受支援且逐案差分已通過，勝方為 defender（守方）則 `tower_survives=true`；勝方為 attacker（攻方）或 `contested`（雙方皆敗）則 `tower_lost=true`。遇到未知輸入或尚未差分，結果不能當成確定的防守結論。

## 援軍

- `reinforcement_eta < enemy_eta`：只在呼叫端提供 `post_merge_snapshot_exact=true`（精確合併後快照）及完整合併後守軍向量時，才評估第一場戰鬥。評估器不會直接把援軍數量加到守軍上。
- `reinforcement_eta == enemy_eta`：因節拍內事件順序未驗證，結果為 `UNSUPPORTED`（不支援）。
- `reinforcement_eta > enemy_eta`：輸出 `REINFORCEMENT_TOO_LATE`（援軍太晚），不把它算入第一場戰鬥。
- 只比較候選來源塔實際能派出的完整普通移動兵力。拒絕任意拼裝兵種或數量。

最低足夠援軍只在候選包含精確、已差分的合併後快照時才輸出。它是在呼叫端提供的完整兵力候選中，以總兵數最少者作離散比較；總兵數不是經濟成本或遊戲價值。塔型容量合併的正式版語意仍須驗證。

候選還要提供 SELF（己方）來源、SELF 目標、完整可派兵力、合法路徑、新鮮世界／目標資料，以及正式版已接受的 `DeployForce`（部署部隊）證據，才可進入行動仲裁。只通過戰鬥評估仍不足以派援軍。

## 行動限制

評估器只回報威脅與候選救援，不送出派兵命令。反應式防守規劃器只有在入站戰鬥、合併結果、路徑 ETA 和 SELF→SELF `DeployForce`（部署部隊）伺服器接受驗證都完成後，才可考慮 `REINFORCE_SELF`（己方增援）。否則保持 `ABSTAIN`（不動）。
