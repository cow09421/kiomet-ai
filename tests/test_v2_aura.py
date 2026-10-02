import pytest

from kiomet_ai.v2.sim.aura import no_periodic_aura_refresh
from kiomet_ai.v2.sim.model import UnsupportedState


def _brute_force_no_refresh(before_tick, chunk_key, slot, passes):
    """Check every possible dense rank against every scheduled pass."""
    for pass_number in range(1, passes + 1):
        world_tick = (before_tick + pass_number) & 0xFFFF
        phase = (world_tick + chunk_key) & 0xF
        for present_rank in range(slot + 1):
            if ((present_rank ^ phase) & 0xF) == 0:
                return False
    return True


def test_no_refresh_matches_all_possible_ranks_for_every_slot_phase_and_horizon():
    for slot in range(256):
        for phase_start in range(16):
            for passes in range(1, 17):
                expected = _brute_force_no_refresh(phase_start, 0, slot, passes)
                assert no_periodic_aura_refresh(
                    phase_start, 0, slot, passes
                ) is expected


@pytest.mark.parametrize(
    ('before_tick', 'chunk_key'),
    [
        (65535, 0),
        (65535, 65535),
        (65534, 15),
        (65520, 65535),
        (0, 65535),
    ],
)
def test_world_u16_wrap_uses_each_future_scheduler_tick(before_tick, chunk_key):
    for slot in range(16):
        for passes in range(1, 17):
            expected = _brute_force_no_refresh(
                before_tick, chunk_key, slot, passes
            )
            assert no_periodic_aura_refresh(
                before_tick, chunk_key, slot, passes
            ) is expected


@pytest.mark.parametrize(
    ('arguments', 'reason'),
    [
        ((True, 0, 0, 1), 'INVALID_AURA_WORLD_TICK'),
        ((-1, 0, 0, 1), 'INVALID_AURA_WORLD_TICK'),
        ((65536, 0, 0, 1), 'INVALID_AURA_WORLD_TICK'),
        ((0, False, 0, 1), 'INVALID_AURA_CHUNK_KEY'),
        ((0, -1, 0, 1), 'INVALID_AURA_CHUNK_KEY'),
        ((0, 65536, 0, 1), 'INVALID_AURA_CHUNK_KEY'),
        ((0, 0, True, 1), 'INVALID_AURA_SLOT'),
        ((0, 0, -1, 1), 'INVALID_AURA_SLOT'),
        ((0, 0, 256, 1), 'INVALID_AURA_SLOT'),
        ((0, 0, 0, False), 'INVALID_AURA_PASSES'),
        ((0, 0, 0, 0), 'INVALID_AURA_PASSES'),
        ((0, 0, 0, 17), 'INVALID_AURA_PASSES'),
        ((1.0, 0, 0, 1), 'INVALID_AURA_WORLD_TICK'),
        ((0, '1', 0, 1), 'INVALID_AURA_CHUNK_KEY'),
        ((0, 0, None, 1), 'INVALID_AURA_SLOT'),
        ((0, 0, 0, 1.0), 'INVALID_AURA_PASSES'),
    ],
)
def test_rejects_bool_non_integer_and_out_of_range_inputs(arguments, reason):
    with pytest.raises(UnsupportedState, match=reason):
        no_periodic_aura_refresh(*arguments)
