"""Reprocess already legally captured upgrade transitions, not a live gate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256
from kiomet_ai.v2.observe.upgrades import UpgradeTracker
from kiomet_ai.v2.state import Fact,Knowledge,Tower


def main(paths):
    cohorts=[]
    for supplied in paths:
        path=(ROOT/supplied).resolve()
        if (ROOT/'runtime/research/v2').resolve() not in path.parents:
            raise ValueError('only project observation history is accepted')
        tracker=UpgradeTracker()
        digest=hashlib.sha256()
        starts={}
        accepted=tracked=unknown_delays=0
        with path.open('rb') as stream:
            for line in stream:
                digest.update(line)
                state=json.loads(line)
                if state['client_sha256']!=CLIENT_SHA256 or state['source_mode']['value']!='NETWORK':
                    raise ValueError('historical client version/source mode mismatch')
                towers=[]
                for row in state['towers']:
                    if row['visibility']['knowledge']!='OBSERVED' or row['visibility']['value'] is not True:
                        raise ValueError('history entity was not positively currently observed')
                    def fact(name):
                        f=row[name]
                        return Fact(f['value'],Knowledge(f['knowledge']),f['source'],f['observed_at_ms'])
                    towers.append(Tower(row['id'],fact('visibility'),owner=fact('owner'),
                        tower_type=fact('tower_type'),delay_ticks=fact('delay_ticks')))
                result=tracker.update(towers,state['match_id']['value'],state['tick']['value'],state['sampled_at_ms'])
                accepted+=1
                for tower in result:
                    if tower.upgrade.value:
                        details=dict(tower.upgrade.value)
                        key=(state['match_id']['value'],tower.id,details['transition_tick'])
                        starts.setdefault(key,{'id':tower.id,'match_epoch':key[0],**details})
                        tracked+=1
                    elif tower.delay_ticks.value:
                        unknown_delays+=1
        cohorts.append({'snapshot_file':path.name,'snapshot_sha256':digest.hexdigest(),
            'snapshots':accepted,'verified_transitions':list(starts.values()),
            'tracked_delay_facts':tracked,'remaining_unknown_delay_facts':unknown_delays})
    report={'status':'PARTIAL','cohorts':cohorts,'live_gate_evidence':False,
        'limits':'offline reprocessing of original legal live facts; no new independent UI comparisons'}
    out=ROOT/'runtime/research/v2'/f'upgrade-history-{uuid4().hex[:12]}.json'
    out.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'file':str(out),'cohorts':cohorts}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshots',nargs='+',type=Path)
    main(parser.parse_args().snapshots)
