"""Finite nonoverlapping 5-second rollouts, no resetting to observed intermediates."""
import argparse, collections, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import from_canonical, step, UnsupportedState, RuntimeTimeModel
from v2_sim_differential import signature

def mismatch_summary(predicted,observed):
    left,right=signature(predicted),signature(observed)
    a={t[0]:t for t in left['towers']};b={t[0]:t for t in right['towers']}
    return {'predicted_signature_sha256':hashlib.sha256(json.dumps(left).encode()).hexdigest(),
        'observed_signature_sha256':hashlib.sha256(json.dumps(right).encode()).hexdigest(),
        'tower_differences':[{'id':key,'predicted':a.get(key),'observed':b.get(key)}
                             for key in sorted(a.keys()|b.keys()) if a.get(key)!=b.get(key)],
        'force_difference':{'predicted':left['forces'],'observed':right['forces']}
                            if left['forces']!=right['forces'] else None,
        'ruler_difference':{'predicted':left['rulers'],'observed':right['rulers']}
                            if left['rulers']!=right['rulers'] else None}

def inspect(cohort,ticks):
    counts=collections.Counter(); chains=[]; failures=[]
    predicted=None; last_tick=None; start=None; length=events=0
    source=ROOT/f'runtime/research/v2/snapshots-{cohort}.jsonl'
    with source.open() as stream:
        for line in stream:
            canonical=state_from_dict(json.loads(line))
            if canonical.tick.value==last_tick: continue
            last_tick=canonical.tick.value
            try: observed=from_canonical(canonical)
            except UnsupportedState as exc:
                counts['exclude:'+str(exc).split(':')[0]]+=1
                predicted=None; continue
            if predicted is not None:
                same_scope=(predicted.document,predicted.match_epoch,predicted.player)==(observed.document,observed.match_epoch,observed.player)
                if not same_scope or (observed.world_sequence-predicted.world_sequence)%65536!=1:
                    counts['exclude:scope_or_sequence']+=1; predicted=None
            if predicted is None:
                predicted=observed; start=canonical.sequence; length=events=0; continue
            old=predicted
            try: predicted=step(old)
            except UnsupportedState as exc:
                counts['exclude:'+str(exc)]+=1; predicted=None; continue
            if signature(predicted)!=signature(observed):
                counts['intermediate_mismatches']+=1
                if len(failures)<10: failures.append({'cohort':cohort,'start':start,'at':canonical.sequence,'ticks':length+1,
                    **mismatch_summary(predicted,observed)})
                predicted=None; continue
            length+=1
            events+=int(old.towers!=predicted.towers or old.forces!=predicted.forces)
            if length==ticks:
                if events>=2:
                    counts['complete_matched_trajectories']+=1
                    chains.append({'cohort':cohort,'start':start,'end':canonical.sequence,'ticks':length,'event_ticks':events})
                else: counts['exclude:fewer_than_two_events']+=1
                predicted=None
    return {'cohort':cohort,'raw_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'counts':dict(counts),'failures':failures},chains

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cohorts',nargs='+',required=True); args=parser.parse_args()
    time_model=RuntimeTimeModel.from_live_evidence(json.loads((ROOT/'docs/V2_M1B_EVIDENCE.json').read_text()))
    ticks=round(5000/time_model.tick_duration_ms)
    reports=[]; chains=[];total=collections.Counter()
    for cohort in args.cohorts:
        report,rows=inspect(cohort,ticks);reports.append(report);chains.extend(rows);total.update(report['counts'])
        print(json.dumps({'cohort':cohort,'counts':report['counts']}),flush=True)
    result={'status':'IN_PROGRESS','validation_split':'development','tick_duration_ms':time_model.tick_duration_ms,
        'trajectory_ticks':ticks,'trajectory_duration_ms':time_model.milliseconds(ticks),
        'selection':'First observation per tick; nonoverlapping complete consecutive chains, same scope; no intermediate canonical reset. All mismatches retained, not counted as success.',
        'counts':dict(total),'cohorts':reports,'matched_trajectories':chains,
        'source_manifest':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'src/kiomet_ai/v2/sim').glob('*.py')}}
    (ROOT/'docs/V2_M2A_TRAJECTORIES.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'counts':dict(total)}))

if __name__=='__main__': main()
