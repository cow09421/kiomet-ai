"""Upgrade cause from consecutive positive visible facts, never hidden inputs."""
from dataclasses import replace
from ..state import Fact, Knowledge
from .rules import DOWNGRADE, UPGRADE_DELAY


class UpgradeTracker:
    def __init__(self):
        self.clear()

    def clear(self):
        self.scope = self.tick = self.at = None
        self.previous = {}
        self.starts = {}

    def update(self, towers, identity, tick, at):
        if (identity is None or tick is None or identity != self.scope or
                self.at is not None and not 0 <= at-self.at <= 1000):
            self.clear()
        delta = (tick-self.tick)&65535 if self.tick is not None and tick is not None else None
        if delta not in (0, 1):
            self.starts = {}
        starts, result = {}, []
        for tower in towers:
            old = self.previous.get(tower.id)
            typ, owner, delay = tower.tower_type.value, tower.owner.value, tower.delay_ticks.value
            start = self.starts.get(tower.id)
            same_owner = old is not None and owner is not None and owner > 0 and owner == old.owner.value
            if (same_owner and delta == 1 and old.delay_ticks.value == 0 and
                    typ != old.tower_type.value and DOWNGRADE[typ] == old.tower_type.value and
                    delay == UPGRADE_DELAY[typ] and delay > 0):
                start = (old.tower_type.value, typ, tick, at)
            elif not (start and same_owner and delta in (0, 1) and typ == old.tower_type.value and
                    delay is not None and old.delay_ticks.value is not None and
                    delay == max(0, old.delay_ticks.value-delta)):
                start = None
            if start and delay:
                starts[tower.id] = start
                tower = replace(tower, upgrade=Fact((('in_progress', True),
                    ('from_type', start[0]), ('to_type', start[1]),
                    ('transition_tick', start[2]), ('first_seen_ms', start[3]),
                    ('remaining_delay_ticks', delay)), Knowledge.DERIVED,
                    'consecutive currently visible direct upgrade type transition + pinned nominal delay; '
                    'matching countdown only; gaps/ownership/EMP delay jumps invalidate cause', at))
            result.append(tower)
        self.starts = starts if identity is not None else {}
        self.previous = {t.id:t for t in result} if identity is not None else {}
        self.scope, self.tick, self.at = identity, tick, at
        return tuple(result)
