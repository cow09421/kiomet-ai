"""Live force snapshots retain the read-only inputs needed for ETA work."""
import asyncio
import struct
from pathlib import Path
from types import SimpleNamespace

from kiomet_ai.live_controller import LiveController


class MemoryBrowser:
    def __init__(self, *, valid_path=True):
        self.game = {"match": {"id": "match-1"}}
        header = bytearray(24)
        struct.pack_into("<III", header, 0, 1, 2000, 1)
        struct.pack_into("<III", header, 12, 0, 0, 0)

        entry = bytearray(24)
        struct.pack_into("<III", entry, 0, 2, 3000, 2)
        struct.pack_into("<H", entry, 12, 42)
        entry[14:21] = bytes((0, 0, 0, 0, 0, 3, 4))
        entry[21:24] = bytes((1, 37, 19))
        self.memory = {
            (1000, 24): bytes(header),
            (2000, 24): bytes(entry),
            (3000, 8): (struct.pack("<II", 2, 1) if valid_path
                        else struct.pack("<II", 2, 2)),
        }

    async def read_wasm_bytes(self, address, size):
        return self.memory[(address, size)]


def controller(browser):
    live = LiveController.__new__(LiveController)
    live.app = SimpleNamespace(browser=browser)
    return live


def test_snapshot_preserves_speed_progress_and_endurance_for_eta():
    snapshot = asyncio.run(controller(MemoryBrowser()).snapshot_collections(1000))

    inbound = snapshot["collections"]["inbound"]
    assert inbound["length"] == 1
    assert inbound["entries"] == [{
        "ref": 2000,
        "path": [2, 1],
        "owner_id": 42,
        "units": {
            "Shield": 4, "Fighter": 0, "Chopper": 0,
            "Bomber": 0, "Tank": 0, "Soldier": 3,
            "Shell": 0, "Emp": 0, "Nuke": 0, "Ruler": 0,
        },
        "speed_flag": 1,
        "progress": 37,
        "endurance": 19,
    }]


def test_invalid_force_path_is_omitted_without_claiming_empty_collection():
    snapshot = asyncio.run(
        controller(MemoryBrowser(valid_path=False)).snapshot_collections(1000))

    inbound = snapshot["collections"]["inbound"]
    assert inbound["length"] == 1
    assert inbound["entries"] == []
