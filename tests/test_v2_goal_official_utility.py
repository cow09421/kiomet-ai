"""Fresh Goal015 finite utility controls; no policy or evaluator invocation."""
from __future__ import annotations
import copy
import json
from collections import Counter
from pathlib import Path
import pytest
from tools.v2_goal_official_utility import extract_score, nearest_rank_scale, score_delta, utility

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'tests/fixtures/v2_goal015_utility_sanity.json').read_text(encoding='utf-8'))

@pytest.fixture(scope='module')
def scale():
    artifact = ROOT / 'runtime/research/v2/goal/goal015-baseline-dev.json'
    raw = json.loads(artifact.read_text(encoding='utf-8'))
    assert raw['baseline'] == 'B1'
    assert len(raw['rows']) == len(raw['scale_inputs']) == 60
    assert all(row['status'] == 'EVALUATED' for row in raw['rows'])
    assert raw['scale'] == nearest_rank_scale(raw['scale_inputs']) > 0
    return raw['scale']

def snapshot(case, rows, *, terminal=None, ticks=120):
    out = {
        'status':'EVALUATED', 'ticks_evaluated':ticks,
        'alive':{'1':True,'2':True}, 'pending_core_losses':[], 'terminal':None,
        'final_towers':[(r['id'],r['kind'],r['owner'],r['units']) for r in rows],
        'final_tower_delays':[(r['id'],r['delay']) for r in rows],
        'trace':[
            {'tick':(case['start_tick']+offset)&65535,
             'tower_owners':[(r['id'],r['owner']) for r in rows],
             'tower_delays':[(r['id'],r['delay']) for r in rows]}
            for offset in range(ticks)]}
    if terminal:
        out.update(copy.deepcopy(terminal))
    return out

@pytest.mark.parametrize('pair',DATA['dominance_pairs'],ids=lambda row:row['id'])
def test_authorized_dominance(pair,scale):
    case=pair['case']; good_case=copy.deepcopy(case)
    if pair['category']=='production':
        good_case['towers'][2]['kind']=3
    bad=snapshot(case,pair['bad']); good=snapshot(good_case,pair['good'])
    db=score_delta(case,bad);dg=score_delta(good_case,good)
    assert db.known and dg.known
    assert (db.value,dg.value)==(pair['expected_delta_bad'],pair['expected_delta_good'])
    ub=utility(case,bad,scale);ug=utility(good_case,good,scale)
    assert ub.known and ug.known and not ub.catastrophe and not ug.catastrophe
    if pair['category']=='score':
        assert ug.value>ub.value
    else:
        assert ug.value>=ub.value
        assert ug.value==ub.value==0

@pytest.mark.parametrize('hand',DATA['anti_proxy'],ids=lambda row:row['id'])
def test_anti_proxy_terminal_priority(hand,scale):
    case=hand['case'];bad=snapshot(case,hand['bad'],terminal=hand['bad_terminal']);good=snapshot(case,hand['good'])
    ub=utility(case,bad,scale);ug=utility(case,good,scale)
    assert ub.known and ub.value==-1 and ub.catastrophe is True
    assert ug.known and ug.value>ub.value and ug.catastrophe is False
    assert hand['bad'][2]['units'][5]>hand['good'][2]['units'][5]

def test_exact_fresh_control_counts():
    assert Counter(p['category'] for p in DATA['dominance_pairs'])=={'score':100,'force':50,'production':50}
    assert len(DATA['anti_proxy'])==20
    ids=[p['id'] for p in DATA['dominance_pairs']+DATA['anti_proxy']]
    assert len(ids)==len(set(ids))==220

@pytest.mark.parametrize('bad_scale',[0,-1,None,True,float('inf'),float('nan'),'1'])
def test_invalid_scale_keeps_unknown(bad_scale):
    pair=DATA['dominance_pairs'][0];case=pair['case']
    got=utility(case,snapshot(case,pair['good']),bad_scale)
    assert not got.known and got.value is None and got.catastrophe is None

@pytest.mark.parametrize('values',[[],[0]*60,[None],[True],[float('nan')],[float('inf')]])
def test_scale_never_fabricates_epsilon(values):
    with pytest.raises(ValueError):nearest_rank_scale(values)

def test_nearest_rank_recipe():
    assert nearest_rank_scale(list(range(1,61)))==54
    assert nearest_rank_scale([-v for v in range(1,61)])==54

@pytest.mark.parametrize('mode',['opponent_processed','opponent_pending'])
def test_opponent_terminal_only_when_self_safe(mode,scale):
    pair=DATA['dominance_pairs'][0];case=pair['case']
    terminal={'alive':{'1':True,'2':False},'pending_core_losses':[],'terminal':'CORE_LOSS:2'} if mode=='opponent_processed' else {'alive':{'1':True,'2':True},'pending_core_losses':[2],'terminal':'CORE_LOSS_PENDING_AT_HORIZON'}
    got=utility(case,snapshot(case,pair['bad'],terminal=terminal),scale)
    assert got.known and got.value==1 and got.catastrophe is False

@pytest.mark.parametrize('field,value',[
    ('alive',{'1':None,'2':False}),('alive',{'2':False}),('pending_core_losses',None),
    ('pending_core_losses',[2,2]),('terminal','WIN'),('terminal',None),
    ('status','UNSUPPORTED')])
def test_terminal_unknown_or_contradictory_is_not_success(field,value,scale):
    pair=DATA['dominance_pairs'][0];case=pair['case']
    out=snapshot(case,pair['bad'],terminal={'alive':{'1':True,'2':False},'pending_core_losses':[],'terminal':'CORE_LOSS:2'})
    out[field]=value;got=utility(case,out,scale)
    assert not got.known and got.value is None

@pytest.mark.parametrize('mutation',['missing_delay','missing_owner','hidden_row','unsupported_kind','duplicate_row','extra_delay','missing_row','unknown_delay','wrong_tick','wrong_horizon','open_world','partial_nonterminal'])
def test_score_lineage_fails_closed(mutation,scale):
    pair=copy.deepcopy(DATA['dominance_pairs'][0]);case=pair['case'];out=snapshot(case,pair['good'])
    if mutation=='missing_delay':del case['towers'][0]['delay']
    elif mutation=='missing_owner':del case['towers'][0]['owner']
    elif mutation=='hidden_row':case['towers'][0]['visible']=False
    elif mutation=='unsupported_kind':case['towers'][0]['kind']=6
    elif mutation=='duplicate_row':case['towers'].append(copy.deepcopy(case['towers'][0]))
    elif mutation=='extra_delay':out['final_tower_delays'].append((987654,0))
    elif mutation=='missing_row':out['final_towers'].pop()
    elif mutation=='unknown_delay':out['final_tower_delays'][0]=(out['final_tower_delays'][0][0],None)
    elif mutation=='wrong_tick':out['trace'][1]['tick']+=1
    elif mutation=='wrong_horizon':case['horizon_ticks']=119
    elif mutation=='open_world':case['closed_by_construction']=False
    else:out['ticks_evaluated']=4;out['trace']=out['trace'][:4]
    got=utility(case,out,scale)
    assert not got.known and got.value is None

def test_explicit_active_delay_and_weight():
    rows=[{'id':731,'kind':9,'owner':1,'delay':0},{'id':732,'kind':25,'owner':1,'delay':1},{'id':733,'kind':3,'owner':2,'delay':0},{'id':734,'kind':7,'owner':None,'delay':0}]
    assert extract_score(rows,None,1,[731,732,733,734]).value==2
    assert extract_score(rows,None,2,[731,732,733,734]).value==1
    assert not extract_score(rows,None,1).known

def test_endpoint_permutation_and_player_sign(scale):
    pair=copy.deepcopy(DATA['dominance_pairs'][3]);case=pair['case'];out=snapshot(case,pair['good'])
    value=utility(case,out,scale).value
    case['towers'].reverse();out['final_towers'].reverse();out['final_tower_delays'].reverse()
    for row in out['trace']:row['tower_owners'].reverse();row['tower_delays'].reverse()
    assert utility(case,out,scale).value==value
    case['player']=2
    assert utility(case,out,scale).value==-value

def test_clipping_boundaries(scale):
    pair=DATA['dominance_pairs'][0];case=copy.deepcopy(pair['case']);rows=copy.deepcopy(pair['good'])
    for i in range(300):
        row={'id':600000+i,'kind':3,'owner':None,'delay':0,'units':[0]*10,'visible':True}
        case['towers'].append(copy.deepcopy(row));row['owner']=1;rows.append(row)
    out=snapshot(case,rows)
    assert utility(case,out,scale).value==1
    case['player']=2
    assert utility(case,out,scale).value==-1

@pytest.mark.parametrize('lost_owner',[1,2])
def test_dead_official_score_unknown_with_exact_utility_override(lost_owner,scale):
    pair=DATA['dominance_pairs'][0];case=pair['case']
    out=snapshot(case,pair['bad'],terminal={'alive':{'1':lost_owner!=1,'2':lost_owner!=2},'pending_core_losses':[],'terminal':f'CORE_LOSS:{lost_owner}'},ticks=2)
    delta=score_delta(case,out)
    assert not delta.known and delta.value is None
    assert utility(case,out,scale).value==(-1 if lost_owner==1 else 1)

@pytest.mark.parametrize('ticks',[0,None,True,121])
def test_terminal_invalid_tick_count_unknown(ticks,scale):
    hand=DATA['anti_proxy'][0];case=hand['case'];out=snapshot(case,hand['bad'],terminal=hand['bad_terminal'])
    out['ticks_evaluated']=ticks
    assert not utility(case,out,scale).known

def test_pending_loss_label_requires_full_horizon(scale):
    hand=DATA['anti_proxy'][1];case=hand['case'];out=snapshot(case,hand['bad'],terminal=hand['bad_terminal'],ticks=2)
    assert not utility(case,out,scale).known
    assert not score_delta(case,out).known
