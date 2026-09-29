"""Real observer core（真實觀察器核心）：MatchObservation 快照＋新鮮度門控。

唯讀資料結構，不碰瀏覽器、不發送。所有未知欄位為 UNKNOWN（None），
絕不用 0 代替。舊 match 的資料一律視為 STALE（陳舊），不得餵給
Dry Run／Planner／Executor。
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kiomet_ai.force_units import DeployableForce

UNKNOWN = None
# 新鮮度門檻（秒）：觀察超過此年齡視為 STALE。
FRESHNESS_LIMIT_S = 30.0


def _observation_age(timestamp, now: float | None = None) -> float | None:
    """Return age only when both clock values are finite and causal."""
    now = time.time() if now is None else now
    if (type(timestamp) not in (int, float)
            or type(now) not in (int, float)):
        return None
    try:
        if not math.isfinite(timestamp) or not math.isfinite(now):
            return None
        if timestamp > now:
            return None
        age = now - timestamp
        if not math.isfinite(age):
            return None
    except (OverflowError, TypeError):
        return None
    return float(age)

# 所有權（Owner）正式列舉。ALLY／ENEMY 語意來自公開來源
# client/src/color.rs（Blue=0 自身、Gray=1 中立、Purple=2 盟友、Red=3 敵方）；
# 其中 2=ALLY 尚無本局 Runtime／Vision 樣本，標 SOURCE_VERIFIED。
OWNER_SELF = "SELF"
OWNER_NEUTRAL = "NEUTRAL"
OWNER_ALLY = "ALLY"
OWNER_ENEMY = "ENEMY"
# 相容舊研究工具輸出；新分類一律用 ALLY／ENEMY，不再產生 OTHER。
OWNER_OTHER = "OTHER"

# 兵力種類（Units Kind）。SINGLE 目前只有結構證據，UI 配對不足，
# 一律視為 CANDIDATE（候選），不得升 PASS。
UNITS_KIND_MANY = "MANY"
UNITS_KIND_SINGLE = "SINGLE"
UNITS_KIND_UNKNOWN = "UNKNOWN"

# Unit 列舉（公開來源 common/src/unit.rs），供 Single 型對照。
UNIT_NAMES = ["Shield", "Fighter", "Chopper", "Bomber", "Tank",
              "Soldier", "Shell", "Emp", "Nuke", "Ruler"]

# TowerType（塔種類，公開來源 common/src/tower.rs enum 順序）。
# +46 值＝enum 序號：7 型由 GPT 30 筆 UI 真值驗證（懸崖 7、兵營 3、
# 砲兵陣地 2、軍械庫 1、跑道 22、發電機 10、採石場 16）；
# 4 型由新局 m1-1790506322 spot-check 自然驗證（工廠 9、壁壘 18、
# 預警系統 8、礦場 14）；2 型由 m1-1790523816 自然驗證
# （村莊 26、總部 11）。其餘型別為來源順序推斷 CANDIDATE。
TOWER_TYPES = [
    "Airfield", "Armory", "Artillery", "Barracks", "Bunker",
    "Centrifuge", "City", "Cliff", "Ews", "Factory",
    "Generator", "Headquarters", "Helipad", "Launcher", "Mine",
    "Projector", "Quarry", "Radar", "Rampart", "Reactor",
    "Refinery", "Rocket", "Runway", "Satellite", "Silo",
    "Town", "Village",
]
# 中文 UI 塔名→enum。前 7 型由 GPT 30 筆真值驗證；工廠／壁壘／
# 預警系統／礦場由 m1-1790506322 自然驗證；村莊（×2）／總部由
# m1-1790523816 自然驗證。升級前置列（工廠=0/2 等）不是兵力列，
# UI 比對必須用兵種詞彙過濾（見 spot_check_units）。
TOWER_TYPE_ZH = {
    "跑道": "Runway", "兵營": "Barracks", "砲兵陣地": "Artillery",
    "軍械庫": "Armory", "發電機": "Generator", "懸崖": "Cliff",
    "採石場": "Quarry",
    "工廠": "Factory", "壁壘": "Rampart", "預警系統": "Ews", "礦場": "Mine",
    "村莊": "Village", "總部": "Headquarters",
    "機場": "Airfield", "發射井": "Silo", "反應爐": "Reactor",
}
# tower_ref 基準的 TowerType 偏移（Units 結構 +38..+44 緊接之後）。
TOWER_TYPE_OFFSET = 46
# tower_ref +45：擁有者國王旗標。跨多局驗證：
# +45=1 ⟺ 盾容量顯示 raw+10。m1-1790539798 出現同玩家雙塔
# 分歧（Factory 0／Runway 1，UI 10/10 vs 10/15），證實為
# per-tower（逐塔）語意；國王可在 Many 塔駐守提供加成，
# 不必轉為 Single。實體欄位身分仍為候選詮釋。
OWNER_RULER_FLAG_OFFSET = 45
# Tower::RULER_SHIELD_BOOST（來源常數，UI 已驗證其效果）。
RULER_SHIELD_BOOST = 10
# 來源 #[capacity] 原始容量表（vendor/kiomet-ref common/src/tower.rs）。
# 盾容量＝raw＋(10 if +45=1)；非盾容量＝raw。此推導規則經
# m1-1790487672 與 m1-1790506322 兩局 UI 分母全量驗證
# （覆蓋 Shield／Fighter／Soldier／Tank；其餘兵種為來源推導）。
TOWER_TYPE_RAW_CAPACITY = {
    "Airfield": {"Fighter": 4, "Bomber": 4, "Soldier": 4, "Tank": 3, "Shield": 10},
    "Armory": {"Soldier": 4, "Tank": 5, "Shield": 15},
    "Artillery": {"Shell": 3, "Shield": 20},
    "Barracks": {"Soldier": 12, "Tank": 2, "Shield": 10},
    "Bunker": {"Soldier": 6, "Shield": 40},
    "Centrifuge": {"Soldier": 4, "Tank": 2, "Shield": 15},
    "City": {"Fighter": 2, "Soldier": 6, "Tank": 2, "Shield": 15},
    "Cliff": {"Soldier": 4, "Tank": 2, "Shield": 30},
    "Ews": {"Soldier": 4, "Tank": 2, "Shield": 15},
    "Factory": {"Soldier": 4, "Tank": 2, "Shield": 10},
    "Generator": {"Soldier": 4, "Tank": 2, "Shield": 10},
    "Headquarters": {"Soldier": 8, "Tank": 2, "Shield": 40},
    "Helipad": {"Chopper": 3, "Soldier": 4, "Tank": 2, "Shield": 15},
    "Launcher": {"Emp": 1, "Shield": 15},
    "Mine": {"Soldier": 4, "Tank": 2, "Shield": 15},
    "Projector": {"Soldier": 4, "Tank": 2, "Shield": 10},
    "Quarry": {"Soldier": 6, "Tank": 2, "Shield": 10},
    "Radar": {"Soldier": 4, "Tank": 2, "Shield": 10},
    "Rampart": {"Soldier": 8, "Shield": 45},
    "Reactor": {"Soldier": 4, "Tank": 2, "Shield": 10},
    "Refinery": {"Soldier": 4, "Tank": 2, "Shield": 5},
    "Rocket": {"Soldier": 4, "Tank": 2, "Shield": 15},
    "Runway": {"Fighter": 4, "Soldier": 4, "Tank": 2, "Shield": 5},
    "Satellite": {"Soldier": 4, "Tank": 2, "Shield": 15},
    "Silo": {"Nuke": 1, "Soldier": 4, "Tank": 1, "Shield": 20},
    "Town": {"Fighter": 1, "Soldier": 4, "Tank": 1, "Shield": 10},
    "Village": {"Soldier": 4, "Shield": 5},
}


def decode_owner_ruler_flag(struct_bytes) -> bool | None:
    """+45 國王旗標：True=有活著的 Ruler、False=無。過短回 UNKNOWN。"""
    raw = list(struct_bytes)
    if len(raw) <= OWNER_RULER_FLAG_OFFSET:
        return None
    return raw[OWNER_RULER_FLAG_OFFSET] == 1


def unit_capacity(unit_name: str, tower_type: str | None,
                  owner_has_ruler: bool | None) -> int | None:
    """推導容量：raw＋盾的國王加成。未知型別／未知旗標回 UNKNOWN。

    驗證狀態：推導規則經兩局 UI 全量驗證（Shield／Fighter／
    Soldier／Tank）；其餘兵種為來源推導（SOURCE_DERIVED）。
    """
    if not tower_type:
        return None
    table = TOWER_TYPE_RAW_CAPACITY.get(tower_type)
    if table is None:
        return None
    raw_cap = table.get(unit_name, 0)
    if unit_name == "Shield":
        if owner_has_ruler is None:
            return None
        return raw_cap + (RULER_SHIELD_BOOST if owner_has_ruler else 0)
    return raw_cap


def decode_tower_type(struct_bytes) -> str | None:
    """由塔結構原始位元組解出 TowerType 名；越界或過短回 UNKNOWN（None）。"""
    raw = list(struct_bytes)
    if len(raw) <= TOWER_TYPE_OFFSET:
        return None
    value = raw[TOWER_TYPE_OFFSET]
    if 0 <= value < len(TOWER_TYPES):
        return TOWER_TYPES[value]
    return None

# 已驗證的 Production WASM（正式網頁組件）雜湊；版本不同禁止沿用偏移。
UNITS_PRODUCTION_WASM_SHA256 = (
    "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c")
# tower_ref 基準的 Units 結構起點；全部 unsigned 8-bit（無號 8 位元）。
UNITS_STRUCT_BASE = 38


def classify_owner(render_color: int | None) -> str | None:
    """render_color（渲染顏色值）→正式 Owner。未知值回 UNKNOWN（None）。

    0=SELF（Runtime＋Vision HIGH）、1=NEUTRAL（Runtime 15 塔 STRONG）、
    2=ALLY（來源明確、執行期未驗證）、3=ENEMY（Runtime 7 塔 STRONG）。
    UNKNOWN 永不自動升 SELF。
    """
    return {0: OWNER_SELF, 1: OWNER_NEUTRAL,
            2: OWNER_ALLY, 3: OWNER_ENEMY}.get(render_color)


@dataclass(frozen=True)
class TowerUnitCounts:
    """單塔目前兵力（Current Counts）。注意：不是可派兵量！

    deployable_units（可派兵量）在 Tower::force_units 未驗證前永遠 UNKNOWN，
    故本結構不設該欄位，Planner（規劃器）不得用各欄位加總當可派兵量。
    Single 型為 CANDIDATE（候選），UI 配對完成前不得當 PASS 使用。
    """
    tower_ref: int | None = None
    observed_at: float | None = None
    units_kind: str = UNITS_KIND_UNKNOWN       # MANY / SINGLE / UNKNOWN
    fighter: int | None = None
    chopper: int | None = None
    bomber: int | None = None
    tank: int | None = None
    soldier: int | None = None
    shield: int | None = None
    single_unit_type: str | None = None        # Single 型才有
    single_count: int | None = None            # Single 型才有

    def age(self, now: float | None = None) -> float | None:
        if self.observed_at is None:
            return None
        now = time.time() if now is None else now
        return max(0.0, now - self.observed_at)


def decode_tower_units(struct_bytes, tower_ref: int | None = None,
                       observed_at: float | None = None) -> TowerUnitCounts:
    """由塔結構原始位元組解出 TowerUnitCounts（純函式，不碰瀏覽器）。

    struct_bytes 至少 45 位元組；以 UNITS_STRUCT_BASE=+38 為 Units 起點。
    未知 tag 拋錯；Single 結構非法則回整筆 UNKNOWN（寬容，不崩觀察器）。
    """
    raw = list(struct_bytes)
    if len(raw) < UNITS_STRUCT_BASE + 7:
        raise ValueError(f"塔結構長度不足：{len(raw)}")
    tag, a, b, c, d, e, shield = raw[UNITS_STRUCT_BASE:UNITS_STRUCT_BASE + 7]
    base = dict(tower_ref=tower_ref, observed_at=observed_at, shield=shield)
    if tag == 0:
        return TowerUnitCounts(units_kind=UNITS_KIND_MANY, fighter=a,
                               chopper=b, bomber=c, tank=d, soldier=e, **base)
    if tag == 1:
        if a > 0 and 0 <= b < len(UNIT_NAMES):
            return TowerUnitCounts(units_kind=UNITS_KIND_SINGLE,
                                   single_unit_type=UNIT_NAMES[b],
                                   single_count=a, **base)
        return TowerUnitCounts(tower_ref=tower_ref, observed_at=observed_at,
                               shield=shield)
    raise ValueError(f"未知 UnitsEither 標籤：{tag}")


@dataclass(frozen=True)
class ObservedTower:
    tower_id: int | None = None          # packed_id
    tower_ref: int | None = None
    world_x: float | None = None
    world_y: float | None = None
    screen_x: float | None = None
    screen_y: float | None = None
    owner: str | None = None             # SELF / NEUTRAL / ALLY / ENEMY / UNKNOWN(None)
    owner_confidence: str = "UNKNOWN"    # LOW / MEDIUM / HIGH / UNKNOWN
    owner_ruler: bool | None = None      # +45 國王旗標：擁有者有活著 Ruler
    tower_type: str | None = None
    units: int | None = None             # 舊欄位保留相容；新程式用 units_detail
    units_detail: TowerUnitCounts | None = None  # 目前兵力≠可派兵量
    upgrade_state: str | None = None


@dataclass(frozen=True)
class ObservedEdge:
    source: int
    target: int


@dataclass(frozen=True)
class MatchObservation:
    match_id: str | None
    timestamp: float
    camera: dict = field(default_factory=dict)
    viewport: dict = field(default_factory=dict)
    dpr: float | None = None
    towers: tuple = ()
    edges: tuple = ()
    forces: tuple = ()

    def age(self, now: float | None = None) -> float | None:
        return _observation_age(self.timestamp, now)

    def freshness(self, current_match_id: str | None,
                  now: float | None = None) -> str:
        """FRESH／STALE／UNKNOWN。舊局一律 STALE；超齡 STALE。"""
        if not self.match_id or not current_match_id:
            return "UNKNOWN"
        if self.match_id != current_match_id:
            return "STALE"
        age = self.age(now)
        if age is None:
            return "UNKNOWN"
        if age > FRESHNESS_LIMIT_S:
            return "STALE"
        return "FRESH"

    def tower(self, tower_id: int) -> ObservedTower | None:
        return next((t for t in self.towers if t.tower_id == tower_id), None)


def build_snapshot(match_id: str, camera: dict, view_meta: dict, dpr: float,
                   anchor_towers: list, anchor_edges: list,
                   screen_map: dict | None = None,
                   timestamp: float | None = None) -> MatchObservation:
    """由錨點塔＋屏座標映射建快照。screen_map 缺項的塔 screen 為 UNKNOWN。"""
    screen_map = screen_map or {}
    towers = []
    for t in anchor_towers:
        pid = t.get("packed_id")
        pos = t.get("position") or [None, None]
        screen = screen_map.get(pid, (None, None))
        towers.append(ObservedTower(
            tower_id=pid, tower_ref=t.get("tower_ref"),
            world_x=pos[0], world_y=pos[1],
            screen_x=screen[0], screen_y=screen[1],
            owner=t.get("owner") if t.get("owner") in (
                "SELF", "NEUTRAL", "ALLY", "ENEMY", "OTHER") else None,
            owner_confidence="UNKNOWN",
            owner_ruler=t.get("owner_ruler"),
            tower_type=t.get("tower_type"), units=t.get("units"),
            upgrade_state=t.get("upgrade_state")))
    edges = tuple(ObservedEdge(a, b) for a, b in anchor_edges
                  if isinstance(a, int) and isinstance(b, int))
    return MatchObservation(
        match_id=match_id, timestamp=time.time() if timestamp is None else timestamp,
        camera=dict(camera), viewport=dict(view_meta), dpr=dpr,
        towers=tuple(towers), edges=edges, forces=())


def gate_check(observation: MatchObservation, current_match_id: str | None,
               now: float | None = None) -> tuple[bool, str]:
    """Dry Run／Planner／Executor 共用門：非 FRESH 一律拒絕。"""
    freshness = observation.freshness(current_match_id, now)
    if freshness != "FRESH":
        return False, f"拒絕：觀察為 {freshness}（非 FRESH 不可用）"
    return True, "FRESH"


@dataclass(frozen=True)
class RealTowerState:
    """正式資料契約：單塔完整狀態（組合自 MatchObservation＋鄰居）。

    deployable_units（舊整數欄位）不適合逐兵種結果，一律 UNKNOWN（None）。
    deployable_force 只在 Many 目前數量完整時標 DERIVED（推導）；
    Single 輸入與正式輸出仍缺獨立核對。upgrade_state（升級狀態）亦未知。
    neighbors（鄰居）僅含已觀察到的塔；缺證據不等於沒有鄰居。
    """
    tower_id: int
    match_id: str | None
    timestamp: float
    tower_ref: int | None = None
    world_x: float | None = None
    world_y: float | None = None
    screen_x: float | None = None
    screen_y: float | None = None
    owner: str | None = None             # SELF/NEUTRAL/ALLY/ENEMY/UNKNOWN(None)
    owner_confidence: str = "UNKNOWN"
    owner_ruler: bool | None = None      # +45 國王旗標（容量推導用）
    tower_type: str | None = None
    units_kind: str = UNITS_KIND_UNKNOWN
    unit_counts: TowerUnitCounts | None = None
    deployable_units: int | None = None  # 舊整數欄位，永遠 UNKNOWN
    deployable_force: DeployableForce | None = None  # 逐兵種組成；完整 Many 可標 DERIVED
    deployable_force_confidence: str = "UNKNOWN"
    upgrade_state: str | None = None     # UNKNOWN 直到 UI 真值收集
    neighbors: tuple = ()                # tower_id tuple

    def age(self, now: float | None = None) -> float | None:
        return _observation_age(self.timestamp, now)

    def freshness(self, current_match_id: str | None,
                  now: float | None = None) -> str:
        if not self.match_id or not current_match_id:
            return "UNKNOWN"
        if self.match_id != current_match_id:
            return "STALE"
        age = self.age(now)
        if age is None:
            return "UNKNOWN"
        if age > FRESHNESS_LIMIT_S:
            return "STALE"
        return "FRESH"


def build_real_tower_states(observation: MatchObservation) -> tuple:
    """由 MatchObservation 組出每塔 RealTowerState（含鄰居表）。

    這是資料層的正式入口：錨點塔、兵力解碼、塔種類與鄰居全部接通。
    舊局資料經 RealTowerState.freshness 自然變 STALE。
    """
    from kiomet_ai.force_units import mirror_force_units

    neighbor_map = {}
    for edge in observation.edges:
        neighbor_map.setdefault(edge.source, []).append(edge.target)
        neighbor_map.setdefault(edge.target, []).append(edge.source)
    states = []
    for t in observation.towers:
        counts = t.units_detail
        # Single 目前只有 Ruler 結構樣本，缺獨立介面數字核對；先維持 UNKNOWN。
        force = (mirror_force_units(counts, t.tower_type)
                 if counts and counts.units_kind == UNITS_KIND_MANY else None)
        states.append(RealTowerState(
            tower_id=t.tower_id, match_id=observation.match_id,
            timestamp=observation.timestamp, tower_ref=t.tower_ref,
            world_x=t.world_x, world_y=t.world_y,
            screen_x=t.screen_x, screen_y=t.screen_y,
            owner=t.owner, owner_confidence=t.owner_confidence,
            owner_ruler=t.owner_ruler,
            tower_type=t.tower_type,
            units_kind=counts.units_kind if counts else UNITS_KIND_UNKNOWN,
            unit_counts=counts,
            deployable_units=UNKNOWN,   # 舊整數欄位不能表達逐兵種組成
            deployable_force=force,
            deployable_force_confidence="DERIVED" if force else "UNKNOWN",
            upgrade_state=t.upgrade_state,
            neighbors=tuple(sorted(set(neighbor_map.get(t.tower_id, []))))))
    return tuple(states)
