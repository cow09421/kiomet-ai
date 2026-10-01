# M2A — minimum deterministic world simulator

STATUS: PARTIAL，持續施工。M1B PASS checkpoint `2212346`；OLD M1 FAIL 原樣保留。

`src/kiomet_ai/v2/sim/` 新 Python reference core，沒有延伸舊 simulate.py。
Canonical→compact SimulationState 轉換先通過 M1B control gate，再拒絕其
未支援機制。模擬以u16 world sequence及離散 tick為主軸；RuntimeTimeModel
以M1B正式 cadence中位數校準，預設時間長度UNKNOWN，不要求Unix timestamp。

目前：tick前進／wrap、普通生產（本方／敵方已知owner、morale旗標、Single
Ruler優先及capacity）、當前路段移動，顯式可見來源行動的本機launch模型。
有明確terminal情境時可處理有限友方不溢位增援及空中立塔探索／ownership。
後兩項目前只有參考／合成驗證，不宣稱live到達正確率。永久force ID不參與
模擬，force比較採owner/current segment/composition/progress multiset。

未支援：active upgrade／EMP、special units／production、overflow／定期decay、
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

46項v2回歸通過。尚未公布Transitions/sec；正確支援範圍先驗證，profile後才
考慮將熱迴圈移至Rust或C++，不碰GPU／CUDA。
