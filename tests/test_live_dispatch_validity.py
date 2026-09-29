"""Live dispatch must validate its snapshot and hold tower reservations."""
import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.live_controller import LiveController
from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    TowerUnitCounts,
    build_real_tower_states,
)


def many(**values):
    return TowerUnitCounts(
        units_kind="MANY", fighter=values.get("fighter", 0),
        chopper=values.get("chopper", 0), bomber=values.get("bomber", 0),
        tank=values.get("tank", 0), soldier=values.get("soldier", 0),
        shield=values.get("shield", 0))


class FakeApp:
    def __init__(self, root, *, sent=False):
        self.root = root
        self.browser = SimpleNamespace(game={
            "state": "IN_MATCH", "match": {"id": "m1"}})
        self.autonomy_paused = False
        self.execute_calls = []
        self.sent = sent
        self.controller = None
        self.reservation_checks = []

    def _check_reservation(self):
        if self.controller is not None:
            source_holder = self.controller._reservations.holder(1)
            target_holder = self.controller._reservations.holder(2)
            assert source_holder is not None
            assert target_holder == source_holder
            self.reservation_checks.append(source_holder)

    async def execute_move(self, payload):
        self._check_reservation()
        self.execute_calls.append(payload)
        return {"sent": self.sent, "result": "test-stop"}

    def record_verification(self, verdict, match_id):
        self._check_reservation()

    def append_live_action(self, payload):
        self._check_reservation()


def make_controller(tmp_path, *, sent=False, ruler=False):
    (tmp_path / "runtime/research/units").mkdir(parents=True)
    (tmp_path / "runtime/research/source-map").mkdir(parents=True)
    probe_path = (tmp_path / "runtime/research/units"
                  / "unit-struct-probe-m1.json")
    probe_path.write_text(json.dumps({"match_id": "m1", "rows": []}),
                          encoding="utf-8")
    (tmp_path / "runtime/research/source-map"
     / "verified-anchor-current.json").write_text("{}", encoding="utf-8")

    now = time.time()
    observation = MatchObservation(
        match_id="m1", timestamp=now,
        towers=(
            ObservedTower(
                tower_id=1, tower_ref=11, world_x=0, world_y=0,
                owner="SELF", tower_type="Runway",
                owner_ruler=ruler,
                units_detail=many(fighter=4, soldier=4, shield=15)),
            ObservedTower(
                tower_id=2, tower_ref=22, world_x=5, world_y=0,
                owner="NEUTRAL", tower_type="Cliff",
                units_detail=many(soldier=2, shield=3)),
            ObservedTower(
                tower_id=3, tower_ref=33, world_x=20, world_y=0,
                owner="SELF", tower_type="Cliff",
                units_detail=many(soldier=2, shield=3)),
        ), edges=(ObservedEdge(1, 2),))
    states = build_real_tower_states(observation)
    anchor = {"match_id": "m1", "towers": [
        {"packed_id": 1, "tower_ref": 11, "position": [0, 0]},
        {"packed_id": 2, "tower_ref": 22, "position": [5, 0]},
        {"packed_id": 3, "tower_ref": 33, "position": [20, 0]},
    ]}
    app = FakeApp(tmp_path, sent=sent)
    controller = LiveController(app)
    app.controller = controller

    async def ensure_anchor(match_id):
        assert match_id == "m1"
        return anchor

    async def run_tool(script, *args):
        assert script == "unit_struct_probe.py"
        return 0, ""

    async def snapshot_collections(tower_ref):
        return {"match_id": "m1", "captured_at": time.time(),
                "collections": {
            "inbound": {"length": 0, "entries": []},
            "outbound": {"length": 0, "entries": []}}}

    async def fresh_screen_map(_towers):
        return {1: (100.0, 200.0), 2: (150.0, 200.0),
                3: (250.0, 200.0)}, {
            "w": 800, "h": 600, "camera": (0, 1.0, 2.0, 3.0),
            "viewport": (800, 600), "dpr": 1.0,
            "canvas_rect": (0.0, 0.0, 800.0, 600.0),
        }

    controller.ensure_anchor = ensure_anchor
    controller.build_states = lambda _a, _rows, _now: states
    controller._check_pending_captures = lambda *_args: None
    controller._run_tool = run_tool
    controller.snapshot_collections = snapshot_collections
    controller.fresh_screen_map = fresh_screen_map
    return controller


def test_live_dispatch_stops_when_validity_token_is_stale(tmp_path):
    controller = make_controller(tmp_path)
    controller._build_dispatch_token = lambda *_args: (
        None, "STALE_PROPOSAL:camera-changed")

    phase, info = asyncio.run(controller.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert info["match_id"] == "m1"
    assert info["reason"] == "STALE_PROPOSAL:camera-changed"
    assert controller.app.execute_calls == []
    assert controller._reservations.holder(1) is None
    assert controller._reservations.holder(2) is None


def test_live_dispatch_reaches_execute_only_with_valid_token(tmp_path):
    controller = make_controller(tmp_path)

    phase, info = asyncio.run(controller.cycle_once())

    assert phase == "PRECHECK_REJECTED", info
    assert info["reason"] == "test-stop"
    assert len(controller.app.execute_calls) == 1
    assert controller.journal["last_action_validity"]["status"] == "OK"
    assert controller.journal["last_source_safety"]["result"] == "SAFE"
    assert controller._reservations.holder(1) is None
    assert controller._reservations.holder(2) is None


def test_live_dispatch_can_expand_from_ruler_garrison_without_inbound_threat(
        tmp_path):
    controller = make_controller(tmp_path, ruler=True)

    phase, info = asyncio.run(controller.cycle_once())

    assert phase == "PRECHECK_REJECTED"
    assert info["reason"] == "test-stop"
    assert len(controller.app.execute_calls) == 1
    assert controller.journal["last_source_safety"]["result"] == "SAFE"


def test_reservation_stays_held_through_mocked_verification(tmp_path,
                                                           monkeypatch):
    controller = make_controller(tmp_path, sent=True)
    import kiomet_ai.live_controller as live_controller_module

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(live_controller_module.asyncio, "sleep", no_sleep)
    correlate_calls = []

    def correlate_force(*args, dispatched_at=None):
        correlate_calls.append((args, dispatched_at))
        return "NOT_FOUND"

    controller.correlate_force = correlate_force

    phase, _ = asyncio.run(controller.cycle_once())

    assert phase == "VERIFYING"
    assert len(controller.app.execute_calls) == 1
    assert len(controller.app.reservation_checks) == 3
    assert len(set(controller.app.reservation_checks)) == 1
    sent_at = controller.journal["last_action"]["sent_at"]
    assert len(correlate_calls) == 2
    assert all(call[1] == sent_at for call in correlate_calls)
    assert controller._reservations.holder(1) is None
    assert controller._reservations.holder(2) is None


def test_live_dispatch_rejects_reserved_source_before_observation_or_action(
        tmp_path):
    controller = make_controller(tmp_path)
    controller._select_reservation_match("m1")
    controller._reservations.reserve("existing-action", 1, 9)

    phase, info = asyncio.run(controller.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert info["match_id"] == "m1"
    assert info["reason"] == "RESOURCE_RESERVED:source"
    assert controller.app.execute_calls == []
    assert controller._reservations.holder(1) == "existing-action"


def test_dispatch_reservation_is_held_through_verification_and_released():
    controller = LiveController(SimpleNamespace(root=Path(".")))
    controller._select_reservation_match("m1")

    async def verify():
        assert controller._reservations.holder(1) == "action-1"
        assert controller._reservations.holder(2) == "action-1"
        return "VERIFYING", {"verdict": "FORCE_OBSERVED"}

    result = asyncio.run(controller._with_action_reservation(
        "action-1", 1, 2, verify))

    assert result == ("VERIFYING", {"verdict": "FORCE_OBSERVED"})
    assert controller._reservations.holder(1) is None
    assert controller._reservations.holder(2) is None


def test_dispatch_reservation_releases_when_verification_raises():
    controller = LiveController(SimpleNamespace(root=Path(".")))
    controller._select_reservation_match("m1")

    async def fail_verification():
        assert controller._reservations.holder(1) == "action-2"
        raise RuntimeError("verification failed")

    with pytest.raises(RuntimeError, match="verification failed"):
        asyncio.run(controller._with_action_reservation(
            "action-2", 1, 2, fail_verification))

    assert controller._reservations.holder(1) is None
    assert controller._reservations.holder(2) is None


def test_dispatch_reservation_rejects_invalid_tower_ids():
    controller = LiveController(SimpleNamespace(root=Path(".")))
    controller._select_reservation_match("m1")
    called = []

    async def operation():
        called.append(True)

    result = asyncio.run(controller._with_action_reservation(
        "bad-action", True, 2, operation))

    assert result == ("NO_SAFE_PROPOSAL", {
        "reason": "STALE_PROPOSAL:tower-id-unknown"})
    assert called == []
    assert controller._reservations.holder(True) is None


def test_token_requires_known_camera_snapshot_and_deployable_counts(tmp_path):
    controller = make_controller(tmp_path)
    states = build_real_tower_states(MatchObservation(
        match_id="m1", timestamp=1000.0,
        towers=(
            ObservedTower(tower_id=1, tower_ref=11, owner="SELF",
                          tower_type="Runway",
                          units_detail=many(fighter=4, soldier=4, shield=15)),
            ObservedTower(tower_id=2, tower_ref=22, owner="NEUTRAL",
                          tower_type="Cliff",
                          units_detail=many(soldier=2, shield=3)),
        ), edges=(ObservedEdge(1, 2),)))
    source, target = states
    deployable = source.deployable_force.counts
    camera = {"w": 800, "h": 600, "camera": (0, 1.0, 2.0, 3.0),
              "viewport": (800, 600), "dpr": 1.0,
              "canvas_rect": (0.0, 0.0, 800.0, 600.0)}

    token, status = controller._build_dispatch_token(
        "m1", 1, source, target, camera, deployable)
    assert token is not None
    assert status == "OK"

    _, bad_camera = controller._build_dispatch_token(
        "m1", 1, source, target, {"w": 800, "h": 600}, deployable)
    _, bad_deployable = controller._build_dispatch_token(
        "m1", 1, source, target, camera, None)
    assert bad_camera == "STALE_PROPOSAL:camera-unknown"
    assert bad_deployable == "STALE_PROPOSAL:deployable-unknown"


@pytest.mark.parametrize("inbound,reason", [
    (None, "inbound-collection-unknown"),
    ({"length": None, "entries": []}, "inbound-collection-incomplete"),
    ({"length": 1, "entries": []}, "inbound-collection-incomplete"),
    ({"length": 1, "entries": [{"owner_id": 12}]},
     "inbound-force-owner-unresolved"),
])
def test_live_dispatch_fails_closed_on_unknown_source_inbound(
        tmp_path, inbound, reason):
    controller = make_controller(tmp_path)

    async def snapshot_collections(tower_ref):
        return {"match_id": "m1", "captured_at": time.time(),
                "collections": {
            "inbound": inbound,
            "outbound": {"length": 0, "entries": []}}}

    controller.snapshot_collections = snapshot_collections
    phase, info = asyncio.run(controller.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert info["match_id"] == "m1"
    assert info["reason"] == "SOURCE_SAFETY_" + reason
    assert controller.app.execute_calls == []
    assert controller.journal["last_source_safety"]["result"] == "UNKNOWN"


def test_live_dispatch_accepts_inbound_force_only_with_verified_self_id(tmp_path):
    controller = make_controller(tmp_path)
    controller._select_player_id_match("m1")
    controller._player_ids.observe("SELF", 5)
    units = {name: 0 for name in (
        "Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
        "Shell", "Emp", "Nuke", "Ruler")}
    units["Soldier"] = 1

    async def snapshot_collections(tower_ref):
        inbound = ({"length": 1, "entries": [{
            "ref": 501, "owner_id": 5, "path": [1, 3], "units": units,
            "speed_flag": 0, "progress": 0, "endurance": 20}]}
                   if tower_ref == 11 else {"length": 0, "entries": []})
        return {"match_id": "m1", "captured_at": time.time(),
                "collections": {
            "inbound": inbound,
            "outbound": {"length": 0, "entries": []}}}

    controller.snapshot_collections = snapshot_collections
    phase, info = asyncio.run(controller.cycle_once())

    assert phase == "PRECHECK_REJECTED", info
    assert info["reason"] == "test-stop"
    assert len(controller.app.execute_calls) == 1
    assert controller.journal["last_source_safety"]["result"] == "SAFE"


def test_live_dispatch_rejects_self_id_force_from_nonself_origin(tmp_path):
    controller = make_controller(tmp_path)
    controller._select_player_id_match("m1")
    controller._player_ids.observe("SELF", 5)
    units = {name: 0 for name in (
        "Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
        "Shell", "Emp", "Nuke", "Ruler")}
    units["Soldier"] = 1

    async def snapshot_collections(tower_ref):
        inbound = ({"length": 1, "entries": [{
            "ref": 502, "owner_id": 5, "path": [1, 2], "units": units,
            "speed_flag": 0, "progress": 0, "endurance": 20}]}
                   if tower_ref == 11 else {"length": 0, "entries": []})
        return {"match_id": "m1", "captured_at": time.time(),
                "collections": {
            "inbound": inbound,
            "outbound": {"length": 0, "entries": []}}}

    controller.snapshot_collections = snapshot_collections
    phase, info = asyncio.run(controller.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL", info
    assert info["reason"] == (
        "SOURCE_SAFETY_inbound-force-self-owner-conflicts-with-origin")
    assert controller.app.execute_calls == []
    assert controller.journal["last_source_safety"]["result"] == "UNKNOWN"


def test_overlapping_live_cycles_cannot_double_dispatch(tmp_path):
    controller = make_controller(tmp_path)

    async def yielding_snapshot(_tower_ref):
        await asyncio.sleep(0)
        return {"match_id": "m1", "captured_at": time.time(),
                "collections": {
            "inbound": {"length": 0, "entries": []},
            "outbound": {"length": 0, "entries": []}}}

    controller.snapshot_collections = yielding_snapshot

    async def run_overlapping_cycles():
        return await asyncio.gather(controller.cycle_once(),
                                    controller.cycle_once())

    results = asyncio.run(run_overlapping_cycles())

    assert all(info.get("match_id") == "m1" for _, info in results)
    assert len(controller.app.execute_calls) == 1
    assert sum(phase == "NO_SAFE_PROPOSAL"
               and info.get("reason") == "RESOURCE_RESERVED:source"
               for phase, info in results) == 1
    assert controller._reservations.holder(1) is None
    assert controller._reservations.holder(2) is None


def test_live_dispatch_fails_closed_when_source_snapshot_is_from_old_match(
        tmp_path):
    controller = make_controller(tmp_path)

    async def snapshot_collections(tower_ref):
        return {"match_id": "old-match", "captured_at": time.time(),
                "collections": {
            "inbound": {"length": 0, "entries": []},
            "outbound": {"length": 0, "entries": []}}}

    controller.snapshot_collections = snapshot_collections
    phase, info = asyncio.run(controller.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert info["match_id"] == "m1"
    assert info["reason"] == (
        "SOURCE_SAFETY_source-snapshot-match-mismatch")
    assert controller.app.execute_calls == []
