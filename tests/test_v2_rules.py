from kiomet_ai.v2.observe.extractor import decode_units,normalize
from kiomet_ai.v2.observe.rules import capacity,production,mobile_inventory,player_mobile_inventory,upgrade_candidates
import pytest
from kiomet_ai.v2.state import Knowledge


def test_visible_boost_changes_capacity_without_inventing_ruler_occupancy():
    # Live self Barracks panel: 20/20 shields, 12/12 soldiers; Many, no ruler.
    units=decode_units([0,0,0,0,0,12,20])
    assert dict(units.counts)[9]==0
    assert dict(capacity(3,1).counts)[0]==20
    assert dict(capacity(3,0).counts)[0]==10
    assert production(3,units,7,0,1)==((0,10),(5,12))


def test_ruler_delay_and_neutral_production_are_not_conflated():
    ruler=decode_units([1,1,9,222,111,99,15])
    assert dict(ruler.counts)[9]==1  # Union padding is not Many troops.
    assert production(22,ruler,7,0,1)==((0,10),)
    assert production(22,ruler,7,240,1)==()  # Could be EMP, not necessarily upgrade.
    assert production(22,ruler,0,0,0)==()
    assert dict(mobile_inventory(22,ruler).counts)[0]==0
    assert dict(mobile_inventory(15,ruler).counts)[0]==15


def test_absent_king_and_absent_rule_metadata_remain_unknown():
    raw={'sampled_at_ms':500,'player_id':7,'towers':[{'id':3,'visible':True,
        'visibility_source':'test visibility','owner':7,'relation':'SELF','type':3,
        'units7':[0,0,0,0,0,12,20],'position':[2,3]}]}
    state=normalize(raw,'s','d',1,101,100)
    assert state.king.knowledge==Knowledge.UNKNOWN
    assert state.towers[0].capacity.knowledge==Knowledge.UNKNOWN
    raw['towers'][0].update(morale=1,delay_ticks=0)
    state=normalize(raw,'s','d',2,102,101)
    assert state.towers[0].capacity.knowledge==Knowledge.DERIVED
    assert state.towers[0].effects.value==(('MORALE_BOOST',True),)
    assert state.towers[0].upgrade.value==(('in_progress',False),)
    raw['towers'][0]['delay_ticks']=60
    delayed=normalize(raw,'s','d',3,103,102)
    assert delayed.towers[0].upgrade.knowledge==Knowledge.UNKNOWN
    assert delayed.towers[0].delay_ticks.value==60


def test_observed_own_prerequisites_do_not_certify_unlock_or_upgrade_cause():
    counts=[0]*27;counts[9]=counts[14]=1
    candidates=upgrade_candidates(3,counts,0)
    assert candidates==((1,((9,1,1),(14,1,1)),True),)
    assert upgrade_candidates(3,counts,240)==()
    assert upgrade_candidates(3,None,0) is None
    raw={'sampled_at_ms':500,'player_id':7,'own_tower_counts':counts,
         'towers':[{'id':3,'visible':True,'visibility_source':'test visibility',
         'owner':7,'relation':'SELF','type':3,'units7':[0,0,0,0,0,12,20],
         'position':[2,3],'morale':1,'delay_ticks':0}]}
    state=normalize(raw,'s','d',1,101,100)
    assert state.upgrade_resources.knowledge==Knowledge.OBSERVED
    assert dict(state.upgrade_resources.value)[9]==1
    assert dict(state.upgrade_resources.value)[10]==0  # A real observed zero.
    assert state.towers[0].upgrade_candidates.value==candidates
    assert state.towers[0].upgrade.value==(('in_progress',False),)
    raw['towers'][0].update(owner=8,relation='ENEMY')
    assert normalize(raw,'s','d',2,102,101).towers[0].upgrade_candidates.knowledge==Knowledge.UNKNOWN
    del raw['own_tower_counts']
    assert normalize(raw,'s','d',3,103,102).upgrade_resources.knowledge==Knowledge.UNKNOWN
    for malformed in ([0]*26,[0]*26+[-1],[0]*26+[65536]):
        raw['own_tower_counts']=malformed
        with pytest.raises(ValueError,match='prerequisite tower counts'):
            normalize(raw,'s','d',4,104,103)


def test_known_source_ownership_zero_differs_from_missing_player_identity():
    units=decode_units([0,0,0,0,0,12,20])
    assert dict(player_mobile_inventory(3,units,7,7).counts)[5]==12
    for owner in (0,8):
        assert all(n==0 for _,n in player_mobile_inventory(3,units,owner,7).counts)
    assert player_mobile_inventory(3,units,7,None) is None
    assert player_mobile_inventory(3,units,7,0) is None


def test_owned_unlock_zero_and_empty_are_known_but_missing_is_unknown():
    raw={'sampled_at_ms':500,'player_id':7,'towers':[]}
    missing=normalize(raw,'s','d',1,101,100)
    assert missing.upgrade_keys.knowledge==Knowledge.UNKNOWN
    assert missing.unlocked_tower_types.knowledge==Knowledge.UNKNOWN
    raw['own_unlocks']={'keys':0,'unlocked_types':[]}
    known=normalize(raw,'s','d',2,102,101)
    assert known.upgrade_keys.value==0
    assert known.upgrade_keys.knowledge==Knowledge.OBSERVED
    assert known.unlocked_tower_types.value==()
    assert known.unlocked_tower_types.knowledge==Knowledge.OBSERVED
    for bad in ({'keys':-1,'unlocked_types':[]},{'keys':3,'unlocked_types':[1,1]},
                {'keys':3,'unlocked_types':[27]}):
        raw['own_unlocks']=bad
        with pytest.raises(ValueError,match='persistent unlock'):
            normalize(raw,'s','d',3,103,102)
