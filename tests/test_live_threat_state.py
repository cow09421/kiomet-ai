"""Live threat-state collection is complete, cycle-bound and read-only."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.live_controller import LiveController
import kiomet_ai.live_controller as live_controller_module
from kiomet_ai.observe import UNIT_NAMES


def tower(tower_id, owner, x, match_id="m1", freshness="FRESH"):
    return SimpleNamespace(
        tower_id=tower_id, tower_ref=tower_id + 1000,
        match_id=match_id, owner=owner, world_x=x, world_y=0.0,
        freshness=lambda current, _now: (
            freshness if current == match_id else "STALE"))


def force_entry(ref, owner_id, path, *, progress=0):
    units = {name: 0 for name in UNIT_NAMES}
    units["Soldier"] = 4
    return {"ref": ref, "owner_id": owner_id, "path": list(path),
            "units": units, "speed_flag": 0, "progress": progress,
            "endurance": 20}


def snapshot(match_id, entries=(), *, error=None, captured_at=None):
    value = {"match_id": match_id,
             "captured_at": time.time() if captured_at is None else captured_at,
             "collections": {
                 "inbound": {"length": len(entries), "entries": list(entries)},
                 "outbound": {"length": 0, "entries": []},
             }}
    if error:
        value["error"] = error
    return value


def make_controller(snapshots, match_id="m1", self_id=7):
    browser = SimpleNamespace(game={"state": "IN_MATCH",
                                    "match": {"id": match_id}})
    controller = LiveController(SimpleNamespace(root=Path("."), browser=browser))
    controller.cycle_seq = 4
    controller._select_player_id_match(match_id)
    if self_id is not None:
        controller._player_ids.observe("SELF", self_id)

    async def read_snapshot(tower_ref):
        return snapshots[tower_ref]

    controller.snapshot_collections = read_snapshot
    return controller


def collect(controller, match_id, cycle_id, states):
    by_id = {state.tower_id: state for state in states}
    return asyncio.run(controller._observe_cycle_threat_state(
        match_id, cycle_id, states, by_id, time.time()))


def test_per_cycle_state_collects_multiple_threats_across_self_towers():
    self_a, self_b = tower(10, "SELF", 100.0), tower(20, "SELF", 200.0)
    enemy_a, enemy_b = tower(1, "ENEMY", 0.0), tower(2, "ENEMY", 50.0)
    states = [self_a, self_b, enemy_a, enemy_b]
    snapshots = {
        self_a.tower_ref: snapshot("m1", [
            force_entry(101, 42, [10, 1]),
            force_entry(102, 21, [10, 2]),
        ]),
        self_b.tower_ref: snapshot("m1", [force_entry(201, 42, [20, 1])]),
    }
    controller = make_controller(snapshots)

    result = collect(controller, "m1", 4, states)

    assert result["status"] == "OBSERVED_CANDIDATE"
    assert result["match_id"] == "m1"
    assert result["cycle_id"] == 4
    assert result["coverage"] == {"self_towers": 2, "scanned": 2,
                                  "complete": True}
    assert {row["source_force_id"] for row in result["threats"]} == {
        101, 102, 201}
    assert all(row["cycle_id"] == 4 for row in result["threats"])
    assert all(row["owner_id"] in (21, 42) for row in result["threats"])
    assert all(row["relation"] == "ENEMY" for row in result["threats"])
    assert all(row["confidence"] == "CANDIDATE" for row in result["threats"])
    assert all(row["freshness"] == "FRESH" for row in result["threats"])
    assert all(row["provenance"]["source"] == "WASM_INBOUND_COLLECTION"
               for row in result["threats"])
    assert all(type(row["eta_ticks"]) is int for row in result["threats"])
    assert result == controller.journal["threat_state"]


def test_partial_scan_keeps_known_candidate_but_marks_whole_state_unknown():
    self_a, self_b = tower(10, "SELF", 100.0), tower(20, "SELF", 200.0)
    enemy = tower(1, "ENEMY", 0.0)
    states = [self_a, self_b, enemy]
    snapshots = {
        self_a.tower_ref: snapshot("m1", [force_entry(101, 42, [10, 1])]),
        self_b.tower_ref: snapshot("m1", error="read-failed"),
    }
    controller = make_controller(snapshots)

    result = collect(controller, "m1", 9, states)

    assert result["status"] == "UNKNOWN"
    assert result["coverage"] == {"self_towers": 2, "scanned": 2,
                                  "complete": False}
    assert result["threats"][0]["source_force_id"] == 101
    assert result["threats"][0]["cycle_id"] == 9


def test_stale_self_tower_does_not_skip_other_fresh_self_tower():
    stale_self = tower(10, "SELF", 100.0, freshness="STALE")
    fresh_self = tower(20, "SELF", 200.0)
    controller = make_controller({
        fresh_self.tower_ref: snapshot(
            "m1", [force_entry(201, 42, [20, 1])])})

    result = collect(controller, "m1", 10, [stale_self, fresh_self])

    assert result["status"] == "UNKNOWN"
    assert result["coverage"] == {"self_towers": 2, "scanned": 1,
                                  "complete": False}
    assert [row["source_force_id"] for row in result["threats"]] == [201]


def test_unknown_relation_and_eta_are_preserved_without_zero_defaults():
    self_tower = tower(10, "SELF", 100.0)
    # The path source has no fresh position/owner evidence.
    states = [self_tower]
    snapshots = {self_tower.tower_ref: snapshot(
        "m1", [force_entry(101, 42, [10, 99])])}
    controller = make_controller(snapshots)

    result = collect(controller, "m1", 3, states)

    assert result["status"] == "OBSERVED_CANDIDATE"
    row = result["threats"][0]
    assert row["relation"] == "UNKNOWN"
    assert row["eta_ticks"] is None
    assert row["eta_seconds"] is None
    assert row["eta_status"] == "UNKNOWN"
    assert row["freshness"] == "FRESH"


def test_cross_match_snapshot_makes_state_unknown_and_drops_old_rows():
    self_tower = tower(10, "SELF", 100.0)
    enemy = tower(1, "ENEMY", 0.0)
    states = [self_tower, enemy]
    controller = make_controller({
        self_tower.tower_ref: snapshot("m1", [force_entry(101, 42, [10, 1])])})

    first = collect(controller, "m1", 1, states)
    controller.snapshot_collections = lambda _tower_ref: asyncio.sleep(
        0, result=snapshot("m2", [force_entry(202, 52, [10, 1])]))
    second = collect(controller, "m2", 2,
                     [tower(10, "SELF", 100.0, "m2"),
                      tower(1, "ENEMY", 0.0, "m2")])

    assert first["threats"][0]["source_force_id"] == 101
    assert second["match_id"] == "m2"
    assert second["cycle_id"] == 2
    assert second["status"] == "UNKNOWN"
    assert second["threats"] == []
    assert second["freshness"] == "STALE"


def test_stale_self_tower_and_no_self_towers_never_report_clear():
    stale_self = tower(10, "SELF", 100.0, freshness="STALE")
    controller = make_controller({})

    stale = collect(controller, "m1", 5, [stale_self])
    no_self = collect(controller, "m1", 6, [tower(1, "ENEMY", 0.0)])

    assert stale["status"] == "UNKNOWN"
    assert stale["coverage"]["complete"] is False
    assert no_self["status"] == "UNKNOWN"
    assert no_self["threats"] == []


def test_complete_empty_inbound_across_all_self_towers_is_clear():
    self_a, self_b = tower(10, "SELF", 100.0), tower(20, "SELF", 200.0)
    controller = make_controller({
        self_a.tower_ref: snapshot("m1"),
        self_b.tower_ref: snapshot("m1"),
    })

    result = collect(controller, "m1", 12, [self_a, self_b])

    assert result["status"] == "CLEAR"
    assert result["freshness"] == "FRESH"
    assert result["coverage"] == {"self_towers": 2, "scanned": 2,
                                   "complete": True}
    assert result["threats"] == []


def test_stale_snapshot_cannot_clear_inbound_threat_state():
    self_tower = tower(10, "SELF", 100.0)
    controller = make_controller({self_tower.tower_ref: snapshot(
        "m1", captured_at=time.time() - 31)})

    result = collect(controller, "m1", 13, [self_tower])

    assert result["status"] == "UNKNOWN"
    assert result["freshness"] == "STALE"
    assert result["threats"] == []


def test_cycle_once_publishes_threat_state_before_no_action_exit(
        tmp_path, monkeypatch):
    browser = SimpleNamespace(game={"state": "IN_MATCH",
                                    "match": {"id": "m1"}})
    controller = LiveController(SimpleNamespace(root=tmp_path,
                                                browser=browser))
    controller.cycle_seq = 42
    self_tower = tower(10, "SELF", 100.0)
    enemy = tower(1, "ENEMY", 0.0)

    async def ensure_anchor(_match_id):
        return {"match_id": "m1"}

    async def read_snapshot(_tower_ref):
        return snapshot("m1", [force_entry(101, 42, [10, 1])])

    controller.ensure_anchor = ensure_anchor
    controller.snapshot_collections = read_snapshot
    controller.build_states = lambda *_args: [self_tower, enemy]
    probe_path = (tmp_path / "runtime/research/units"
                  / "unit-struct-probe-m1.json")
    probe_path.parent.mkdir(parents=True)
    probe_path.write_text(json.dumps({"rows": []}), encoding="utf-8")
    monkeypatch.setattr(live_controller_module,
                        "rank_expansion_targets", lambda *_args: [])
    monkeypatch.setattr(live_controller_module,
                        "rejection_reasons", lambda *_args: [])

    phase, _info = asyncio.run(controller.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert controller.journal["threat_state"]["cycle_id"] == 42
    assert controller.journal["threat_state"]["status"] == "OBSERVED_CANDIDATE"
    assert controller.heartbeat()["threat_state"]["threats"][0][
        "source_force_id"] == 101
