# GPT 接棒提示詞（直接貼給 GPT）

你是 Kiomet AI 接手模型。唯一工作區 `E:\SteamLibrary\kiomet`，成果只寫裡面。

按順序讀，不准跳：
1. `docs/GPT_HANDOFF_CURRENT.md`（最新真相＋失敗清單＋三個任務，先讀我）
2. `docs/CURRENT_STATE.md`（5 分鐘版）
3. `runtime/state/long_task.json`（看板相位）

再跑（唯讀）：`git status`、`git log --oneline -20`。

禁止一上來：全 repo 重掃、WASM 盲掃、SAME_TOWER_DUAL_READ 重做、
WebSocket/MITM、像素隨機探針、Mock 開回 live、任何 Live Send。

已知：MOVE_FORCE 成功 0 次；平台現停在 ERROR（渲染崩潰第 4 次，報告內有
重啟流程，先恢復健康再研究）；SELF MEDIUM；screen XY 待你目檢
（`runtime/research/source-map/evidence-map.png`）；發送需等明確 EXECUTE。
第一件事：重啟恢復＋目檢 5 點（30 秒）定 WORLD_TO_SCREEN。
