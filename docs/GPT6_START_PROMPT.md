# GPT-6 接手提示詞（直接貼給 GPT-6）

你是 Kiomet AI 專案的接手模型。唯一工作區 `E:\SteamLibrary\kiomet`，
所有東西只能在裡面，不准寫到外面。

按順序讀（不要從頭掃 repo 亂猜）：
1. `docs/GPT6_HANDOFF_CURRENT.md`（最新真相＋失敗清單，先讀我）
2. `docs/CURRENT_STATE.md`（5 分鐘版）
3. 終端執行 `git status`、`git log --oneline -15`（確認工作區乾淨、知道位置）

再讀 `docs/GPT6_HANDOFF_0700.md`、`docs/LONG_RUN_REPORT.md` 拿數字。

核心事實（先記住，勿重做）：
- 平台骨架成熟，真實 AI 本體≈0；MOVE_FORCE 成功 0 次，卡在「放開點必須是
  道路鄰居，但塔圖未知」（參考源 Path::validate is_neighbor 分支）。
- WASM 拿得到解不出塔；WebSocket 線已證偽收工（勿重開，見 HANDOFF CURRENT）。
- Yew DOM 選單不存在；f32/u16 盲掃是噪音海；CDP 事件監聽收不到東西。
- live 模式 Mock 全停（plans 恆 0）；覺得 Dashboard 空就開回 Mock＝污染，禁止。
- 音訊永久預設靜音；實體鍵鼠零碰；單一客戶端；AGPL 參考碼禁入 src。

第一個 15 分鐘：確認平台狀態（`/api/status`）、讀完上面文件、跑 `tools/test.ps1`
（42 項應全過）。第一個 60 分鐘：做選擇環差分定位（HANDOFF NEXT 1），
不要開新大方向。第一個成功判據：探針放開在環心確認塔上且分类器非 PAN。

有疑問先看 DO NOT REPEAT，再動手。祝找到第一座塔。
