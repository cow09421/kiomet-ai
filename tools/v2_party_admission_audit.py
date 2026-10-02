"""Offline, diagnostic-only admission checks for a saved player-visible cohort."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.control import control_readiness_gaps
from kiomet_ai.v2.sim import from_canonical, step, UnsupportedState, Scenario
from v2_sim_differential import signature, input_event_categories


def changes(a,b):
    before={t.id:t for t in a.towers}; after={t.id:t for t in b.towers}
    shared=before.keys()&after.keys()
    fields={'owner':'tower_owner_changes','kind':'tower_kind_changes','units':'tower_unit_vector_changes',
            'morale':'tower_aura_changes','capacity':'tower_capacity_changes','production':'tower_production_changes'}
    result={label:sum(getattr(before[i],field)!=getattr(after[i],field) for i in shared)
            for field,label in fields.items()}
    result.update(towers_added=len(after.keys()-before.keys()),towers_removed=len(before.keys()-after.keys()),
                  force_count_before=len(a.forces),force_count_after=len(b.forces))
    return result


def first_difference(predicted,observed,path=''):
    if type(predicted) is not type(observed):
        return {'field':path,'predicted':predicted,'observed':observed}
    if isinstance(predicted,dict):
        if predicted.keys()!=observed.keys():
            return {'field':path,'predicted_keys':list(predicted),'observed_keys':list(observed)}
        for key in predicted:
            mismatch=first_difference(predicted[key],observed[key],path+'/'+str(key))
            if mismatch is not None:return mismatch
    elif isinstance(predicted,(tuple,list)):
        if len(predicted)!=len(observed):
            return {'field':path+'/length','predicted':len(predicted),'observed':len(observed)}
        for ordinal,(left,right) in enumerate(zip(predicted,observed)):
            mismatch=first_difference(left,right,path+'/'+str(ordinal))
            if mismatch is not None:return mismatch
    elif predicted!=observed:
        return {'field':path,'predicted':predicted,'observed':observed}
    return None


def audit(path):
    raw=path.read_bytes()
    payload=gzip.decompress(raw) if path.suffix=='.gz' else raw
    receipt=json.loads(payload.decode('utf8'))
    states=[state_from_dict(row['state']) for row in receipt['OBSERVED']]
    gaps=[control_readiness_gaps(state,state.received_at_ms) for state in states]
    canonical=[from_canonical(state) for state in states]
    failures=[]; state_passes=0; reasons=Counter()
    for ordinal,state in enumerate(canonical,1):
        try:
            step(state,scenario=Scenario(fixed_morale=True)); state_passes+=1
        except UnsupportedState as exc:
            reason=str(exc); reasons[reason]+=1
            failures.append({'sample':ordinal,'tick':state.world_sequence,'reason':reason})
    pairs=[]; timeline=Counter()
    for ordinal,(before,after) in enumerate(zip(canonical,canonical[1:]),2):
        delta=(after.world_sequence-before.world_sequence)&65535
        if delta==0:
            timeline['repeat_same_tick']+=1; continue
        if delta!=1:
            timeline['multi_tick_gap']+=1; continue
        timeline['exact_consecutive']+=1
        row={'pair_ordinal':ordinal,'before_tick':before.world_sequence,'after_tick':after.world_sequence,
             'before_event_categories':input_event_categories(before),'observed_delta_counts':changes(before,after)}
        try:
            predicted=step(before,scenario=Scenario(fixed_morale=True))
            timeline['step_pass']+=1
            predicted_signature=signature(predicted); observed_signature=signature(after)
            equal=predicted_signature==observed_signature
            timeline['signature_match' if equal else 'signature_mismatch']+=1
            row['comparison']='EXACT_SIGNATURE_MATCH' if equal else 'SIGNATURE_MISMATCH'
            if not equal:
                row['prediction_delta_counts']=changes(predicted,after)
                row['first_difference']=first_difference(predicted_signature,observed_signature)
        except UnsupportedState as exc:
            reason=str(exc); timeline['step_rejected:'+reason]+=1
            row.update(admission='STEP_REJECTED',first_failure=reason)
        pairs.append(row)
    return {'status':'DIAGNOSTIC_ONLY_NO_FORMAL_CREDIT','formal_credit':0,
            'input':{'fixture':str(path),'artifact_sha256':hashlib.sha256(raw).hexdigest(),
                     'payload_sha256':hashlib.sha256(payload).hexdigest(),'sample_count':len(states)},
            'scenario':{'fixed_morale':True,'diagnostic_premise_only':True,
                        'whole_world_and_foreign_action_completeness':'UNKNOWN'},
            'canonical_readiness':{'restored_samples':len(states),'states_with_control_readiness_gaps':sum(bool(g) for g in gaps)},
            'single_state_step':{'pass':state_passes,'failure_reasons':dict(reasons)},
            'state_first_failures':failures,'pair_timeline':dict(timeline),'pairs':pairs,
            'boundary':'Independent one-tick diagnostics. No long trajectory, formal admission, after-fit route/fuel, or hidden-world facts are inferred.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'tests/fixtures/v2/party-route-readiness-20261002/party-readiness-route-supported-2-20261002.json.gz')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.resolve()==args.input.resolve():parser.error('output must preserve input')
    report=audit(args.input)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({'output':str(args.output),'formal_credit':0,'samples':report['input']['sample_count'],
                      'pair_timeline':report['pair_timeline'],'first_failures':report['state_first_failures']}))

if __name__=='__main__':main()
