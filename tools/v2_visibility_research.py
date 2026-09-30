"""Bounded real sensor loss/recovery research; no hidden actor payload reads."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kiomet_ai.v2.observe.extractor import ObservationSession,connect_dedicated,CLIENT_SHA256
from playwright.async_api import async_playwright,Error as PlaywrightError


def import_history(path):
    history={}
    if path is None:
        return history
    path=(ROOT/path).resolve()
    if (ROOT/'runtime/research/v2').resolve() not in path.parents:
        raise ValueError('history must be an existing project research snapshot stream')
    with path.open(encoding='utf8') as stream:
        for line in stream:
            state=json.loads(line)
            if state['client_sha256']!=CLIENT_SHA256:
                raise ValueError('history client version mismatch')
            for tower in state['towers']:
                if tower['visibility']['value'] is not True or tower['visibility']['knowledge']!='OBSERVED':
                    raise ValueError('history has no positive legal visibility')
                history[tower['id']]={'at_ms':state['received_at_ms'],
                    'document_id':state['document_id'],'match_epoch':state['match_id']['value'],
                    'source_tick':state['tick']['value'],'imported':True}
    return history


async def main(args):
    lease=ROOT/'runtime/research/v2/headless-host.json'
    if lease.exists():
        host=json.loads(lease.read_text())
        if host['deadline_monotonic_ms']-time.monotonic_ns()//1000000<(args.seconds+30)*1000:
            raise ValueError('owned browser deadline cannot cover visibility cohort + teardown margin')
    history=import_history(args.history)
    initial_ids=set(history)
    previous={i:True for i in history}
    visible_epochs={}
    lost_epochs={}
    events,errors=[],[]
    checks=set()
    leaks=[]
    accepted=coherent=joins=0
    started=time.monotonic()
    async with async_playwright() as pw:
        browser=await connect_dedicated(pw,ROOT)
        page=next(p for p in browser.contexts[0].pages if p.url=='https://kiomet.com/')
        observer=ObservationSession(page)
        try:
            while time.monotonic()-started<args.seconds:
                try:
                    meta=await observer.metadata()
                    if args.join and joins==0 and meta.get('derived_lifecycle') in ('MENU','RESULT'):
                        observer.extractor.lifecycle.begin_join()
                        await page.locator('#play_button').click()
                        joins+=1
                        events.append({'event':'official_join','prior_lifecycle':meta['derived_lifecycle']})
                        await asyncio.sleep(.3)
                        continue
                    state,raw=await observer.sample()
                    accepted+=1
                    epoch=state.match_id.value
                    current={t.id for t in state.towers}
                    for tower in state.towers:
                        history[tower.id]={'at_ms':state.received_at_ms,'document_id':state.document_id,
                            'match_epoch':epoch,'source_tick':state.tick.value,'imported':False}
                    if len(history)>4096:
                        raise ValueError('known-visibility history exceeds bounded 4096-ID research limit')
                    sensor=await observer.extractor.visibility(sorted(history))
                    if any(sensor[k]!=raw[k] for k in ('document_time_origin','player_id','tick','root_candidate')):
                        continue
                    coherent+=1
                    now=time.monotonic_ns()//1000000
                    for truth in sensor['watched_visibility']:
                        ident,visible=truth['id'],truth['visible']
                        prior=previous.get(ident)
                        if visible is False:
                            checks.add((epoch,ident,raw['tick']))
                            if ident in current:
                                leaks.append({'id':ident,'tick':raw['tick'],'epoch':epoch})
                        if prior is True and visible is False:
                            lost_epochs[ident]=(epoch,visible_epochs.get(ident)==epoch)
                            known=history[ident]
                            events.append({'event':'sensor_loss','id':ident,'tick':raw['tick'],
                                'epoch':epoch,'prior_observation_epoch':known['match_epoch'],
                                'historical_observed_at_ms':known['at_ms'],
                                'historical_observation_age_ms':max(0,now-known['at_ms']),
                                'historical_knowledge':'DERIVED','current_actor_observed':ident in current,
                                'historical_status':'STALE',
                                'scope':'imported_history' if known['imported'] else 'same_observer'})
                        elif prior is False and visible is True:
                            events.append({'event':'sensor_recovery','id':ident,'tick':raw['tick'],
                                'epoch':epoch,'loss_epoch':lost_epochs.get(ident,(None,False))[0],
                                'same_epoch_cycle':lost_epochs.get(ident)==(epoch,True),
                                'current_actor_observed':ident in current,
                                'fresh_actor_observed_at_ms':state.received_at_ms if ident in current else None})
                        previous[ident]=visible
                        if visible and ident in current:
                            visible_epochs[ident]=epoch
                except (ValueError,RuntimeError) as error:
                    errors.append(str(error)[:180])
                    if '4096-ID' in str(error):
                        break
                except PlaywrightError as error:
                    errors.append(str(error)[:180])
                    break  # Preserve partial evidence if the owned browser closes.
                await asyncio.sleep(.2)
        finally:
            await observer.close()
    report={'status':'PARTIAL','seconds':time.monotonic()-started,'accepted_snapshots':accepted,
        'coherent_sensor_brackets':coherent,'known_ids':len(history),'imported_history_ids':len(initial_ids),
        'unique_hidden_absence_checks':len(checks),'leaks':leaks,'events':events,
        'sensor_losses':sum(e['event']=='sensor_loss' for e in events),
        'sensor_recoveries':sum(e['event']=='sensor_recovery' for e in events),
        'same_epoch_fresh_recoveries':sum(e['event']=='sensor_recovery' and e['same_epoch_cycle']
            and e['current_actor_observed'] for e in events),
        'errors':errors,'official_joins':joins,'tactical_commands':0,
        'limits':'own sensor references for previously observed IDs only; imported history is not same-match continuity proof'}
    path=ROOT/'runtime/research/v2'/f'visibility-research-{uuid4().hex[:12]}.json'
    path.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({'file':str(path),**{k:v for k,v in report.items() if k not in ('events','errors')},
        'error_count':len(errors),'errors':errors[:5]}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=600)
    parser.add_argument('--join',action='store_true',help='One normal official Play/Play Again when unavailable')
    parser.add_argument('--history',type=Path,default=None)
    args=parser.parse_args()
    if not 1<=args.seconds<=600:
        parser.error('seconds must be 1..600')
    asyncio.run(main(args))
