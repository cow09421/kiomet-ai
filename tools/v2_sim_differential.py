"""Finite full observable-state one-tick differential corpus, with exclusions."""
import argparse, collections, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import from_canonical, step, UnsupportedState, Scenario
from kiomet_ai.v2.sim.step import phase, movement_parameters
from kiomet_ai.v2.observe.rules import DOWNGRADE


def input_has_potential_event(state):
    """Before-only selection; an at-capacity production attempt is not an event.

    Potential unsupported decay/deployment still reaches step and is excluded
    by its explicit guard. Never drop a mismatch because the after state stayed
    unchanged when the before state predicted a real production event.
    """
    if state.forces:
        return True
    sequence=(state.world_sequence+1)&65535
    for tower in state.towers:
        clock=phase(sequence,tower.id)
        if not tower.owner:
            if clock%40==0 and any(tower.units) or clock%240==0 and DOWNGRADE[tower.kind]!=27:
                return True
            continue
        if clock%120==0 and any(n>tower.capacity[i] for i,n in enumerate(tower.units)):
            return True
        for unit,period in tower.production:
            if period<=0:
                return True  # Let step report INVALID_PRODUCTION_PERIOD.
            if clock%period:
                continue
            if unit in (6,7,8,9):
                return True  # Unverified special production must hit its guard.
            if 1<=unit<=5 and any(tower.units[6:10]):
                continue
            if tower.units[unit]<tower.capacity[unit]:
                return True
            if not tower.units[9] and (unit or tower.kind==15):
                return True  # Full mobile production may auto-deploy; do not ignore it.
    return False


def input_event_categories(state):
    """Overlapping diagnostics derived only from the observed before state.

    These do not select cases, and each category has its own matched count.
    In particular, ordinary movement must not dilute combat failures.
    """
    categories=[]
    next_tick=(state.world_sequence+1)&65535
    if any(phase(next_tick,t.id)%period==0 for t in state.towers
           for unit,period in t.production):
        categories.append('production_due')
    if state.forces:
        categories.append('current_leg_movement')
    towers={t.id:t for t in state.towers}
    for force in state.forces:
        source=towers[force.source]
        target=towers[force.destination]
        speed,required=movement_parameters(force.units,source.position,target.position)
        if force.accelerated:
            required=max(1,required*4//5)
        if min(255,force.progress+speed)>=required and target.owner!=force.owner:
            if target.owner or any(target.units):
                categories.append('ordinary_air_unit_combat_arrival' if any(force.units[i] or target.units[i] for i in (1,2,3))
                                  else 'ground_combat_arrival')
                break
    return categories


def signature(state):
    return {'world_sequence':state.world_sequence,
            'towers':[(t.id,t.owner,t.kind,t.units,t.delay,t.morale) for t in state.towers],
            # Multiset comparison does not pretend observer IDs are permanent.
            'forces':sorted((f.owner,f.source,f.destination,f.units,f.progress) for f in state.forces),
            'rulers':sorted(state.visible_rulers)}


def inspect(cohort, ground_combat=False, ordinary_combat=False):
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
            if len(start.forces)!=len(end.forces) and not (ground_combat or ordinary_combat):
                counts['exclude:external_force_birth_or_arrival']+=1;continue
            if len(end.forces)>len(start.forces):
                counts['exclude:unrecorded_external_launch']+=1;continue
            if not input_has_potential_event(start):
                counts['exclude:no_potential_visible_event']+=1;continue
            try: predicted=step(start,scenario=Scenario(ground_combat=ground_combat,ordinary_combat=ordinary_combat))
            except UnsupportedState as exc:
                counts['exclude:'+str(exc)]+=1;continue
            expected=signature(end)
            actual=signature(predicted)
            matched=actual==expected
            counts['cases']+=1
            counts['matched']+=matched
            counts['movement_cases' if start.forces else 'production_cases']+=1
            event_categories=input_event_categories(start)
            for category in event_categories:
                counts['event:'+category+':cases']+=1
                counts['event:'+category+':matched']+=int(matched)
            payload={'cohort':cohort,'before_sequence':before.sequence,'after_sequence':current.sequence,
                     'world_sequence':start.world_sequence,'matched':matched,'event_categories':event_categories,'input':signature(start),
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
    parser.add_argument('--ordinary-combat',action='store_true',help='Evaluate the ordinary Air/Surface hypothesis in a separate corpus')
    parser.add_argument('--label',default='development',choices=['development','holdout','hypothesis','ordinary_hypothesis'])
    args=parser.parse_args()
    if args.ground_combat!=(args.label=='hypothesis') or args.ordinary_combat!=(args.label=='ordinary_hypothesis'):
        parser.error('use --ground-combat with --label hypothesis OR --ordinary-combat with --label ordinary_hypothesis; hypotheses are isolated from formal corpus')
    results=[]
    output=ROOT/f'runtime/research/v2/m2a-{args.label}-transition-corpus.jsonl'
    total=collections.Counter()
    with output.open('w',encoding='utf8') as stream:
        for cohort in args.cohorts:
            report,cases=inspect(cohort,args.ground_combat,args.ordinary_combat)
            results.append(report)
            total.update(report['counts'])
            for row in cases: stream.write(json.dumps(row)+'\n')
            print(json.dumps(report),flush=True)
    result={'status':'HYPOTHESIS_ONLY' if (args.ground_combat or args.ordinary_combat) else 'IN_PROGRESS','scope':'complete supported visible-state step; no live commands; explicit no-exogenous-action fixed-morale scenario',
            'ground_combat_reference_enabled':args.ground_combat,
            'ordinary_combat_reference_enabled':args.ordinary_combat,
            'validation_split':args.label,
            'selection':'First observation per tick, same epoch and visible set, known minimum inputs; no owner/type/delay/aura changes or net force births. Combat hypotheses permit force count decreases. Before-only event predicate rejects at-capacity stationary production attempts, while potential unsupported events still reach explicit guards. Predictions and after-state agreement never select cases.',
            'event_count_semantics':'Overlapping event categories are derived from before-state inputs; each reports its own complete-state matched count. They are not additional independent cases.',
            'limitations':'Excluded events and unsupported mechanics do not count as accurate. Repeated tick polls and no-event states excluded; full-state accuracy within supported corpus only.',
            'counts':dict(total),'cohorts':results,'corpus_file':str(output.relative_to(ROOT)),
            'corpus_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_manifest':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (ROOT/'src/kiomet_ai/v2/sim').glob('*.py')}}
    target={'holdout':'V2_M2A_HOLDOUT.json','development':'V2_M2A_DIFFERENTIAL.json','hypothesis':'V2_M2A_GROUND_CANDIDATE.json',
            'ordinary_hypothesis':'V2_M2A_ORDINARY_CANDIDATE.json'}[args.label]
    (ROOT/'docs'/target).write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'counts':dict(total),'accuracy':total['matched']/total['cases'] if total['cases'] else None}))

if __name__=='__main__':main()
