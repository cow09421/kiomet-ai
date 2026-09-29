import time

from kiomet_ai.live_controller import LiveController


def entry(path, *, progress=0, owner_id=5, ref=None):
    return {"ref": 100 + progress if ref is None else ref,
            "path": list(path), "owner_id": owner_id,
            "units": {"Shield": 0, "Fighter": 0, "Chopper": 0,
                      "Bomber": 0, "Tank": 0, "Soldier": 4,
                      "Shell": 0, "Emp": 0, "Nuke": 0, "Ruler": 0},
            "speed_flag": 0, "progress": progress, "endurance": 0}


def snapshot(entries, *, captured_at=None):
    if captured_at is None:
        captured_at = time.time()
    return {"match_id": "m1", "captured_at": captured_at,
            "collections": {
        "outbound": {"length": len(entries), "entries": entries},
        "inbound": {"length": 0, "entries": []},
    }}


def correlate(after, expected_path=(3, 7), before=None):
    controller = LiveController.__new__(LiveController)
    now = time.time()
    before = before or snapshot([], captured_at=now - 10.0)
    return controller.correlate_force(
        before, after, expected_path,
        dispatched_at=before["captured_at"] + 1.0)


def test_direct_reverse_route_is_verified():
    assert correlate(snapshot([entry((7, 3))])) == "FORCE_MATCH_VERIFIED"


def test_single_multi_hop_route_with_matching_endpoints_is_derived():
    assert correlate(snapshot([entry((7, 5, 3))])) == "FORCE_MATCH_DERIVED"


def test_wrong_direction_new_force_cannot_verify_action():
    status = correlate(snapshot([entry((3, 7))]))

    assert status == "FORCE_MATCH_NOT_FOUND"
    assert status not in ("FORCE_MATCH_VERIFIED", "FORCE_MATCH_DERIVED")


def test_unrelated_new_force_cannot_be_derived_as_action():
    status = correlate(snapshot([entry((9, 8))]))

    assert status == "FORCE_MATCH_NOT_FOUND"
    assert status not in ("FORCE_MATCH_VERIFIED", "FORCE_MATCH_DERIVED")


def test_missing_expected_route_fails_closed():
    status = correlate(snapshot([entry((7, 3))]), expected_path=None)

    assert status == "FORCE_MATCH_UNVERIFIABLE"
    assert status not in ("FORCE_MATCH_VERIFIED", "FORCE_MATCH_DERIVED")


def test_route_must_end_at_the_selected_target_and_source():
    status = correlate(snapshot([entry((9, 7, 3))]))

    assert status == "FORCE_MATCH_NOT_FOUND"
    assert status not in ("FORCE_MATCH_VERIFIED", "FORCE_MATCH_DERIVED")


def test_multiple_new_routes_to_same_pair_are_ambiguous():
    status = correlate(snapshot([
        entry((7, 3)),
        entry((7, 5, 3), progress=1),
    ]))

    assert status == "FORCE_MATCH_AMBIGUOUS"
    assert status not in ("FORCE_MATCH_VERIFIED", "FORCE_MATCH_DERIVED")


def test_snapshot_error_does_not_become_force_not_found():
    after = snapshot([])
    after["error"] = "read failed"

    assert correlate(after) == "FORCE_MATCH_UNKNOWN"


def test_force_from_before_ui_dispatch_cannot_prove_dispatch_effect():
    controller = LiveController.__new__(LiveController)
    now = time.time()
    before = snapshot([], captured_at=now - 10.0)
    route_seen_before_dispatch = snapshot(
        [entry((7, 3))], captured_at=now - 5.0)

    result = controller.correlate_force(
        before, [route_seen_before_dispatch], (3, 7),
        dispatched_at=now - 4.0)

    assert result == "FORCE_MATCH_UNKNOWN"


def test_existing_force_progress_change_is_not_a_new_dispatch():
    controller = LiveController.__new__(LiveController)
    now = time.time()
    before = snapshot(
        [entry((7, 3), progress=10, ref=44)], captured_at=now - 10.0)
    after = snapshot(
        [entry((7, 3), progress=11, ref=44)], captured_at=now - 1.0)

    result = controller.correlate_force(
        before, after, (3, 7), dispatched_at=now - 2.0)

    assert result == "FORCE_MATCH_NOT_FOUND"


def test_force_correlation_rejects_missing_stale_and_future_snapshot_times():
    controller = LiveController.__new__(LiveController)
    now = time.time()
    before = snapshot([], captured_at=now - 10.0)
    dispatch = now - 2.0

    bad_times = (None, now - 40.0, now + 5.0, True)
    for captured_at in bad_times:
        after = snapshot([entry((7, 3))], captured_at=now - 1.0)
        if captured_at is None:
            after.pop("captured_at")
        else:
            after["captured_at"] = captured_at
        assert controller.correlate_force(
            before, after, (3, 7), dispatched_at=dispatch
        ) == "FORCE_MATCH_UNKNOWN"
