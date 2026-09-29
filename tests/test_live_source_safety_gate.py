"""Source-safety adapter tests; these use no browser or live runtime."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.live_controller import LiveController
from kiomet_ai.observe import UNIT_NAMES


def make_controller():
    return LiveController(SimpleNamespace(root=Path("."), browser=None))


def make_source(**overrides):
    values = {
        "match_id": "match-1", "tower_id": 1,
        "unit_counts": SimpleNamespace(
            units_kind="MANY", shield=11, fighter=4, chopper=1,
            bomber=2, tank=3, soldier=9),
        "owner_ruler": False, "tower_type": "Cliff",
        "freshness": lambda match_id, _now: (
            "FRESH" if match_id == "match-1" else "STALE"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def clear_snapshot():
    return {"match_id": "match-1", "captured_at": time.time(),
            "collections": {
        "inbound": {"length": 0, "entries": []}}}


def proposal(**overrides):
    values = {name: 0 for name in UNIT_NAMES}
    values.update(overrides)
    return values


def test_adapter_passes_exact_post_dispatch_defenders_to_evaluator(monkeypatch):
    import kiomet_ai.pvp_live as pvp_live

    captured = {}

    def evaluate(defenders, threats, capacities, tower_type,
                 self_id=None, enemy_id=None):
        captured.update(defenders=defenders, threats=threats,
                        capacities=capacities, tower_type=tower_type,
                        self_id=self_id, enemy_id=enemy_id)
        return {"result": "SAFE"}

    monkeypatch.setattr(pvp_live, "evaluate_source_safety", evaluate)
    controller = make_controller()

    result = controller.evaluate_live_source_safety(
        "match-1", make_source(), clear_snapshot(),
        proposal(Fighter=1, Soldier=2))

    assert result["result"] == "SAFE"
    assert captured["defenders"] == {
        "Shield": 11, "Fighter": 3, "Chopper": 1, "Bomber": 2,
        "Tank": 3, "Soldier": 7, "Shell": 0, "Emp": 0,
        "Nuke": 0, "Ruler": 0}
    assert captured["threats"] == []
    assert captured["tower_type"] == "Cliff"


def test_verified_self_inbound_force_is_accepted_without_becoming_a_threat(
        monkeypatch):
    import kiomet_ai.pvp_live as pvp_live

    calls = []
    monkeypatch.setattr(pvp_live, "evaluate_source_safety",
                        lambda defenders, threats, *args, **kwargs:
                        calls.append((defenders, threats)) or {"result": "SAFE"})
    controller = make_controller()
    controller._select_player_id_match("match-1")
    controller._player_ids.observe("SELF", 5)
    units = {name: 0 for name in UNIT_NAMES}
    units["Soldier"] = 1
    snapshot = {"match_id": "match-1", "captured_at": time.time(),
                "collections": {
        "inbound": {"length": 1, "entries": [{
            "owner_id": 5, "path": [1, 2], "units": units}]}}}

    result = controller.evaluate_live_source_safety(
        "match-1", make_source(), snapshot, proposal())

    assert result["result"] == "SAFE"
    assert len(calls) == 1
    assert calls[0][1] == []


@pytest.mark.parametrize("origin_state", [
    None,
    SimpleNamespace(
        match_id="match-1", tower_id=2, owner="ENEMY",
        freshness=lambda match_id, _now: (
            "FRESH" if match_id == "match-1" else "STALE")),
    SimpleNamespace(
        match_id="match-1", tower_id=2, owner="SELF",
        freshness=lambda _match_id, _now: "STALE"),
])
def test_self_id_inbound_requires_fresh_self_owned_origin(
        origin_state, monkeypatch):
    import kiomet_ai.pvp_live as pvp_live

    monkeypatch.setattr(
        pvp_live, "evaluate_source_safety",
        lambda *_args, **_kwargs: pytest.fail(
            "contradictory inbound owner evidence reached the evaluator"))
    controller = make_controller()
    controller._select_player_id_match("match-1")
    controller._player_ids.observe("SELF", 5)
    units = {name: 0 for name in UNIT_NAMES}
    units["Soldier"] = 1
    snapshot = {"match_id": "match-1", "captured_at": time.time(),
                "collections": {
        "inbound": {"length": 1, "entries": [{
            "owner_id": 5, "path": [1, 2], "units": units}]}}}
    states = {} if origin_state is None else {2: origin_state}

    result = controller.evaluate_live_source_safety(
        "match-1", make_source(), snapshot, proposal(),
        tower_states_by_id=states)

    assert result == {
        "result": "UNKNOWN",
        "reason": "inbound-force-self-owner-conflicts-with-origin"}


def test_self_id_inbound_accepts_fresh_self_owned_origin(monkeypatch):
    import kiomet_ai.pvp_live as pvp_live

    calls = []
    monkeypatch.setattr(
        pvp_live, "evaluate_source_safety",
        lambda defenders, threats, *args, **kwargs:
        calls.append((defenders, threats)) or {"result": "SAFE"})
    controller = make_controller()
    controller._select_player_id_match("match-1")
    controller._player_ids.observe("SELF", 5)
    units = {name: 0 for name in UNIT_NAMES}
    units["Soldier"] = 1
    snapshot = {"match_id": "match-1", "captured_at": time.time(),
                "collections": {
        "inbound": {"length": 1, "entries": [{
            "owner_id": 5, "path": [1, 2], "units": units}]}}}
    origin = SimpleNamespace(
        match_id="match-1", tower_id=2, owner="SELF",
        freshness=lambda match_id, _now: (
            "FRESH" if match_id == "match-1" else "STALE"))

    result = controller.evaluate_live_source_safety(
        "match-1", make_source(), snapshot, proposal(),
        tower_states_by_id={2: origin})

    assert result["result"] == "SAFE"
    assert len(calls) == 1
    assert calls[0][1] == []


@pytest.mark.parametrize("timestamp_case", ["missing", "malformed", "stale", "future"])
def test_source_safety_rejects_unknown_or_stale_snapshot_timestamp(
        timestamp_case, monkeypatch):
    import kiomet_ai.pvp_live as pvp_live

    monkeypatch.setattr(
        pvp_live, "evaluate_source_safety",
        lambda *_args, **_kwargs: pytest.fail(
            "snapshot without fresh timing evidence reached the evaluator"))
    snapshot = clear_snapshot()
    if timestamp_case == "missing":
        snapshot.pop("captured_at")
    elif timestamp_case == "malformed":
        snapshot["captured_at"] = True
    elif timestamp_case == "stale":
        snapshot["captured_at"] = time.time() - 31.0
    else:
        snapshot["captured_at"] = time.time() + 2.0

    result = make_controller().evaluate_live_source_safety(
        "match-1", make_source(), snapshot, proposal())

    assert result == {
        "result": "UNKNOWN",
        "reason": "source-snapshot-time-unknown-or-stale"}


@pytest.mark.parametrize("snapshot", [
    {"match_id": "match-1", "collections": {}},
    {"match_id": "match-1", "collections": {
        "inbound": {"length": None, "entries": []}}},
    {"match_id": "match-1", "collections": {
        "inbound": {"length": 2, "entries": []}}},
    {"match_id": "match-2", "collections": {
        "inbound": {"length": 0, "entries": []}}},
])
def test_unknown_or_stale_inbound_evidence_abstains(snapshot, monkeypatch):
    import kiomet_ai.pvp_live as pvp_live

    monkeypatch.setattr(
        pvp_live, "evaluate_source_safety",
        lambda *_args, **_kwargs: pytest.fail("unknown evidence reached evaluator"))
    result = make_controller().evaluate_live_source_safety(
        "match-1", make_source(), snapshot, proposal())

    assert result["result"] == "UNKNOWN"


@pytest.mark.parametrize("source,units,reason", [
    (make_source(owner_ruler=None), proposal(),
     "source-force-vector-unknown"),
    (make_source(), {**proposal(), "Soldier": -1},
     "source-force-vector-unknown"),
    (make_source(), {name: 0 for name in UNIT_NAMES[:-1]},
     "source-force-vector-unknown"),
    (make_source(), proposal(Ruler=1),
     "source-special-dispatch-unsupported"),
])
def test_unknown_composition_and_invalid_proposal_abstain(
        source, units, reason, monkeypatch):
    import kiomet_ai.pvp_live as pvp_live

    monkeypatch.setattr(
        pvp_live, "evaluate_source_safety",
        lambda *_args, **_kwargs: pytest.fail("invalid data reached evaluator"))
    result = make_controller().evaluate_live_source_safety(
        "match-1", source, clear_snapshot(), units)

    assert result == {"result": "UNKNOWN", "reason": reason}


def test_resident_ruler_does_not_block_dispatch_when_no_threat_is_inbound():
    result = make_controller().evaluate_live_source_safety(
        "match-1", make_source(owner_ruler=True), clear_snapshot(),
        proposal(Fighter=1, Soldier=2))

    assert result == {"result": "SAFE",
                      "reason": "source-state-and-inbound-known"}
