from kiomet_ai.force import ForceUnits, MovingForceState
from kiomet_ai.pvp_live import threat_from_force

_DEFAULT = object()


def unit_vector(**units):
    return {name: units.get(name, 0) for name in (
        "Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
        "Ruler", "Shell", "Emp", "Nuke")}


def force(*, counts=_DEFAULT, progress=0, speed_flag=0,
          source=1, destination=2):
    if counts is _DEFAULT:
        counts = unit_vector(Soldier=1)
    decoded = ForceUnits(tag=0, counts=counts) if counts is not None else None
    return MovingForceState(
        collection_role="INBOUND", owner_id=12, owner_relation="ENEMY",
        units=decoded, current_source=source,
        current_destination=destination, progress=progress,
        speed_flag=speed_flag)


POSITIONS = {1: (0.0, 0.0), 2: (100.0, 0.0)}


def threat(moving):
    return threat_from_force(moving, {2}, POSITIONS)


def test_eta_uses_slowest_observed_unit_speed():
    tank = threat(force(counts=unit_vector(Tank=1)))
    soldier = threat(force(counts=unit_vector(Soldier=1)))
    mixed = threat(force(counts=unit_vector(Tank=1, Soldier=1)))

    assert tank["eta_ticks"] == 255
    assert soldier["eta_ticks"] == 128
    assert mixed["eta_ticks"] == 255


def test_speed_flag_applies_acceleration_to_composition_speed():
    accelerated_tank = threat(
        force(counts=unit_vector(Tank=1), speed_flag=1))

    assert accelerated_tank["eta_ticks"] == 204


def test_unknown_eta_inputs_never_default_to_zero_or_normal_speed():
    cases = (
        force(progress=None),
        force(speed_flag=None),
        force(counts=None),
        force(speed_flag=2),
        force(progress=True),
        force(progress=-1),
        force(progress=256),
        force(speed_flag=True),
        force(source=None),
    )

    for moving in cases:
        observed = threat(moving)
        assert observed is not None
        assert observed["eta_ticks"] is None
        assert observed["eta_seconds"] is None


def test_unknown_positions_keep_eta_unknown():
    moving = force()

    observed = threat_from_force(moving, {2}, {2: (100.0, 0.0)})

    assert observed is not None
    assert observed["eta_ticks"] is None
    assert observed["eta_seconds"] is None


def test_invalid_positions_and_unit_vectors_remain_unknown():
    moving = force()
    invalid_positions = (
        {1: (True, 0.0), 2: (100.0, 0.0)},
        {1: (float("nan"), 0.0), 2: (100.0, 0.0)},
        {1: (0.0,), 2: (100.0, 0.0)},
        {1: (0.0, 0.0), 2: (0.0, 0.0)},
    )
    for positions in invalid_positions:
        observed = threat_from_force(moving, {2}, positions)
        assert observed["eta_ticks"] is None

    malformed_units = force(counts={"Soldier": 1})
    observed = threat(malformed_units)
    assert observed["eta_ticks"] is None
    assert observed["units"] is None


def test_non_self_destination_is_not_a_threat():
    assert threat_from_force(force(destination=3), {2}, POSITIONS) is None
