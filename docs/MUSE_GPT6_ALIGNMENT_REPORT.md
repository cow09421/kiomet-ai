# MUSE ↔ GPT-6 INTELLIGENCE SYNC（情報共享報告）

讀者：先看完這份，再決定下一刀。所有「已驗證」都是 Muse 用檔案＋雜湊＋
計數獨立重算的；「未驗證」是 GPT-6 說了但產物裡沒有的。

## A. GPT-6 NEW BREAKTHROUGHS（新突破，5 個未提交檔案＋source-map 產物）
1. 正式 WASM 身份＋雜湊門控（`production-client_bg.wasm`，下載來源全記錄）。
2. 公開源碼本地編譯（`kiomet-local/`＋自帶工具鏈＋`target/` 產物，release 1m35s）。
3. Source→Production 函式比對器（WABT 結構特徵＋啟發式評分）。
4. CDP Debugger 渲染錨點：func1242＋0xD8D48 斷點讀塔（16 座）／0xDCC00 讀色
   （33 座＋SELF×5），單次停頓 ≤31ms，全程 IN_MATCH 同局門控。
5. 記憶體道路位元遮罩直讀（固定表位址，僅限已觀察塔，雙向強制）。

## B. VERIFIED BY MUSE（獨立核實通過）
- B1 正式檔雜湊：本地重算 sha256 `fae13d1d…054c` 與宣稱一致；大小 1,744,720；
  來源 `https://kiomet.com/client_bg.wasm`（provenance 有 URL＋位元組＋時間）。
- B2 命名計數：總 6831（含 442 import）、具名 1194、**Rust 具名恰 752**（宣稱吻合）；
  含 `TowerId::closest`、`ChunkMap::iter_towers_square`（grep 見正文）。
- B3 本地編譯：`build-local.log` 末行 release 成功；`target/.../client.wasm`
  37MB 存在；工具鏈 `nightly-2024-04-20`；`build-local.ps1` 可重跑（本輪不重跑）。
- B4 比對器：update_visible→production 483 相似度 0.88492（宣稱 0.885 吻合）；
  方法＝WABT 反組譯特徵（大小／指令分布／call／常數／記憶體操作／表操作），
  warning 明寫「啟發式非機率、內聯可致失效」——誠實分。
- B5 錨點數學：packed=x|y<<16（如 266,285→18678026）；position≈id×5＋偏移
  （1334＝266×5＋4，符合 CONVERSION＝5＋offset 0..4）；tower_ref 步長 48；
  彙總器邏輯嚴格（三輪同見證＋同局＋雙向＋僅觀察塔，否則拋錯）。
- B6  Cardiff 式三輪計數：render-anchor-in-match rounds 16/16/16、
  render-owner 33/33/33、result-screen 16/16/16（檔案內計數）。
- B7 儀器安全：斷點 finally 必清除＋Debugger.disable；平台現 live／RUNNING／
  IN_MATCH、live 幀推進、錯誤 0——無殘留暫停；僅平台 2 進程存活。

## C. CLAIMED BUT NOT YET VERIFIED（說了，產物裡沒有）
- C1 「三輪同一批」：存檔樣本全是 round 0（anchor 16、owner 33），跨輪**集合
  相等只能由彙總器跑過間接證明**，產物裡沒有三輪 ID 交集表。嚴格說是
  「程式邏輯保證過」，不是「存檔可重算」。
- C2 「33 座塔」：Verified 檔 33 條**全 round 0**，即單輪 33 unique；
  「三輪共 33」易誤讀，實際是 1 輪 33Unique＋3 輪計數 33/33/33。
  （anchor 16 同理：單輪 16 unique。）
- C3 func1242 的源碼對應：matches.json 僅 5 條，無 1242 條目；
  「可見塔迭代＋viewport 過濾」是行為推斷（連續 stride-48 引用＋合法座標），
  非匹配器輸出。證據 MEDIUM，非 HIGH。
- C4 取樣≠呼叫：1242 命中是斷點命中（迭代取樣），研究腳本自己也註明；
  不可解讀為呼叫頻次。
- C5 SELF 5 座：render_color 0→SELF 映射基於調色盤順序假設，**無 LIVE VIEW
  像素交叉驗證紀錄**；MEDIUM。灰色→UNKNOWN 是保守正確。

## D. TOWER DATA CURRENTLY AVAILABLE（唯一真表）
- 每塔：packed_id（x|y<<16，真 TowerId 整數編碼）、id [x,y]（0..512 合法）、
  tower_ref（堆引用，stride 48 排列）、position [wx,wy]（≈id×5＋0..4 偏移）、
  render_color（0＝SELF、1＝UNKNOWN；2/3 保留 OTHER 未出現）。
- 前 5（round 0，match m2-1790465771）：18678026 [266,285] ref 2682976
  [1334,1427]／18678027 [267,285] ref 2683024 [1336,1426]／18678028 [268,285]
  ref 2683072 [1343,1427]／18678029 [269,285] ref 2683120 [1348,1428]／
  （第 5 起略，檔案內按序排列）。
- SELF 例：18809099 [267,287] ref 2684560 [1339,1439] color 0。
- 尚無：TowerType／Owner id／Units／Screen XY／Neighbor（見 F）。

## E. PRODUCTION WASM MAPPING（重要函式）
- update_visible（local 2190）→ prod **483**，0.88492（已驗）。
- ChunkMap::get（local 2987）→ prod **2919** `ChunkMap::get_0`，0.88004。
- TowerId::offset／integer_position（local 2918／2919）→ prod **1905**（無名，
  0.768／0.753）。
- player_inner（local 2870）→ prod **1655**（無名，0.732）。
- func **1242**（無名）：源碼對應未建；行為＝可見塔迭代，斷點 0xD8D48 讀
  tower_ref／packed／world XY，0xDCC00 讀 Color。
- 方法特徵：函式大小／指令分布／call／常數／記憶體操作／表操作／呼叫者；
  符號名不計分（防內聯誤導），warning 已聲明。

## F. TOWER GRAPH STATUS
- 分類：**C＋D 混合**——不是運行時 neighbor list，也不是 edge 資料塊，而是
  **固定位址鄰居位元遮罩表**（`table@1365240`，512×512 u8；方向表
  `@1363184` 8×int16）**只讀已觀察塔**（腳本拒絕未觀察 id，彙總器雙向強制）。
- 規模：anchor 轮 18 無向邊／owner 輪 43 無向邊（86 有向，全雙向已驗）。
- 樣本邊：18678026↔18678027、18678026↔18743562、18678028↔18743564、
  18678029↔18743565、18678030↔18743566（均雙向；id 皆在觀察集合內）。
- Node 欄位現況：identity YES／world position YES／owner SELF-vs-UNKNOWN／
  screen position NO。

## G. OWNERSHIP STATUS
- SELF 5／OTHER 0／UNKNOWN 28／NEUTRAL UNKNOWN（未分類）。
- 機制：Color::new 返回值（0＝SELF；2/3＝OTHER 保留；1＝灰→UNKNOWN）。
- Confidence：SELF MEDIUM（調色盤假設＋5 座一致，無像素交叉驗證）；
  UNKNOWN 低（僅表「非自身色」，敵／中立／灰未分）。

## H. WORLD-TO-SCREEN STATUS
- 缺：camera transform／zoom／viewport／screen XY 全部未定位。
- 為何不用 render path 直讀：斷點讀的是**輸入端**區域變數（tower_ref／world XY），
  座標轉換發生在下游；要 screen XY 需在轉換**完成後**另設斷點（未做，
  GPT-6 額度先用完，非技術不可行）。
- 附帶：`to_client_position` 公式在參考源（viewport＋dpr），可用作驗證。

## I. MOVE_FORCE STATUS：**0**（VERIFIED SUCCESS = 0，未突破，勿誤讀）

## J. CURRENT HARD BLOCKER
放開點合法性不可驗：普通步兵要求道路鄰居，但塔圖（positions→ids→neighbors）
的螢幕側仍缺 screen XY 與即時性，WORLD 側已有 id＋遮罩。

## K. DO NOT REPEAT
f32/u16 盲掃／Yew DOM 選單／隨機像素放開／CDP Network 事件監聽／WebSocket
inbound（傳輸疑 WebTransport＋加密，MITM 禁止）／為靜音 resume AI／
Mock 回 live／vendor 入 Git／把取樣命中當呼叫次數／把單輪 33 讀成三輪 99。

## L. RECOMMENDED NEXT 3 STEPS
1. **轉換完成後斷點讀 screen XY**（func1242 下游或 Color 路徑下游；同安全門控；
   成功判據：同一塔 world↔screen 配對＋重進局可重現）。
2. **RESULT→Play Again→新 match 全鏈路**（selector 已知同 `#play_button`；
   成功判據：match_index＋1 且新局錨點可重建）。
3. **SELF 源邊首探**（self_source_edges 已有；用已知 SELF＋已知鄰居放開；
   成功判據：分類器 SUCCESS＋source units 下降，否則 valueless 不追）。
