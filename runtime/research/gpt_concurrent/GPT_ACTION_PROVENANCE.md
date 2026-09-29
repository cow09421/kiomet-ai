# 兩次真實操作的來源鑑識

本報告只讀取既存檔案與程式碼；沒有連接瀏覽器、控制介面或執行期。時間均為臺灣時間（UTC+08:00）。`sent_actions=2` 是 `runtime/state/live_gameplay.json` 的**歷史累計**，並不表示目前控制器正在遊玩，也不表示遊戲已接受兩次派兵。

## 計數與呼叫鏈

唯一已確認會增加這份歷史累計的程式位置是 `Application.execute_move`（平台執行一次調兵；原提交 `716ce70` 的 `src/kiomet_ai/app.py:185`，本輪 Muse 同步編輯時位移至約 `:199`）：它等待 `BrowserHost.execute_directed_move`（瀏覽器定向拖曳）回傳 `sent=True` 後，才將 `journal.sent_actions` 加一。瀏覽器函式在滑鼠放開後設定 `sent=True`（本輪工作樹約 `browser.py:1133`），接著擷取一秒後的畫面；它**不驗證遊戲世界是否接受命令**。

入口是 `src/kiomet_ai/dashboard/__init__.py:62-80` 的 `POST /api/execute-move`（控制介面發送請求），使用控制憑證檢查，再呼叫 `Application.execute_move`。歷史上的 `tools/live_controller.py:242-251` 也能透過同一 HTTP（網頁請求）入口送操作，但平台當時沒有保存呼叫端、請求程序編號或 action_id（行動識別碼）。因此可證明**傳輸類型**是 DIRECT_API_POST（直接控制介面請求），不能僅由此判斷是人工探針、外部測試程式或自主控制器發起。Muse 後續提交 `e4d371f` 已加入來源欄位；它不能追溯填補舊兩筆紀錄。

`src/kiomet_ai/app.py:196` 把每次 `LiveMove`（真實調兵紀錄）寫入 `runtime/logs/decisions.jsonl`。該筆只有時間、畫面座標、提案識別與 `ACTION_SENT`（輸入已送出），沒有呼叫端或驗證欄位。`runtime/state/live_gameplay.json` 只保留最後一次操作，`last_verification=null`，`verified_moves=0`。另外 `src/kiomet_ai/app.py:79` 的頂層 `sent_actions` 指的是 MockExecutor（模擬執行器）的計數；`live_sent_actions` 是目前程序記憶體中的定向拖曳長度，程序重啟後歸零。三個數字不可混用。

## Action #1（第一個操作）

| 欄位 | 鑑識結果 |
|---|---|
| 時間 | 2026-09-28 09:55:48.0919；決策紀錄第 61 行，`sent_at=1790560548.0919023` |
| 對局 | `m1-1790559914` |
| 來源塔 → 目的塔 | `15139012 → 15073477`，由 `proposal_id`（提案識別）字串解析；未另有塔參照直接核對 |
| 畫面起點 → 終點 | `[859.06,385.24] → [963.67,524.71]` |
| 平台程序 PID（程序編號） | **UNKNOWN（未知）**；當時的控制檔已被後續程序覆寫，紀錄未存 PID |
| 呼叫函式／檔案 | `Dashboard.Handler.do_POST`（控制介面）→ `Application.execute_move`（`app.py`）→ `BrowserHost.execute_directed_move`（`browser.py`） |
| 誰觸發 | **UNKNOWN**。提案字串形狀與 `tools/live_controller.py:245` 一致，但任何持有控制憑證的呼叫端都能提交該字串；無請求來源紀錄 |
| 類別 | **DIRECT_API_POST（直接控制介面請求）已證明；自主或人工發起者 UNKNOWN** |
| 定向拖曳函式 | **YES（有）**；`runtime/moves/1790560546/before.png` 與 `after_settle.png` 存在，且日誌回傳 `ACTION_SENT` |
| Verifier（驗證器） | 平台的 `execute_move` **NO（沒有）**呼叫驗證器；外部呼叫端是否在當時另行驗證 **UNKNOWN**。歷史累計 `verified_moves=0` |
| 結果 | **輸入已送出；遊戲成功未驗證**。一秒後截圖尚無足夠證據。約三分鐘後第二次操作的事前畫面可見該目的區域轉藍，屬後見線索，缺少行動匹配的移動部隊及中間觀察，不升級為已驗證擴張 |

## Action #2（第二個操作）

| 欄位 | 鑑識結果 |
|---|---|
| 時間 | 2026-09-28 09:59:06.5131；決策紀錄第 62 行，`sent_at=1790560746.5130615` |
| 對局 | `m1-1790559914` |
| 來源塔 → 目的塔 | `15073477 → 15073476`，由提案識別解析 |
| 畫面起點 → 終點 | `[963.67,524.71] → [859.06,594.45]` |
| 平台程序 PID | **UNKNOWN**，原因同第一個操作 |
| 呼叫函式／檔案 | 與第一個操作相同；日誌 `runtime/logs/decisions.jsonl:62` |
| 誰觸發 | **UNKNOWN**；只有 HTTP（網頁請求）入口可確認 |
| 類別 | **DIRECT_API_POST（直接控制介面請求）已證明；自主或人工發起者 UNKNOWN** |
| 定向拖曳函式 | **YES**；`runtime/moves/1790560744/before.png`／`after_settle.png` 存在，日誌 `ACTION_SENT` |
| Verifier（驗證器） | 平台 **NO**；外部 **UNKNOWN**；沒有已驗證移動紀錄 |
| 結果 | **輸入已送出；遊戲成功未驗證**；一秒後畫面不足以判定派兵或擴張 |

## 能與不能下的結論

歷史 `live_gameplay.sent_actions=2` 對應上述兩筆 `LiveMove` 紀錄與兩個截圖資料夾，沒有證據顯示為 `probe_move`（探針調兵）或 MockExecutor（模擬執行器）計數。`tools/live_controller.py` 在 09:41 的提交中已具備同格式提案與相同 POST（網頁請求）路徑；後來的 `live_controller_log.jsonl` 從 11:12 才開始追加，因附加日誌功能直到 11:07 的提交才存在，不能用「11:12 前無日誌」排除早期控制器曾運行。現存控制器狀態已由後續啟動覆寫，故兩筆**無法證實也無法排除**由自主控制器發起。

**LIVE AUTONOMOUS EXECUTION（真實自主執行）= 0 VERIFIED ACTIONS（零筆已驗證操作）**；這表示缺少可稽核的自主來源與遊戲結果證據，不宣稱兩筆一定由人工發出。後續需在平台接收請求時持久記錄 `action_id`、發起者類型、發起程序 PID、對局、提案、授權來源、派送與驗證證據，並將「輸入送出」與「世界狀態驗證」分開計數。
