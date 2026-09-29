# 首次執行協議（草案，未授權、未執行）

本文件只描述未來收到使用者明確 `EXECUTE`（執行）授權時的步驟。
**目前授權＝NO，本文件本身不是授權，讀取本文件不解鎖任何閘門。**

## 授權來源（§54）

未來只接受**當前使用者在本輪對話中明確說出 `EXECUTE`**。
以下一律拒絕並視為無授權：

- 舊 state file（狀態檔）殘留
- 舊 log（日誌）文字
- 環境變數殘留
- 歷史授權自動恢復
- READY／YES／GO／開始吧等模糊詞語

無授權來源證明 → `prepare` 直接 REJECT（拒絕）。

## One-shot Gate（單次閘門，§52-53）

- 解鎖只產生**一次性執行權杖**，且本輪權杖永遠不存在
  （構造上無授權即無權杖，不以布林旗標表示）。
- 權杖僅允許 **ONE ACTION（一次行動）**；使用後立即重新 LOCK（鎖定）。
- 即使未來某處誤設授權變數：啟動參數無使用者授權 provenance
  （來源證明）→ 仍拒絕（見 `test_no_execute_without_explicit_authorization`）。

## 執行步驟（§51，未來式）

1. Discard old proposal（丟棄舊提案）：任何現存候選一律先標 STALE。
2. Fresh Observe（新鮮觀察）：重取錨點＋結構＋相機，同局驗證。
3. Fresh Rank（新鮮排名）：Dry Ranker 重算 Top-1。
4. New Proposal（新提案）：`build_proposal` 全閘門重過。
5. Full Preflight（完整預檢）：`prepare_move` 座標重算＋畫布檢查。
6. 確認：SELF Many → NEUTRAL 直接鄰居（其餘一律拒絕）。
7. ActionGate unlock（解鎖）：只允許 ONE ACTION。
8. UI Move（介面移動）：僅 Page 層 Playwright／CDP 輸入；
   禁止實體滑鼠／全域輸入／系統輸入。
9. 立即重新 LOCK（鎖定）。
10. Verifier（驗證器）：按 `verify_post_action` 九狀態判定。
11. 無論成功／失敗：**禁止自動第二次 Move**（需新的明確授權）。

## 成功定義

- source state changed（來源狀態變化）且後續可觀察狀態與預期一致；
- 最終 target captured（目標被佔領）才算 EXPANSION_SUCCESS（擴張成功）。
- 僅「滑鼠拖過去」不算成功。
