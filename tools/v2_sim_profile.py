"""Profile COMPLETE supported world steps from observed canonical inputs."""
import cProfile, hashlib, io, json, pstats, sys, time
from statistics import median
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import from_canonical, step
from v2_sim_differential import signature

def main():
    report=json.loads((ROOT/'docs/V2_M2A_DIFFERENTIAL.json').read_text())
    cases=[json.loads(line) for line in (ROOT/report['corpus_file']).read_text().splitlines()]
    selected={(r['cohort'],r['before_sequence']):r for r in cases if r['matched']}
    inputs=[]
    for cohort in sorted({key[0] for key in selected}):
        with (ROOT/f'runtime/research/v2/snapshots-{cohort}.jsonl').open() as stream:
            for line in stream:
                raw=json.loads(line)
                case=selected.get((cohort,raw['sequence']))
                if case is None: continue
                state=from_canonical(state_from_dict(raw))
                # Every timed input has a complete end-state comparison first.
                assert json.loads(json.dumps(signature(step(state))))==case['expected']
                inputs.append(state)
    assert inputs
    repeats=max(1,(100000+len(inputs)-1)//len(inputs))
    trials=[]
    for _ in range(3):
        start=time.perf_counter()
        for _ in range(repeats):
            for state in inputs: step(state)
        elapsed=time.perf_counter()-start
        trials.append({'complete_transitions':repeats*len(inputs),'elapsed_seconds':elapsed,
                       'complete_transitions_per_second':repeats*len(inputs)/elapsed})
    profiler=cProfile.Profile()
    profiler.enable()
    for state in inputs: step(state)
    profiler.disable()
    output=io.StringIO()
    pstats.Stats(profiler,stream=output).sort_stats('cumtime').print_stats(18)
    result={'status':'MEASURED_SUPPORTED_SCOPE_ONLY','input_cases':len(inputs),
            'complete_transitions':sum(t['complete_transitions'] for t in trials),
            'elapsed_seconds':sum(t['elapsed_seconds'] for t in trials),
            'complete_transitions_per_second':median(t['complete_transitions_per_second'] for t in trials),
            'rate_statistic':'median of three trials, each >=100000 complete transitions',
            'trials':trials,
            'scope':'Full Python step over all visible towers and forces, no conversion/IO in timing; genuine-event input restored and every full output checked before timing. Pure movement and static phase-offset caches warmed by validation. No combat PASS.',
            'corpus_sha256':report['corpus_sha256'],
            'source_manifest':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (ROOT/'src/kiomet_ai/v2/sim').glob('*.py')},
            'profile':output.getvalue()}
    (ROOT/'docs/V2_M2A_PERFORMANCE.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__': main()
