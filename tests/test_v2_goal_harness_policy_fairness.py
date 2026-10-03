"""Adversarial checks that evaluator-only fields stay outside chooser input."""
import copy

import pytest

import tools.v2_goal_decision_harness as harness


def _case():
    return {
        "case_id": "visible-case",
        "stratum": "S2",
        "start_tick": 1,
        "horizon_ticks": 120,
        "player": 1,
        "alive": {"1": True, "2": True},
        "closed_by_construction": True,
        "towers": [
            {"id": 10, "xy": [1, 1], "kind": 3, "owner": 1,
             "units": [0, 0, 0, 0, 0, 4, 0, 0, 0, 0],
             "delay": 0, "supply": False, "visible": True},
            {"id": 11, "xy": [1, 2], "kind": 4, "owner": 2,
             "units": [0] * 10, "delay": 0, "supply": False, "visible": True},
            {"id": 12, "xy": [0, 2], "kind": 7, "owner": None,
             "units": [0] * 10, "delay": 0, "supply": False, "visible": True},
        ],
        "forces": [
            {"owner": 2, "src": 11, "dst": 10, "progress": 17, "fuel": 150,
             "units": [0, 0, 0, 0, 0, 2, 0, 0, 0, 0], "visible": True},
        ],
        "future_opponents": [],
    }


def _run_policy_without_evaluation(monkeypatch, case):
    seen = []
    monkeypatch.setattr(harness, "evaluate", lambda _case, _choice: {"status": "STUB"})

    def choose(view, legal_choices):
        seen.append((view, legal_choices))
        return legal_choices[0]

    result = harness.run_policy(case, choose)
    assert result["status"] == "STUB"
    assert len(seen) == 1
    return seen[0], result["policy_input"]


def _mutate_force_field(field, value):
    def mutate(case):
        case["forces"][0][field] = value
    return mutate


def _mutate_enemy_supply(value, *, remove=False):
    def mutate(case):
        if remove:
            case["towers"][1].pop("supply", None)
        else:
            case["towers"][1]["supply"] = value
    return mutate


@pytest.mark.parametrize("mutation", [
    _mutate_force_field("owner", "owner-secret-91"),
    _mutate_force_field("src", "source-secret-92"),
    _mutate_force_field("dst", "destination-secret-93"),
    _mutate_force_field("progress", {"progress_secret": 94}),
    _mutate_force_field("fuel", "fuel-secret-95"),
    _mutate_force_field("units", [0, 0, 0, 0, 0, 88, 0, 0, 0, 0]),
    _mutate_force_field("future_route", ["future-secret-97"]),
    _mutate_enemy_supply(True),
    _mutate_enemy_supply("supply-secret-99"),
    _mutate_enemy_supply(None, remove=True),
    lambda c: c.update(future_opponents=[{"source": "future-100", "target": "future-101"}]),
    lambda c: c.update(stratum="latent-stratum-102"),
    lambda c: c.update(case_id="latent-case-103"),
    lambda c: c.update(alive={"1": False, "2": "latent-alive-104"}),
])
def test_latent_enemy_fields_do_not_change_policy_view_or_callback_input(monkeypatch, mutation):
    base = _case()
    changed = copy.deepcopy(base)
    mutation(changed)

    base_seen, base_input = _run_policy_without_evaluation(monkeypatch, base)
    changed_seen, changed_input = _run_policy_without_evaluation(monkeypatch, changed)

    assert base_seen == changed_seen
    assert base_input == changed_input
    assert len(base_seen[1]) >= 2
    assert len(base_seen[0].forces) == 1
    force = base_seen[0].forces[0]
    assert force.visible is True
    assert (force.owner, force.source, force.target, force.progress, force.units) == (None,) * 5
    assert not hasattr(force, "fuel")
    assert base_seen[0].towers[1].supply is None
    assert base_input["forces"] == ({
        "visible": True, "owner": None, "source": None, "target": None,
        "progress": None, "units": None,
    },)
    assert base_seen[0].towers[2].supply is None


def test_hidden_force_row_is_skipped_without_reading_other_fields():
    case = _case()
    hidden = {"visible": False, "owner": ["secret"], "src": {"secret": 1},
              "dst": object(), "progress": object(), "fuel": object(), "units": object()}
    baseline = harness.visible_state(case)
    case["forces"].append(hidden)
    assert harness.visible_state(case) == baseline


def test_force_without_explicit_visibility_refuses_policy_callback():
    case = _case()
    case["forces"][0].pop("visible")
    callbacks = []
    result = harness.run_policy(case, lambda view, choices: callbacks.append((view, choices)))
    assert result["status"] == "UNSUPPORTED"
    assert callbacks == []


def test_own_supply_presence_remains_in_current_view():
    case = _case()
    case["towers"][0]["supply"] = True
    view = harness.visible_state(case)
    assert view.towers[0].supply is True
