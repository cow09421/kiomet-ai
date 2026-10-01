# M2A — minimum deterministic world simulator

STATUS: IN_PROGRESS，持續施工。M1B PASS checkpoint `2212346`；OLD M1 FAIL 原樣保留。

`src/kiomet_ai/v2/sim/` 新 Python reference core，沒有延伸舊 simulate.py。
Canonical→compact SimulationState 轉換先通過 M1B control gate，再拒絕其
未支援機制。模擬以u16 world sequence及離散 tick為主軸；RuntimeTimeModel
以M1B正式 cadence中位數校準，預設時間長度UNKNOWN，不要求Unix timestamp。

目前：tick前進／wrap、普通生產（本方／敵方已知owner、morale旗標、Single
Ruler優先及capacity）、當前路段移動，顯式可見來源行動的本機launch模型。
有明確terminal情境時可處理有限友方不溢位增援及空中立塔探索／ownership。
後兩項目前只有參考／合成驗證，不宣稱live到達正確率。永久force ID不參與
模擬，force比較採owner/current segment/composition/progress multiset。

未支援：active upgrade／EMP、special force／production、mobile overflow decay、
neutral downgrade、未知加速接近抵達、未知post-arrival path、相向部隊戰鬥、
普通敵方戰鬥／死亡後全域elimination、動態morale aura與供應線。各項明確
UNSUPPORTED_STATE／NOT_READY，不靜默忽略，不列為accuracy成功。

## 第一批真實差分

440個獨立one-tick「完整可觀察輸入」案例，440/440吻合；283production、
157movement。來自fe678ebb30ce（302/302）及03d032d57e5b（138/138），
原始SHA與所有排除計數見V2_M2A_DIFFERENTIAL.json。本機小型轉移corpus保存
原state序號、输入、預測與實際，source manifest固定；原始大型檔gitignored。

選取同epoch、相鄰單tick、同可見集合與已知最小輸入；owner/type/delay/aura
變化、force birth／arrival未有可觀察行動紀錄時排除為外部或未支援事件。
比較兵數不作選樣条件；全部不吻合仍記錄。重複tick輪詢與沒有任何生產／
移動事件的state不列case。沒有把一座塔的十兵種當十個完整transition。
固定morale／無新外部行動是顯式情境，不宣稱隱藏對手沒有行動。

這是development corpus與有限支援範圍結果，不是正式M2 PASS；normal combat、
arrival／capture與king方向的live驗證、1,000獨立case、100多事件軌跡及效能Gate
仍未完成。接著使用新的正式資料做獨立驗證，不因ordinary樣本不足停止。

## Production phase：公開假設→正式來源→真實比較

公開common/src/chunk.rs以chunk的x/y組合u16加world tick；本輪定位正式
WASM `0x1a449` world.tick load、`0x1a459` chunk ID load、`0x1a4a0..1a4aa`
加總及u16mask，再由`0x1a676..1a69b`按morale調整period並取餘。
生成呼叫`0x1a6a0..1a6b9` add_inner(2,overflow=false)並減去added-1，保留
每次最多1個淨生成；delay在`0x1a619..1a627`單步減1且當tick不生成。
因此phase=(next_world_sequence+(tower_x>>4)+((tower_y>>4)<<8))&65535，
並非為了配合corpus任意調參。440差分驗證支持目前普通生產／移動分支。

純地面damage／field另已離線核對正式Unit::damage、Unit::field，0/4/5/9
兵種surface damage為1/3/1/1；這只驗證純scalar，不等於fight順序或live戰鬥。

55項v2回歸通過。完整世界轉移已profile；正確支援範圍先驗證，profile後才
考慮將熱迴圈移至Rust或C++，不碰GPU／CUDA。

## 平行施工審核 checkpoint

CURRENT MILESTONE: M2A。STATUS: IN_PROGRESS。M2 Gate 尚未通過。

SUBAGENTS USED: 3，均以 `gpt-6-luna / high` 明確派工；模型身分只記錄
工具設定，不把子代理自述的泛用人格當成模型證據。

- arrival_review：唯讀抵達／增援與production/movement紅隊；接受Single/Many
  invariant、overflow順序和production供應線風險。含Shield的探索與友方overflow
  是待驗證候選，尚未擴大正式支援。
- combat_review：唯讀普通戰鬥與morale dataflow；接受固定版 `0xffab8..0xffb52`
  的morale advantage及 `0x1acda..0x1ad06` signed初始damage差異。
  拒絕把舊公開zero-start fight提升為正式combat authority。Sol親自找到
  aggregate i32寫入scratch308..311：Force+21正是scratch309，退回子代理
  「previous iterator Tower旗標」錯誤判讀，取得更正；Shield enum0不計入
  morale headcount。候選signed bonus已整合，ground flag預設仍OFF。
- corpus_candidates：新工具唯讀資料採礦；首版EOF漏最後完整pair且9471語意過寬，
  退回REWORK，修正後接受為候選發現工具。9475次tick-group比較，7099個
  同scope相鄰完整可見eligible pair，300筆候選；後驗推導的情境輸入不能當
  獨立accuracy案例。根代理重跑並檢查counts、輸入SHA與uncertainty標記。

SOL DIRECT WORK：親讀固定WASM `0x1a570..0x1a5f4` owned120/neutral40
decay、capacity比較、subtract1及Projector mobile分支；實作immobile Shield
overflow decay與保留超量生產。補上Single/Many invariant，保留特殊靜止庫存，
拒絕其production/dispatch/combat。production接近mobile容量可能觸發供應線時
回報PRODUCTION_SUPPLY_LINE。修正launch在world tick後建立progress0，普通
觀測的兩筆enemy birth與公開tick_before/after_inputs是順序證據，不將後驗
重建的opponent action當獨立驗證。自己實作差分、完整profile及不重置中間
狀態的5秒trajectory工具；按profile消除未變塔兵數複製與重複movement規則計算。

DIFFERENTIAL RESULTS：開發集868/868，295production、573movement；新未用於
語義調參的600秒holdout `85391858b5d8` 338/338，105production、233movement。
合計1206個獨立完整one-tick案例，限定目前支援範圍；零吻合案例的第一批
holdout `daf86d0544b7` 原試驗存於runtime/m2a-daf-first-holdout-zero.json，
由其unsupported資料修規則後已明確改列development。供應線保護使先前
1007開發案例下降為868，未把排除列成accuracy成功。

SUPPORTED：known production/current-leg movement、owned immobile Shield overflow
decay、靜止特殊庫存原樣保留、explicit local launch與有限terminal參考情境。
UNSUPPORTED：普通戰鬥正式驗證、king death/elimination、動態morale、未知
future path、unknown supply-line觸發、special production/movement及複雜事件。
Single tuple與固定相位皆有新回歸；舊M1三份FAIL文件無diff。

TRAJECTORIES：四個cohort目前1條完整5秒多事件鏈吻合；12處中間差異全部留存，
逐筆檢查均有observed force birth（預測force數較少），無記錄的opponent
inputs尚未納入。不能據此宣告100條Gate通過。所有中間world state完整比較，
不重置成canonical，不把單tick串接冒充rollout。

PERFORMANCE：首次493case約19212完整transitions/sec；守住供應線後868case
約28956/sec；profile導向Python改善後曾約49296/sec，fuel保護後約44302/sec，
99820個完整step涵蓋
全可見塔與forces，先逐筆驗證完整輸出，再量測；pure movement cache由
驗證預熱，非冷啟動效能；
conversion/IO未含在timing中。最新profile見V2_M2A_PERFORMANCE.json。
尚未宣告50000/sec Gate通過。已查PATH及有限常見位置，無native compiler。

最後三次持續量測各100688個完整轉移：51403、48663、50409/sec，中位數
50409/sec。低於門檻的trial仍完整保留；目前只是支援範圍效能證據，不能
把中位數略過50000當成combat、trajectory或正式M2 Gate全部通過。

GROUND CANDIDATE：初次869個candidate cases中868吻合，僅比正式範圍新增
1個defense event，該event不吻合：daf cohort序號125、tick23737，進攻4Soldier，
防守Shield20+Soldier12且morale True，預測Shield20、實際19。保留整體state
差異與原始refs，不能用868個production/movement成功沖淡這唯一combat失敗。
正式DIFFERENTIAL與HOLDOUT維持ground OFF；hypothesis使用獨立輸出檔。

真正阻塞：目前無；普通bug、樣本量和效能不足仍是施工項目。

抵達額外保護：canonical force fuel仍UNKNOWN，不把terminal情境當fuel證明。
合併／探索前拒絕UNKNOWN_ARRIVAL_FUEL與EXPIRED_ARRIVAL；防守摧毀進攻force
先於expiry分支，不要求未知future route/fuel。Sol定位固定Chunk::apply_0
`0x7d849..0x7d875` Force記錄scratch80及+23 fuel150；本機新建非boost部隊
使用此已知值，來源morale True的launch在flag初始化驗證前UNSUPPORTED。
NEXT PARALLEL PLAN：Sol整合combat side/flag與完整轉移；Luna唯讀解析morale
caller、採礦arrival/defense與紅隊驗證。M2未PASS前不進M3、不重開timestamp。
