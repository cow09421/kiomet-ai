"""UI input delivery is distinct from observing the resulting force."""
from kiomet_ai.live_controller import LiveController


def test_dispatch_requires_verified_source_and_target_force_snapshots():
    assert LiveController._dispatch_observation_status(
        "FORCE_MATCH_VERIFIED", "FORCE_MATCH_VERIFIED") == "FORCE_OBSERVED"


def test_two_complete_not_found_snapshots_are_explicitly_unobserved():
    assert LiveController._dispatch_observation_status(
        "FORCE_MATCH_NOT_FOUND", "FORCE_MATCH_NOT_FOUND") == (
            "DISPATCH_NOT_OBSERVED")


def test_partial_or_derived_force_evidence_stays_unknown():
    assert LiveController._dispatch_observation_status(
        "FORCE_MATCH_VERIFIED", "FORCE_MATCH_NOT_FOUND") == "UNKNOWN"
    assert LiveController._dispatch_observation_status(
        "FORCE_MATCH_DERIVED", "FORCE_MATCH_DERIVED") == "UNKNOWN"
    assert LiveController._dispatch_observation_status(
        "FORCE_MATCH_UNKNOWN", "FORCE_MATCH_NOT_FOUND") == "UNKNOWN"


def test_observation_metrics_do_not_promote_ui_send_to_verified_move():
    live = LiveController.__new__(LiveController)
    live.journal = {"sent_actions": 1, "verified_moves": 0}

    status = live._record_dispatch_observation(
        "m1:1->2:10", "m1", "FORCE_MATCH_NOT_FOUND",
        "FORCE_MATCH_NOT_FOUND")

    assert status == "DISPATCH_NOT_OBSERVED"
    assert live.journal["sent_actions"] == 1
    assert live.journal["verified_moves"] == 0
    assert live.journal["unobserved_dispatches"] == 1
    assert live.journal["last_dispatch_observation"]["ui_event_sent"] is True
