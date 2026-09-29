"""Read static WASM data segments; never instantiate or call the game module."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WASM = ROOT / "runtime/research/source-map/production-client_bg.wasm"
OUTPUT = Path(__file__).with_name("GPT_COMBAT_TABLES.json")


def uleb(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 127) << shift
        if byte < 128:
            return result, pos
        shift += 7


def sleb(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 127) << shift
        shift += 7
        if byte < 128:
            if byte & 64:
                result |= -(1 << shift)
            return result, pos


def static_memory(data: bytes) -> bytearray:
    assert data[:4] == b"\0asm"
    pos = 8
    segments = []
    while pos < len(data):
        section = data[pos]
        pos += 1
        size, pos = uleb(data, pos)
        end = pos + size
        if section == 11:
            count, pos = uleb(data, pos)
            for _ in range(count):
                flags, pos = uleb(data, pos)
                if flags & 2:
                    _, pos = uleb(data, pos)
                address = None
                if not flags & 1:
                    assert data[pos] == 0x41
                    address, pos = sleb(data, pos + 1)
                    assert data[pos] == 0x0B
                    pos += 1
                length, pos = uleb(data, pos)
                payload = data[pos : pos + length]
                pos += length
                if address is not None:
                    segments.append((address, payload))
            assert pos == end
        pos = end
    memory = bytearray(max(a + len(p) for a, p in segments))
    for address, payload in segments:
        memory[address : address + len(payload)] = payload
    return memory


def main() -> None:
    data = WASM.read_bytes()
    memory = static_memory(data)
    bases = list(range(1362240, 1363081, 40))
    # Positional alignment with the source enum and capacity attributes. The
    # five omitted tower types have special-case branches in function 732.
    source_aligned_types = [
        "Airfield", "Armory", "Barracks", "Centrifuge", "City", "Cliff",
        "Ews", "Factory", "Generator", "Headquarters", "Helipad", "Mine",
        "Projector", "Quarry", "Radar", "Reactor", "Refinery", "Rocket",
        "Runway", "Satellite", "Silo", "Town",
    ]
    tables = []
    for base, tower_type in zip(bases, source_aligned_types, strict=True):
        raw = bytes(memory[base : base + 40])
        assert len(raw) == 40
        tables.append({
            "memory_address": base,
            "unit_index_order": ["Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier", "Shell", "Emp", "Nuke", "Ruler"],
            "raw_u32_le": list(struct.unpack("<10I", raw)),
            "raw_hex": raw.hex(),
            "source_aligned_tower_type": tower_type,
            "mapping_status": "CANDIDATE: source enum order and exact capacity row match; production br_table not exhaustively traced",
        })
    output = {
        "wasm_sha256": hashlib.sha256(data).hexdigest(),
        "method": "static data-section decoding only; no WASM invocation",
        "production_function": 732,
        "production_table_stride_bytes": 40,
        "production_capacity_rows": tables,
        "caution": "Rows are exact raw function-732 lookup data. Tower-type labels are source-aligned candidates; five special-case towers and complete production dispatch require further tracing. Do not use as a production capacity oracle yet.",
        "source_special_case_tower_capacity": {
            "Artillery": {"Shield": 20, "Shell": 3, "Ruler": 1},
            "Bunker": {"Shield": 40, "Soldier": 6, "Ruler": 1},
            "Launcher": {"Shield": 15, "Emp": 1, "Ruler": 1},
            "Rampart": {"Shield": 45, "Soldier": 8, "Ruler": 1},
            "Village": {"Shield": 5, "Soldier": 4, "Ruler": 1},
            "status": "SOURCE_ONLY; production special branches not exhaustively decoded",
        },
        "source_unit_damage": {
            "Tank": 3,
            "Fighter_air": 3,
            "Bomber_air_to_surface": 5,
            "Chopper_air": 3,
            "Nuke": "infinite sentinel 31",
            "Shell": 3,
            "otherwise": 1,
            "source": "vendor/kiomet-ref/common/src/unit.rs:161-177",
            "production_alignment": "func 2970 uses the same enum-index switch and constants 1,3,5,31; no separate damage memory table",
        },
        "source_tower_ranged_damage": {
            "Bunker": "floor(damage/3)",
            "Headquarters": "floor(2*damage/3)",
            "other": "damage",
            "source": "vendor/kiomet-ref/common/src/tower.rs:402-410",
            "production_alignment": "func 2022 compares tower type indexes 4 and 11 and applies the same divisors",
        },
        "source_max_overflow": {
            "Shield": 15, "Soldier": 10, "Tank": 5, "Fighter": 4,
            "Bomber": 2, "Chopper": 2, "otherwise": 0,
            "source": "vendor/kiomet-ref/common/src/unit.rs:140-151",
            "production_alignment": "not exhaustively validated",
        },
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(tables)} rows; {OUTPUT}")


if __name__ == "__main__":
    main()
