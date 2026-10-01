# M1B — Control-Relevant State Gate

OLD M1: FAIL（不改寫）。NEW M1B: PASS。2026-10-01 Asia/Taipei。
開始版本 `2bc15a59234cced9423dc220cfc9cca5f5825eff`，唯一分支 v2-rebuild。
M1B 是狀態取得能力關卡，不保證每份部分觀察都可決策；個別 state 必須通過
`control_readiness_gaps`，M2 還必須通過其 supported-mechanics 轉換。

## 為何改用相對節拍

使用者的新指令明確解除「每份 Game 的生成 timestamp」前置 Gate。
這是新控制模型，沒有將舊 M1 的失敗改成成功。三份舊停止文件原樣保留。
絕對伺服器時間、傳輸前排隊延遲、精確 launch time 仍 UNKNOWN。

OPEN-SOURCE CONFIRMED，Kiomet 參考 commit
`d3f0956f27f48f6cac9ac9991f948fa7f90ba77c`（本機 vendor 原碼已核對）：

- [common/src/protocol.rs](https://github.com/SoftbearStudios/kiomet/blob/d3f0956f27f48f6cac9ac9991f948fa7f90ba77c/common/src/protocol.rs)：Update 包含 actor_update／non_actor。
- [common/src/ticks.rs](https://github.com/SoftbearStudios/kiomet/blob/d3f0956f27f48f6cac9ac9991f948fa7f90ba77c/common/src/ticks.rs)：GenTicks<4>。
- [common/src/singleton.rs](https://github.com/SoftbearStudios/kiomet/blob/d3f0956f27f48f6cac9ac9991f948fa7f90ba77c/common/src/singleton.rs)、common/src/world.rs：Singleton.tick／tick.next()。
- [server/src/service.rs](https://github.com/SoftbearStudios/kiomet/blob/d3f0956f27f48f6cac9ac9991f948fa7f90ba77c/server/src/service.rs)：無事件仍傳更新供 time-keeping。
- [client/src/state.rs](https://github.com/SoftbearStudios/kiomet/blob/d3f0956f27f48f6cac9ac9991f948fa7f90ba77c/client/src/state.rs)、client/src/game.rs：套用後修正 time_since_last_tick，每畫面累加 elapsed_seconds，供部隊插值。

先前公開 Kodiak 審查的固定版本 `83f62d2aacd94647dbc97d1bd4764fbfc17cdf55`：
[common/src/protocol/updates.rs](https://github.com/SoftbearStudios/kodiak/blob/83f62d2aacd94647dbc97d1bd4764fbfc17cdf55/common/src/protocol/updates.rs)
的 CommonUpdate::Game(GU)、SessionCreated.date_created；actor_model 的 define_world
生成 ActorUpdate；[server/src/socket/socket.rs](https://github.com/SoftbearStudios/kodiak/blob/83f62d2aacd94647dbc97d1bd4764fbfc17cdf55/server/src/socket/socket.rs)
直接 encode 訊息。沿用使用者公開審查與舊 M1 來源記錄；本輪網頁重取未成功，
沒有宣稱重新取得或核對最新遠端內容。

以上不是 2026 正式版完整等價證明。LIVE OBSERVED：固定正式 WASM
`fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c` 的網路
World.Singleton u16 序號與來源行為已實測。WORKING ASSUMPTION：其離散世界順序
與本機插值是控制時間基礎；若出現相反正式證據立即重新評估。

## Gate review

| 條件 | 結論與有限證據 |
|---|---|
| World order | PASS：直接序號與正常推進；u16 modulo 前進辨識 wrap，倒退／半圈歧義撤銷 epoch；重複輪詢不刷新 first observation。wrap 邊界為合成回歸，不假稱 live wrap。 |
| Rate | PASS：重用三段約600秒的 fe678ebb30ce／03d032d57e5b／f3f22dae0791，7.993／7.944／6.673 Hz。 |
| Extraction latency | PASS：上述 p95 8.248／7.745／6.998 ms；新版60秒短確認 p95 10.964 ms，低於25 ms。 |
| 三段安全長測 | PASS：新 serialization 有限重讀全部 4,797／4,767／4,004 筆，版本／NETWORK、正向 actor visibility、十兵種、合法端點、順序、unknown epoch 不復用 ID 均零已知違例。這是舊 live 資料離線核對，不新增 live 樣本。 |
| Isolation | PASS：既有真實 RESULT→MENU→JOINING→IN_MATCH、reload 舊 reader 拒絕、新 document／epoch、offline／reconnect 與 HTTP fallback；來源自然停滯1,062 ms撤銷 ID。現行更保守的倒退檢查另有回歸。 |
| Visibility safety | PASS 安全門控／PARTIAL 真實 sensor cycle：正式正向 refs 才讀 actor；Node 的受監測 synthetic memory 證明 hidden payload 未讀、dirty／擴張／offline 拒讀。既有有限 sensor-history 檢查零洩漏；鏡頭 actor 失去／恢復不冒充 sensor cycle。 |
| Critical state | PASS 最小輸入取得能力：fe cohort 有4,723份 M1B可接受 state；剩餘74份拒絕。03d有891份可接受／3,876份拒絕。最後f3f全部4,004份拒絕。沒有丟掉這些 NOT_READY 或以缺失值補零。 |
| UNKNOWN | PASS：未知 None／已知零／已知空集合有獨立語意；不要求永久 force ID、未使用的 timestamp／ranking／future path；缺 owner、current segment、units／progress 仍拒絕。 |

版本相容限於固定正式 client 與安全契約。各舊 observer manifest 原樣保存；
歷史長測不是宣稱新增欄位當時已存在。新60秒只確認新增 observation timing 的
實際行為與成本，不算第四段十分鐘。安全檢查證明的是已取得合法資料邊界，
不是「全部世界資訊完整」或整份 state 100% 正確。

## 本輪實測與時間模型

有限 cadence：fe 2,398 advance events／2,398 steps，249.967 ms/step；03d
2,304 events／2,305 steps，250.142 ms/step；f3f 的已知 epoch 180 events／181
steps，250.348 ms/step。各事件中位數250 ms。M2 RuntimeTimeModel 使用此
live cadence 校準，標 DERIVED；離散 tick 才是主軸，不硬編碼 Unix 時間。

新增 `world_sequence_observed_at_ms` 為目前序號首次 host observation，重複
讀取不更新；`received_at_ms` 是完整擷取完成。ControlTime 明確帶序號、
首次觀察、完成、match_epoch、document、source mode。超過1,000 ms未見
前進、時域錯誤、未知 epoch／非NETWORK／部分覆蓋均 NOT_READY。
1,000 ms 是保守來源連續性政策，不是伺服器年齡或延遲 SLA。

`sampling-0b5d10bffb15`：60.052秒、476份、7.926 Hz；擷取 p95 10.964 ms；
序號首次觀察→完成 p95 189 ms，476筆都有該度量；含1次 dirty 拒讀。
因 coverage／不可见路段，476份全部 NOT_READY，沒有假稱可決策。

獨立 UI 沿用最終inventory：2,147兵數／容量、1,356關係、1,231塔型、
1,314 delay、554前置數、235 disabled、276 lock 各分母一致。
前置 requirement flag 554布林不是完整需求數值；ALLY與特殊兵種仍 PARTIAL。
部隊既有正常 getter 十兵種組成、速度、進度／位置及 current segment 純規則
有限核對支持最小移動模型；required 30/30僅未加速同距離分支。
缺終點／未驗證抵達及戰鬥規則，在 M2 拒絕，不用永久 ID 補猜。

41項v2回歸與Node隱私邊界通過。原 M1 readiness 不變，新 Gate 在 control.py。
可追溯重用結果與 SHA-256：V2_M1B_EVIDENCE.json；原始大型 runtime 紀錄留本機。

M1B PASS 後提交推送，正式進 M2A。M2A 先做可驗證的相對tick、普通生產、
移動及顯式行動／情境；未驗證特殊兵種、抵達後續路徑、戰鬥／供應線不靜默忽略。
