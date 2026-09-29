# GPT 可派兵量高難題交接

更新：2026-09-27。所有研究檔案均在 `E:\SteamLibrary\kiomet`。**本輪 `sent_actions=0`、真實 `MOVE_FORCE=0`、未取得 `EXECUTE`（執行）授權。**

| 項目 | 結論 |
| --- | --- |
| FORCE_UNITS_SOURCE（公開來源語意） | PASS（通過）；`docs/FORCE_UNITS_SOURCE_SEMANTICS.md` |
| FORCE_UNITS_PRODUCTION（正式版函式 2031） | PASS（靜態語意通過）；`docs/FORCE_UNITS_PRODUCTION_ANALYSIS.md` |
| FORCE_UNITS_MIRROR（離線鏡像） | PASS（純函式與歷史輸入可計算）；`src/kiomet_ai/force_units.py` |
| FORCE_UNITS_RUNTIME_VALIDATION（正式執行期輸出核驗） | NOT AVAILABLE（目前不可取得）；不以靜態推導冒充真實輸出 |
| deployable_force（逐兵種可派組成） | Many（多兵種）完整輸入：DERIVED（推導）；Single（單兵種）：觀察器維持 UNKNOWN（未知） |
| Local Differential（本機 WASM 差分） | 0/0，未執行；本機客戶端 WASM 有 379 個匯入，無安全獨立呼叫架構 |

## FORCE_UNITS_SOURCE / PRODUCTION（來源與正式版）

公開來源 `vendor/kiomet-ref/common/src/tower.rs`：`force_units()` 回傳 `Units`，逐兵種保留可移動者。正式版 **func[2031]**，偏移 `0x1096F9`，簽章 `(i32 result_ptr,i32 tower_ref)->nil`，回傳 7 位元組 `Units` 結構。它讀 `tower_ref+38` 的兵力與 `+46` 的塔類型，檢查 `+46==15`（Projector，投射器）。經 `5440 → 3825 → 5444 → 1637` 取得非零兵種和目前數量，再用 `5906 Units::add` 組合回傳。1637 是 `Units::available`（取得某兵種目前數量），**不是可派兵量**；2031 不直接呼叫它，經迭代器間接呼叫。

**MANY RULE（多兵種規則）：** Fighter（戰鬥機）、Chopper（直升機）、Bomber（轟炸機）、Tank（坦克）、Soldier（士兵）全部原量納入。**SINGLE RULE（單兵種規則）：** Shell（砲彈）、Emp（電磁脈衝）、Nuke（核武）、Ruler（國王）原量納入；正式版解碼分支已證，但自然輸入目前只看過 Ruler。**SHIELD RULE（護盾規則）：** 只有 Projector 的 Shield 可派；其他塔 Shield 原量留塔。**RULER RULE（國王規則）：** 2031 不保留國王；危險路徑延遲和自動補給線限制位於其他流程。**TOWER TYPE EFFECT（塔種類影響）：** 2031 只用「是否 Projector」決定 Shield；不讀國王旗標 `+45`、容量、玩家所有權或路徑。

## RUNTIME FIELDS / OFFLINE MIRROR（執行期欄位與鏡像）

`tower_ref+38`：Many/Single 標籤；`+39..+43`：五種 Many 數量或 Single 數量／兵種編號；`+44`：Shield；`+46`：Tower Type（塔種類）列舉。均為 1 位元組無號。`+45` 的玩家國王旗標不進入 2031。鏡像 `mirror_force_units(TowerUnitCounts,tower_type)` 輸出 `DeployableForce.counts`（十兵種逐項）、`total`（輔助總數）、逐筆推理軌跡及證據狀態；未知輸入回 `None`，不冒充零。

`runtime/research/force_units/fixtures.json` 保存歷史同局 **10 座塔 × 3 時點 = 30 筆**輸入和離線輸出，涵蓋己方／中立／敵方、7 種塔類型與 `Single(Ruler,1)`。例：Runway（跑道）Shield15、Fighter4、Soldier4 → 可派 8；Quarry（採石場）僅 Shield21 → 可派 0；一座敵方 Armory（軍械庫）的 Tank 可派量隨自然事件 `2→4→1`。這些數字是**離線推導**，不是正式客戶端輸出真值。

`RealTowerState.deployable_force` 已接到只讀觀察器契約：只對完整 Many 輸入標 `DERIVED`（推導）；Single 維持 `UNKNOWN`（未知）。舊 `deployable_units: int` 永遠未知，因為官方輸出是逐兵種結構，不能用單一整數代替。使用任何推導值前仍須通過同局新鮮度門控。

## RUNTIME VALIDATION / CURRENT HARD BLOCKER（正式執行期核驗／障礙）

單純選塔只顯示原始兵力，來源 `client/src/game.rs` 的 `drag.start==current` 分支不呼叫 2031。正常呼叫者包含 `KiometGame::peek_mouse`（滑鼠拖曳狀態）、渲染拖曳預覽、自然補給線和 `Tower::deploy_force`（實際部署）。尚未有不需拖曳／派兵即可讀出的 2031 結果結構。**唯一剩餘的不確定輸入分支是 Single：目前只有兩個 Ruler 結構樣本，缺獨立數字介面驗證。** 沒有 2031 主要分支未解。詳見 `docs/FORCE_UNITS_HARD_BLOCKER.md`。

## TESTS / FILES（測試／檔案）

- 本輪完整套件 `python -m pytest -q`：**87 passed（87 項通過）**；另有 1 則既存測試快取目錄存取權警告，不影響結果。
- `tools/extract_wasm_functions.py` 靜態節錄正式版與本機 WASM；正式版輸入雜湊固定，指令檔在 `runtime/research/force_units/production/`，本機函式 2997／2893 在 `local/`。
- `tools/force_units_fixture.py` 從已保存的 `units_ground_truth.json` 生成離線樣本，無瀏覽器連線。此輪未呼叫正式版函式，未操控滑鼠鍵盤。
- 最後只讀健康檢查時，`127.0.0.1:8765` 拒絕連線，平台目前未提供執行狀態；本輪未因此重啟或接觸遊戲。音訊目前狀態與全域焦點計數記為 UNKNOWN（未知），不能把歷史靜音／焦點結果誤稱為當下證據。

## MUSE NEXT TASK（Muse 下一步）

找正常遊戲自然觸發 2031 時**可讀的結果**，優先被動觀察自然補給線派兵或已存在的預覽資料；以同一塔、同一時點的原始 `Units`、塔類型和正式結果配對。若沒有安全唯讀輸出，保持 `DERIVED`，不要為了把標籤升成 VERIFIED（已核驗）而嘗試拖曳、真實派兵或直接呼叫 2031。

## 最終判定

**「給定一座目前 Observer（觀察器）已知完整狀態的 Tower（塔），在不呼叫正式版 WASM 的情況下，能否離線精確算出官方 Client（客戶端）會認為可派出的 Force（部隊）？」——PARTIAL（部分）：完整 Many 狀態可以；Single 的執行期輸入仍缺獨立數值驗證。正式版 2031 本身沒有剩餘未知主要分支。**
