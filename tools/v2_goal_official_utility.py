"""Independent official-score utility for the bounded v2 goal harness.

This module consumes only closed-world outcome snapshots. It does not import or
call the policy chooser, evaluator, or transition code.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

# Goal014 cached source: kinds 9 (Factory) and 25 (Town) weigh 2; the other supported kinds default to 1.
SCORE_WEIGHTS: dict[int, int] = {
    3: 1, 4: 1, 7: 1, 9: 2, 10: 1, 15: 1, 17: 1, 25: 2, 26: 1,
}
SUPPORTED_SCORE_KINDS = frozenset(SCORE_WEIGHTS)
SCORE_REFRESH_TICKS = 4
HORIZON_TICKS = 120


@dataclass(frozen=True)
class ScoreResult:
    """A known integer score or a fail-closed extraction result."""

    status: Literal["KNOWN", "UNKNOWN"]
    value: int | None
    reason: str | None = None

    @property
    def known(self) -> bool:
        return self.status == "KNOWN"


@dataclass(frozen=True)
class UtilityResult:
    """Utility plus the separate catastrophe marker used by L1 reporting."""

    status: Literal["KNOWN", "UNKNOWN"]
    value: float | None
    catastrophe: bool | None
    reason: str | None = None

    @property
    def known(self) -> bool:
        return self.status == "KNOWN"


def _unknown_score(reason: str) -> ScoreResult:
    return ScoreResult("UNKNOWN", None, reason)


def _unknown_utility(reason: str) -> UtilityResult:
    return UtilityResult("UNKNOWN", None, None, reason)


def _tower_fields(row: Any) -> tuple[int, int, int | None, int | None] | None:
    """Read id/kind/owner/optional-delay from a case row or final-tower tuple."""
    if isinstance(row, Mapping):
        ident, kind, owner = row.get("id"), row.get("kind"), row.get("owner", _MISSING)
        delay = row.get("delay", _MISSING)
        if "visible" in row and row["visible"] is not True:
            return None
    elif isinstance(row, (list, tuple)) and len(row) >= 3:
        ident, kind, owner = row[0], row[1], row[2]
        delay = _MISSING
    else:
        return None
    if (type(ident) is not int or ident < 0 or type(kind) is not int
            or kind not in SUPPORTED_SCORE_KINDS
            or (owner is not None and (type(owner) is not int or owner not in (1, 2)))):
        return None
    if delay is _MISSING:
        parsed_delay = None
    elif type(delay) is int and 0 <= delay <= 255:
        parsed_delay = delay
    else:
        return None
    return ident, kind, owner, parsed_delay


_MISSING = object()


def _normalize_delays(delay_rows: Any) -> dict[int, int] | None:
    """Normalize an exact delay table, rejecting aliases, duplicates, and gaps."""
    if isinstance(delay_rows, Mapping):
        items = list(delay_rows.items())
    elif isinstance(delay_rows, Sequence) and not isinstance(delay_rows, (str, bytes)):
        items = []
        for row in delay_rows:
            if isinstance(row, Mapping):
                if "id" not in row or "delay" not in row:
                    return None
                items.append((row["id"], row["delay"]))
            elif isinstance(row, (list, tuple)) and len(row) == 2:
                items.append((row[0], row[1]))
            else:
                return None
    else:
        return None
    result: dict[int, int] = {}
    for ident, delay in items:
        if (type(ident) is not int or ident < 0 or ident in result
                or type(delay) is not int or not 0 <= delay <= 255):
            return None
        result[ident] = delay
    return result


def _expected_id_set(expected_ids: Iterable[int] | None) -> set[int] | None:
    if expected_ids is None:
        return None
    try:
        values = list(expected_ids)
    except TypeError:
        return set()
    if any(type(value) is not int or value < 0 for value in values):
        return set()
    if len(values) != len(set(values)):
        return set()
    return set(values)


def extract_score(
    tower_rows: Sequence[Any],
    delay_rows: Any,
    player: int,
    expected_ids: Iterable[int] | None = None,
) -> ScoreResult:
    """Sum source-official weights for known active towers owned by ``player``.

    A row is active only when its observed harness delay is exactly zero. Supply
    ``expected_ids`` to certify complete closed-world coverage;
    missing, extra, or duplicate rows then produce UNKNOWN. Neutral ownership
    (``None``) is a certified fact and contributes no score.
    """
    if type(player) is not int or player not in (1, 2):
        return _unknown_score("PLAYER_UNKNOWN")
    if not isinstance(tower_rows, Sequence) or isinstance(tower_rows, (str, bytes)):
        return _unknown_score("TOWER_ROWS_UNKNOWN")
    if not tower_rows:
        return _unknown_score("TOWER_ROWS_EMPTY")
    if expected_ids is None:
        return _unknown_score("EXPECTED_IDS_REQUIRED")
    expected = _expected_id_set(expected_ids)
    if not expected:
        return _unknown_score("EXPECTED_IDS_INVALID")
    delays = _normalize_delays(delay_rows)
    if delays is None:
        # `delay_rows=None` permits case rows that each carry an explicit delay.
        if delay_rows is not None:
            return _unknown_score("DELAYS_UNKNOWN")
        delays = {}
    parsed: dict[int, tuple[int, int | None]] = {}
    for row in tower_rows:
        fields = _tower_fields(row)
        if fields is None:
            return _unknown_score("TOWER_FACT_UNKNOWN_OR_UNSUPPORTED")
        ident, kind, owner, embedded_delay = fields
        if ident in parsed:
            return _unknown_score("DUPLICATE_TOWER_ID")
        if delay_rows is None:
            if embedded_delay is None:
                return _unknown_score("TOWER_DELAY_UNKNOWN")
            delay = embedded_delay
        else:
            delay = delays.get(ident)
            if delay is None:
                return _unknown_score("TOWER_DELAY_MISSING")
        parsed[ident] = (kind, owner, delay)
    ids = set(parsed)
    if expected is not None and ids != expected:
        return _unknown_score("TOWER_ID_SET_MISMATCH")
    if delay_rows is not None and set(delays) != ids:
        return _unknown_score("DELAY_ID_SET_MISMATCH")
    score = sum(SCORE_WEIGHTS[kind] for kind, owner, delay in parsed.values()
                if owner == player and delay == 0)
    return ScoreResult("KNOWN", score)


def _strict_id_set(rows: Any) -> set[int] | None:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return None
    ids: set[int] = set()
    for row in rows:
        fields = _tower_fields(row)
        if fields is None or fields[0] in ids:
            return None
        ids.add(fields[0])
    return ids or None


def _initial_boundary(case: Mapping[str, Any]) -> tuple[int, int] | None:
    start = case.get("start_tick")
    if type(start) is not int or not 0 <= start <= 0xFFFF:
        return None
    initial = (start - 1) & 0xFFFF
    if initial % SCORE_REFRESH_TICKS:
        return None
    return start, initial


def _snapshot_rows_from_trace(
    initial_rows: Sequence[Any], trace_row: Mapping[str, Any], expected_ids: set[int]
) -> tuple[list[tuple[int, int, int | None]], Any] | None:
    owners_raw = trace_row.get("tower_owners", _MISSING)
    delays_raw = trace_row.get("tower_delays", _MISSING)
    if owners_raw is _MISSING or delays_raw is _MISSING:
        return None
    owners = _normalize_owners(owners_raw)
    delays = _normalize_delays(delays_raw)
    if owners is None or delays is None or set(owners) != expected_ids or set(delays) != expected_ids:
        return None
    initial_fields = [_tower_fields(row) for row in initial_rows]
    if any(fields is None for fields in initial_fields):
        return None
    rows = [(fields[0], fields[1], owners[fields[0]]) for fields in initial_fields]
    return rows, delays


def _normalize_owners(owner_rows: Any) -> dict[int, int | None] | None:
    if not isinstance(owner_rows, Sequence) or isinstance(owner_rows, (str, bytes)):
        return None
    owners: dict[int, int | None] = {}
    for row in owner_rows:
        if isinstance(row, (list, tuple)) and len(row) == 2:
            ident, owner = row
        elif isinstance(row, Mapping) and "id" in row and "owner" in row:
            ident, owner = row["id"], row["owner"]
        else:
            return None
        if (type(ident) is not int or ident < 0 or ident in owners
                or (owner is not None and (type(owner) is not int or owner not in (1, 2)))):
            return None
        owners[ident] = owner
    return owners


def _endpoint_rows(
    case: Mapping[str, Any], outcome: Mapping[str, Any], start: int,
    expected_ids: set[int], initial_rows: Sequence[Any],
) -> tuple[list[Any], Any] | None:
    """Return the last cached-score snapshot, including early terminal stops."""
    ticks = outcome.get("ticks_evaluated")
    trace = outcome.get("trace")
    if type(ticks) is not int or not 0 <= ticks <= HORIZON_TICKS:
        return None
    if not isinstance(trace, Sequence) or isinstance(trace, (str, bytes)) or len(trace) != ticks:
        return None
    last_refresh: tuple[list[Any], Any] | None = None
    for offset, item in enumerate(trace):
        if not isinstance(item, Mapping):
            return None
        expected_tick = (start + offset) & 0xFFFF
        tick = item.get("tick")
        if type(tick) is not int or tick != expected_tick:
            return None
        # All tower snapshots must have exact ID coverage, even between refreshes.
        owners = _normalize_owners(item.get("tower_owners", _MISSING))
        delays = _normalize_delays(item.get("tower_delays", _MISSING))
        if owners is None or delays is None or set(owners) != expected_ids or set(delays) != expected_ids:
            return None
        if tick % SCORE_REFRESH_TICKS == 0:
            snapshot = _snapshot_rows_from_trace(initial_rows, item, expected_ids)
            if snapshot is None:
                return None
            rows, delay_map = snapshot
            last_refresh = (rows, delay_map)
    if ticks == HORIZON_TICKS:
        endpoint_tick = (start + HORIZON_TICKS - 1) & 0xFFFF
        if endpoint_tick % SCORE_REFRESH_TICKS:
            return None
        final_rows = outcome.get("final_towers", _MISSING)
        final_delays = outcome.get("final_tower_delays", _MISSING)
        final_ids = _strict_id_set(final_rows)
        if final_ids != expected_ids:
            return None
        # Trace and final exports must describe the same endpoint facts.
        final_delay_map = _normalize_delays(final_delays)
        final_fields = [_tower_fields(row) for row in final_rows]
        if (final_delay_map is None or set(final_delay_map) != expected_ids
                or len(final_fields) != len(expected_ids) or any(fields is None for fields in final_fields)):
            return None
        final_by_id = {fields[0]: (fields[1], fields[2]) for fields in final_fields}
        trace_by_id = ({row[0]: (row[1], row[2]) for row in last_refresh[0]}
                       if last_refresh is not None else None)
        if last_refresh is None or trace_by_id != final_by_id or last_refresh[1] != final_delay_map:
            return None
        return list(final_rows), final_delays
    # Before the first post-start refresh, the official cache still equals the
    # aligned initial score. Keep that terminal delta numeric instead of omitting it.
    if last_refresh is not None:
        return last_refresh
    initial_delays: dict[int, int] = {}
    initial_score_rows: list[tuple[int, int, int | None]] = []
    for row in initial_rows:
        fields = _tower_fields(row)
        if fields is None or fields[3] is None:
            return None
        initial_score_rows.append((fields[0], fields[1], fields[2]))
        initial_delays[fields[0]] = fields[3]
    if set(initial_delays) != expected_ids:
        return None
    return initial_score_rows, initial_delays


def score_delta(case: Mapping[str, Any], outcome: Mapping[str, Any]) -> ScoreResult:
    """Return the change in (self score − opponent score) at source refreshes.

    Initial score is measured at ``start_tick - 1``. A full episode must end at
    tick 120 on a refresh boundary. Processed death has no source-official
    numeric score; pending loss at the full horizon remains numeric while alive.
    """
    if not isinstance(case, Mapping) or not isinstance(outcome, Mapping):
        return _unknown_score("CASE_OR_OUTCOME_UNKNOWN")
    if case.get("closed_by_construction") is not True:
        return _unknown_score("WORLD_NOT_CLOSED")
    if outcome.get("status") != "EVALUATED":
        return _unknown_score("OUTCOME_NOT_EVALUATED")
    if type(case.get("horizon_ticks")) is not int or case.get("horizon_ticks") != HORIZON_TICKS:
        return _unknown_score("HORIZON_UNKNOWN")
    boundary = _initial_boundary(case)
    if boundary is None:
        return _unknown_score("INITIAL_SCORE_REFRESH_BOUNDARY_UNKNOWN")
    start, _ = boundary
    player = case.get("player")
    if type(player) is not int or player not in (1, 2):
        return _unknown_score("PLAYER_UNKNOWN")
    alive = _normalized_alive(outcome.get("alive", _MISSING))
    if alive is None:
        return _unknown_score("ALIVE_TERMINAL_STATE_UNKNOWN")
    if player not in alive or 3 - player not in alive:
        return _unknown_score("ALIVE_TERMINAL_STATE_INCOMPLETE")
    if not alive[player] or not alive[3 - player]:
        return _unknown_score("SOURCE_OFFICIAL_SCORE_UNAVAILABLE_DEAD_PLAYER")
    ticks = outcome.get("ticks_evaluated")
    if type(ticks) is not int or not 0 <= ticks <= HORIZON_TICKS:
        return _unknown_score("TICK_COUNT_UNKNOWN")
    if ticks != HORIZON_TICKS:
        return _unknown_score("SCORE_ENDPOINT_NOT_FULL_HORIZON")
    initial_rows = case.get("towers")
    expected_ids = _strict_id_set(initial_rows)
    if expected_ids is None:
        return _unknown_score("INITIAL_TOWER_SET_UNKNOWN")
    initial_score_self = extract_score(initial_rows, None, player, expected_ids)
    initial_score_opp = extract_score(initial_rows, None, 3 - player, expected_ids)
    if not initial_score_self.known or not initial_score_opp.known:
        return _unknown_score("INITIAL_SCORE_UNKNOWN")
    endpoint = _endpoint_rows(case, outcome, start, expected_ids, initial_rows)
    if endpoint is None:
        return _unknown_score("ENDPOINT_SCORE_SNAPSHOT_UNKNOWN")
    endpoint_rows, endpoint_delays = endpoint
    end_score_self = extract_score(endpoint_rows, endpoint_delays, player, expected_ids)
    end_score_opp = extract_score(endpoint_rows, endpoint_delays, 3 - player, expected_ids)
    if not end_score_self.known or not end_score_opp.known:
        return _unknown_score("ENDPOINT_SCORE_UNKNOWN")
    initial_diff = initial_score_self.value - initial_score_opp.value  # type: ignore[operator]
    end_diff = end_score_self.value - end_score_opp.value  # type: ignore[operator]
    return ScoreResult("KNOWN", end_diff - initial_diff)


def _normalized_alive(raw: Any) -> dict[int, bool] | None:
    if not isinstance(raw, Mapping):
        return None
    result: dict[int, bool] = {}
    for key, value in raw.items():
        if type(key) is int and key in (1, 2):
            owner = key
        elif type(key) is str and key in ("1", "2"):
            owner = int(key)
        else:
            return None
        if type(value) is not bool or owner in result:
            return None
        result[owner] = value
    return result


def _normalized_pending(raw: Any) -> set[int] | None:
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return None
    values = list(raw)
    if any(type(value) is not int or value not in (1, 2) for value in values):
        return None
    if len(values) != len(set(values)):
        return None
    return set(values)


def _terminal_players(terminal: Any) -> set[int] | None:
    if terminal is None:
        return set()
    if terminal == "CORE_LOSS_PENDING_AT_HORIZON":
        return None
    if type(terminal) is not str or not terminal.startswith("CORE_LOSS:"):
        return None
    suffix = terminal[len("CORE_LOSS:"):]
    if not suffix:
        return None
    parts = suffix.split(",")
    if any(part not in ("1", "2") for part in parts) or len(parts) != len(set(parts)):
        return None
    return {int(part) for part in parts}


def _terminal_utility(outcome: Mapping[str, Any], player: int) -> UtilityResult | None:
    """Return an exact terminal override or UNKNOWN when terminal state is open."""
    alive = _normalized_alive(outcome.get("alive", _MISSING))
    pending = _normalized_pending(outcome.get("pending_core_losses", _MISSING))
    terminal = outcome.get("terminal", _MISSING)
    if alive is None or pending is None or terminal is _MISSING:
        return _unknown_utility("ALIVE_OR_PENDING_TERMINAL_STATE_UNKNOWN")
    if player not in alive or 3 - player not in alive:
        return _unknown_utility("ALIVE_TERMINAL_STATE_INCOMPLETE")
    terminal_owners = _terminal_players(terminal)
    if terminal == "CORE_LOSS_PENDING_AT_HORIZON":
        if not pending or any(not alive[owner] for owner in pending):
            return _unknown_utility("PENDING_TERMINAL_STATE_INCONSISTENT")
        terminal_owners = set(pending)
    elif terminal_owners is None:
        return _unknown_utility("TERMINAL_LABEL_UNKNOWN")
    elif terminal_owners:
        if pending or any(alive[owner] for owner in terminal_owners):
            return _unknown_utility("PROCESSED_TERMINAL_STATE_INCONSISTENT")
    elif pending or not all(alive.values()):
        return _unknown_utility("NONTERMINAL_STATE_INCONSISTENT")

    own_dead = player in pending or not alive[player] or player in terminal_owners
    if own_dead:
        return UtilityResult("KNOWN", -1.0, True, "SELF_CORE_LOSS")
    opponent_dead = (3 - player) in pending or not alive[3 - player] or (3 - player) in terminal_owners
    if opponent_dead:
        if alive[player] is True:
            return UtilityResult("KNOWN", 1.0, False, "OPPONENT_CORE_LOSS")
        return _unknown_utility("SELF_SAFETY_UNKNOWN")
    if alive[player] is True and alive[3 - player] is True and not pending and terminal is None:
        return UtilityResult("KNOWN", 0.0, False, "NONTERMINAL")
    return _unknown_utility("TERMINAL_CLASSIFICATION_UNKNOWN")


def nearest_rank_scale(deltas: Iterable[int | float]) -> float:
    """Return the positive finite nearest-rank 90th percentile of |deltas|."""
    try:
        values = list(deltas)
    except TypeError as exc:
        raise ValueError("deltas must be a finite nonempty iterable") from exc
    if not values:
        raise ValueError("at least one known B1 score delta is required")
    absolute: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("all deltas must be known numeric values")
        try:
            numeric = float(value)
        except OverflowError as exc:
            raise ValueError("all deltas must be finite") from exc
        if not math.isfinite(numeric):
            raise ValueError("all deltas must be finite")
        absolute.append(abs(numeric))
    absolute.sort()
    rank = math.ceil(0.9 * len(absolute))
    scale = absolute[rank - 1]
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("nearest-rank 90th percentile must be positive and finite")
    return scale


def utility(case: Mapping[str, Any], outcome: Mapping[str, Any], scale: int | float) -> UtilityResult:
    """Compute clipped normalized official-score delta with exact L1 overrides."""
    if isinstance(scale, bool) or not isinstance(scale, (int, float)):
        return _unknown_utility("SCALE_NOT_NUMERIC")
    try:
        normalized_scale = float(scale)
    except OverflowError:
        return _unknown_utility("SCALE_NOT_POSITIVE_FINITE")
    if not math.isfinite(normalized_scale) or normalized_scale <= 0:
        return _unknown_utility("SCALE_NOT_POSITIVE_FINITE")
    if not isinstance(case, Mapping) or not isinstance(outcome, Mapping):
        return _unknown_utility("CASE_OR_OUTCOME_UNKNOWN")
    if case.get("closed_by_construction") is not True:
        return _unknown_utility("WORLD_NOT_CLOSED")
    if type(case.get("horizon_ticks")) is not int or case.get("horizon_ticks") != HORIZON_TICKS:
        return _unknown_utility("HORIZON_UNKNOWN")
    if outcome.get("status") != "EVALUATED":
        return _unknown_utility("OUTCOME_NOT_EVALUATED")
    ticks = outcome.get("ticks_evaluated")
    if type(ticks) is not int or not 1 <= ticks <= HORIZON_TICKS:
        return _unknown_utility("TICK_COUNT_UNKNOWN")
    if outcome.get("terminal") == "CORE_LOSS_PENDING_AT_HORIZON" and ticks != HORIZON_TICKS:
        return _unknown_utility("PENDING_LOSS_BEFORE_HORIZON_INCONSISTENT")
    player = case.get("player")
    if type(player) is not int or player not in (1, 2):
        return _unknown_utility("PLAYER_UNKNOWN")
    terminal = _terminal_utility(outcome, player)
    if not terminal.known:
        return terminal
    if terminal.reason != "NONTERMINAL":
        return terminal
    delta = score_delta(case, outcome)
    if not delta.known:
        return _unknown_utility(delta.reason or "OFFICIAL_SCORE_DELTA_UNKNOWN")
    value = max(-1.0, min(1.0, float(delta.value) / normalized_scale))  # type: ignore[arg-type]
    if not math.isfinite(value):
        return _unknown_utility("UTILITY_NOT_FINITE")
    return UtilityResult("KNOWN", value, False, "OFFICIAL_SCORE_DELTA")
