# PvP 行動仲裁契約 v0

`arbitrate_pvp_action()`（PvP 行動仲裁）不推導遊戲狀態。它只接受 ThreatEvaluator（威脅評估器）、DefenseEvaluator（防守評估器）、AttackEvaluator（攻擊評估器）和 Neutral Expansion（中立擴張）提供的候選。

## 固定次序

1. **觀察或驗證不足：** 任一入站威脅不是 `SUPPORTED`（已支援），立即 `ABSTAIN`（不動）。
2. **已證明將失守：** 依敵軍最早 ETA（預估抵達時間）排序，同 ETA 以塔 ID 固定排序。只檢查優先塔；若沒有驗證過的及時援軍，`ABSTAIN`。有的話 `REINFORCE_SELF`（己方增援）。
3. **安全攻擊：** 沒有失守威脅時，只接受全條件通過的 `ROBUST_WIN` 候選。輸入候選先依目標 ID、來源 ID 排序，確保結果穩定。
4. **中立擴張：** 沒有安全攻擊時，才接受現有擴張器已驗證的候選。
5. **其他情況：** `ABSTAIN`。

行動集合為 `REINFORCE_SELF`、`ATTACK_ENEMY`（攻擊敵人）、`EXPAND_NEUTRAL`（中立擴張）、`ABSTAIN`。防守子規劃器本身仍只允許 `ABSTAIN` 或 `REINFORCE_SELF`。未知威脅會阻止其他行動；看見敵軍本身不等於塔將失守。

## 狀態軌跡

規劃器狀態為 `OBSERVE`（觀察）→ `ASSESS_THREATS`（評估威脅）→ `EVALUATE_DEFENSE`（評估防守）→ `EVALUATE_ATTACK`（評估攻擊）→ `EVALUATE_EXPANSION`（評估擴張）→ `SELECT_ACTION`（選擇行動）或 `ABSTAIN`。各分支只走必要狀態，不做 MCTS（蒙地卡羅樹搜尋）、RL（強化學習）、self-play（自我對弈）或 opponent model（對手模型）。
