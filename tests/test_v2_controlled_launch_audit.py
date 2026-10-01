import copy
import gzip
import json
from pathlib import Path

from tools.v2_controlled_launch_audit import audit_events
from tools.v2_direct_route_certificate import direct_route_certificate
from kiomet_ai.v2.serialization import state_from_dict


def recording():
    path = Path(__file__).parent / 'fixtures/v2/controlled-transition-77636cad4e97.jsonl.gz'
    return [json.loads(line) for line in gzip.decompress(path.read_bytes()).decode('utf8').splitlines()]


def test_original_before_rollout_predicts_launch_without_quantity_fit_or_resets():
    result = audit_events(recording(), allow_legacy_manual_ui=True)
    assert result['status'] == 'STOPPED_UNSUPPORTED'
    assert result['reason'] == 'UNKNOWN_POST_ARRIVAL_PATH'
    assert result['first_unsupported_tick'] == 65186
    assert result['matched_intermediate_ticks'] == list(range(65156, 65186))
    assert result['application_displayed_tick'] == 65157
    assert result['predicted_newborn'] == {'units': [(5, 4)], 'progress': 0, 'accelerated': True, 'fuel': 150}
    assert result['birth_vector_equal'] is True
    assert result['formal_credit'] == result['trajectory_credit'] == 0
    assert result['validation_class'] == 'CALIBRATION_ONLY_TEMPORAL_ALIGNMENT'


def test_altered_observed_birth_is_comparison_only_and_does_not_change_command_quantity():
    events = copy.deepcopy(recording())
    birth = next(row for row in events if row.get('kind') == 'AFTER_DISTINCT_TICK'
                 and row['observation']['state']['tick']['value'] == 65157)
    force = birth['observation']['state']['forces']['value'][0]
    force['units']['value']['counts'][5][1] = 3
    force['unit_count']['value'] = 3
    result = audit_events(events, allow_legacy_manual_ui=True)
    assert result['application_displayed_tick'] == 65157
    assert result['predicted_newborn']['units'] == [(5, 4)]
    assert result['birth_vector_equal'] is False
    assert result['status'] == 'MISMATCH'
    assert result['first_divergence']['tick'] == 65157
    assert result['first_divergence']['field'] == '/force_context/0/3/5'


def test_gaps_and_unqualified_legacy_semantics_cannot_obtain_audit_credit():
    events = recording()
    assert audit_events(events)['reason'] == 'all_current_input_semantics_not_qualified'
    events = [row for row in events if not (row.get('kind') == 'AFTER_DISTINCT_TICK'
              and row['observation']['state']['tick']['value'] == 65160)]
    result = audit_events(events, allow_legacy_manual_ui=True)
    assert result['reason'] == 'noncontiguous_observation_ticks'
    assert result['matched_intermediate_ticks'] == []
    assert result['formal_credit'] == 0


def test_before_route_certificate_supports_rollout_but_never_grants_trajectory_credit():
    events = recording()
    intent = next(row for row in events if row['kind'] == 'BEFORE_INTENT')
    before = state_from_dict(intent['state'])
    # Synthetic schema migration only: the original recording is unchanged,
    # and this is not an independently recorded certificate or new case.
    intent['before_selection_evidence'] = {'confirmed': True, 'selected_tower': None,
        'tick': before.tick.value, 'sampled_at_ms': before.sampled_at_ms}
    intent['before_only_route_certificate'] = direct_route_certificate(
        before, intent['source'], intent['destination'],
        client_sha256=before.client_sha256, selected_tower=None, selection_confirmed=True,
        selection_tick=before.tick.value, selection_sampled_at_ms=before.sampled_at_ms)
    result = audit_events(events, allow_legacy_manual_ui=True)
    assert result['status'] == 'MATCHED_RECORDED_WINDOW'
    assert result['matched_intermediate_ticks'] == list(range(65156, 65196))
    assert result['formal_credit'] == result['trajectory_credit'] == 0
    assert result['terminal_path_application'] == 'CONDITIONAL_ON_UNPROVED_GESTURE_CONTINUITY'
    intent['before_only_route_certificate']['frontier'][0]['f'] += 1
    assert audit_events(events, allow_legacy_manual_ui=True)['reason'] == 'recorded_before_route_certificate_does_not_revalidate'


def test_route_audit_never_infers_none_from_an_omitted_selection_field():
    events = recording()
    intent = next(row for row in events if row['kind'] == 'BEFORE_INTENT')
    before = state_from_dict(intent['state'])
    intent['before_only_route_certificate'] = direct_route_certificate(
        before, intent['source'], intent['destination'], client_sha256=before.client_sha256,
        selected_tower=None, selection_confirmed=True, selection_tick=before.tick.value,
        selection_sampled_at_ms=before.sampled_at_ms)
    selection = {'confirmed': True, 'selected_tower': None,
                 'tick': before.tick.value, 'sampled_at_ms': before.sampled_at_ms}
    for omitted in (None, {}, {key: value for key, value in selection.items() if key != 'selected_tower'}):
        intent['before_selection_evidence'] = omitted
        result = audit_events(events, allow_legacy_manual_ui=True)
        assert result['reason'] == 'recorded_before_selection_evidence_missing'
        assert result['matched_intermediate_ticks'] == []
        assert result['formal_credit'] == result['trajectory_credit'] == 0
    for invalid in (False, 0):
        intent['before_selection_evidence'] = dict(selection, selected_tower=invalid)
        assert audit_events(events, allow_legacy_manual_ui=True)['reason'] == 'recorded_before_route_certificate_does_not_revalidate'
