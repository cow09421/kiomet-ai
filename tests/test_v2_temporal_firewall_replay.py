from __future__ import annotations

from types import SimpleNamespace

from tools import v2_external_action_replay as prior
from tools import v2_temporal_firewall_replay as firewall


def _fact(value, knowledge="OBSERVED"):
    return {"value": value, "knowledge": knowledge}


def _raw_tower(units=(0, 0), *, owner=4, relation="SELF"):
    counts = [[i, units[i] if i < len(units) else 0] for i in range(10)]
    return {"id": 10, "visibility": _fact(True), "owner": _fact(owner),
            "relation": _fact(relation), "units": _fact({"counts": counts}),
            "production": _fact([]), "tower_type": _fact(1),
            "effects": _fact([["MORALE_BOOST", False]])}


def _raw_force(force_id="force-1", progress=0, *, units=(0, 2)):
    counts = [[i, units[i] if i < len(units) else 0] for i in range(10)]
    return {"id": _fact(force_id, "DERIVED"), "confidence": _fact("NEW_TRACK" if progress == 0 else "UNIQUE_CONTINUATION", "DERIVED"),
            "visibility": _fact(True), "owner": _fact(4), "source": _fact(10), "destination": _fact(11),
            "relation": _fact("SELF"), "unit_count": _fact(sum(units), "DERIVED"),
            "units": _fact({"counts": counts}), "progress": _fact(progress)}


def _record(sequence, towers, forces=()):
    return {"sequence": sequence, "tick": _fact(sequence), "towers": towers,
            "forces": _fact(list(forces))}


def test_real_raw_schema_direct_tower_ids_and_force_fact_collection():
    before = _record(1, [_raw_tower()], [_raw_force(progress=1)])
    after = _record(2, [_raw_tower()], [_raw_force(progress=2)])
    result = firewall.classify_future_transition(before, after)
    assert result["event_tags"] == ["MOVEMENT", "MOVEMENT_ONLY"]
    assert "UNKNOWN" not in result["event_tags"]


def test_static_transition_is_stable_not_movement_or_event():
    row = _record(1, [_raw_tower()])
    result = firewall.classify_future_transition(row, _record(2, [_raw_tower()]))
    assert result["event_tags"] == ["STABLE"]


def test_production_tag_requires_exact_deterministic_unit_prediction(monkeypatch):
    before = _record(1, [_raw_tower((0, 2))])
    after = _record(2, [_raw_tower((0, 3))])
    before_state = SimpleNamespace(towers=(SimpleNamespace(id=10, units=(0, 2)),))
    after_state = SimpleNamespace(towers=(SimpleNamespace(id=10, units=(0, 3)),))
    monkeypatch.setattr(firewall, "from_canonical", lambda state: {"before": before_state, "after": after_state}[state])
    monkeypatch.setattr(firewall, "step", lambda state: after_state)
    result = firewall.classify_future_transition(before, after, "before", "after")
    assert "PRODUCTION" in result["event_tags"]
    assert "UNKNOWN" not in result["event_tags"]


def test_replay_case_freezes_birth_pair_action_while_mutated_future_changes_forecast(monkeypatch):
    class State:
        def __init__(self, n, towers=()):
            self.n, self.towers, self.player = n, towers, 4
            self.world_sequence = n

    def canonical(tick, observed_n):
        return SimpleNamespace(tick=SimpleNamespace(value=tick), document_id="d",
            match_id=SimpleNamespace(value="m"), player_id=SimpleNamespace(value=4),
            observed_n=observed_n, sampled_at_ms=tick * 250)

    source_before = SimpleNamespace(id=10, units=(0, 5, 0, 0, 0, 0, 0, 0, 0, 0),
        owner=4, kind=1, morale=False, neighbors=(11,))
    source_after = SimpleNamespace(id=10, units=(0, 5, 0, 0, 0, 0, 0, 0, 0, 0),
        owner=4, kind=1, morale=False, neighbors=(11,))
    destination = SimpleNamespace(id=11, units=(0,) * 10, owner=4, kind=1,
        morale=False, neighbors=(10,))
    before_can, birth_can = canonical(1, 1), canonical(2, 2)
    future1_can, future2_can = canonical(3, 3), canonical(4, 4)
    before_raw = {"sequence": 7, "towers": [_raw_tower((0, 5)), {**_raw_tower((0, 0)), "id": 11}],
                  "forces": _fact([])}
    birth_raw = {"sequence": 8, "towers": [_raw_tower((0, 3)), {**_raw_tower((0, 0)), "id": 11}],
                 "forces": _fact([_raw_force(progress=0)])}
    future1_raw = {"sequence": 9, "towers": birth_raw["towers"],
                   "forces": _fact([_raw_force(progress=1)])}
    future2_raw = {"sequence": 10, "towers": birth_raw["towers"],
                   "forces": _fact([_raw_force(progress=2)])}
    rows = [(before_raw, before_can), (birth_raw, birth_can),
            (future1_raw, future1_can), (future2_raw, future2_can)]

    # Keep the production/action classifier real; replace only the model boundary
    # with small deterministic states so replay_case can be tested cheaply.
    def model_for(canonical_row):
        source = source_before if canonical_row is before_can else source_after
        return State(canonical_row.tick.value, (source, destination))
    monkeypatch.setattr(firewall.prior, "from_canonical", model_for)
    monkeypatch.setattr(firewall.prior, "step", lambda state: state)
    monkeypatch.setattr(firewall, "from_canonical", lambda c: State(c.observed_n, (source_after, destination)))
    monkeypatch.setattr(firewall, "step", lambda state: State(state.n + 1, state.towers))
    monkeypatch.setattr(firewall.prior, "_apply_injected_step",
                        lambda state, _actions: State(state.n + 1, state.towers))
    monkeypatch.setattr(firewall.prior, "_error_summary",
        lambda predicted, observed: {"matches": predicted.n == observed.n,
            "first_differences": [] if predicted.n == observed.n else [{"field": "n"}]})

    original = firewall.replay_case({"cohort": "c", "trajectory_start_sequence": 7,
        "mismatch_sequence": 8}, rows, 1)
    mutated_rows = list(rows)
    mutated_rows[2] = ({**future1_raw, "forces": _fact([_raw_force(progress=77)])},
                       canonical(3, 100))
    mutated_rows[3] = ({**future2_raw, "forces": _fact([_raw_force(progress=88)])},
                       canonical(4, 200))
    mutated = firewall.replay_case({"cohort": "c", "trajectory_start_sequence": 7,
        "mismatch_sequence": 8}, mutated_rows, 1)

    assert original["action_inference"] == mutated["action_inference"]
    assert original["action_inference"]["status"] == "UNIQUE"
    assert original["action_inference"]["unit_vector"][1] == 2
    assert original["future_forecast"]["first_future_divergence"] is None
    assert mutated["future_forecast"]["first_future_divergence"] is not None


def test_decision_metrics_never_claim_capture_from_owner_agreement():
    predicted = SimpleNamespace(towers=[SimpleNamespace(id=11, owner=4, units=(0, 2))])
    observed = SimpleNamespace(towers=[SimpleNamespace(id=11, owner=4, units=(0, 2))])
    metrics = firewall._decision_metrics(predicted, observed, 11)
    assert metrics["target_owner_agreement"] is True
    assert metrics["capture_result_correct"] is None
    assert metrics["capture_result_eligible"] is False


def test_birth_tick_is_excluded_and_prediction_advances_without_reset(monkeypatch):
    class State:
        def __init__(self, n):
            self.n = n
            self.world_sequence = n
            self.towers = ()

    def canonical(tick):
        return SimpleNamespace(tick=SimpleNamespace(value=tick), document_id="d",
            match_id=SimpleNamespace(value="m"), player_id=SimpleNamespace(value=4),
            sample_time=tick)

    start, birth, future1, future2 = canonical(10), canonical(11), canonical(12), canonical(13)
    rows = [({"sequence": i + 1}, c) for i, c in enumerate((start, birth, future1, future2))]
    calls = []
    applied = []
    monkeypatch.setattr(firewall, "from_canonical", lambda c: State(0) if c is start else State(c.tick.value))

    def advance(state):
        calls.append(state.n)
        return State(state.n + 1)

    monkeypatch.setattr(firewall, "step", advance)
    monkeypatch.setattr(firewall.prior, "_apply_injected_step", lambda state, _actions: (applied.append(state.n) or State(state.n + 1)))
    monkeypatch.setattr(firewall.prior, "_birth_candidates", lambda *_: ([], None))
    monkeypatch.setattr(firewall.prior, "_error_summary", lambda *_: {"matches": True, "first_differences": []})
    result = firewall.simulate_continuous(start, rows, 1, [{"destination": 11}], 3)
    assert applied == [0]
    assert calls == [1, 2]
    assert [row["future_tick_offset_from_birth"] for row in result["error_growth"]] == [1, 2]
    assert result["birth_tick_scored"] is False
    assert result["continuous_prediction_no_reset"] is True
