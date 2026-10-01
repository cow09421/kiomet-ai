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


def entry_recording():
    """Synthetic journal migration; no new game event or formal evidence."""
    events = recording()
    first = next(index for index, row in enumerate(events)
                 if row.get('kind') == 'AFTER_DISTINCT_TICK')
    state = events[first]['observation']['state']
    intent = next(row for row in events if row['kind'] == 'BEFORE_INTENT')
    down_check = {'qualified': True, 'certificate': {'scope': 'DOWN_SOURCE_ENDPOINT_ONLY',
                  'gesture_route_continuity': 'UNKNOWN', 'source': {'tower_id': intent['source']}}}
    pair_check = {'qualified': True, 'certificate': {'scope': 'ENTRY_ENDPOINTS_ONLY',
                  'gesture_route_continuity': 'UNKNOWN', 'source': {'tower_id': intent['source']},
                  'destination': {'tower_id': intent['destination']}}}
    events[first:first] = [
        {'kind': 'INPUT_ENTRY_DOWN_ADOPTED', 'state': copy.deepcopy(state)},
        {'kind': 'INPUT_ENTRY_DOWN_ENDPOINT_CHECK', 'certificate': down_check},
        {'kind': 'INPUT_ENTRY_UP_ADOPTED', 'state': copy.deepcopy(state)},
        {'kind': 'INPUT_ENTRY_ENDPOINT_PAIR_CHECK', 'certificate': pair_check},
        {'kind': 'INPUT_ENTRY_CAPTURE_RECEIPT', 'status': 'VALID', 'error': None,
         'down_canonicalized': True, 'up_canonicalized': True, 'destination_move_attempted': True,
         'mouse_release_attempted': True, 'endpoint_certificate': pair_check,
         'observer_summary': {'valid': True, 'status': 'COMPLETE', 'drained_stages': ['down', 'up'],
             'reset_free': True, 'reset_history': [], 'reset_history_truncated': 0,
             'document_loading_at_install': True, 'one_shot': True,
             'guard_evidence': {'pointer_lock_element_is_null': True, 'visibility_state': 'visible'}},
         'disarm': {'disarmed': True}},
    ]
    return events


def test_entry_frames_continue_original_prediction_and_compare_duplicate_ticks():
    result = audit_events(entry_recording(), allow_legacy_manual_ui=True)
    assert result['status'] == 'STOPPED_UNSUPPORTED'
    assert result['matched_intermediate_ticks'] == list(range(65156, 65186))
    assert result['same_tick_entry_comparisons'] == [
        {'kind': 'INPUT_ENTRY_UP_ADOPTED', 'tick': 65156},
        {'kind': 'AFTER_DISTINCT_TICK', 'tick': 65156},
    ]
    assert result['predicted_newborn']['units'] == [(5, 4)]
    assert result['input_entry_application_boundary'] == 'OBSERVED_BIRTH_AFTER_CAPTURED_UP; SERVER_TIME_UNKNOWN'
    assert result['formal_credit'] == result['trajectory_credit'] == 0


def test_same_tick_conflict_never_resets_prediction_to_entry_snapshot():
    events = entry_recording()
    up = next(row for row in events if row['kind'] == 'INPUT_ENTRY_UP_ADOPTED')
    tower = up['state']['towers'][0]
    tower['units']['value']['counts'][5][1] += 1
    result = audit_events(events, allow_legacy_manual_ui=True)
    assert result['reason'] == 'same_tick_visible_world_conflicts'
    assert result['first_divergence']['tick'] == 65156
    assert result['matched_intermediate_ticks'] == []
    assert result['formal_credit'] == result['trajectory_credit'] == 0


def test_entry_pair_gaps_and_order_fail_closed():
    events = entry_recording()
    events = [row for row in events if row['kind'] != 'INPUT_ENTRY_UP_ADOPTED']
    assert audit_events(events, allow_legacy_manual_ui=True)['reason'] == 'incomplete_or_reordered_input_entry_pair'
    events = entry_recording()
    entry_indexes = [i for i, row in enumerate(events) if row['kind'] in
                     ('INPUT_ENTRY_DOWN_ADOPTED', 'INPUT_ENTRY_UP_ADOPTED')]
    left, right = entry_indexes
    events[left], events[right] = events[right], events[left]
    assert audit_events(events, allow_legacy_manual_ui=True)['reason'] == 'incomplete_or_reordered_input_entry_pair'
    events = entry_recording()
    down = next(row for row in events if row['kind'] == 'INPUT_ENTRY_DOWN_ADOPTED')
    down['state']['tick']['value'] += 1
    assert audit_events(events, allow_legacy_manual_ui=True)['reason'] == 'noncontiguous_observation_ticks'


def test_birth_already_present_at_mouse_up_entry_cannot_be_attributed_to_release():
    events = entry_recording()
    birth = next(row for row in events if row.get('kind') == 'AFTER_DISTINCT_TICK'
                 and row['observation']['state']['tick']['value'] == 65157)
    up = next(row for row in events if row['kind'] == 'INPUT_ENTRY_UP_ADOPTED')
    up['state'] = copy.deepcopy(birth['observation']['state'])
    events = [row for row in events if not (row.get('kind') == 'AFTER_DISTINCT_TICK'
              and row['observation']['state']['tick']['value'] == 65156)]
    result = audit_events(events, allow_legacy_manual_ui=True)
    assert result['reason'] == 'candidate_birth_not_after_mouse_up_entry'
    assert result['formal_credit'] == result['trajectory_credit'] == 0


def test_rejected_or_partial_gesture_never_claims_a_causal_release_boundary():
    for kind, field, value, reason in (
        ('INPUT_ENTRY_ENDPOINT_PAIR_CHECK', 'qualified', False, 'input_entry_endpoint_evidence_not_qualified'),
        ('INPUT_ENTRY_CAPTURE_RECEIPT', 'status', 'INVALID_OR_PARTIAL', 'input_entry_capture_receipt_not_valid'),
    ):
        events = entry_recording()
        row = next(row for row in events if row['kind'] == kind)
        if kind.endswith('_CHECK'):
            row['certificate'][field] = value
        else:
            row[field] = value
        result = audit_events(events, allow_legacy_manual_ui=True)
        assert result['reason'] == reason
        assert 'input_entry_application_boundary' not in result
        assert result['matched_intermediate_ticks'] == []
        assert result['formal_credit'] == result['trajectory_credit'] == 0


def test_nominal_valid_receipt_cannot_hide_missing_or_reset_observer_history():
    for summary in (None, {}, {'valid': True, 'status': 'COMPLETE', 'reset_history': ['blur']}):
        events = entry_recording()
        receipt = next(row for row in events if row['kind'] == 'INPUT_ENTRY_CAPTURE_RECEIPT')
        receipt['observer_summary'] = summary
        result = audit_events(events, allow_legacy_manual_ui=True)
        assert result['reason'] == 'input_entry_observer_history_not_qualified'
        assert 'input_entry_application_boundary' not in result
        assert result['formal_credit'] == result['trajectory_credit'] == 0
