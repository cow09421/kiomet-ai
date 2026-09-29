# 下一輪 GPT 高難題（2026-09-28 長跑第二輪版，Muse 整理）

提醒：2031 本體語意＝PASS、離線鏡像＝PASS，**不要重解函式本身**，
只追 caller（呼叫者）／output（輸出）。以下按優先級排序。

---

## P0：2031 caller／output dataflow（呼叫者／輸出資料流）

Problem（問題）：
正式版 2031 在官方 Client 正常流程中的被動輸出從未被直接捕捉；
Many 停在 DERIVED（推導）無法升 VERIFIED（已核驗）。

Why hard（為何難）：
已知呼叫者（448 tick、488 peek_mouse、1091 supply、1242 render、
1791 deploy）全需拖曳狀態或真實派兵；單純選塔不呼叫
（`drag.start==current` 分支確認）。Muse 禁止製造拖曳／派兵。

What is proven（已證明）：
靜態分支全對應；離線鏡像與 30 筆歷史輸入一致。

Runtime evidence（執行期證據）：
- 2 起自然下降（m1-1790523816 兩座敵方兵營 Soldier 4→0、盾不動），
  下降向量與鏡像逐兵種一致：
  `runtime/research/force_units/passive/drop-001-m1-1790523816.json`
- 差分工具：`tools/dispatch_diff.py`

Source paths（來源路徑）：
`vendor/kiomet-ref/common/src/tower.rs`（force_units／take_force_units）。

Production functions（正式版函式）：
2031（`+38`＋`+46==15` 判斷）、3825、5444、1637、5906。

Best fixtures（最佳樣本）：
`runtime/research/force_units/fixtures.json`（30 筆＋鏡像輸出）。

Failed approaches（失敗方法）：
純選塔等待輸出（來源證實不呼叫）；高頻快照只抓到生長事件。

Exact next experiment（精確下一步）：
反組譯 488 peek_mouse 拖曳強度分支，找其讀取的已存在預覽結果位址；
或自然補給派兵瞬間高頻前後快照＋Force 結構定位。

---

## P1：Upgrade State Runtime layout（升級狀態執行期布局）

Problem（問題）：
升級中狀態在 production 的儲存位置未知（`delay` 候選，但 +45 已被
國王旗標佔據）；升級按鈕 enabled／cost／cooldown 的 Runtime 對應未知。

Why hard（為何難）：
需將 UI 按鈕狀態與記憶體位元組逐項配對，且升級事件稀少。

What is proven（已證明）：
UI 真值包已就緒（見下）；5 條升級鏈全部來源交叉驗證。

Runtime evidence（執行期證據）：
- `runtime/research/upgrade/ui/upgrade_ui_ground_truth.json`：
  m1-1790523816 共 21 塔（5 SELF 帶升級 UI＋16 無）。
- 5 條鏈：Generator→Reactor、Mine→Bunker、Runway→Airfield、
  Village→Headquarters＋Town；每條的 UI 前置數字 == 來源
  prerequisite 屬性（如 Airfield 需 Factory=2、Radar=1，
  UI 顯示 工廠=0/2、雷達=0/1）。
- 國王鄰近加成註記（「你的國王就在附近…士氣高昂」）與 +45=1 同步。
- 語意解析器：`src/kiomet_ai/ui_parse.py`
 （UnitRow／PrereqRow／NoteRow／UpgradeTarget 分流＋測試）。

Best fixtures（最佳樣本）：
14811364 村莊（雙升級選項＋前置 發電機=2/1、村莊=1/3）；
14745828 跑道（機場＋工廠=0/2、雷達=0/1）。

Exact next experiment（精確下一步）：
自然升級事件前後同塔位元組差分（特別 +45／+47 之後區域），
以 UI 按鈕 enabled 變化為錨。

---

## P1：來源快照與 Production 的 has_ruler 語意差異

Problem（問題）：
vendor 快照 `capacity()` 以塔自身含 Ruler 決定 +10，且 add_inner
會把 Many 轉 Single；production 實測國王可駐守 Many 塔
（帶其他兵力）並提供加成。m1-1790539798 更出現同玩家雙塔分歧
（Factory +45=0／UI 10/10；Runway +45=1／UI 10/15），證實
+45 與加成為 per-tower（逐塔）語意。

What is proven（已證明）：
`+45=1 ⟺ 該塔盾容量 raw+10`（多局；含同玩家分歧雙塔 UI 驗證）。
Single(Ruler,1)＝國王單獨駐守狀態，非國王存在的唯一形式。
證據：`runtime/research/units/ruler-event-m1-1790539798.json`、
`tests/test_capacity.py`。

Runtime evidence（執行期證據）：
容量推導測試 `tests/test_capacity.py`（兩局 UI 分母全量）；
`decode_owner_ruler_flag`＋`unit_capacity` 已工程化。

Exact next experiment（精確下一步）：
自然國王死亡事件：+45 是否 1→0、盾容量是否同步回落
（本輪整晚未發生，+45 穩定）。

---

## P2：Moving Force layout（移動軍隊布局）

Problem（問題）：
Force 結構／路徑／進度全未知；自然樣本整晚 0 筆。

What is proven（已證明）：
收集框架（`tools/force_samples.py`）＋來源路徑
（`common/src/tower.rs` inbound／outbound_forces；
`common/src/force.rs` 待讀）。

Exact next experiment（精確下一步）：
攢 ≥10 自然樣本後再逆向；樣本為 0 時不開工。

---

## Single 狀態說明（首個直接真值已得，仍缺量）

五局自然樣本：四個 Single(Ruler,1)＋一個 Single(Nuke,1)；
+39 count／+40 enum 同構；Nuke 樣本有 UI 直接數字
（核彈=1/1）。Single 塔 +41..+43 可能帶轉換殘留
（只讀 +39／+40／+44，已有迴歸測試）。
Ruler 不顯示數字（UI_NOT_VISIBLE）。
**再攢 2 個以上非 Ruler 真值才升整體 DERIVED。**
證據：`runtime/research/units/single-sample-*.json`。

---

## P1：Renderer Crash 上游觸發（本輪新證據更新）

Problem（問題）：
直接故障路徑已定（chrome.dll+0x710E1A7）但上游觸發未定。

What is proven（已證明）：
- 本輪新增 2 起（crash-006／007），逐位元組驗證 SAME_SIGNATURE
  （0xC0000005、前 18 堆疊偏移一致）。
- 7/7 渲染崩潰全部伴隨斷點／CDP 重度研究會話；A/B 260 分鐘＋
  本輪非斷點運行全程零崩潰。研究工具活動關聯：強。
- 證據：`runtime/research/crash/incidents/crash-006-2026-09-28.json`、
  `crash-007-2026-09-28.json`；傾印目录新增 afe9abb5、296e0d62。

Exact next experiment（精確下一步）：
「截圖 ON＋無研究工具」vs「截圖 ON＋斷點活動」對照；
或逆向 chrome.dll+0x710E1A7 上游呼叫者，確認斷點暫停如何觸發該路徑。
