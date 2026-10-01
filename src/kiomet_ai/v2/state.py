"""Immutable player-information state. None is unknown, never neutral/zero."""
from dataclasses import dataclass, field, is_dataclass
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class Knowledge(StrEnum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    UNKNOWN = "UNKNOWN"


def _immutable(value):
    if value is None or type(value) in (str, int, bool, float) or isinstance(value, StrEnum):
        return True
    if isinstance(value, tuple):
        return all(_immutable(v) for v in value)
    if is_dataclass(value) and value.__dataclass_params__.frozen:
        return all(_immutable(getattr(value, f)) for f in value.__dataclass_fields__)
    return False


@dataclass(frozen=True, slots=True)
class Fact(Generic[T]):
    value: T | None = None
    knowledge: Knowledge = Knowledge.UNKNOWN
    source: str = "unavailable"
    observed_at_ms: int | None = None

    def __post_init__(self):
        if not isinstance(self.knowledge, Knowledge):
            raise ValueError("invalid knowledge")
        if (self.knowledge == Knowledge.UNKNOWN) != (self.value is None):
            raise ValueError("unknown facts must have None; known facts must have a value")
        if not _immutable(self.value):
            raise TypeError("facts cannot contain mutable values")
        if self.observed_at_ms is not None and (type(self.observed_at_ms) is not int or self.observed_at_ms < 0):
            raise ValueError("invalid fact timestamp")
        if self.knowledge != Knowledge.UNKNOWN and (not self.source or self.observed_at_ms is None):
            raise ValueError("known facts require provenance and observation time")


class Relation(StrEnum):
    SELF = "SELF"
    NEUTRAL = "NEUTRAL"
    ALLY = "ALLY"
    ENEMY = "ENEMY"


class Lifecycle(StrEnum):
    MENU = "MENU"
    JOINING = "JOINING"
    IN_MATCH = "IN_MATCH"
    RESULT = "RESULT"
    DISCONNECTED = "DISCONNECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Units:
    # Complete typed vector, including known zero counts. Stable enum IDs.
    counts: tuple[tuple[int, int], ...]

    def __post_init__(self):
        if not isinstance(self.counts, tuple) or any(
            not isinstance(pair, tuple) or len(pair) != 2 or
            any(type(v) is not int or v < 0 for v in pair) for pair in self.counts
        ):
            raise ValueError("invalid typed unit vector")
        if len({u for u, _ in self.counts}) != len(self.counts):
            raise ValueError("duplicate unit types")


@dataclass(frozen=True, slots=True)
class Tower:
    id: int
    visibility: Fact[bool]
    owner: Fact[int] = field(default_factory=Fact)
    relation: Fact[Relation] = field(default_factory=Fact)
    tower_type: Fact[int] = field(default_factory=Fact)
    units: Fact[Units] = field(default_factory=Fact)
    deployable: Fact[Units] = field(default_factory=Fact)
    capacity: Fact[Units] = field(default_factory=Fact)
    production: Fact[tuple] = field(default_factory=Fact)
    neighbors: Fact[tuple[int, ...]] = field(default_factory=Fact)
    # Integer world coordinates; screen coordinates never enter canonical state.
    position: Fact[tuple[int, int]] = field(default_factory=Fact)
    upgrade: Fact[tuple] = field(default_factory=Fact)
    upgrade_candidates: Fact[tuple] = field(default_factory=Fact)
    # Normal UI lock policy, including its optional basis downgrade target.
    # This does not establish final command eligibility.
    upgrade_locks: Fact[tuple[tuple[int, bool], ...]] = field(default_factory=Fact)
    effects: Fact[tuple] = field(default_factory=Fact)
    # Delay can be caused by upgrade or EMP; never assume its cause.
    delay_ticks: Fact[int] = field(default_factory=Fact)

    def __post_init__(self):
        if type(self.id) is not int or self.id < 0:
            raise ValueError("invalid tower ID")
        if self.visibility.value is not True or self.visibility.knowledge != Knowledge.OBSERVED:
            raise ValueError("current towers require positively observed visibility")


@dataclass(frozen=True, slots=True)
class Force:
    id: Fact[str]
    visibility: Fact[bool]
    owner: Fact[int] = field(default_factory=Fact)
    relation: Fact[Relation] = field(default_factory=Fact)
    source: Fact[int] = field(default_factory=Fact)
    destination: Fact[int] = field(default_factory=Fact)
    units: Fact[Units] = field(default_factory=Fact)
    launch_ms: Fact[int] = field(default_factory=Fact)
    unit_count: Fact[int] = field(default_factory=Fact)
    eta_ms: Fact[int] = field(default_factory=Fact)
    progress: Fact[int] = field(default_factory=Fact)
    first_seen_ms: Fact[int] = field(default_factory=Fact)
    confidence: Fact[str] = field(default_factory=Fact)
    accelerated: Fact[bool] = field(default_factory=Fact)

    def __post_init__(self):
        if self.visibility.value is not True or self.visibility.knowledge != Knowledge.OBSERVED:
            raise ValueError("current forces require positively observed visibility")


@dataclass(frozen=True, slots=True)
class GameState:
    session_id: str
    document_id: str
    match_id: Fact[str]
    sequence: int
    sampled_at_ms: int
    received_at_ms: int
    client_sha256: str
    # Capture/update-window/first-seen timestamps share this clock domain.
    # Browser epoch time is stored separately and must never be subtracted.
    clock_domain: str = "host_monotonic_ms"
    client_sampled_at_ms: Fact[int] = field(default_factory=Fact)
    document_time_origin_ms: Fact[float] = field(default_factory=Fact)
    # Last confirmed authoritative update, distinct from last memory poll.
    updated_at_ms: Fact[int] = field(default_factory=Fact)
    tick: Fact[int] = field(default_factory=Fact)
    # Observed displayed-world sequence; NETWORK and OFFLINE never share a clock.
    source_mode: Fact[str] = field(default_factory=Fact)
    # Host-clock interval containing the client's last world application.
    # It does not bound server generation or prior network delay.
    source_update_window_ms: Fact[tuple[int, int]] = field(default_factory=Fact)
    lifecycle: Fact[Lifecycle] = field(default_factory=Fact)
    player_id: Fact[int] = field(default_factory=Fact)
    towers: tuple[Tower, ...] = ()
    forces: Fact[tuple[Force, ...]] = field(default_factory=Fact)
    king: Fact[tuple] = field(default_factory=Fact)
    upgrade_resources: Fact[tuple] = field(default_factory=Fact)
    upgrade_keys: Fact[int] = field(default_factory=Fact)
    unlocked_tower_types: Fact[tuple[int, ...]] = field(default_factory=Fact)
    ranking: Fact[tuple] = field(default_factory=Fact)
    coverage: str = "PARTIAL"
    coverage_evidence: Fact[tuple] = field(default_factory=Fact)
    world_sequence_observed_at_ms: Fact[int] = field(default_factory=Fact)

    def __post_init__(self):
        if any(type(v) is not int or v < 0 for v in (self.sequence, self.sampled_at_ms, self.received_at_ms)):
            raise ValueError("snapshot times and sequence must be nonnegative integers")
        if not self.session_id or not self.document_id or self.sequence < 1:
            raise ValueError("missing snapshot identity")
        if self.received_at_ms < self.sampled_at_ms:
            raise ValueError("receipt predates sample")
        if self.clock_domain != "host_monotonic_ms":
            raise ValueError("unsupported canonical clock domain")
        update = self.updated_at_ms.value
        if update is not None and (type(update) is not int or update < 0 or update > self.received_at_ms):
            # A browser/server epoch cannot masquerade as a host-clock point.
            # Generation precedes receipt; conversion uncertainty stays unknown.
            raise ValueError("invalid authoritative update time in host clock")
        observed = self.world_sequence_observed_at_ms.value
        if observed is not None and (type(observed) is not int or observed < 0 or observed > self.received_at_ms):
            raise ValueError("invalid world sequence observation time")
        window = self.source_update_window_ms.value
        if window is not None and (len(window) != 2 or
                any(type(t) is not int or t < 0 for t in window) or
                window[0] > window[1] or window[1] > self.received_at_ms or
                self.tick.value is None):
            raise ValueError("invalid source update window")
        if not isinstance(self.towers, tuple) or not all(isinstance(t, Tower) for t in self.towers):
            raise TypeError("towers must be an immutable tuple")
        ids = {t.id for t in self.towers}
        if len(ids) != len(self.towers):
            raise ValueError("duplicate towers")
        if self.coverage == 'PLAYER_VISIBLE_COMPLETE' and self.coverage_evidence.knowledge == Knowledge.UNKNOWN:
            raise ValueError('complete visibility coverage requires evidence')
        for tower in self.towers:
            if tower.neighbors.value is not None and any(n not in ids for n in tower.neighbors.value):
                raise ValueError("graph exposes an unobserved tower")
        for force in self.forces.value or ():
            if any(f.value is not None and f.value not in ids for f in (force.source, force.destination)):
                raise ValueError("force path exposes an unobserved tower")

    def age_ms(self, now_ms: int) -> int | None:
        if type(now_ms) is not int or now_ms < self.received_at_ms or self.updated_at_ms.value is None:
            return None
        return now_ms - self.updated_at_ms.value

    def age_bounds_ms(self, now_ms: int) -> tuple[int, int] | None:
        """Diagnostic client-application bounds; authoritative point age is age_ms.

        Without an application window, a known authoritative point gives exact
        bounds. An application window must never override authoritative readiness.
        """
        if type(now_ms) is not int or now_ms < self.received_at_ms:
            return None
        window = self.source_update_window_ms.value
        if window is None:
            age = self.age_ms(now_ms)
            return None if age is None else (age, age)
        # Read endpoints and now are floor-quantized milliseconds. Expand the
        # elapsed-age interval to cover the submillisecond parts of both reads.
        return (max(0, now_ms - window[1] - 1), max(0, now_ms - window[0] + 1))

    def readiness_gaps(self, now_ms: int, max_age_ms: int = 250) -> tuple[str, ...]:
        gaps = []
        for name in ("match_id", "tick", "player_id", "forces", "king", "upgrade_resources"):
            if getattr(self, name).knowledge == Knowledge.UNKNOWN:
                gaps.append(name)
        age = self.age_ms(now_ms)
        if age is None or age > max_age_ms:
            gaps.append("freshness")
        if self.coverage != "PLAYER_VISIBLE_COMPLETE":
            gaps.append("coverage")
        if not self.towers:
            gaps.append("towers")
        for tower in self.towers:
            for name in ("owner", "relation", "tower_type", "units", "deployable", "capacity", "production", "neighbors", "position", "upgrade", "effects"):
                if getattr(tower, name).knowledge == Knowledge.UNKNOWN:
                    gaps.append(f"tower:{tower.id}:{name}")
        for index, force in enumerate(self.forces.value or ()):
            # An observed collection does not certify its members' fields.
            # Index labels locate a gap in this snapshot; they are not entity IDs.
            for name in ("id", "owner", "relation", "source", "destination", "units",
                         "unit_count", "eta_ms", "progress"):
                if getattr(force, name).knowledge == Knowledge.UNKNOWN:
                    gaps.append(f"force:{index}:{name}")
        return tuple(gaps)
