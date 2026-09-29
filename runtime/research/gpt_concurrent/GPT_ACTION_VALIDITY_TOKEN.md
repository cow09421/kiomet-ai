# 行動有效性權杖契約（Round 11）

每個計畫候選（Proposal，提案）建立時，必須攜帶完整權杖：

| 欄位 | 用途 |
|---|---|
| `match_id` | 防止跨對局沿用行動。 |
| `cycle_id` | 綁定本次規劃週期與仲裁結果。 |
| `world_snapshot_id` | 綁定規劃時的完整世界觀測。 |
| `source_state_version` | 綁定來源塔 owner、兵力、塔型、入站威脅及出站部隊。 |
| `target_state_version` | 綁定目標塔 owner、兵力、容量、塔型及入站部隊。 |
| `camera_version` | 綁定畫面座標與攝影機轉換版本；避免世界資料新鮮但點擊位置過期。 |
| `created_at` | 以單調時鐘或同一伺服器 tick 記錄提案建立時間。 |

## Dispatch（派送）前置檢查

執行器在發出任何遊戲命令前，從當下狀態重新讀取 `match_id`、`cycle_id`、`world_snapshot_id`、`source_state_version`、`target_state_version`、`camera_version`，逐一與 Proposal 比對。`created_at` 必須存在、不得晚於目前單調時間，而且年齡須在部署設定的有效期限內。任何欄位缺失、無法讀取、不相等或逾期時，回 `STALE_PROPOSAL`（提案已過期），取消這次命令，釋放資源保留並重新規劃。

不得只重新確認目標 owner。來源兵力、來源威脅、世界快照、對局、cycle 或 camera 任一項變更，整份戰鬥評估和行動都失效。

## 防止重複與雙重花費

- 仲裁器以 `(match_id, cycle_id, source_state_version)`（對局、週期、來源版本）作單次原子保留，同一來源狀態只允許一個互斥派兵動作。
- Action（行動）仍在 `VERIFYING`（驗證中）時鎖住該 Proposal 的來源、目標及命令識別；下一個 cycle 不得重發同一命令。
- 執行成功、明確拒絕或驗證逾時都要結束鎖定並刷新快照；不允許靜默重試忙迴圈。
- 相機／畫面版本只作為執行座標有效性的閘門，不可代替世界狀態驗證。

本檔是資料與控制流契約，沒有修改 Muse Runtime（執行期）或 Round 10 正式程式。
