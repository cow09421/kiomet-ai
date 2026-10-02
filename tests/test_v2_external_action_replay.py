from __future__ import annotations

from types import SimpleNamespace
import json

from tools import v2_external_action_replay as replay


def _fact(value, knowledge="OBSERVED"):
    return {"value": value, "knowledge": knowledge}


def _force(identifier, *, confidence="NEW_TRACK", visible=True, progress=0):
    return {
        "id": _fact(identifier, "DERIVED"),
        "confidence": _fact(confidence, "DERIVED"),
        "visibility": _fact(visible),
        "progress": _fact(progress),
        "owner": _fact(3),
        "source": _fact(10),
        "destination": _fact(11),
        "relation": _fact("SELF"),
        "unit_count": _fact(2, "DERIVED"),
        "units": _fact({"counts": [[i, 2 if i == 1 else 0] for i in range(10)]}),
    }


def _snapshot(forces):
    return {"forces": _fact(forces)}


def test_new_visible_new_track_progress_zero_is_candidate_birth():
    births, error = replay._birth_candidates(_snapshot([]), _snapshot([_force("f1")]))
    assert error is None
    assert births[0]["units"][1] == 2
    assert births[0]["snapshot_birth_order"] == 0


def test_missing_observer_id_fails_closed_instead_of_ignoring_force():
    malformed = _force(None)
    births, error = replay._birth_candidates(_snapshot([]), _snapshot([malformed]))
    assert births == []
    assert error == "AFTER_FORCE_OBSERVER_ID_UNAVAILABLE"


def test_missing_before_observer_id_fails_closed():
    malformed = _force(None)
    births, error = replay._birth_candidates(_snapshot([malformed]), _snapshot([]))
    assert births == []
    assert error == "BEFORE_FORCE_OBSERVER_ID_UNAVAILABLE"


def test_unobserved_visibility_fails_closed_for_force_birth():
    births, error = replay._birth_candidates(
        _snapshot([]), _snapshot([_force("f1", visible=False)]))
    assert births == []
    assert error == "FORCE_VISIBILITY_NOT_OBSERVED"


def _model_tower(identifier, units, *, owner=3, kind=1, morale=False, neighbors=()):
    return SimpleNamespace(id=identifier, units=tuple(units), owner=owner, kind=kind,
                           morale=morale, neighbors=tuple(neighbors))


def _raw_tower(identifier, units, *, owner=3, kind=1, morale=False, visible=True):
    return {"id": identifier, "visibility": _fact(visible), "owner": _fact(owner),
            "tower_type": _fact(kind), "effects": _fact([["MORALE_BOOST", morale]]),
            "units": _fact({"counts": [[i, n] for i,n in enumerate(units)]})}


def test_exact_source_conservation_uses_no_action_delta_after_production():
    before_units=(0,5,0,0,0,0,0,0,0,0)
    observed_units=(0,3,0,0,0,0,0,0,0,0)
    no_action_units=(0,6,0,0,0,0,0,0,0,0)
    source_before=_model_tower(10,before_units,neighbors=(11,))
    source_after=_model_tower(10,no_action_units,neighbors=(11,))
    dest=_model_tower(11,(0,0,0,0,0,0,0,0,0,0))
    before_state=SimpleNamespace(towers=(source_before,dest),player=3)
    no_action=SimpleNamespace(towers=(source_after,dest))
    raw_before={"towers":[_raw_tower(10,before_units),_raw_tower(11,dest.units)]}
    raw_after={"towers":[_raw_tower(10,observed_units),_raw_tower(11,dest.units)]}
    birth={"owner":3,"source":10,"destination":11,"units":(0,3,0,0,0,0,0,0,0,0)}
    actions,reason,proof=replay._exact_launch_actions(raw_before,raw_after,before_state,no_action,[birth])
    assert reason is None and actions[0]["evidence_grade"] == "B"
    assert proof[0]["raw_before_to_observed_after_source_delta"][1] == 2
    assert proof[0]["deterministic_no_action_to_observed_source_delta"][1] == 3


def test_nonconserving_source_delta_stays_unknown():
    before_units=(0,5,0,0,0,0,0,0,0,0)
    observed_units=(0,4,0,0,0,0,0,0,0,0)
    no_action_units=(0,6,0,0,0,0,0,0,0,0)
    source_before=_model_tower(10,before_units,neighbors=(11,))
    source_after=_model_tower(10,no_action_units,neighbors=(11,))
    dest=_model_tower(11,(0,0,0,0,0,0,0,0,0,0))
    before_state=SimpleNamespace(towers=(source_before,dest),player=3)
    no_action=SimpleNamespace(towers=(source_after,dest))
    raw_before={"towers":[_raw_tower(10,before_units),_raw_tower(11,dest.units)]}
    raw_after={"towers":[_raw_tower(10,observed_units),_raw_tower(11,dest.units)]}
    birth={"owner":3,"source":10,"destination":11,"units":(0,3,0,0,0,0,0,0,0,0)}
    actions,reason,_=replay._exact_launch_actions(raw_before,raw_after,before_state,no_action,[birth])
    assert actions is None
    assert reason == "SOURCE_DELTA_DOES_NOT_EXACTLY_MATCH_BIRTHS"


def test_truncated_observation_window_cannot_claim_full_horizon(monkeypatch):
    before = SimpleNamespace(tick=SimpleNamespace(value=1), document_id="d",
                             match_id=SimpleNamespace(value="m"), player_id=SimpleNamespace(value=3))
    after = SimpleNamespace(tick=SimpleNamespace(value=2), document_id="d",
                            match_id=SimpleNamespace(value="m"), player_id=SimpleNamespace(value=3))
    observed = SimpleNamespace(world_sequence=2)
    monkeypatch.setattr(replay, "from_canonical", lambda _: observed)
    monkeypatch.setattr(replay, "step", lambda state: state)
    monkeypatch.setattr(replay, "_error_summary", lambda *_: {"matches": True, "first_differences": []})
    rows = [({"sequence": 10}, before), ({"sequence": 11}, after)]
    result = replay._run_branch(object(), rows, [[]], limit=1, inject=False, requested_limit=20)
    assert result["simulated_and_compared_ticks"] == 1
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == "OBSERVATION_GAP"
    assert result["full_trajectory_match"] is False


def test_replay_branch_advances_its_prediction_without_reset(monkeypatch):
    calls = []
    before = SimpleNamespace(tick=SimpleNamespace(value=1), document_id="d",
                             match_id=SimpleNamespace(value="m"), player_id=SimpleNamespace(value=3))
    middle = SimpleNamespace(tick=SimpleNamespace(value=2), document_id="d",
                             match_id=SimpleNamespace(value="m"), player_id=SimpleNamespace(value=3))
    after = SimpleNamespace(tick=SimpleNamespace(value=3), document_id="d",
                            match_id=SimpleNamespace(value="m"), player_id=SimpleNamespace(value=3))
    class State:
        def __init__(self, n): self.n=n; self.world_sequence=n
    observed = {2: State(100), 3: State(200)}
    monkeypatch.setattr(replay, "from_canonical", lambda canonical: observed[canonical.tick.value])
    def advance(state):
        calls.append(state.n)
        return State(state.n + 1)
    monkeypatch.setattr(replay, "step", advance)
    monkeypatch.setattr(replay, "_error_summary", lambda *_: {"matches": True, "first_differences": []})
    rows = [({"sequence": 10}, before), ({"sequence": 11}, middle), ({"sequence": 12}, after)]
    result = replay._run_branch(State(1), rows, [[], []], limit=2, inject=False, requested_limit=2)
    assert calls == [1, 2]
    assert result["full_trajectory_match"] is True


def test_replay_branch_stops_when_scope_changes_even_if_signatures_match(monkeypatch):
    def canonical(tick, match="m"):
        return SimpleNamespace(tick=SimpleNamespace(value=tick), document_id="d",
                               match_id=SimpleNamespace(value=match),
                               player_id=SimpleNamespace(value=3))
    class State:
        world_sequence = 1
    monkeypatch.setattr(replay, "from_canonical", lambda _: State())
    monkeypatch.setattr(replay, "step", lambda state: state)
    monkeypatch.setattr(replay, "_error_summary", lambda *_: {"matches": True, "first_differences": []})
    rows = [({"sequence": 1}, canonical(1)), ({"sequence": 2}, canonical(2)),
            ({"sequence": 3}, canonical(3, "other"))]
    result = replay._run_branch(State(), rows, [[], []], limit=2, inject=False, requested_limit=2)
    assert result["simulated_and_compared_ticks"] == 1
    assert result["status"] == "PARTIAL"
    assert result["stop_reason"] == "OBSERVATION_SCOPE_CHANGED"
    assert result["full_trajectory_match"] is False


def test_snapshot_hash_slash_key_mismatch_blocks_all_case_replay(monkeypatch):
    audit = json.loads(replay.AUDIT_PATH.read_text(encoding="utf-8"))
    trajectories = json.loads(replay.TRAJECTORIES_PATH.read_text(encoding="utf-8"))
    audit["source_sha256"][audit["failures"][0]["before"]["file"]] = "0" * 64
    original_read_text = type(replay.AUDIT_PATH).read_text
    def fake_read_text(path, *args, **kwargs):
        if path == replay.AUDIT_PATH:
            return "AUDIT"
        if path == replay.TRAJECTORIES_PATH:
            return "TRAJECTORIES"
        return original_read_text(path, *args, **kwargs)
    monkeypatch.setattr(type(replay.AUDIT_PATH), "read_text", fake_read_text)
    monkeypatch.setattr(replay.json, "loads", lambda value: audit if value == "AUDIT" else trajectories)

    def collect(path, specs, horizon):
        return {index: [] for index, _ in specs}, "a" * 64
    monkeypatch.setattr(replay, "_collect_case_windows", collect)
    monkeypatch.setattr(replay, "_sha256", lambda _path: "b" * 64)
    monkeypatch.setattr(replay, "replay_case", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("replay_case called")))
    result = replay.run_replay(replay.ROOT / "runtime/research/v2/provenance-negative-test.json")
    assert result["status"] == "SNAPSHOT_PROVENANCE_MISMATCH_FAIL_CLOSED"
    assert result["total_cases"] == 13
    assert result["grade_c"] == 13
    assert all(case["injected_action_replay"]["status"] == "NOT_REPLAYABLE" for case in result["cases"])
