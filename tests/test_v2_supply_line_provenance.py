"""Provenance checks for canonical and compact supply-line presence."""
import pytest

from kiomet_ai.v2.observe.extractor import normalize
from kiomet_ai.v2.sim.model import SimTower, SimulationState
from kiomet_ai.v2.state import Fact, GameState, Knowledge, Relation, Tower
from test_v2_observation import raw


def known_flag(value, knowledge=Knowledge.OBSERVED):
    return Fact(value, knowledge, "test evidence", 10)


def canonical_tower(flag):
    return Tower(
        4,
        visibility=known_flag(True),
        supply_line_present=flag,
    )


def sim_tower(owner, supply_line_present, relation=None):
    return SimTower(
        4, owner, 1, (0,) * 10, (0,) * 10, (), (), (0, 0), 0, False,
        relation=relation, supply_line_present=supply_line_present,
    )


def sim_state(player, tower):
    return SimulationState(1, player, "match", "document", (tower,), ())


def canonical_state(player, owner):
    return GameState(
        "session", "document", Fact(), 1, 10, 10, "sha",
        player_id=known_flag(player),
        towers=(Tower(4, known_flag(True), owner=known_flag(owner),
                      relation=known_flag(Relation.SELF),
                      supply_line_present=known_flag(False)),),
    )


@pytest.mark.parametrize("value", (False, True))
def test_canonical_known_supply_line_requires_observed_provenance(value):
    accepted = canonical_tower(known_flag(value))
    assert accepted.supply_line_present.value is value

    with pytest.raises(ValueError, match="supply-line presence must be observed"):
        canonical_tower(known_flag(value, Knowledge.DERIVED))


@pytest.mark.parametrize("value", (False, True))
def test_simulation_state_accepts_known_presence_for_owned_tower(value):
    # Ownership is authoritative here; relation may still be stale during capture.
    state = sim_state(7, sim_tower(7, value, relation="ENEMY"))
    assert state.towers[0].supply_line_present is value


@pytest.mark.parametrize(
    "player,owner",
    ((7, 8), (7, 0), (0, 0)),
)
def test_simulation_state_rejects_known_presence_without_positive_own_owner(
    player, owner
):
    with pytest.raises(ValueError, match="supply-line presence is own-only"):
        sim_state(player, sim_tower(owner, False))


def test_simulation_state_keeps_missing_legacy_presence_unknown():
    state = sim_state(0, sim_tower(8, None))
    assert state.towers[0].supply_line_present is None


@pytest.mark.parametrize(
    "player,owner",
    ((1, True), (True, 1), (-1, -1), ("1", "1"), (1.0, 1.0)),
)
def test_canonical_known_presence_requires_exact_positive_integer_identity(
    player, owner
):
    with pytest.raises(ValueError, match="supply-line presence is own-only"):
        canonical_state(player, owner)


def test_canonical_known_false_accepts_exact_positive_own_identity():
    state = canonical_state(1, 1)
    assert state.towers[0].supply_line_present.value is False


@pytest.mark.parametrize(
    "player,owner",
    ((1, True), (True, 1), (-1, -1), ("1", "1"), (1.0, 1.0)),
)
def test_simulation_state_known_presence_requires_exact_positive_integer_identity(
    player, owner
):
    with pytest.raises(ValueError, match="supply-line presence is own-only"):
        sim_state(player, sim_tower(owner, False))


def test_normalize_rejects_boolean_player_id_for_known_own_presence():
    payload = raw()
    payload["player_id"] = True
    payload["towers"][0].update(
        owner=1, relation="SELF", supply_line_present=False
    )

    with pytest.raises(ValueError, match="supply-line presence is own-only"):
        normalize(payload, "session", "document", 1, 101)
