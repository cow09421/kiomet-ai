# Kiomet 雙 Agent 協作區

GPT 與 MUSE 是同級工程代理（peer engineers），可以各自研究、實作、測試、除錯和審查。沒有固定的「研究／實作」分工。唯一的檔案規則是：同一時間只能有一個代理認領某個可修改路徑。

## 權威狀態

`coord.db` 是任務、路徑認領、訊息、心跳與決策的唯一權威狀態。`BOARD.md`、`status/` 和 `inbox/` 是由命令產生的可讀檢視；不要手動把它們當成資料庫替代品。

需要 Python 3.12 或更新版本；協作工具只用 Python 標準函式庫，資料庫採 SQLite WAL（預寫式記錄）模式，資料庫鎖等待上限至少 5 秒。

## 常用命令

在專案根目錄執行：

```powershell
python agent_coordination\coord.py board
python agent_coordination\coord.py tasks
python agent_coordination\coord.py inbox GPT
python agent_coordination\coord.py claim <TASK_ID> GPT
python agent_coordination\coord.py start <TASK_ID> GPT
python agent_coordination\coord.py heartbeat GPT --phase working --note "進度摘要"
python agent_coordination\coord.py done <TASK_ID> GPT --summary "完成內容與測試"
python agent_coordination\coord.py block <TASK_ID> GPT "阻塞原因"
python agent_coordination\coord.py release <TASK_ID> GPT
python agent_coordination\coord.py message MUSE P1 SUBJECT "訊息內容"
python agent_coordination\coord.py snapshot
```

首次建立資料庫時執行 `python agent_coordination\coord.py bootstrap`。認領會在單一資料庫交易中檢查任務狀態與路徑衝突，再一起更新任務、路徑鎖與心跳。若另一代理先取得任務，命令會回報 `ALREADY_CLAIMED`；若修改路徑重疊，則回報 `PATH_CONFLICT`。

## 共用工作樹安全

- 認領任務前讀取 `board` 和自己的 `inbox`，認領後只修改已認領路徑。
- 看到另一代理的未提交修改，先保留原狀並把該路徑當成 `FOREIGN_ACTIVE`（另一代理施工中）。
- 禁止 `git add -A`、`git add .`、`git reset --hard`、`git clean`、`git restore .` 和 `git checkout .`。
- 若需提交，只精確暫存已認領路徑；提交前核對工作樹和暫存清單。
- `snapshot` 只保存協作資料庫副本與 Git 狀態摘要，不會複製工作樹檔案內容。

## 里程碑安全規則

- 未知值（UNKNOWN）永遠不能默認成 0。
- 尚未由正式執行期（runtime）驗證的同節拍援軍一律拒絕判定，必須棄權（ABSTAIN）。
- PvP v0 禁用特殊單位。
- 正式操作只走遊戲官方 UI 事件路徑。
- 每個派兵動作都必須先驗證上一動作，再刷新觀察並重新規劃。

目前里程碑與成功條件見 [CURRENT_MILESTONE.md](CURRENT_MILESTONE.md)。
