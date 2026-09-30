from kiomet_ai.v2.state import Lifecycle
from kiomet_ai.v2.observe.lifecycle import MatchLifecycle


def metadata(active=False,play="Play",player=7,online=True,transport=True,origin=100):
    return dict(active=active,play_text=play,player_id=player,online=online,
                transport_connected=transport,document_time_origin=origin,tick=55)


def test_official_join_result_menu_and_new_match_have_separate_epochs():
    tracker = MatchLifecycle("doc")
    assert tracker.observe(metadata(),100)[0] == Lifecycle.MENU
    tracker.begin_join()
    assert tracker.observe(metadata(),200)[0] == Lifecycle.JOINING
    life, a = tracker.observe(metadata(True,None),300)
    assert life == Lifecycle.IN_MATCH and a
    assert tracker.observe(metadata(True,None),500)[1] == a
    assert tracker.observe(metadata(False,"Play Again"),600) == (Lifecycle.RESULT,None)
    assert tracker.observe(metadata(),700) == (Lifecycle.MENU,None)
    tracker.begin_join()
    b = tracker.observe(metadata(True,None),900)[1]
    assert b and b != a


def test_player_document_disconnect_and_uncertain_gap_do_not_reuse_old_state():
    tracker = MatchLifecycle("doc")
    a = tracker.observe(metadata(True,None),100)[1]
    assert tracker.observe(metadata(True,None,online=False),200) == (Lifecycle.DISCONNECTED,None)
    assert tracker.observe(metadata(True,None),300)[1] == a
    assert tracker.observe(metadata(True,None,transport=False),400) == (Lifecycle.DISCONNECTED,None)
    b = tracker.observe(metadata(True,None,player=8),500)[1]
    assert b and b != a
    c = tracker.observe(metadata(True,None,player=8,origin=200),600)[1]
    assert c and c != b
    assert tracker.observe(metadata(True,None,player=8,origin=200),2000)[1] is None
    assert tracker.observe(metadata(True,None,player=8,origin=200),2100)[1] is None
    tracker.begin_join()
    assert tracker.observe(metadata(True,None,player=8,origin=200),2200)[1]
    assert tracker.observe(metadata(True,None,transport=False),2300)[0] == Lifecycle.DISCONNECTED


def test_conflicting_or_unrecognized_ui_stays_unknown():
    tracker = MatchLifecycle("doc")
    assert tracker.observe(metadata(True,"Play Again"),100)[0] == Lifecycle.UNKNOWN
    assert tracker.observe(metadata(False,None),200)[0] == Lifecycle.UNKNOWN


def test_offline_harness_cannot_resume_a_network_match_epoch():
    tracker=MatchLifecycle('doc')
    live=metadata(True,None);live['transport_mode']='NETWORK'
    a=tracker.observe(live,100)[1]
    offline=metadata(True,None,transport=False);offline['transport_mode']='OFFLINE'
    assert tracker.observe(offline,200)==(Lifecycle.DISCONNECTED,None)
    assert tracker.observe(live,300)[1] is None
    tracker.observe(metadata(),400)
    tracker.begin_join()
    b=tracker.observe(live,500)[1]
    assert b and b!=a
