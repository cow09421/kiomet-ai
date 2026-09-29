# 真實自主閉環狀態機

以下是實作規格，不代表目前平台已連線或獲准自行送操作。每次轉移均帶同一 `match_id`（對局識別）、單調的 observation_version（觀察版本）與 controller_epoch（控制器世代）；切局、重啟、暫停均使舊提案失效。所有逾時值是**初始上限建議**，應依既有觀察能力量測再調整。

| 狀態 | 進入條件／工作 | 正常退出條件 → 下一狀態 | 逾時與錯誤轉移 |
|---|---|---|
| STARTING（啟動中） | 真實模式、明確授權、唯一控制器實例成立；確認平台、瀏覽器與唯讀通道 | 取得當局、新鮮狀態及活性心跳 → OBSERVING（觀察中） | 30 秒無法連線／多實例／授權缺失 → FAILSAFE（安全封鎖）或 PAUSED（暫停） |
| OBSERVING（觀察中） | 同一局取新鮮塔、部隊、畫面映射及世界節拍；所有指標與標記檢查通過 | 觀察完整且在有效時窗 → PLANNING（規劃中）；結算 → MATCH_END（對局結束） | 30 秒內三次觀察無效 → FAILSAFE；單次無效則重試 OBSERVING |
| PLANNING（規劃中） | 對最新 observation_version 只產生候選，不派送 | 有安全候選 → PREFLIGHT（執行前檢查）；無安全候選 → NO_SAFE_PROPOSAL（無安全提案） | 5 秒超時／資料版本變動 → REPLANNING（重新規劃） |
| NO_SAFE_PROPOSAL（無安全提案） | 記錄具體拒絕原因並保持唯讀觀察 | 有新節拍／局面變化 → OBSERVING | 60 秒心跳，超時仍停留；觀察故障 → FAILSAFE |
| PREFLIGHT（執行前檢查） | 重新核對同局、擁有權、塔狀態、畫面座標、授權、無在途操作及提案新鮮度 | 全部通過且 action_id（行動識別）已持久寫入 → DISPATCHING（派送中） | 5 秒超時／任一資料變舊 → REPLANNING；授權或閘門失效 → PAUSED |
| DISPATCHING（派送中） | 單次定向拖曳，持久記錄行動識別、呼叫端、輸入證據與派送結果 | 明確 `sent=True` → VERIFYING（驗證中）；明確未送 → REPLANNING | 120 秒平台回應上限；若是否送出不明，進 FAILSAFE，先查重，**不得重送** |
| VERIFYING（驗證中） | 依本輪驗證規格讀連續快照，匹配該 action_id 與世界部隊／結果 | 強證據達標 → VERIFIED_MOVE（已驗證移動）；目標擁有權再達標 → VERIFIED_EXPANSION（已驗證擴張） | 到預計單段抵達時間加寬限仍不明 → FAILSAFE 或帶 UNKNOWN（未知）進 REPLANNING；絕不視同成功 |
| VERIFIED_MOVE（已驗證移動） | 記錄精確證據鏈，只代表命令造成匹配部隊離塔 | 行動紀錄落盤 → REPLANNING；若後續目標被確認佔領 → VERIFIED_EXPANSION | 紀錄失敗／證據後來矛盾 → FAILSAFE |
| VERIFIED_EXPANSION（已驗證擴張） | 同一 action_id 的移動證據與目的塔擁有權變化均成立 | 紀錄落盤 → REPLANNING | 目的塔歸屬不明 → 留在 VERIFIED_MOVE；不倒填擴張 |
| REPLANNING（重新規劃） | 清除提案、重新觀察；保留行動稽核與冷卻 | 前次行動處置已終結且新快照可用 → OBSERVING | 若還有未決 action_id 或連續三次驗證不明 → FAILSAFE |
| PAUSED（暫停） | 人工暫停、授權撤銷或暫時閘門關閉；停止新派送，唯讀觀察可續行 | 明確恢復授權且取得新觀察 → OBSERVING | 不自動恢復派送；切局清除舊提案 |
| FAILSAFE（安全封鎖） | 未決派送、來源不明、觀察不可信或連續錯誤；停止所有新操作 | 人工處置後重新建立當局／控制器世代 → STARTING | 無自動解除；保留診斷證據 |
| MATCH_END（對局結束） | 遊戲結算、對局識別變動或頁面離局 | 新對局啟動且重錨定完成 → STARTING | 舊行動標為跨局未決；不得轉到新局驗證 |

**核心不變式：一個 Action（行動）→ 驗證 → 重新觀察 → 下一個 Action。** 任一時刻最多一個未完成 `action_id`；禁止批次派送或在只看到 `ACTION_SENT`（輸入已送出）後直接規劃第二次。狀態轉移與拒絕原因必須附時間、對局、控制器世代及操作識別持久記錄；儀表板只顯示新鮮狀態。
