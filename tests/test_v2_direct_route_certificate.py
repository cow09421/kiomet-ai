from dataclasses import replace
import gzip
import json
from pathlib import Path
from types import SimpleNamespace as NS

from kiomet_ai.v2.observe.extractor import CLIENT_SHA256
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.state import Fact
from kiomet_ai.v2.state import Units
from tools.v2_direct_route_certificate import direct_route_certificate


def before():
    path = Path(__file__).parent / 'fixtures/v2/controlled-transition-77636cad4e97.jsonl.gz'
    events = [json.loads(line) for line in gzip.decompress(path.read_bytes()).decode('utf8').splitlines()]
    return state_from_dict(next(row['state'] for row in events if row['kind'] == 'BEFORE_INTENT'))


def certificate(state):
    return direct_route_certificate(state, 14090505, 14090504,
                                    client_sha256=CLIENT_SHA256, selected_tower=None,
                                    selection_confirmed=True, selection_tick=state.tick.value,
                                    selection_sampled_at_ms=state.sampled_at_ms)


def test_frozen_before_proves_direct_path_with_exhaustive_visible_local_cells():
    result = certificate(before())
    assert result['qualified'] is True
    assert result['path'] == [14090505, 14090504]
    assert [row['f'] for row in result['frontier']] == [1144, 2680, 2797, 3270, 3275]
    assert result['current_path_ends_here'] is True
    assert result['continuation_after_arrival'] == 'UNKNOWN'
    assert result['scope'] == 'BEFORE_SNAPSHOT_ONLY'
    assert result['gesture_continuity'] == 'UNKNOWN'


def test_visible_filtered_neighbors_alone_do_not_prove_complete_static_frontier():
    state = before()
    source = next(t for t in state.towers if t.id == 14090505)
    x, y = source.id & 65535, source.id >> 16
    local_non_neighbor = next(t.id for t in state.towers if t.id not in source.neighbors.value
                             and t.id != source.id and abs((t.id & 65535) - x) <= 1
                             and abs((t.id >> 16) - y) <= 1)
    visible = tuple(replace(t, neighbors=replace(t.neighbors, value=tuple(
        ident for ident in t.neighbors.value if ident != local_non_neighbor)))
        for t in state.towers if t.id != local_non_neighbor)
    reduced = replace(state, towers=visible)
    result = certificate(reduced)
    assert result['qualified'] is False
    assert result['reason'] == 'exhaustive_local_visible_cells_not_proved'
    assert result['path'] is None


def test_ranged_tower_unknown_owner_and_selection_are_not_silently_qualified():
    state = before()
    source = next(t for t in state.towers if t.id == 14090505)
    ranged = replace(source, tower_type=replace(source.tower_type, value=2))
    result = certificate(replace(state, towers=tuple(ranged if t.id == source.id else t for t in state.towers)))
    assert result['reason'] == 'tower_range_override_not_excluded'
    assert direct_route_certificate(state, source.id, 14090504,
                                    client_sha256=CLIENT_SHA256, selected_tower=source.id)['qualified'] is False
    neighbor = next(t for t in state.towers if t.id == 14024969)
    unknown = replace(neighbor, owner=Fact(), supply_line_present=Fact())
    result = certificate(replace(state, towers=tuple(unknown if t.id == neighbor.id else t for t in state.towers)))
    assert result['reason'] == 'incoherent_or_unknown_snapshot_fact'


def test_own_direct_goal_is_rejected_when_an_empty_neutral_frontier_node_is_cheaper():
    def fact(value, source='synthetic test'):
        return NS(value=value, source=source, knowledge='OBSERVED', observed_at_ms=1)
    src, dst = 100 | 100 << 16, 100 | 101 << 16
    adjacent = [(100 + dx) | ((100 + dy) << 16) for dx in (-1, 0, 1)
                for dy in (-1, 0, 1) if dx or dy]
    towers = []
    for ident in [src, *adjacent]:
        x, y = ident & 65535, ident >> 16
        point = (x * 5 + 2, y * 5 + 2)
        if ident == src:
            point = (500, 500)
        elif ident == dst:
            point = (500, 509)
        elif ident == (99 | 100 << 16):
            point = (499, 504)
        counts = tuple((i, int(i == 5 and ident == src)) for i in range(10))
        owner = 7 if ident in (src, dst) else 0
        towers.append(NS(id=ident, visibility=fact(True), owner=fact(owner),
            relation=fact('SELF' if owner else 'NEUTRAL'), tower_type=fact(7),
            units=fact(Units(counts)), deployable=fact(Units(counts)),
            neighbors=fact(tuple(adjacent) if ident == src else (),
                           'official neighbor table intersect current Visible.refs'),
            position=fact(point, 'official integer-position offset table')))
    state = NS(towers=tuple(towers), player_id=fact(7), lifecycle=fact('IN_MATCH'),
               coverage='PLAYER_VISIBLE_COMPLETE', coverage_evidence=fact('synthetic complete'),
               client_sha256=CLIENT_SHA256, tick=fact(1), sampled_at_ms=1)
    result = direct_route_certificate(state, src, dst, client_sha256=CLIENT_SHA256, selected_tower=None,
                                     selection_confirmed=True, selection_tick=1, selection_sampled_at_ms=1)
    assert result['qualified'] is False
    assert result['reason'] == 'goal_not_unique_frontier_minimum'


def test_stale_neighbor_units_and_mixed_tick_time_cannot_prove_a_route():
    state = before()
    neighbor = next(t for t in state.towers if t.id == 14024969)
    stale = replace(neighbor, units=replace(neighbor.units, observed_at_ms=state.sampled_at_ms - 1))
    assert certificate(replace(state, towers=tuple(stale if t.id == neighbor.id else t
                                                 for t in state.towers)))['qualified'] is False
    assert certificate(replace(state, tick=replace(state.tick,
                      observed_at_ms=state.sampled_at_ms - 1)))['qualified'] is False


def test_missing_or_mixed_selection_evidence_cannot_mean_confirmed_none():
    state = before()
    arguments = dict(client_sha256=CLIENT_SHA256, selected_tower=None,
                     selection_tick=state.tick.value, selection_sampled_at_ms=state.sampled_at_ms)
    assert direct_route_certificate(state, 14090505, 14090504, **arguments)['qualified'] is False
    arguments['selection_confirmed'] = True
    arguments['selection_tick'] -= 1
    assert direct_route_certificate(state, 14090505, 14090504, **arguments)['qualified'] is False
    arguments['selection_tick'] += 1
    arguments['selection_sampled_at_ms'] -= 1
    assert direct_route_certificate(state, 14090505, 14090504, **arguments)['qualified'] is False
