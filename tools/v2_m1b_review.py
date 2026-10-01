"""Finite reuse audit: existing production cohorts, never a new live benchmark."""
import collections, hashlib, json, statistics, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.control import CLIENT_PIN, control_readiness_gaps

def review(name):
    folder=ROOT/'runtime/research/v2'
    path=folder/f'snapshots-{name}.jsonl'
    original=json.loads((folder/f'sampling-{name}.json').read_text(encoding='utf8'))
    digest=hashlib.sha256()
    counts=collections.Counter()
    gaps=collections.Counter()
    faults=collections.Counter()
    prior=None
    cadence=[]
    total_delta=0
    elapsed=0
    last_event=None
    with path.open('rb') as stream:
        for raw in stream:
            digest.update(raw)
            state=state_from_dict(json.loads(raw))
            counts['snapshots']+=1
            if state.client_sha256!=CLIENT_PIN: faults['version']+=1
            if state.source_mode.value!='NETWORK': faults['mode']+=1
            ids={t.id for t in state.towers}
            for actor in (*state.towers,*(state.forces.value or ())):
                if actor.visibility.value is not True or str(actor.visibility.knowledge)!='OBSERVED':
                    faults['visibility']+=1
                if actor.units.value is not None and {u for u,n in actor.units.value.counts}!=set(range(10)):
                    faults['unit_vector']+=1
            for force in state.forces.value or ():
                if state.match_id.value is None and force.id.value is not None: faults['epoch_id_reuse']+=1
                if any(f.value is not None and f.value not in ids for f in (force.source,force.destination)):
                    faults['hidden_endpoint']+=1
            scope=(state.document_id,state.match_id.value,state.player_id.value)
            if prior and scope==prior[0] and state.tick.value!=prior[1]:
                delta=(state.tick.value-prior[1])%65536
                if delta>=32768: faults['backward_sequence']+=1
            if last_event is None or scope!=last_event[0]:
                last_event=(scope,state.tick.value,state.sampled_at_ms)
            elif state.tick.value!=last_event[1]:
                delta=(state.tick.value-last_event[1])%65536
                dt=state.sampled_at_ms-last_event[2]
                if state.match_id.value is not None and 0<delta<=16 and dt>0:
                    cadence.append(dt/delta)
                    total_delta+=delta
                    elapsed+=dt
                last_event=(scope,state.tick.value,state.sampled_at_ms)
            prior=(scope,state.tick.value)
            current_gaps=control_readiness_gaps(state,state.received_at_ms)
            gaps.update(current_gaps)
            counts['control_ready' if not current_gaps else 'not_ready']+=1
            counts['complete_visible' if state.coverage=='PLAYER_VISIBLE_COMPLETE' else 'partial_visible']+=1
    return {'cohort':name,'recorded_benchmark':original,'snapshot_sha256':digest.hexdigest(),
            'audit_counts':dict(counts),'rejection_fields':dict(gaps),'faults':dict(faults),
            'runtime_tick_model':{'knowledge':'DERIVED','scope':'observed client world cadence, not server wall time',
                'advance_events':len(cadence),'tick_steps':total_delta,
                'observed_ms_per_tick':elapsed/total_delta if total_delta else None,
                'median_event_ms_per_tick':statistics.median(cadence) if cadence else None}}

def main():
    reports=[review(name) for name in ('fe678ebb30ce','03d032d57e5b','f3f22dae0791')]
    result={'status':'REVIEW','question':'Do three existing pinned live cohorts preserve M1B safety, order and measured rate/latency?',
            'limits':'Offline audit of previously recorded live data; not new live sampling, not whole-state correctness. Missing fields remain unknown.',
            'cohorts':reports,'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (ROOT/'docs/V2_M1B_EVIDENCE.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    for row in reports:
        print(json.dumps({key:row[key] for key in ('cohort','audit_counts','faults','runtime_tick_model')}))

if __name__=='__main__': main()
