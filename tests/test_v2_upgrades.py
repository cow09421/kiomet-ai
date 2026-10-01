from kiomet_ai.v2.observe.extractor import normalize
from kiomet_ai.v2.observe.upgrades import UpgradeTracker
from kiomet_ai.v2.state import Knowledge


def snapshot(tracker, tick, typ, delay, at, identity='m', owner=19, visible=True):
    raw={'sampled_at_ms':at,'tick':tick,'player_id':19,'towers':[]}
    if visible:
        raw['towers']=[{'id':19333381,'visible':True,'visibility_source':'test current sensor',
            'owner':owner,'relation':'SELF' if owner==19 else 'ENEMY','type':typ,
            'delay_ticks':delay,'morale':0,'units7':[0,0,0,0,0,0,10],'position':[1,2]}]
    return normalize(raw,'s','d',1,at+1,at,match_identity=identity,upgrade_tracker=tracker)


def test_real_reactor_transition_counts_down_but_does_not_invent_first_seen_cause():
    # Real 12f8a3edfab7: Generator(10)->Reactor(19), tick 5257, delay 160.
    tracker=UpgradeTracker()
    assert snapshot(tracker,5256,10,0,100).towers[0].upgrade.value==(('in_progress',False),)
    upgrade=snapshot(tracker,5257,19,160,350).towers[0].upgrade
    assert upgrade.knowledge==Knowledge.DERIVED
    assert dict(upgrade.value)['from_type']==10
    assert dict(upgrade.value)['remaining_delay_ticks']==160
    assert dict(snapshot(tracker,5257,19,160,450).towers[0].upgrade.value)['in_progress']
    assert dict(snapshot(tracker,5258,19,159,600).towers[0].upgrade.value)['remaining_delay_ticks']==159
    first_seen=snapshot(UpgradeTracker(),5258,19,159,600).towers[0]
    assert first_seen.upgrade.knowledge==Knowledge.UNKNOWN


def test_emp_visibility_identity_and_missed_update_invalidate_upgrade_cause():
    for case in ('emp','hidden','identity','owner','missed','gap'):
        tracker=UpgradeTracker()
        snapshot(tracker,5256,10,0,100)
        snapshot(tracker,5257,19,160,350)
        if case=='hidden':snapshot(tracker,5258,19,159,600,visible=False)
        state=snapshot(tracker,5259 if case in ('missed','hidden') else 5258,19,
            240 if case=='emp' else 158 if case in ('missed','hidden') else 159,
            1500 if case=='gap' else 700,
            identity='new' if case=='identity' else 'm',owner=20 if case=='owner' else 19)
        assert state.towers[0].upgrade.knowledge==Knowledge.UNKNOWN,case
