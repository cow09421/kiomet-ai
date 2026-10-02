"""Conservative eligibility checks for the periodic Tower aura refresh."""

from .model import UnsupportedState


def no_periodic_aura_refresh(before_tick, chunk_key, slot, passes):
    """Return whether every future pass is ineligible for every possible rank.

    This uses the static rank bound ``0 <= present_rank <= slot`` for a Tower
    at its row-major local slot. It assumes the actor remains in the same
    chunk and slot for the requested horizon. It does not model morale values,
    other morale writes, or any other state changes.
    """
    fields = (
        (before_tick, 0, 65535, 'INVALID_AURA_WORLD_TICK'),
        (chunk_key, 0, 65535, 'INVALID_AURA_CHUNK_KEY'),
        (slot, 0, 255, 'INVALID_AURA_SLOT'),
        (passes, 1, 16, 'INVALID_AURA_PASSES'),
    )
    for value, lower, upper, reason in fields:
        if type(value) is not int or not lower <= value <= upper:
            raise UnsupportedState(reason)

    # All possible present ranks are 0..slot. A refresh is eligible when a
    # rank equals the phase modulo 16, so a phase above slot misses them all.
    # Each scheduler pass increments the u16 world clock before this check.
    for pass_number in range(1, passes + 1):
        world_tick = (before_tick + pass_number) & 0xFFFF
        phase = (world_tick + chunk_key) & 0xF
        if phase <= slot:
            return False
    return True
