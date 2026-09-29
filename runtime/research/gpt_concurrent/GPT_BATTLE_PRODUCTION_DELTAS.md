# 正式版相對公開參考碼的戰鬥差異

證據來源：Round 5–7 已抽取的正式版 WASM（網頁組件）反組譯與 `vendor/kiomet-ref`。這份表只寫有證據的差異；`UNKNOWN`（未知）保留為未知。

| 正式版函式／分支 | 參考碼 | 正式版變化 | 對戰鬥的影響 | 信心 |
|---|---|---|---|---|
| `1778 Combatants::morale_advantage`；由 `448`、`522` 呼叫 | `combatants.rs` 初始累積值固定 0，沒有士氣 helper | 新增 `min(3, floor(non-single-use unit count/2))` | 依排他光環把單一 signed i32 accumulator 初始化為攻方正值或守方負值；不是傷害倍率 | 高；逐指令可見 |
| `448:0x01a4e7..0x01a561`、`1791:0x1004a9..0x1004b0`、Force `+21`／Tower `+45` | 參考 Tower／Force 沒有這些戰鬥 aura 欄位 | 依擁有者國王位置同塔／鄰塔週期更新 Tower 布林旗標，派兵時複製給 Force | 改士氣條件；同一 Force 旗標也改變進度需求 | 高；玩家位置伺服器來源仍未知 |
| `2689 Force::progress_required` | `force.rs` 依距離算需求值 | 旗標 1 時需求值約乘 4/5 並取整 | 有旗標的部隊更快移動；與勝負傷害公式分開 | 高 |
| `2022` 與 `2970` | 參考碼使用同一兵種基本傷害與 TowerType 遠程規則 | 正式版 `2022` 加入前一累積值檢查；Nuke 無限傷害在反向累積跨越有號半範圍時上限 1000 | 防止無限傷害讓 signed accumulator 溢位；普通單位 damage table 對齊 | 高；精確 guard 見算術文件 |
| `448`／`522` 內聯戰鬥 terminal block | 參考 `Combatants::fight` 明列終端剩兵和勝者規則 | Round 8 已將存活、塔方平手規則、塔主轉換及 522 回寫旗標逐段對上 | 普通 Force-vs-Tower 與 Force-vs-Force 可靜態預測勝者／殘兵；未與執行中 Production 差分 | 高；靜態對應 |
| `1347`／`1348` single-use 與 Ruler 回呼 | 參考碼明確記錄 EMP、核爆、砲彈爆炸與失去國王事件 | 一次性旗標、立即扣除、last-unit、Ruler 擊殺者、1943 事件轉換與 EMP 塔延遲已對上 | 特殊單位局部效果可描述；鏡像仍拒絕特殊輸入，Ruler 的事件消費後玩家狀態不在戰鬥函式 | 高；局部回呼，外部玩家後果部分 |
| `4969` Shield 準備 | 參考碼 `hack`：只清除攻塔部隊的 Shield | 正式版以 TowerType sentinel 27 區分 Force；真 Tower 型別呼叫時從 Force 單位移除 Shield | 進士氣與戰鬥迴圈前就生效；塔盾保留 | 高 |
| `3571`／`3107` 所有權寫回／重整 | 參考 `chunk.rs` 戰後設主並 reconcile | `3571` 塔主寫回；`3107` 用於中立空塔直佔；敵方佔領不自動 reconcile | 攻方勝換主、守方勝保留、無勝者清空；無主時降塔型／清延遲 | 高；分支用途已對上 |
| `732` 容量表 | 參考 TowerType 容量資料 | 正式版資料段有 22×10 個 u32，22/22 列數值與參考碼相符 | 供 Tower 單位 Air/Surface overflow 判斷和併兵容量 | 表值高；正式版動態特殊塔分支未全追 |

Production battle graph（正式版戰鬥呼叫圖）沒有發現亂數呼叫。尚未確認「為何加入士氣／旗標」的設計理由；本文件不把程式效果冒充設計意圖。
