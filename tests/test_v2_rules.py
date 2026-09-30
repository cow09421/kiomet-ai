from kiomet_ai.v2.observe.extractor import decode_units,normalize
from kiomet_ai.v2.observe.rules import capacity,production,mobile_inventory
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
    assert state.towers[0].upgrade.knowledge==Knowledge.UNKNOWN
