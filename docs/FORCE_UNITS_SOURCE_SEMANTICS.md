# `Tower::force_units`（塔可派兵力）公開來源語意

更新：2026-09-27。此文件只分析 `vendor/kiomet-ref/` 的公開快照；正式版須另依 `docs/FORCE_UNITS_PRODUCTION_ANALYSIS.md` 核對。

## 輸入與輸出

`common/src/tower.rs` 的 `Tower::force_units(&self) -> Units` 接受一座塔，不接受路徑、目標、玩家或預留策略，回傳**另一個 `Units` 結構**，保存各兵種數量，並非總數。它建立空 `Units`，遍歷 `self.units.iter()` 的所有非零兵種，略過 `!unit.is_mobile(Some(self.tower_type))`，其餘以 `ret.add(unit,count)` 加入結果。`Units` 定義於 `common/src/units.rs`：一個 Shield（護盾）數量與 `Many`（五種常規兵力）或 `Single`（一種特殊兵力）變體。

`common/src/unit.rs` 的 `Unit::speed(tower_type)` 決定是否可移動。Fighter（戰鬥機）、Chopper（直升機）、Bomber（轟炸機）、Shell（砲彈）為 Fast（快）；Nuke（核武）、Tank（坦克）為 Slow（慢）；Soldier（士兵）、Emp（電磁脈衝）、Ruler（國王）為 Normal（一般）。**Shield 只在 `tower_type=None` 或 `Some(Projector)` 時為 Fast；其他塔的 Shield 為 Immobile（不能移動）。** `force_units` 傳入的永遠是 `Some(self.tower_type)`，所以真實塔只有 Projector（投射器）能把 Shield 納入結果。

## 特殊規則與邊界

- **Ruler（國王）不在函式內保留。** 其 `speed=Normal`，因此若在塔的 `Units` 中，`force_units` 會納入。遊戲在其他階段有額外保護：`client/src/game.rs` 的危險路徑拖曳等待 `RULER_DRAG_DELAY`；`common/src/chunk.rs` 的自動補給線部署條件有 `!tower.units.has_ruler()`。這些不是 `force_units` 的過濾條件。
- **Many（多種類）變體**：除一般塔 Shield 外，所有非零常規兵種原量複製。Projector 則連 Shield 也可複製。沒有固定守軍、預留比例或以容量為上限重新扣減的邏輯。
- **Single（單一種類）變體**：來源的 `Units::iter()` 同樣給出非零 Shield 與該特殊兵種；`force_units` 對每個兵種用同一移動性條件。Ruler、Shell、Emp、Nuke 均可移動；Shield 仍只在 Projector 可移動。正式版 Single 實證目前主要是 Ruler，其他特殊兵種須保留驗證層級。
- `Units::available(unit)` 是**目前持有數量**，不是「可派兵量」或「剩餘容量」。`Units::capacity(unit,tower_type)` 在別處計算容量。`ret.add` 的目標是非塔 `Units`，來源數量均為無號 8 位元，正常值不因塔容量而變小。
- `force_units` 本身不讀 `player_id`、聯盟、道路、目的地或升級延遲。是否由己方發送、路徑是否合法、是否改設定補給線、國王拖曳延遲，皆是**呼叫方規則**，不可混成兵力過濾。

## 呼叫與實際扣兵

`client/src/game.rs` 在拖曳預覽與滑鼠放開的路徑中呼叫 `source_tower.force_units()`，用結果的空／非空、最大邊距、是否含 Ruler 決定預覽或送命令；實際 `Command::DeployForce` 仍須通過路徑與玩家條件。`common/src/chunk.rs` 的自然補給線邏輯用 `force_units().max_edge_distance()` 判斷後續部署。`common/src/tower.rs` 的 `take_force_units()` 再對結果的各兵種逐個 `subtract`；`common/src/chunk/event.rs` 的 `Tower::deploy_force()` 用它建立 `Force`（部隊）。這說明「合法可派出組成」與「策略上想保留多少」是兩層不同決策。

## 來源與正式版差異警戒

既有跨局證據顯示正式版 `+45` 與玩家層國王存活及盾容量加成相關，而公開快照 `Units::capacity` 用塔本身是否含國王判斷。因此**不能僅用來源快照推斷正式版所有行為**。`force_units` 的正式版分支須以函式 2031 的反組譯單獨確認；若函式沒有讀 `+45`，這個容量差異不應被混入可派兵量鏡像。
