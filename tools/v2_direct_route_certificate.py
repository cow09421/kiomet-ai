"""Sufficient before-only certificate for a one-expansion normal UI A* path."""
from math import isqrt

from kiomet_ai.v2.observe.extractor import CLIENT_SHA256
from kiomet_ai.v2.observe.rules import GENERATION


def _counts(fact):
    if fact.value is None:
        raise ValueError('unknown_units')
    pairs = fact.value.counts
    if len(pairs) != 10 or any(type(k) is not int or type(n) is not int or not 0 <= n <= 255 for k, n in pairs):
        raise ValueError('invalid_units')
    counts = dict(pairs)
    if set(counts) != set(range(10)):
        raise ValueError('incomplete_units')
    return tuple(counts[i] for i in range(10))


def _position(tower):
    ident = tower.id
    if type(ident) is not int or not 0 <= ident <= 0xffffffff:
        raise ValueError('invalid_tower_id')
    x, y = ident & 65535, ident >> 16
    if x >= 512 or y >= 512:
        raise ValueError('outside_pinned_world')
    point = tower.position.value
    if (point is None or len(point) != 2 or any(type(n) is not int for n in point)
            or not x * 5 <= point[0] <= x * 5 + 4 or not y * 5 <= point[1] <= y * 5 + 4
            or tower.position.source != 'official integer-position offset table'):
        raise ValueError('unqualified_pinned_position')
    return point


def _distance_cost(left, right):
    return isqrt(sum((a - b) ** 2 for a, b in zip(left, right)) << 16)


def _coherent(fact, sampled_at_ms):
    if (fact.value is None or fact.knowledge not in ('OBSERVED', 'DERIVED')
            or not fact.source or type(fact.observed_at_ms) is not int
            or fact.observed_at_ms != sampled_at_ms):
        raise ValueError('incoherent_or_unknown_snapshot_fact')


def direct_route_certificate(state, source_id, destination_id, *, client_sha256, selected_tower,
                             selection_confirmed=False, selection_tick=None,
                             selection_sampled_at_ms=None):
    failure = {'qualified': False, 'path': None, 'continuation_after_arrival': 'UNKNOWN'}
    if client_sha256 != CLIENT_SHA256 or state.client_sha256 != CLIENT_SHA256:
        return dict(failure, reason='unqualified_client_version')
    if (selected_tower is not None or selection_confirmed is not True
            or type(selection_tick) is not int or selection_tick != state.tick.value
            or type(selection_sampled_at_ms) is not int
            or selection_sampled_at_ms != state.sampled_at_ms):
        return dict(failure, reason='manual_ui_branch_not_qualified')
    try:
        if type(state.sampled_at_ms) is not int or state.sampled_at_ms < 0:
            raise ValueError('invalid_snapshot_time')
        for fact in (state.tick, state.player_id, state.lifecycle, state.coverage_evidence):
            _coherent(fact, state.sampled_at_ms)
    except ValueError as error:
        return dict(failure, reason=str(error))
    if state.coverage != 'PLAYER_VISIBLE_COMPLETE' or state.lifecycle.value != 'IN_MATCH':
        return dict(failure, reason='visible_snapshot_not_qualified')
    if type(source_id) is not int or type(destination_id) is not int or source_id == destination_id:
        return dict(failure, reason='invalid_endpoints')
    player = state.player_id.value
    if type(player) is not int or not 0 < player <= 65535:
        return dict(failure, reason='unknown_player')
    towers = {t.id: t for t in state.towers}
    if len(towers) != len(state.towers):
        return dict(failure, reason='duplicate_tower_ids')
    if source_id not in towers or destination_id not in towers:
        return dict(failure, reason='endpoint_not_visible')
    source, destination = towers[source_id], towers[destination_id]
    try:
        for fact in (source.visibility, source.owner, source.relation, source.tower_type,
                     source.units, source.deployable, source.neighbors, source.position,
                     destination.visibility, destination.owner, destination.relation,
                     destination.units, destination.position):
            _coherent(fact, state.sampled_at_ms)
        if destination.visibility.value is not True:
            raise ValueError('destination_visibility_not_positive')
        if type(source.owner.value) is not int or source.owner.value != player or source.relation.value != 'SELF':
            raise ValueError('source_not_own')
        kind = source.tower_type.value
        if type(kind) is not int or not 0 <= kind < 27 or any(GENERATION[kind][i] is not None for i in (6, 7, 8)):
            raise ValueError('tower_range_override_not_excluded')
        inventory = _counts(source.units)
        if any(inventory[6:]):
            raise ValueError('special_or_ruler_source')
        mobile = (inventory[0] if kind == 15 else 0, *inventory[1:])
        if not any(mobile) or _counts(source.deployable) != mobile:
            raise ValueError('unqualified_mobile_inventory')
        if destination.owner.value == player and destination.relation.value == 'SELF':
            pass
        elif destination.owner.value == 0 and destination.relation.value == 'NEUTRAL' and not any(_counts(destination.units)):
            pass
        else:
            raise ValueError('destination_outside_scope')
        neighbors = source.neighbors.value
        if (neighbors is None or source.neighbors.source != 'official neighbor table intersect current Visible.refs'
                or any(type(n) is not int for n in neighbors) or len(set(neighbors)) != len(neighbors)
                or destination_id not in neighbors or source_id in neighbors):
            raise ValueError('unqualified_neighbor_facts')
        source_point, destination_point = _position(source), _position(destination)
        x, y = source_id & 65535, source_id >> 16
        cells = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if not (dx or dy) or not (0 <= x + dx < 512 and 0 <= y + dy < 512):
                    continue
                ident = (x + dx) | ((y + dy) << 16)
                # Missing cells produce only a reason, never a hidden ID or payload.
                if ident not in towers or towers[ident].visibility.value is not True:
                    raise ValueError('exhaustive_local_visible_cells_not_proved')
                _coherent(towers[ident].visibility, state.sampled_at_ms)
                cells.append(ident)
        if any(ident not in cells for ident in neighbors):
            raise ValueError('neighbor_outside_pinned_adjacent_cells')
        if source.visibility.value is not True:
            raise ValueError('source_visibility_not_positive')
        frontier = []
        for ident in neighbors:
            tower = towers[ident]
            for fact in (tower.owner, tower.units, tower.position):
                _coherent(fact, state.sampled_at_ms)
            owner = tower.owner.value
            if type(owner) is not int or not 0 <= owner <= 65535:
                raise ValueError('unknown_neighbor_owner')
            units = _counts(tower.units)
            point = _position(tower)
            edge = _distance_cost(source_point, point)
            heuristic = _distance_cost(point, destination_point)
            bias = 512 if owner == player else 8192 if owner or any(units) else 0
            frontier.append({'id': ident, 'g': edge, 'h': heuristic, 'bias': bias, 'f': edge + heuristic + bias})
        goal = next(row for row in frontier if row['id'] == destination_id)
        if any(row['f'] <= goal['f'] for row in frontier if row['id'] != destination_id):
            raise ValueError('goal_not_unique_frontier_minimum')
    except (ValueError, TypeError, KeyError) as error:
        return dict(failure, reason=str(error))
    return {'qualified': True, 'path': [source_id, destination_id], 'current_path_ends_here': True,
            'scope': 'BEFORE_SNAPSHOT_ONLY', 'gesture_continuity': 'UNKNOWN',
            'continuation_after_arrival': 'UNKNOWN', 'client_sha256': client_sha256,
            'before_tick': state.tick.value, 'sampled_at_ms': state.sampled_at_ms,
            'frontier': sorted(frontier, key=lambda row: row['f']),
            'all_adjacent_cells_positive': True,
            'basis': 'pinned non-ranged A*: unique direct goal popped before a second expansion; no after facts'}
