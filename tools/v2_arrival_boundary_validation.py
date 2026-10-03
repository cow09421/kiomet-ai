"""Validate the bounded retained ordinary-arrival candidate fixture."""
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
from tools.v2_factorized_coverage import _tower, _force, _infer_pinned_acceleration, val
from tools.v2_arrival_candidate_audit import current_identity, vector
from kiomet_ai.v2.sim import ordinary_arrival_boundary, UnsupportedState
from kiomet_ai.v2.sim.step import phase

FIXTURE = ROOT / 'tests/fixtures/v2/arrival-boundary-candidates.json.gz'
LIVE_FIXTURE = ROOT / 'tests/fixtures/v2/arrival-boundary-live-candidates.json.gz'


def validate_case(case):
    candidate = case['candidate']
    observations = case['observations']
    before, after, following = observations
    source_row = before['source_and_target_facts']['source']['visible_fact_object']
    target_row = before['source_and_target_facts']['target']['visible_fact_object']
    source, missing_source = _tower(source_row)
    target, missing_target = _tower(target_row)
    if missing_source or missing_target:
        return {'accepted_grade_b': False, 'reason': 'ENDPOINT_INPUT_UNKNOWN'}
    towers = {source.id: source, target.id: target}
    signature = (candidate['force_owner'], candidate['source_tower'],
                 candidate['target_tower'], tuple(candidate['force_units']))
    rows = val(before['visible_actor_fields_all_forces'])
    matching = [row for row in rows if current_identity(row) == signature]
    if len(matching) != 1:
        return {'accepted_grade_b': False, 'reason': 'AMBIGUOUS_FORCE_SIGNATURE'}
    raw_force = matching[0]
    force, missing = _force(raw_force)
    if missing:
        return {'accepted_grade_b': False, 'reason': 'FORCE_INPUT_UNKNOWN'}
    force = _infer_pinned_acceleration(force, raw_force, towers)
    acceleration_basis = ('OBSERVED_CURRENT_FORCE_ACCELERATION' if
        type(val(raw_force.get('accelerated'))) is bool else 'UNIQUE_PINNED_ETA_INVERSION_FOR_KNOWN_LEG_ONLY')
    others = []
    complete = True
    for row in rows:
        if row is raw_force:
            continue
        other, gaps = _force(row)
        if gaps:
            complete = False
            if val(row.get('destination')) == target.id:
                return {'accepted_grade_b': False, 'reason': 'UNKNOWN_OTHER_INBOUND'}
        else:
            others.append(other)
    try:
        event = ordinary_arrival_boundary(force, source, target, candidate['before_tick'],
            other_inbound=tuple(others), inbound_context_complete=complete, fixed_morale=True)
    except UnsupportedState as exc:
        return {'accepted_grade_b': False, 'reason': str(exc)}
    target_after = after['source_and_target_facts']['target']['visible_fact_object']
    target_next = following['source_and_target_facts']['target']['visible_fact_object']
    potential_production = [unit for unit, period in target.production if target.owner
        if phase(candidate['arrival_observation_tick'], target.id) % period == 0
        and target.units[unit] < target.capacity[unit]]
    scopes_equal = all(o['scope']['document_id'] == before['scope']['document_id']
        and val(o['scope']['match_id']) == val(before['scope']['match_id'])
        and val(o['scope']['player_id']) == val(before['scope']['player_id'])
        and val(o['observation']['document_time_origin_ms']) ==
            val(before['observation']['document_time_origin_ms']) for o in observations)
    ticks = [val(o['observation']['tick']) for o in observations]
    consecutive = scopes_equal and all((ticks[i+1]-ticks[i]) % 65536 == 1 for i in (0,1))
    absent = all(not any(current_identity(row) == signature for row in
                        val(o['visible_actor_fields_all_forces'])) for o in (after, following))
    inventory_match = vector(target_after, 'units') == tuple(
        target.units[i] + force.units[i] for i in range(10))
    owner_match = (val(target_after['owner']) == val(target_next['owner']) == force.owner
        and (target.owner == force.owner or target.owner == 0 and not any(target.units)))
    tick_match = event is not None and event.tick == ticks[1]
    next_inventory_known = vector(target_next, 'units') is not None
    identity_match = source.id == candidate['source_tower'] and all(
        row['id'] == candidate['target_tower'] for row in (target_row, target_after, target_next))
    accepted = (tick_match and consecutive and absent and inventory_match and owner_match
                and next_inventory_known and identity_match and not potential_production)
    return {'accepted_grade_b': accepted, 'formal_grade_a': False,
        'acceleration_basis': acceleration_basis,
        'event': asdict(event) if event else None,
        'checks': {'arrival_tick': tick_match, 'three_contiguous_scoped_observations': consecutive,
            'force_signature_absent_after_and_next': absent, 'target_vector_delta': inventory_match,
            'target_owner_next_tick': owner_match, 'target_production_due': potential_production,
            'next_tick_inventory_observed': next_inventory_known, 'endpoint_identity': identity_match},
        'premises': [acceleration_basis,
                     'fixed morale over this one tick; no launch attribution',
                     'current-leg boundary only; unknown relay/terminal/fuel never becomes full reinforcement proof'],
        'reason': 'CORROBORATED_CURRENT_LEG_BOUNDARY' if accepted else 'UNQUALIFIED_BOUNDARY_CANDIDATE'}


def run():
    fixture = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    cases = list(fixture['cases'])
    if LIVE_FIXTURE.exists():
        cases.extend(json.loads(gzip.decompress(LIVE_FIXTURE.read_bytes()))['cases'])
    results = [{'cohort': case['candidate']['cohort'], 'tick': case['candidate']['before_tick'],
                'source': case['candidate']['source_tower'], 'target': case['candidate']['target_tower'],
                'kind': case['candidate']['kind'], **validate_case(case)} for case in cases]
    accepted = [r for r in results if r['accepted_grade_b']]
    groups = {(r['cohort'], r['tick']) for r in accepted}
    report = {'status': 'PARTIAL', 'formal_grade_a_added': 0, 'accepted_grade_b_boundary_added': len(accepted),
        'independent_world_transition_groups': len(groups),
        'five_case_goal_met': len(groups) >= 5,
        'independence_limit': 'distinct observed transition groups, not independent randomized trials; shared matches/source/composition retained',
        'accepted_contexts': len({r['cohort'] for r in accepted}),
        'full_reinforcement_credit_added': 0, 'capture_credit_added': 0,
        'fixture_sha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        'live_fixture_sha256': hashlib.sha256(LIVE_FIXTURE.read_bytes()).hexdigest() if LIVE_FIXTURE.exists() else None,
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), ROOT/'src/kiomet_ai/v2/sim/arrival.py')},
        'cases': results}
    output = ROOT/'runtime/research/v2/arrival-boundary-validation.json'
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
    print(json.dumps({k: report[k] for k in ('formal_grade_a_added','accepted_grade_b_boundary_added',
        'five_case_goal_met', 'accepted_contexts')}))
    return report


if __name__ == '__main__':
    run()
