"""Archive selected three-tick arrival observations from one bounded live scene."""
import gzip
import hashlib
import json
from pathlib import Path
from tools.v2_arrival_candidate_audit import observation, indexed, pair_candidates

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'runtime/research/v2/ordinary-arrival-scene-ae45ad53c1b4.json'
OUTPUT = ROOT/'tests/fixtures/v2/arrival-boundary-live-candidates.json.gz'


def run():
    payload = SOURCE.read_bytes()
    receipt = json.loads(payload)
    if receipt['status'] != 'PASSIVE_SCENE_RECORDED_NOT_CERTIFIED' or receipt['troop_dispatch_attempts'] != 0:
        raise ValueError('bounded passive scene receipt required')
    unique = []
    seen = set()
    for index, raw in enumerate(receipt['observations']):
        row = observation(raw)
        if row is None or (*row['scope'], row['tick']) in seen:
            continue
        # Unlike the historical compact scan, retain a target after the final
        # force disappears: it is still a positively visible tower.
        row['towers'] = indexed(raw['towers'])
        unique.append((row, raw, index))
        seen.add((*row['scope'], row['tick']))
    cases = []
    for triple in zip(unique, unique[1:], unique[2:]):
        b, a, n = [item[0] for item in triple]
        if b['scope'] != a['scope'] or a['scope'] != n['scope']:
            continue
        if (a['tick']-b['tick']) % 65536 != 1 or (n['tick']-a['tick']) % 65536 != 1:
            continue
        for candidate in pair_candidates('live-ae45ad53c1b4', b, a, n):
            observations = []
            for role, (_, raw, index) in zip(('before','arrival','following'), triple):
                towers = {t['id']: t for t in raw['towers']}
                observations.append({'role': role,
                    'raw_source': {'path': str(SOURCE.relative_to(ROOT)),
                        'sha256': hashlib.sha256(payload).hexdigest(), 'json_observations_array_index': index,
                        'canonical_object_sha256': hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':')).encode()).hexdigest()},
                    'scope': {k: raw[k] for k in ('document_id','session_id','match_id','player_id','lifecycle','source_mode')},
                    'observation': {k: raw[k] for k in ('tick','sequence','coverage','document_time_origin_ms','sampled_at_ms','received_at_ms')},
                    'source_and_target_facts': {key: {'tower_id': ident,'visible_fact_object': towers.get(ident)}
                        for key, ident in (('source',candidate['source_tower']),('target',candidate['target_tower']))},
                    'visible_actor_fields_all_forces': raw['forces']})
            cases.append({'candidate': candidate, 'observations': observations})
    result = {'status': 'BOUNDED_NEW_LIVE_BOUNDARY_CANDIDATES_NOT_CERTIFIED', 'cases': cases,
        'source_sha256': hashlib.sha256(payload).hexdigest(), 'source_observations': len(receipt['observations']),
        'troop_dispatch_attempts': 0, 'source_ui_actions': receipt['ui_actions'],
        'selection': 'three consecutive same-scope observations; all visible towers; no tracker-ID criterion',
        'context': 'one fresh ordinary Party scene; forces already present at first retained tick; launch provenance unknown; no troop input from agent',
        'formal_credit': 0}
    OUTPUT.write_bytes(gzip.compress((json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0))
    print(json.dumps({'candidates': len(cases),'fixture':str(OUTPUT.relative_to(ROOT))}))


if __name__ == '__main__':
    run()
