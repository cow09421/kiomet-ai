# Round 11 → Muse 整合增量

只列 Round 10 之後新增的整合要求。

## IMMEDIATE（立即加入的閘門）

1. **Action Validity Token（行動有效性權杖）派送前檢查**：保留 `match_id`、`cycle_id`、`world_snapshot_id`、`source_state_version`、`target_state_version`、`camera_version`、`created_at`。任何不符就回 `STALE_PROPOSAL` 並重新規劃。
2. **Source Safety Gate（來源塔安全閘門）**：先套用完整可派兵力，再逐支評估來源塔已知威脅；來源將失守或任何資料未知時拒絕 `REINFORCE_SELF` 與 `ATTACK_ENEMY`。
3. **Multi-Threat Defense（多威脅防守）**：每個目標塔排序全部已知入站部隊，逐場寫回狀態；第二支威脅未處理前，第一場守住不代表威脅已解除。
4. 同一輪的所有 Planner（規劃器）共用原子來源保留與 VERIFYING lock（驗證中鎖定），禁止防守／攻擊雙重花費與重複命令。
5. 同 tick（同節拍）Force（部隊）沒有「援軍優先」規則。缺少當下 inbound Vec index（入站向量索引）與生產版驗證時，DefenseEvaluator（防守評估器）必須 ABSTAIN（暫不行動）。

## AFTER RUNTIME VALIDATION（執行期驗證後）

- 只對已驗證分支啟用逐支時間序模擬：多敵軍、多援軍、owner flip（塔主切換）後的第二支抵達、碰撞與塔抵達同 tick。
- 將觀察到的 Collection index（集合索引）、Tower owner（塔主）、units（兵力）、Force progress（部隊進度）及 InfoEvent（資訊事件）納入差分紀錄；快照一變即使 token 失效。
- 把驗證登錄依對局版本、正式版雜湊與測項分開保存；樣本不能推廣到未測的塔型、光環、特殊兵種或順序。

## DO NOT ENABLE（禁止啟用）

- 同節拍但集合順序未知的救援或攻擊。
- 只評估第一支入站敵軍的 `THREAT RESOLVED` 判定。
- 未做來源派兵後安全檢查的攻擊／增援。
- Ruler（國王）、Shell（砲彈）、EMP（電磁脈衝）、Nuke（核彈）或其他未支援戰鬥。
- 以浮點秒數、兵力總和或 UNKNOWN（未知）轉零來填補順序、兵種或合併容量。

Round 11 沒有修改 Muse 正式程式，沒有連線執行期，也沒有發出遊戲行動。
