"""Moving Force（移動部隊）唯讀觀察器：GPT 靜態配方工程化。

布局（靜態 PASS，執行期驗證待做）：
- 每塔 tower_ref+0 入站集合、+12 出站集合；各 12 位元組 Vec
  （容量+0、指標+4、長度+8，u32 小端序）；項目步長 24。
- Force 項目 24 位元組：+0..+11 路徑 Vec（容量／指標／長度），
  +12 擁有者 u16（空值編碼待實測），+14..+20 內嵌 7 位元組 Units，
  +21 加速旗標，+22 路段進度，+23 續航。
- 路徑倒序：path[len-1]＝目前來源，path[len-2]＝目前目的，
  path[0]＝最終目的。
- 座標：來源→目的按進度／速度／需求內插（GPT 公式）。

所有欄位帶 evidence_status（VERIFIED／DERIVED／CANDIDATE／
UNKNOWN）。靜態 fixture 通過 ≠ 執行期已驗證。
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

from kiomet_ai.observe import TOWER_TYPES, UNIT_NAMES

ENTRY_SIZE = 24
COLLECTION_SIZE = 12
MAX_PATH_LEN = 64
MAX_MEM_SNAPSHOT = 1 << 26  # 16 MiB 上限，防護超大讀取


def _u32le(data: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(data):
        return None
    return struct.unpack_from("<I", data, offset)[0]


def _u16le(data: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 2 > len(data):
        return None
    return data[offset] | (data[offset + 1] << 8)


@dataclass(frozen=True)
class ForceUnits:
    """Force 內嵌 7 位元組 Units（重用 observe 解碼語意，不另起映射）。"""
    tag: int
    counts: dict
    status: str = "CANDIDATE"  # VERIFIED 需執行期对照


def decode_force_units(raw7: bytes) -> ForceUnits | None:
    """解 +14..+20。tag 非 0/1、Single 非法 → None（UNKNOWN）。"""
    if len(raw7) < 7:
        return None
    tag, a, b, c, d, e, shield = raw7[:7]
    counts = {name: 0 for name in UNIT_NAMES}
    counts["Shield"] = shield
    if tag == 0:
        for name, value in zip(UNIT_NAMES[1:6], (a, b, c, d, e)):
            counts[name] = value
    elif tag == 1:
        if not (a > 0 and 0 <= b < len(UNIT_NAMES)):
            return None
        counts[UNIT_NAMES[b]] = a
    else:
        return None
    return ForceUnits(tag=tag, counts=counts)


@dataclass(frozen=True)
class MovingForceState:
    """單支部隊正式契約。未知欄位一律 None（UNKNOWN），不用 0 冒充。"""
    match_id: str | None = None
    timestamp: float | None = None
    collection_role: str | None = None     # INBOUND / OUTBOUND
    anchor_tower_id: int | None = None
    owner_id: int | None = None            # u16 原值；空值編碼待實測
    owner_relation: str | None = None      # SELF / ALLY / ENEMY / UNKNOWN
    units: ForceUnits | None = None
    path: tuple = ()                       # 倒序塔編號
    current_source: int | None = None      # path[-1]
    current_destination: int | None = None  # path[-2]
    final_destination: int | None = None   # path[0]
    speed_flag: int | None = None          # +21
    progress: int | None = None            # +22
    endurance: int | None = None           # +23
    world_xy: tuple | None = None
    screen_xy: tuple | None = None
    direction: tuple | None = None
    evidence_status: str = "UNKNOWN"       # VERIFIED / DERIVED / CANDIDATE / UNKNOWN
    raw_ref: int | None = None
    raw_offset: int | None = None


def _valid_tower_id(value: int | None) -> bool:
    return (isinstance(value, int) and 0 <= (value & 65535) < 512
            and 0 <= (value >> 16) < 512)


def decode_collection(mem: bytes, base: int, mem_base: int) -> dict | None:
    """解 12 位元組集合頭。length==0 回空集合；頭非法回 None。

    注意：只驗證頭本身；項目區由逐筆讀取時各自驗證（不在同一視窗）。
    """
    if base < mem_base or base + COLLECTION_SIZE > mem_base + len(mem):
        return None
    off = base - mem_base
    capacity = _u32le(mem, off)
    pointer = _u32le(mem, off + 4)
    length = _u32le(mem, off + 8)
    if capacity is None or pointer is None or length is None:
        return None
    if length == 0:
        return {"capacity": capacity, "pointer": pointer, "length": 0, "entries": []}
    if length > capacity or length > 1024 or pointer <= 0:
        return None
    return {"capacity": capacity, "pointer": pointer, "length": length,
            "entries": [pointer + ENTRY_SIZE * i for i in range(length)]}


def decode_entry(mem: bytes, entry: int, mem_base: int) -> dict | None:
    """解 24 位元組項目。任一驗證失敗回 None。"""
    if entry < mem_base or entry + ENTRY_SIZE > mem_base + len(mem):
        return None
    off = entry - mem_base
    path_cap = _u32le(mem, off)
    path_ptr = _u32le(mem, off + 4)
    path_len = _u32le(mem, off + 8)
    owner_id = _u16le(mem, off + 12)
    units = decode_force_units(bytes(mem[off + 14:off + 21]))
    if path_cap is None or path_ptr is None or path_len is None or owner_id is None:
        return None
    if units is None:
        return None
    if not (2 <= path_len <= MAX_PATH_LEN):
        return None
    if path_ptr <= 0 or path_ptr + 4 * path_len > mem_base + len(mem):
        return None
    path = []
    for i in range(path_len):
        tower_id = _u32le(mem, path_ptr - mem_base + 4 * i)
        if not _valid_tower_id(tower_id):
            return None
        path.append(tower_id)
    if len(set(path)) != len(path) or path[-1] == path[-2]:
        # 路徑自交或來源==目的：無效
        return None
    return {"path": tuple(path), "owner_id": owner_id, "units": units,
            "speed_flag": mem[off + 21], "progress": mem[off + 22],
            "endurance": mem[off + 23], "ref": entry}


def unit_speed(units: ForceUnits) -> int:
    """速度由兵力組成導出（GPT 配方）：Fast=3？ 保守只分快／慢／普通。

    來源 speed() 語意：Bomber/Fighter/Chopper/Shell=Fast，
    Tank/Nuke=Slow，其餘 Normal。這裡映射為節拍進度權重：
    Fast=3、Normal=2、Slow=1（取部隊中最慢者；Shield 忽略）。
    CANDIDATE 權重，待執行期核對。
    """
    weights = {"Fighter": 3, "Chopper": 3, "Bomber": 3, "Shell": 3,
               "Tank": 1, "Nuke": 1, "Soldier": 2, "Emp": 2, "Ruler": 2}
    present = [weights[n] for n, c in units.counts.items()
               if c and n in weights]
    return min(present) if present else 2


def derive_world_xy(source_xy, target_xy, progress: int, speed: int,
                    speed_flag: int) -> tuple | None:
    """GPT 內插公式。fraction_since_tick 未知取 0（節拍起點估計）。"""
    if source_xy is None or target_xy is None:
        return None
    dx = target_xy[0] - source_xy[0]
    dy = target_xy[1] - source_xy[1]
    distance = math.hypot(dx, dy)
    required = min(255, math.floor(distance * 180 / 10))
    if speed_flag == 1:
        required = max(1, math.floor(required * 4 / 5))
    if required <= 0:
        return None
    ratio = min(1.0, progress / required)
    x = source_xy[0] + dx * ratio
    y = source_xy[1] + dy * ratio
    direction = (dx / distance, dy / distance) if distance else (0.0, 0.0)
    return (x, y, direction, required)


class RealForceObserver:
    """唯讀部隊觀察器：吃記憶體快照＋讀函式，不碰瀏覽器。

    read(address, length) 由呼叫方注入（測試用 fixture／正式用 CDP）。
    """

    def __init__(self, read, tower_positions: dict | None = None):
        self._read = read
        self._positions = tower_positions or {}

    def scan_tower(self, match_id: str | None, tower_id: int,
                   tower_ref: int, timestamp: float | None = None) -> list:
        """讀一座塔的出入站集合，回 MovingForceState 列表。

        任一集合非法→該集合 UNKNOWN（不輸出虛構部隊，不拋錯）。
        """
        states = []
        try:
            header = self._read(tower_ref, 24)
        except Exception:
            return states
        if len(header) < 24:
            return states
        mem_base = tower_ref
        for role, base in (("INBOUND", tower_ref), ("OUTBOUND", tower_ref + 12)):
            collection = decode_collection(header, base, mem_base)
            if collection is None:
                continue  # 該集合 UNKNOWN，不輸出
            if not collection["entries"]:
                continue
            for entry in collection["entries"]:
                decoded = self._decode_with_path(entry)
                if decoded is None:
                    continue
                states.append(self._build_state(
                    match_id, timestamp, role, tower_id, tower_ref, decoded))
        return states

    def _decode_with_path(self, entry: int):
        """解項目：先讀 24 位元組頭，再跟讀路徑區（限 256×4）。"""
        try:
            head = self._read(entry, ENTRY_SIZE)
        except Exception:
            return None
        if len(head) < ENTRY_SIZE:
            return None
        path_len = struct.unpack_from("<I", head, 8)[0]
        path_ptr = struct.unpack_from("<I", head, 4)[0]
        owner_id = head[12] | (head[13] << 8)
        units = decode_force_units(bytes(head[14:21]))
        if units is None or not (2 <= path_len <= MAX_PATH_LEN):
            return None
        if path_ptr <= 0 or path_ptr + 4 * path_len > (1 << 32):
            return None
        try:
            path_block = self._read(path_ptr, 4 * path_len)
        except Exception:
            return None
        if len(path_block) < 4 * path_len:
            return None
        path = []
        for i in range(path_len):
            tower_id = struct.unpack_from("<I", path_block, 4 * i)[0]
            if not _valid_tower_id(tower_id):
                return None
            path.append(tower_id)
        if len(set(path)) != len(path) or path[-1] == path[-2]:
            return None
        return {"path": tuple(path), "owner_id": owner_id, "units": units,
                "speed_flag": head[21], "progress": head[22],
                "endurance": head[23], "ref": entry}

    def _build_state(self, match_id, timestamp, role, tower_id,
                     tower_ref, decoded) -> MovingForceState:
        path = decoded["path"]
        source_xy = self._positions.get(path[-1])
        target_xy = self._positions.get(path[-2]) if len(path) >= 2 else None
        speed = unit_speed(decoded["units"])
        world = derive_world_xy(source_xy, target_xy, decoded["progress"],
                                speed, decoded["speed_flag"])
        direction = world[2] if world else None
        return MovingForceState(
            match_id=match_id, timestamp=timestamp,
            collection_role=role, anchor_tower_id=tower_id,
            owner_id=decoded["owner_id"], owner_relation=None,
            units=decoded["units"], path=path,
            current_source=path[-1], current_destination=path[-2],
            final_destination=path[0],
            speed_flag=decoded["speed_flag"], progress=decoded["progress"],
            endurance=decoded["endurance"],
            world_xy=(world[0], world[1]) if world else None,
            direction=direction,
            evidence_status="CANDIDATE",
            raw_ref=decoded["ref"], raw_offset=None)


def eta_ticks(progress: int, speed: int, distance: float,
              speed_flag: int) -> int | None:
    """GPT 公式：required=min(255,floor(distance*180/10))；
    +21==1 時改 max(1,floor(required*4/5))；
    ETA_ticks=ceil(max(0,required-progress)/speed)。4 節拍／秒。
    只做 ETA，不做勝率預測（morale 未知）。
    輸入紀律：bool/非 int 的 progress、speed 一律拒絕（不造 0）；
    distance 必須為正數；speed_flag 非 int 時拒絕，None 視為 0。"""
    if type(progress) is not int or progress < 0:
        return None
    if type(speed) is not int or speed <= 0:
        return None
    if (distance is None or isinstance(distance, bool)
            or not isinstance(distance, (int, float)) or distance <= 0):
        return None
    if speed_flag is None:
        speed_flag = 0
    elif type(speed_flag) is not int:
        return None
    required = min(255, math.floor(distance * 180 / 10))
    if speed_flag == 1:
        required = max(1, math.floor(required * 4 / 5))
    import math as _math
    return _math.ceil(max(0, required - progress) / speed)


@dataclass(frozen=True)
class IncomingThreat:
    """入站威脅客觀資料層：只描述事實，不預測勝負。"""
    force_identity: str | None = None     # 穩定 ID；無則 CANDIDATE 暫定
    target_tower_id: int | None = None    # 被威脅的 SELF 塔
    source_tower_id: int | None = None
    source_player: int | None = None      # owner_id 別名（GPT 契約欄）
    owner_id: int | None = None
    owner_relation: str | None = None     # SELF / ALLY / ENEMY / UNKNOWN
    units: dict | None = None
    progress: int | None = None
    eta_ticks: int | None = None
    eta_seconds: float | None = None
    freshness: str = "UNKNOWN"            # FRESH / STALE / UNKNOWN
    confidence: str = "UNKNOWN"           # VERIFIED / DERIVED / CANDIDATE / UNKNOWN


def threat_eta_seconds(eta_ticks: int | None) -> float | None:
    """ETA_seconds = ETA_ticks / 4（4 節拍／秒）。"""
    if eta_ticks is None or eta_ticks < 0:
        return None
    return eta_ticks / 4.0


# 戰鬥事件分類（GPT P0/P2 靜態；只做分類與所有權轉換，不做勝率鏡像）。
BATTLE_FRIENDLY_MERGE = "FRIENDLY_MERGE"
BATTLE_NEUTRAL_CAPTURE = "NEUTRAL_CAPTURE"
BATTLE_COMBAT_STARTED = "COMBAT_STARTED"
BATTLE_COMBAT_RESOLVED = "COMBAT_RESOLVED"
BATTLE_OWNER_CHANGED = "OWNER_CHANGED"


def classify_battle_event(before_owner, after_owner,
                          attacker_present: bool) -> str | None:
    """所有權轉換＋戰鬥事件分類（純函式，無預測）。"""
    if before_owner == after_owner:
        return BATTLE_FRIENDLY_MERGE if attacker_present else None
    if after_owner == "SELF" and before_owner == "NEUTRAL":
        return BATTLE_NEUTRAL_CAPTURE
    if after_owner != before_owner and attacker_present:
        return BATTLE_OWNER_CHANGED
    if attacker_present:
        return BATTLE_COMBAT_STARTED
    return None


@dataclass(frozen=True)
class ReinforceSelf:
    """SELF→SELF 增援提案契約：SOURCE_SEMANTICS_PASS，
    SERVER_VALIDATION_PENDING（本輪不自動執行）。"""
    source_tower_id: int | None = None
    target_tower_id: int | None = None
    deployable_force: dict | None = None
    eta_ticks: int | None = None
    reason: str | None = None
    status: str = "SOURCE_SEMANTICS_PASS"

def deduplicate(states: list) -> list:
    """同一 Force 的出入站鏡像去重（owner+path+progress+units 特徵）。

    無穩定 ID：回傳 (kept, groups)，group 內標 CANDIDATE 同一體。
    """
    groups: dict = {}
    for state in states:
        key = (state.owner_id, state.path, state.progress,
               tuple(sorted((state.units.counts or {}).items())) if state.units else None)
        groups.setdefault(key, []).append(state)
    kept = [members[0] for members in groups.values()]
    return kept
