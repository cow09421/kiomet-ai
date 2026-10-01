"""Finite full observable-state one-tick differential corpus, with exclusions."""
import argparse, collections, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import from_canonical, step, UnsupportedState, Scenario
from kiomet_ai.v2.sim.step import phase


def signature(state):
    return {'world_sequence':state.world_sequence,
            'towers':[(t.id,t.owner,t.kind,t.units,t.delay,t.morale) for t in state.towers],
            # Multiset comparison does not pretend observer IDs are permanent.
            'forces':sorted((f.owner,f.source,f.destination,f.units,f.progress) for f in state.forces),
            'rulers':sorted(state.visible_rulers)}


def inspect(cohort, ground_combat=False):
    source=ROOT/f'runtime/research/v2/snapshots-{cohort}.jsonl'
    counts=collections.Counter()
    failures=[]
    cases=[]
    previous=None
    digest=hashlib.sha256()
    with source.open('rb') as stream:
        for raw in stream:
            digest.update(raw)
            current=state_from_dict(json.loads(raw))
            if previous is None:
                previous=current
                continue
            if current.tick.value==previous.tick.value:
                continue  # First sampled observation per tick; never select by correctness.
            before=previous
            previous=current
            counts['world_transitions']+=1
            scope=lambda s:(s.document_id,s.match_id.value,s.player_id.value)
            if scope(before)!=scope(current) or before.match_id.value is None:
                counts['exclude:isolation']+=1;continue
            if (current.tick.value-before.tick.value)%65536!=1:
                counts['exclude:multi_tick_or_backward']+=1;continue
            try:
                start=from_canonical(before)
                end=from_canonical(current)
            except UnsupportedState as exc:
                counts['exclude:'+str(exc).split(':')[0]]+=1;continue
            if tuple(t.id for t in start.towers)!=tuple(t.id for t in end.towers):
                counts['exclude:visible_set_change']+=1;continue
            if any((a.owner,a.kind,a.delay,a.morale)!=(b.owner,b.kind,b.delay,b.morale)
                   for a,b in zip(start.towers,end.towers)):
                counts['exclude:external_owner_type_delay_aura_change']+=1;continue
            if len(start.forces)!=len(end.forces) and not ground_combat:
                counts['exclude:external_force_birth_or_arrival']+=1;continue
            if len(end.forces)>len(start.forces):
                counts['exclude:unrecorded_external_launch']+=1;continue
            meaningful=bool(start.forces) or any(t.owner and
                phase((start.world_sequence+1)&65535,t.id)%120==0 and
                any(n>t.capacity[i] for i,n in enumerate(t.units)) for t in start.towers) or any(
                phase((start.world_sequence+1)&65535,t.id)%period==0
                for t in start.towers for unit,period in t.production)
            if not meaningful:
                counts['exclude:no_production_or_movement_event']+=1;continue
            try: predicted=step(start,scenario=Scenario(ground_combat=ground_combat))
            except UnsupportedState as exc:
                counts['exclude:'+str(exc)]+=1;continue
            expected=signature(end)
            actual=signature(predicted)
            matched=actual==expected
            counts['cases']+=1
            counts['matched']+=matched
            counts['movement_cases' if start.forces else 'production_cases']+=1
            payload={'cohort':cohort,'before_sequence':before.sequence,'after_sequence':current.sequence,
                     'world_sequence':start.world_sequence,'matched':matched,'input':signature(start),
                     'expected':expected,'predicted':actual}
            cases.append(payload)
            if not matched and len(failures)<10:
                differences=[]
                for a,b in zip(predicted.towers,end.towers):
                    if a.units!=b.units: differences.append({'tower':a.id,'kind':a.kind,'owner':a.owner,
                        'morale':a.morale,'units_before':next(t.units for t in start.towers if t.id==a.id),
                        'predicted':a.units,'expected':b.units,'production':a.production,'phase':phase(predicted.world_sequence,a.id)})
                failures.append({'before_sequence':before.sequence,'tick':start.world_sequence,
                    'tower_differences':differences,'force_match':actual['forces']==expected['forces']})
    return {'cohort':cohort,'snapshot_sha256':digest.hexdigest(),'counts':dict(counts),'failures':failures},cases


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cohorts',nargs='+',default=['fe678ebb30ce','03d032d57e5b'])
    parser.add_argument('--ground-combat',action='store_true',help='Evaluate the ground-fight reference hypothesis; not a live combat PASS')
    parser.add_argument('--label',default='development',choices=['development','holdout','hypothesis'])
    args=parser.parse_args()
    if args.ground_combat!=(args.label=='hypothesis'):
        parser.error('ground-combat hypotheses require --label hypothesis, isolated from formal corpus')
    results=[]
    output=ROOT/f'runtime/research/v2/m2a-{args.label}-transition-corpus.jsonl'
    total=collections.Counter()
    with output.open('w',encoding='utf8') as stream:
        for cohort in args.cohorts:
            report,cases=inspect(cohort,args.ground_combat)
            results.append(report)
            total.update(report['counts'])
            for row in cases: stream.write(json.dumps(row)+'\n')
            print(json.dumps(report),flush=True)
    result={'status':'HYPOTHESIS_ONLY' if args.ground_combat else 'IN_PROGRESS','scope':'complete supported visible-state step; no live commands; explicit no-exogenous-action fixed-morale scenario',
            'ground_combat_reference_enabled':args.ground_combat,
            'validation_split':args.label,
            'selection':'one-tick same epoch and visible set, known minimum inputs; no owner/type/delay/aura/force count changes. Counts never used to select correctness.',
            'limitations':'Excluded events and unsupported mechanics do not count as accurate. Repeated tick polls and no-event states excluded; full-state accuracy within supported corpus only.',
            'counts':dict(total),'cohorts':results,'corpus_file':str(output.relative_to(ROOT)),
            'corpus_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_manifest':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (ROOT/'src/kiomet_ai/v2/sim').glob('*.py')}}
    target={'holdout':'V2_M2A_HOLDOUT.json','development':'V2_M2A_DIFFERENTIAL.json','hypothesis':'V2_M2A_GROUND_CANDIDATE.json'}[args.label]
    (ROOT/'docs'/target).write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'counts':dict(total),'accuracy':total['matched']/total['cases'] if total['cases'] else None}))

if __name__=='__main__':main()
