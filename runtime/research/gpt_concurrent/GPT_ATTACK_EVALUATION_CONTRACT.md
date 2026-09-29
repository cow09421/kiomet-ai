# 攻擊評估契約（僅限已確認子集）

輸入包含來源塔實際可派兵種與數量、敵塔目前守軍、TowerType、攻守光環布林快照、擁有者關係與觀測節拍。攻方數量必須是 `Tower::force_units`（可派兵力）結果，不能用塔內總兵數；路徑與伺服器命令接受狀態由行動驗證層另行提供。普通 Force 對 Force（部隊對部隊）可用相同介面，但路徑是否在本節拍相撞必須由呼叫端先確認。

將有效資料交給 `battle_mirror_partial.py`。回傳 `PARTIAL_RESULT` 時可讀 `winner`、攻守殘兵與預期新塔主；Force 對 Force 結果的 `new_owner_relation` 為 `not_applicable`。`UNSUPPORTED_CASE` 時不得把結果換算成勝／負或兵力差。只支持普通非空守塔戰及普通 Force 對 Force，含 Shield、六種普通兵與明確的攻守 aura snapshot；不含 Ruler／Shell／EMP／Nuke。中立空塔直佔、己方合併、友盟與抵達後移動分支均不由此契約判定。

普通塔戰已可按靜態對應公式輸出條件式 WIN／LOSE／CONTESTED（攻方勝／守方勝／雙方皆敗）與 owner（塔主）結果；普通 Force 對 Force 可輸出勝者與殘兵。中立空塔的後續容量重整、友軍合併、塔型降級事件與國王淘汰不屬於支援子集。尚未與執行中正式版差分。契約狀態：**普通子集可用，整體 PARTIAL**。
