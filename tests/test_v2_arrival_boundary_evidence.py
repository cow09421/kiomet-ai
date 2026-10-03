from copy import deepcopy
import gzip
import hashlib
import json
import pytest
from tools.v2_arrival_boundary_validation import FIXTURE, LIVE_FIXTURE, validate_case


def cases():
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))['cases']


@pytest.mark.parametrize('index,accepted', [(0,True),(1,False),(2,False),(3,True),(4,True),(5,True)])
def test_v2_real_arrival_requires_tick_vector_owner_and_next_tick(index, accepted):
    result = validate_case(cases()[index])
    assert result['accepted_grade_b'] is accepted
    assert not result['formal_grade_a']
    if accepted:
        assert result['checks']['arrival_tick']
        assert result['checks']['target_vector_delta']
        assert result['checks']['force_signature_absent_after_and_next']
        assert result['event']['status'] == 'SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN'


def test_v2_real_arrival_production_coincidence_is_not_independent_credit():
    case = deepcopy(cases()[0])
    target = case['observations'][0]['source_and_target_facts']['target']['visible_fact_object']
    target['production']['value'] = [[4,1]]
    result = validate_case(case)
    assert result['checks']['target_production_due'] == [4]
    assert not result['accepted_grade_b']


def test_v2_real_arrival_scopes_and_track_ids_are_not_interchangeable():
    case = deepcopy(cases()[0])
    for observation in case['observations']:
        for force in observation['visible_actor_fields_all_forces']['value']:
            force['id']['value'] = None
    assert validate_case(case)['accepted_grade_b']
    case['observations'][2]['scope']['document_id'] = 'different-document'
    assert not validate_case(case)['accepted_grade_b']


def test_v2_real_arrival_next_tick_inventory_missing_does_not_qualify():
    case = deepcopy(cases()[0])
    units = case['observations'][2]['source_and_target_facts']['target']['visible_fact_object']['units']
    units['knowledge'] = 'UNKNOWN'
    units['value'] = None
    assert not validate_case(case)['accepted_grade_b']


@pytest.mark.parametrize('index', range(4))
def test_v2_live_neutral_arrival_is_corroborated_boundary_not_full_capture(index):
    case = json.loads(gzip.decompress(LIVE_FIXTURE.read_bytes()))['cases'][index]
    result = validate_case(case)
    assert result['accepted_grade_b'] and not result['formal_grade_a']
    assert result['event']['branch'] == 'CAPTURE_REQUIRED'
    assert result['acceleration_basis'] == 'OBSERVED_CURRENT_FORCE_ACCELERATION'
    assert result['event']['status'] == 'SUPPORTED_ARRIVAL_BUT_DOWNSTREAM_UNKNOWN'
    assert result['checks']['arrival_tick'] and result['checks']['target_owner_next_tick']
    assert result['checks']['target_vector_delta'] and result['checks']['next_tick_inventory_observed']
    altered = deepcopy(case)
    altered['observations'][1]['source_and_target_facts']['target']['visible_fact_object']['owner']['value'] = 0
    assert not validate_case(altered)['accepted_grade_b']


def test_v2_live_projection_matches_archived_actual_scene_without_added_actor_facts():
    projected = json.loads(gzip.decompress(LIVE_FIXTURE.read_bytes()))
    payload = gzip.decompress((LIVE_FIXTURE.parent/'ordinary-arrival-scene-ae45ad53c1b4.json.gz').read_bytes())
    assert hashlib.sha256(payload).hexdigest() == projected['source_sha256']
    receipt = json.loads(payload)
    assert receipt['troop_dispatch_attempts'] == 0 and len(receipt['observations']) == 175
    for case in projected['cases']:
        for observation in case['observations']:
            raw = receipt['observations'][observation['raw_source']['json_observations_array_index']]
            assert observation['visible_actor_fields_all_forces'] == raw['forces']
            towers = {tower['id']: tower for tower in raw['towers']}
            for endpoint in observation['source_and_target_facts'].values():
                assert endpoint['visible_fact_object'] == towers[endpoint['tower_id']]
