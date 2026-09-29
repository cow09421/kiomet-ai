# 反應式防守規劃器契約 v0

此規劃器只接收 SELF towers（己方塔）、incoming threats（入站威脅）、moving forces（移動部隊）、enemy ETA（敵軍抵達時間）、reinforcement ETA（援軍抵達時間）、current defenders（現有守軍）、完整 deployable forces（可派兵力）及各層評估結果。它不重算道路或戰鬥。

## 行動集合

只允許 `ABSTAIN`（不動）和 `REINFORCE_SELF`（己方增援）。不反攻、不移動 Ruler（國王）、不升級、不使用特殊兵種。

## 優先規則

1. 任一 SELF 塔的入站威脅尚未達到 `SUPPORTED`（已支援），全域先 `ABSTAIN`；未知不能視為安全。
2. 對已驗證案例，找出 evaluator（評估器）判定會失守的塔。塔的基本價值一律相同。
3. 依敵軍最早抵達時間排序；同時到達時用塔 ID（識別碼）固定排序。
4. 只有存在較早抵達、合併快照精確且 `DeployForce`（部署部隊）命令已由正式版接受的救援候選，才輸出 `REINFORCE_SELF`。否則對該威脅 `ABSTAIN`，不因此改派到別座塔。
5. 沒有將失守威脅時，這個防守規劃器輸出 `ABSTAIN`，把其他行動交給仲裁器。

## 解釋性

每個決策保留狀態軌跡：`OBSERVE`（觀察）→ `ASSESS_THREATS`（評估威脅）→ `EVALUATE_DEFENSE`（評估防守）→ `SELECT_ACTION`（選擇行動）或 `ABSTAIN`。多座塔同時受威脅時不使用臆測塔價值，也不使用 MCTS（蒙地卡羅樹搜尋）、RL（強化學習）或對手模型。
