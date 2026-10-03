"""Small descriptive event-changing subset and competing-risk report.

Uses existing pinned complete fixtures. No new observations or causal labels.
"""
from __future__ import annotations
import collections
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HORIZONS = (1, 2, 4, 8, 16, 20)


def risk(stop):
    if stop['kind'] == 'MISMATCH': return 'MISMATCH'
    if stop['kind'] == 'RIGHT_CENSORED_RECORDING_END': return 'RECORDING_END'
    reason = stop['reason']
    if reason.startswith('OBSERVED_ENDPOINT:'):
        observed = reason.split(':', 1)[1]
        return 'UPGRADE_CENSOR' if observed == 'ACTIVE_UPGRADE_OR_EMP' else 'INPUT_UNKNOWN'
    if reason in ('PRODUCTION_SUPPLY_LINE', 'MOBILE_OVERFLOW_SUPPLY_LINE'): return 'SUPPLY_LINE_CENSOR'
    if reason in ('UNKNOWN_POST_ARRIVAL_PATH', 'UNKNOWN_ARRIVAL_ACCELERATION', 'UNKNOWN_ARRIVAL_FUEL', 'EXPIRED_ARRIVAL'): return 'ARRIVAL_CENSOR'
    if reason in ('UNVERIFIED_NORMAL_COMBAT', 'OPPOSED_FORCE_COMBAT', 'UNKNOWN_PAIR_RELATION'): return 'COMBAT_CENSOR'
    if reason == 'ACTIVE_UPGRADE_OR_EMP': return 'UPGRADE_CENSOR'
    if reason in ('OBSERVATION_SCOPE_OR_TICK_GAP', 'NOT_READY'): return 'INPUT_UNKNOWN'
    return 'OTHER_CENSOR'


def outcomes(row):
    return {str(h): 'EXACT_SURVIVAL' if row['clean_ticks'] >= h else risk(row['first_stop']) for h in HORIZONS}


def _load(report, key):
    artifact = report[key]
    path = ROOT / artifact['path'].replace('\\', '/')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact['sha256']
    with gzip.open(path, 'rt', encoding='utf8') as stream:
        return [json.loads(line) for line in stream]


def run(output, horizon_path=None):
    coverage_path = ROOT / 'docs/V2_M2A_COVERAGE_DENOMINATOR.json'
    horizon_path = horizon_path or ROOT / 'docs/V2_M2A_HORIZON_BASELINES.json'
    coverage = json.loads(coverage_path.read_text(encoding='utf8'))
    horizon = json.loads(horizon_path.read_text(encoding='utf8'))
    edges = _load(coverage, 'edge_audit')
    starts = _load(horizon, 'start_audit')
    selected = []
    patterns = collections.Counter()
    for edge in edges:
        if not edge['same_scope_consecutive']: continue
        observed = edge['observed_event_patterns']
        labels = [name for name in ('owner_changes', 'tower_unit_vector_changes') if observed.get(name)]
        if not labels: continue
        patterns.update(labels)
        selected.append({'cohort': edge['cohort'], 'split': edge['split'], 'edge_index': edge['edge_index'],
            'labels': labels, 'whole_world_status': edge['comparison_status'],
            'first_blocker': edge.get('primary_blocker'),
            'static_owner_and_inventory_correct': False,
            'cause': 'UNKNOWN; observed change is not certified production/capture/combat'})
    supported = sum(x['whole_world_status'] in ('SUCCESS', 'MISMATCH') for x in selected)
    correct = sum(x['whole_world_status'] == 'SUCCESS' for x in selected)
    all_risks = {str(h): collections.Counter() for h in HORIZONS}
    active_risks = {str(h): collections.Counter() for h in HORIZONS}
    by_split = {s: {str(h): collections.Counter() for h in HORIZONS} for s in ('development', 'holdout')}
    for row in starts:
        for h, value in outcomes(row).items():
            all_risks[h][value] += 1
            by_split[row['split']][h][value] += 1
            if row['first_edge_activity'] == 'ACTIVE_KNOWN': active_risks[h][value] += 1
    result = {'status': 'CANDIDATE_ANALYSIS_ONLY', 'formal_credit': 0,
        'source_reports_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (coverage_path, horizon_path)},
        'source_fixture_hashes': {'edge_audit': coverage['edge_audit']['sha256'], 'horizon_origins': horizon['start_audit']['sha256']},
        'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'baseline_discriminating': {'scope': 'Observed consecutive owner or typed tower inventory changes; union of edges, not independent events',
            'observed_edges': len(selected), 'patterns_overlapping': dict(patterns),
            'simulator_supported': supported, 'simulator_full_world_correct': correct,
            'coverage': supported / len(selected) if selected else None,
            'accuracy_supported': correct / supported if supported else None,
            'static_owner_and_inventory_correct': 0,
            'selection_limit': 'Static baseline fails by subset definition. This is a descriptive discriminator, not evidence of causal attribution or an independently frozen prospective benchmark.',
            'edge_rows': selected},
        'horizon_competing_risks': {'legal_origin_denominator': len(starts),
            'execution_provenance': horizon.get('git_before', horizon.get('git')),
            'source_hashes': horizon.get('source_hashes'),
            'active_legal_origin_denominator': sum(x['first_edge_activity'] == 'ACTIVE_KNOWN' for x in starts),
            'all_legal_origins': all_risks, 'active_legal_origins': active_risks, 'by_split': by_split,
            'source_forecast': 'Pinned default no-action continuous predictions from the identified source report; no resets. First stop competes; origins overlap and are not independent events.',
            'classification': 'Exact source refusal reason mapped to one risk; observed input loss is separate from semantic step refusal.'}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
    print(json.dumps({'observed': len(selected), 'supported': supported, 'correct': correct,
        'risks': result['horizon_competing_risks']['all_legal_origins']}, default=dict))
    return result


if __name__ == '__main__':
    run(ROOT / 'runtime/research/v2/semantic-checkpoint-metrics.json')
