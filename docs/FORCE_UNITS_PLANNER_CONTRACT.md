# 規劃器可使用的可派兵力資料契約

`Tower::force_units`（塔的可派兵力）回傳逐兵種 `Units` 結構，**不是一個總數**。正式版函式 2031 的靜態語意已重建，離線鏡像位於 `src/kiomet_ai/force_units.py`；正式遊戲自然路徑的輸出尚未有唯讀對照，因此鏡像值標 **DERIVED（推導）**，不標 **VERIFIED（正式執行期核驗）**。

## 已能安全推導

輸入必須包含同一新鮮對局的塔類型與完整目前兵力（`TowerUnitCounts`）。鏡像回傳 `DeployableForce.counts`：Shield（護盾）、Fighter（戰鬥機）、Chopper（直升機）、Bomber（轟炸機）、Tank（坦克）、Soldier（士兵）、Shell（砲彈）、Emp（電磁脈衝）、Nuke（核武）、Ruler（國王）各自數量。`total` 只是輔助加總；派兵決策必須保留組成。

- 一般塔：所有非零非 Shield 兵力原量納入；Shield 留塔。
- Projector（投射器）：Shield 也可移動，原量納入。
- Ruler 不被 `force_units` 自動保留。危險路徑的拖曳延遲與自動補給線禁止國王是其他流程的限制。
- `force_units` 不做最小守軍或策略預留；Planner（規劃器）之後才決定要派其中多少。
- 函式不判斷塔是否屬於己方、目標是否可到達、路徑是否有效，也不保證目前可發送命令。這些必須由獨立的安全門控處理。

## 證據與未知值

`DeployableForce.production_rule=PRODUCTION_PROVEN`（正式版靜態規則已證）是函式 2031 的分支證據。`input_evidence=RUNTIME_VALIDATED`（執行期輸入已核對）只適用 Many（多兵種）目前數量；`input_evidence=INFERRED`（推論）表示 Single（單兵種）目前只有兩個 Ruler 自然結構例，尚無直接的單兵種數字介面核對。若塔類型、Shield 或任何必要兵力未知，`mirror_force_units` 回傳 `None`（未知），**不把未知寫成零**。

歷史樣本 `runtime/research/force_units/fixtures.json` 包含 10 座塔 × 3 時點、己方／中立／敵方、7 種塔類型、Many 與 Single，保存輸入位元組、離線輸出和推理軌跡。這些是**推導樣本，不是正式 Client（客戶端）輸出真值**。

目前 `RealTowerState.deployable_units`（舊整數欄位）維持 `None`：此欄位型別不足以表示官方回傳的逐兵種組成。`RealTowerState.deployable_force` 已新增逐兵種結果；完整 Many 資料標 DERIVED（推導），Single 在獨立數值驗證前維持未知。消費端仍須檢查同局新鮮度。若找到官方正常呼叫 2031 的被動輸出並與鏡像一致，才可升為 VERIFIED（已核驗）。
