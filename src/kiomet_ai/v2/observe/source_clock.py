"""Bound a source update by consecutive read-only observations of its tick.

No interpolation clock or assumed tick period becomes a timestamp. An update
window is DERIVED; the exact source timestamp remains UNKNOWN.
"""
from dataclasses import dataclass


@dataclass
class SourceClock:
    key: tuple | None = None
    previous_tick: int | None = None
    previous_start: int | None = None
    previous_monotonic: float | None = None
    window: tuple[int, int] | None = None

    def clear(self):
        self.key = self.previous_tick = self.previous_start = self.previous_monotonic = self.window = None

    def observe(self, key, tick, started_ms, finished_ms, monotonic_ms):
        if type(tick) is not int or not 0 <= tick <= 65535 or finished_ms < started_ms:
            self.clear()
            return None
        changed_domain = key != self.key
        if self.previous_start is not None:
            wall_elapsed = started_ms - self.previous_start
            mono_elapsed = monotonic_ms - self.previous_monotonic
            # A wall-clock discontinuity invalidates timestamp comparisons.
            changed_domain |= wall_elapsed < 0 or abs(wall_elapsed - mono_elapsed) > 10
        if changed_domain:
            self.clear()
            self.key = key
        elif tick != self.previous_tick:
            # The last read was during [previous_start, previous_finish].
            # The new update must be after its START and before this FINISH.
            # Includes delayed/catch-up updates and u16 wrap; no period assumed.
            self.window = (self.previous_start, finished_ms)
        elif self.previous_start is not None and started_ms - self.previous_start > 1000:
            # A long unobserved gap could hide a reset or a complete counter wrap.
            self.window = None
        self.previous_tick = tick
        self.previous_start = started_ms
        self.previous_monotonic = monotonic_ms
        return self.window
