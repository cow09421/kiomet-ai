"""Offline, no-reset audit of recorded normal-UI ALL_CURRENT_DEPLOYABLE input."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import LaunchAll, UnsupportedState, from_canonical, step
from tools.v2_controlled_transition_capture import collect_new_force_births
from tools.v2_sim_differential import signature
from tools.v2_direct_route_certificate import direct_route_certificate


def first_difference(expected, observed, path=''):
    if type(expected) is not type(observed):
        return {'field': path, 'expected': expected, 'observed': observed}
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(observed)):
            child = f'{path}/{key}'
            if key not in expected or key not in observed:
                return {'field': child, 'expected': expected.get(key), 'observed': observed.get(key)}
            difference = first_difference(expected[key], observed[key], child)
            if difference:
                return difference
    elif isinstance(expected, list):
        if len(expected) != len(observed):
            return {'field': f'{path}/length', 'expected': len(expected), 'observed': len(observed)}
        for index, (left, right) in enumerate(zip(expected, observed)):
            difference = first_difference(left, right, f'{path}/{index}')
            if difference:
                return difference
    elif expected != observed:
        return {'field': path, 'expected': expected, 'observed': observed}
    return None


def _signature(state):
    return json.loads(json.dumps(signature(state)))


def audit_events(events, *, allow_legacy_manual_ui=False):
    result = {'status': 'INELIGIBLE', 'formal_credit': 0, 'trajectory_credit': 0,
              'validation_class': 'CALIBRATION_ONLY_TEMPORAL_ALIGNMENT',
              'matched_intermediate_ticks': [], 'first_divergence': None,
              'terminal_path': 'UNKNOWN', 'classification': 'UNKNOWN'}
    intents = [row for row in events if row.get('kind') == 'BEFORE_INTENT']
    if len(intents) != 1:
        return dict(result, reason='expected_one_before_intent')
    intent = intents[0]
    semantics = intent.get('ACTION', {}).get('semantics')
    if semantics == 'ALL_CURRENT_DEPLOYABLE':
        result['input_basis'] = 'RECORDED_ALL_CURRENT_DEPLOYABLE'
    elif allow_legacy_manual_ui and intent.get('ui_command_branch_proof') == (
        'docs/V2_M2A_UI_INPUT_RULE.md; normal selected Option absent selects deploy_force_from_path branch'
    ):
        result['input_basis'] = 'LEGACY_MANUAL_UI_REINTERPRETED_WITH_PINNED_RULE_CALIBRATION_ONLY'
    else:
        return dict(result, reason='all_current_input_semantics_not_qualified')
    if intent.get('selected_tower_none_confirmed') is not True:
        return dict(result, reason='manual_ui_branch_not_qualified')
    try:
        before = state_from_dict(intent['state'])
        observations = [state_from_dict(row['observation']['state']) for row in events
                        if row.get('kind') == 'AFTER_DISTINCT_TICK']
    except (KeyError, ValueError, TypeError) as error:
        return dict(result, reason=f'invalid_recorded_state: {error}')
    if not observations:
        return dict(result, reason='no_after_ticks')
    if intent.get('tick') != before.tick.value or intent.get('document_id') != before.document_id or intent.get('match_id') != before.match_id.value:
        return dict(result, reason='before_intent_identity_conflicts_with_state')
    identity = (before.document_id, before.match_id.value, before.player_id.value)
    prior_tick = before.tick.value
    for observed in observations:
        if (observed.document_id, observed.match_id.value, observed.player_id.value) != identity:
            return dict(result, reason='identity_changed')
        if type(prior_tick) is not int or observed.tick.value != ((prior_tick + 1) & 65535):
            return dict(result, reason='noncontiguous_observation_ticks', first_gap_after=prior_tick)
        prior_tick = observed.tick.value
    source, destination = intent.get('source'), intent.get('destination')
    if type(source) is not int or type(destination) is not int or source == destination:
        return dict(result, reason='invalid_input_endpoints')
    action = intent.get('ACTION')
    if action and (action.get('source'), action.get('destination')) != (source, destination):
        return dict(result, reason='conflicting_input_endpoints')
    terminal = None
    recorded_route = intent.get('before_only_route_certificate')
    if isinstance(recorded_route, dict) and recorded_route.get('qualified') is True:
        selection = intent.get('before_selection_evidence')
        if (not isinstance(selection, dict)
                or not {'confirmed', 'selected_tower', 'tick', 'sampled_at_ms'} <= selection.keys()):
            return dict(result, reason='recorded_before_selection_evidence_missing')
        proved = direct_route_certificate(before, source, destination,
                                         client_sha256=before.client_sha256,
                                         selected_tower=selection.get('selected_tower'),
                                         selection_confirmed=selection.get('confirmed'),
                                         selection_tick=selection.get('tick'),
                                         selection_sampled_at_ms=selection.get('sampled_at_ms'))
        if not proved['qualified'] or recorded_route != proved:
            return dict(result, reason='recorded_before_route_certificate_does_not_revalidate')
        terminal = True
        result['terminal_path'] = proved
        result['terminal_path_application'] = 'CONDITIONAL_ON_UNPROVED_GESTURE_CONTINUITY'
    if before.forces.value is None:
        return dict(result, reason='before_force_coverage_unknown')
    prior_ids = {force.id.value for force in before.forces.value if force.id.value}
    births = collect_new_force_births(observations, source, destination, prior_ids, before.player_id.value)
    result['observed_birth_analysis'] = births
    if not births['eligible']:
        return dict(result, reason='no_unique_quantity_independent_birth')
    birth = births['candidates'][0]
    result['application_displayed_tick'] = birth['birth_tick']
    result['server_application_time'] = 'UNKNOWN'
    try:
        predicted = from_canonical(before)
    except (UnsupportedState, ValueError) as error:
        return dict(result, reason=f'unsupported_before: {error}', classification='UNSUPPORTED')
    for observed in observations:
        actions = (LaunchAll(source, destination, terminal=terminal),) if observed.tick.value == birth['birth_tick'] else ()
        try:
            predicted = step(predicted, actions)
            actual = from_canonical(observed)
        except (UnsupportedState, ValueError) as error:
            return dict(result, status='STOPPED_UNSUPPORTED', classification='UNSUPPORTED',
                        first_unsupported_tick=observed.tick.value, reason=str(error))
        if actions:
            newborn = predicted.forces[-1]
            result['predicted_newborn'] = {'units': [(i, n) for i, n in enumerate(newborn.units) if n],
                                           'progress': newborn.progress, 'accelerated': newborn.accelerated,
                                           'fuel': newborn.fuel}
            result['birth_vector_equal'] = tuple(result['predicted_newborn']['units']) == tuple(birth['birth_units'])
        difference = first_difference(_signature(predicted), _signature(actual))
        if difference:
            return dict(result, status='MISMATCH', classification='UNKNOWN',
                        first_divergence={'tick': observed.tick.value, **difference},
                        reason='complete_visible_world_diverged; causality_requires_separate_audit')
        result['matched_intermediate_ticks'].append(observed.tick.value)
    return dict(result, status='MATCHED_RECORDED_WINDOW', classification='MATCHED_DIAGNOSTIC_ONLY')


def audit_recording(path, *, allow_legacy_manual_ui=False):
    data = Path(path).read_bytes()
    if str(path).endswith('.gz'):
        data = gzip.decompress(data)
    events = [json.loads(line) for line in data.decode('utf8').splitlines()]
    result = audit_events(events, allow_legacy_manual_ui=allow_legacy_manual_ui)
    result['manifest'] = {'recording_sha256': hashlib.sha256(data).hexdigest(),
                          'auditor_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          'simulator_sha256': hashlib.sha256((ROOT / 'src/kiomet_ai/v2/sim/step.py').read_bytes()).hexdigest()}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording', type=Path)
    parser.add_argument('--legacy-manual-ui-calibration', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    receipt = audit_recording(args.recording, allow_legacy_manual_ui=args.legacy_manual_ui_calibration)
    rendered = json.dumps(receipt, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in receipt.items() if key != 'observed_birth_analysis'}, ensure_ascii=True))
