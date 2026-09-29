# Force（移動部隊）來源語意

證據來源：`vendor/kiomet-ref/common/src/force.rs`、`tower.rs`、`chunk.rs`、`chunk/event.rs`、`client/src/game.rs`。這些是公開來源；實際記憶體偏移另以正式版 WebAssembly（網頁組合語言）核對。

1. `Tower::deploy_force`（塔派兵）從塔取出 Units（兵力），建立 Force，再由 `send_force`（送出部隊）產生兩個事件：來源塔的 outbound（出站）鏡像與目的塔的 inbound（入站）主體。`ChunkEvent::AddInboundForce`（新增入站部隊事件）將主體加入目的塔；出站鏡像則由事件處理器加入來源塔。
2. `Force` 保存完整 `Path`（路徑）、`path_progress`（當前路段進度）、`fuel`（剩餘燃料／續航）、可空的 `player_id`（玩家編號）及 7 位元組 `Units`（兵力）。來源結構**沒有**獨立 Force ID（部隊編號）、固定世界座標、起始節拍或抵達節拍。
3. `Path::new`（建立路徑）反轉輸入。路徑最後一格是當前來源塔，倒數第二格是當前目的塔，第一格是最終目的塔。抵達一段時 `pop`（移除末格），因此路徑仍保留未走完的完整序列；不另存路段索引。
4. 每個 tick（更新節拍）增加速度值 1、2 或 3；來源碼以每秒 4 節拍計。達到該路段 `progress_required`（所需進度）後，進站部隊進入塔與部隊的戰鬥／合併／續行處理；出站鏡像到達時直接移除。`try_move_on`（嘗試續行）可重設進度、耗用續航，並在補給線／同盟情況下改變路徑或擁有者。
5. 每段世界座標由目前來源塔與目的塔座標線性內插。內插比例為 `min(1, (progress + time_since_tick * 4 * speed) / required)`。`required` 取決於塔間距離，正式版另有 `Force+21` 的 4/5 減時分支。
6. 用戶端渲染會遍歷入站部隊，並按可見性條件遍歷出站部隊。同一支實體移動部隊可能同時有兩個鏡像；觀察器必須去重。

來源碼只能證明語意，不能單獨證明正式版欄位順序、指標或根路徑。
