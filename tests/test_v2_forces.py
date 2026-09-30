import pytest
from kiomet_ai.v2.state import Fact,Knowledge,Tower
from kiomet_ai.v2.observe.forces import ForceTracker,motion
from kiomet_ai.v2.observe.extractor import decode_units


def fact(value):
    return Fact(value,Knowledge.OBSERVED,'test-only',100)


def towers():
    return [Tower(1,fact(True),position=fact((0,0))),Tower(2,fact(True),position=fact((5,0)))]


def row(progress=0):
    return dict(visible=True,visibility_source='test-only',owner=7,relation='SELF',
                source=1,destination=2,units7=[0,0,0,0,0,3,0],progress=progress,accelerated=0)


def test_single_layout_matches_pinned_getter_and_does_not_read_union_padding():
    units=decode_units([1,2,6,255,254,253,9])
    assert dict(units.counts)=={0:9,1:0,2:0,3:0,4:0,5:0,6:2,7:0,8:0,9:0}
    for invalid in ([1,0,6,0,0,0,0],[1,2,4,0,0,0,0]):
        with pytest.raises(ValueError,match='Single'):
            decode_units(invalid)


def test_force_eta_is_nominal_current_leg_and_unknown_for_hidden_geometry():
    units=decode_units(row()['units7'])
    assert motion(units,(0,0),(5,0),False,0)==(2,90,11250)
    assert motion(units,(0,0),(5,0),True,0)==(2,72,9000)
    assert motion(units,None,(5,0),True,0)==(2,None,None)


def test_unique_continuation_is_derived_not_pointer_or_collection_index():
    tracker=ForceTracker()
    a=tracker.update([row(0)],towers(),'m1',55,100,decode_units)[0]
    b=tracker.update([row(2)],towers(),'m1',56,300,decode_units)[0]
    assert a.id.knowledge==Knowledge.DERIVED and a.id.value==b.id.value
    assert b.confidence.value=='UNIQUE_CONTINUATION'
    assert b.first_seen_ms.value==100 and b.launch_ms.knowledge==Knowledge.UNKNOWN
    assert b.eta_ms.knowledge==Knowledge.DERIVED
    c=tracker.update([row(4)],towers(),'m2',57,500,decode_units)[0]
    assert c.id.value!=a.id.value


def test_ambiguous_forces_and_visibility_loss_never_fabricate_continuity():
    tracker=ForceTracker()
    a=tracker.update([row(0)],towers(),'m1',55,100,decode_units)[0]
    ambiguous=tracker.update([row(2),row(2)],towers(),'m1',56,300,decode_units)
    assert all(f.id.value is None and f.first_seen_ms.value is None for f in ambiguous)
    tracker.update([],towers(),'m1',57,500,decode_units)
    new=tracker.update([row(6)],towers(),'m1',58,700,decode_units)[0]
    assert new.id.value!=a.id.value
    hidden=row(8);hidden['source']=99
    with pytest.raises(ValueError,match='hidden'):
        tracker.update([hidden],towers(),'m1',59,900,decode_units)
