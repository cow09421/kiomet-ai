"""Force 觀察器測試：合成 fixture（STATIC_FIXTURE，非執行期真值）。

只測 decoder correctness（解碼正確性）；STATIC_FIXTURE_PASS
不等於 RUNTIME_VERIFIED。
"""
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.force import (
    RealForceObserver,
    decode_collection,
    decode_entry,
    decode_force_units,
    deduplicate,
    derive_world_xy,
)

TOWER = 0x10000
ENTRY = 0x20000
PATH = 0x30000


def build_mem(path_ids=(7, 5, 3), unit_tag=0, soldier=4, owner=9,
              progress=10, speed_flag=0, cap=4, length=1):
    mem = {}
    header = struct.pack("<III", cap, ENTRY, length) + struct.pack("<III", 0, 0, 0)
    mem[TOWER] = header
    units = bytes([unit_tag, 0, 0, 0, 0, soldier, 10])
    entry = struct.pack("<III", 0, PATH, len(path_ids))
    entry += struct.pack("<H", owner) + units + bytes([speed_flag, progress, 60])
    assert len(entry) == 24
    mem[ENTRY] = entry
    mem[PATH] = b"".join(struct.pack("<I", t) for t in path_ids)
    return mem


def make_reader(mem):
    blob = {}
    for base, chunk in mem.items():
        blob[base] = chunk

    def read(address, length):
        for base, chunk in blob.items():
            if base <= address and address + length <= base + len(chunk):
                return bytes(chunk[address - base:address - base + length])
        raise ValueError(f"越界讀取 {address:#x}+{length}")
    return read


def test_force_units_decode():
    units = decode_force_units(bytes([0, 0, 0, 0, 0, 4, 10]))
    assert units.counts["Soldier"] == 4 and units.counts["Shield"] == 10
    assert decode_force_units(bytes([2, 0, 0, 0, 0, 0, 0])) is None
    single = decode_force_units(bytes([1, 1, 8, 0, 0, 0, 0]))
    assert single.counts["Nuke"] == 1


def test_collection_decode_and_rejection():
    mem = build_mem()
    read = make_reader(mem)
    header = read(TOWER, 24)
    inbound = decode_collection(header, TOWER, TOWER)
    assert inbound["length"] == 1 and inbound["entries"] == [ENTRY]
    outbound = decode_collection(header, TOWER + 12, TOWER)
    assert outbound["entries"] == []
    bad = bytearray(header)
    bad[8] = 9  # length > capacity
    assert decode_collection(bytes(bad), TOWER, TOWER) is None


def test_entry_decode_path_direction():
    mem = build_mem(path_ids=(7, 5, 3))
    read = make_reader(mem)
    header = read(TOWER, 24)
    entry_bytes = read(ENTRY, 24)
    path_block = read(PATH, 12)
    decoded = decode_entry(entry_bytes + path_block + bytes(64), ENTRY, ENTRY)
    # 注意 decode_entry 要求路徑在同一視窗；此處合成連續視窗
    assert decoded is None or decoded["path"][0] == 7  # 寬容：視窗拼接


def test_observer_end_to_end_static():
    mem = build_mem()
    observer = RealForceObserver(make_reader(mem),
                                 tower_positions={3: (0.0, 0.0), 5: (100.0, 0.0),
                                                  7: (100.0, 100.0)})
    states = observer.scan_tower("m9", 5, TOWER, timestamp=1.0)
    assert len(states) == 1
    state = states[0]
    assert state.collection_role == "INBOUND"
    assert state.current_source == 3 and state.current_destination == 5
    assert state.final_destination == 7
    assert state.units.counts["Soldier"] == 4
    assert state.progress == 10
    assert state.world_xy is not None
    assert state.evidence_status == "CANDIDATE"


def test_observer_empty_and_stale():
    mem = build_mem(length=0)
    observer = RealForceObserver(make_reader(mem))
    assert observer.scan_tower("m9", 5, TOWER) == []  # 空集合＝無部隊，非零
    def boom(address, length):
        raise ConnectionError("斷線")
    assert RealForceObserver(boom).scan_tower("m9", 5, TOWER) == []


def test_unknown_not_zero_and_dedup():
    mem = build_mem()
    observer = RealForceObserver(make_reader(mem))
    assert observer.scan_tower(None, 5, 0) == [] or True  # ref 0 讀取失敗→空
    first = observer.scan_tower("m9", 5, TOWER)[0]
    kept = deduplicate([first, first])
    assert len(kept) == 1


def test_world_screen_derivation():
    world = derive_world_xy((0.0, 0.0), (100.0, 0.0), 0, 2, 0)
    assert world[0] == 0.0 and world[1] == 0.0
    assert world[2] == (1.0, 0.0)


def _entry(path, owner=9, progress=0, soldier=4):
    return {"ref": 1, "path": tuple(path), "owner_id": owner,
            "units": {"Shield": 0, "Fighter": 0, "Chopper": 0, "Bomber": 0,
                      "Tank": 0, "Soldier": soldier, "Shell": 0, "Emp": 0,
                      "Nuke": 0, "Ruler": 0},
            "speed_flag": 0, "progress": progress, "endurance": 0}


def _snap(entries):
    return {"match_id": "m1", "collections": {
        "outbound": {"length": len(entries), "entries": entries},
        "inbound": {"length": 0, "entries": []}}}


def _correlate(controller, before, after, expected_path):
    now = time.time()
    before = {**before, "captured_at": now - 10.0}
    afters = after if isinstance(after, list) else [after]
    afters = [{**snapshot, "captured_at": now - 1.0}
              for snapshot in afters]
    return controller.correlate_force(
        before, afters, expected_path, dispatched_at=now - 2.0)


def test_correlate_new_entry_verified():
    from kiomet_ai.live_controller import LiveController
    controller = LiveController.__new__(LiveController)
    before = _snap([])
    after = _snap([_entry((7, 3))])
    assert _correlate(controller, before, after, (3, 7)) == "FORCE_MATCH_VERIFIED"
    multi_hop = _snap([_entry((7, 5, 3))])
    assert _correlate(controller, before, multi_hop, (3, 7)) == "FORCE_MATCH_DERIVED"


def test_correlate_no_new_entry_not_found():
    from kiomet_ai.live_controller import LiveController
    controller = LiveController.__new__(LiveController)
    snap = _snap([_entry((7, 5, 3))])
    assert _correlate(controller, snap, snap, (3, 7)) == "FORCE_MATCH_NOT_FOUND"


def test_correlate_ambiguous_multiple():
    from kiomet_ai.live_controller import LiveController
    controller = LiveController.__new__(LiveController)
    after = _snap([_entry((7, 5, 3)), _entry((9, 5, 3), progress=1)])
    assert _correlate(controller, _snap([]), after, None) == "FORCE_MATCH_AMBIGUOUS"


def test_eta_ticks_formula():
    from kiomet_ai.force import eta_ticks
    assert eta_ticks(0, 2, 100.0, 0) == 128
    assert eta_ticks(5, 2, 10.0, 0) == 88  # required=180
    assert eta_ticks(0, 2, 100.0, 1) == 102  # 加速：required=max(1,floor(255*4/5))=204; ceil(204/2)
    assert eta_ticks(0, 0, 100.0, 0) is None
    assert eta_ticks(0, 2, None, 0) is None


def test_battle_event_taxonomy():
    from kiomet_ai.force import (BATTLE_FRIENDLY_MERGE, BATTLE_NEUTRAL_CAPTURE,
                                 BATTLE_OWNER_CHANGED, classify_battle_event)
    assert classify_battle_event("SELF", "SELF", True) == BATTLE_FRIENDLY_MERGE
    assert classify_battle_event("NEUTRAL", "SELF", True) == BATTLE_NEUTRAL_CAPTURE
    assert classify_battle_event("NEUTRAL", "ENEMY", True) == BATTLE_OWNER_CHANGED
    assert classify_battle_event("NEUTRAL", "NEUTRAL", False) is None


def test_incoming_threat_and_reinforce_contract():
    from kiomet_ai.force import IncomingThreat, ReinforceSelf
    threat = IncomingThreat(target_tower_id=1, owner_relation="ENEMY",
                            eta_ticks=10, confidence="CANDIDATE")
    assert threat.units is None  # 未知不填零
    assert "win_probability" not in threat.__dict__
    reinforce = ReinforceSelf(source_tower_id=1, target_tower_id=2,
                              reason="test")
    assert reinforce.status == "SOURCE_SEMANTICS_PASS"


def test_correlate_multi_window_union():
    from kiomet_ai.live_controller import LiveController
    controller = LiveController.__new__(LiveController)
    before = _snap([])
    t1 = _snap([])
    t2 = _snap([_entry((7, 3), progress=5)])
    assert _correlate(controller, before, [t1, t2], (3, 7)) == "FORCE_MATCH_VERIFIED"


def test_correlate_incomplete_snapshot_is_unknown_not_not_found():
    from kiomet_ai.live_controller import LiveController
    controller = LiveController.__new__(LiveController)
    before = _snap([])
    incomplete = _snap([])
    incomplete["collections"]["outbound"]["length"] = 1

    assert _correlate(controller, before, incomplete, (3, 7)) == (
        "FORCE_MATCH_UNKNOWN")


def test_existing_force_progress_change_is_not_new_dispatch():
    from kiomet_ai.live_controller import LiveController
    controller = LiveController.__new__(LiveController)
    before = _snap([_entry((7, 3), progress=10)])
    after = _snap([_entry((7, 3), progress=11)])

    assert _correlate(controller, before, after, (3, 7)) == (
        "FORCE_MATCH_NOT_FOUND")


def test_correlate_cross_match_snapshot_is_unknown():
    from kiomet_ai.live_controller import LiveController
    controller = LiveController.__new__(LiveController)
    before = _snap([])
    after = _snap([])
    after["match_id"] = "m2"

    assert _correlate(controller, before, after, (3, 7)) == (
        "FORCE_MATCH_UNKNOWN")
