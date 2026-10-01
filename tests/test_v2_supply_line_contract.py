"""Negative contract tests for the own-only supply-line fact."""
from dataclasses import asdict, replace

import pytest

from kiomet_ai.v2.observe.extractor import normalize
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim.model import SimTower
from kiomet_ai.v2.state import Fact, Knowledge, Relation
from test_v2_observation import fact, raw


def own_raw(supply_line_present=True):
    payload = raw()
    payload["towers"][0].update(owner=7, relation="SELF")
    if supply_line_present is not _MISSING:
        payload["towers"][0]["supply_line_present"] = supply_line_present
    return payload


_MISSING = object()


def normalized(payload):
    return normalize(payload, "session", "document", 1, 101)


def test_missing_supply_line_is_unknown_and_true_false_are_preserved():
    missing = normalized(own_raw(_MISSING)).towers[0].supply_line_present
    assert missing.knowledge == Knowledge.UNKNOWN
    assert missing.value is None

    for value in (False, True):
        observed = normalized(own_raw(value)).towers[0].supply_line_present
        assert observed.value is value
        assert observed.knowledge == Knowledge.OBSERVED


@pytest.mark.parametrize("value", (0, 1, "true", [], {}))
def test_non_boolean_supply_line_input_is_rejected(value):
    with pytest.raises(ValueError, match="supply.line|supply_line|boolean"):
        normalized(own_raw(value))


@pytest.mark.parametrize(
    "owner,relation",
    ((8, "ENEMY"), (0, "NEUTRAL"), (7, "ALLY")),
)
def test_supply_line_input_is_not_accepted_for_non_self_towers(owner, relation):
    payload = raw()
    payload["towers"][0].update(
        owner=owner, relation=relation, supply_line_present=True
    )
    with pytest.raises(ValueError, match="own-only"):
        normalized(payload)


@pytest.mark.parametrize(
    "owner,relation",
    ((fact(8), fact(Relation.ENEMY)), (Fact(), Fact())),
)
def test_game_state_rejects_forged_known_flag_on_foreign_or_unknown_owner(
    owner, relation
):
    state = normalized(own_raw(_MISSING))
    tower = replace(
        state.towers[0], owner=owner, relation=relation,
        supply_line_present=fact(True),
    )
    with pytest.raises(ValueError, match="supply.line|supply_line|own"):
        replace(state, towers=(tower,))


def test_old_canonical_tower_record_defaults_missing_flag_to_unknown():
    state = normalized(own_raw(False))
    row = asdict(state)
    del row["towers"][0]["supply_line_present"]

    restored = state_from_dict(row)
    assert restored.towers[0].supply_line_present.knowledge == Knowledge.UNKNOWN
    assert restored.towers[0].supply_line_present.value is None


@pytest.mark.parametrize("value", (False, True))
def test_canonical_restore_preserves_known_false_and_true(value):
    state = normalized(own_raw(value))
    restored = state_from_dict(asdict(state))
    restored_flag = restored.towers[0].supply_line_present
    assert restored_flag.value is value
    assert restored_flag.knowledge == Knowledge.OBSERVED


def test_sim_tower_default_is_unknown_and_explicit_false_is_preserved():
    legacy_positional = SimTower(3, 7, 14, (0,) * 10, (0,) * 10, (), (),
                                (100, 200), 0, False)
    assert legacy_positional.supply_line_present is None
    explicit_false = SimTower(3, 7, 14, (0,) * 10, (0,) * 10, (), (),
                              (100, 200), 0, False,
                              supply_line_present=False)
    assert explicit_false.supply_line_present is False
