import time

import pytest

from kiomet_ai.v2.observe.extractor import ClientExtractor
from test_v2_observation import raw


def attached():
    extractor = ClientExtractor(None)
    extractor.memories_id = 'test-memory'
    extractor.owner_states_id = 'test-owner'
    extractor.time_origin = 1234567890000
    return extractor


def captured(tick):
    return dict(raw(), sampled_at_ms=9876543210000, document_time_origin=1234567890000,
                root_candidate=1000, tick=tick, transport_mode='NETWORK',
                online=True, transport_connected=True, active=True, play_text=None,
                coverage='PLAYER_VISIBLE_COMPLETE', positive_refs=1, visible_pending=False,
                expanded_visibility=False, forces=[])


def test_entry_payload_uses_host_bracket_and_existing_match_sequence_clock():
    extractor = attached()
    began = time.monotonic_ns() // 1000000 - 100
    first, _ = extractor.adopt_captured_world(captured(10), began_monotonic_ms=began,
                                             received_monotonic_ms=began)
    second, _ = extractor.adopt_captured_world(captured(11), began_monotonic_ms=began + 1,
                                              received_monotonic_ms=began + 2)
    assert first.match_id.value == second.match_id.value
    assert (first.sequence, second.sequence) == (1, 2)
    assert second.sampled_at_ms == began + 1
    assert second.towers[0].units.observed_at_ms == began + 1
    assert second.client_sampled_at_ms.value == 9876543210000
    assert second.source_update_window_ms.value == (began, began + 2)


def test_retrospective_buffer_cannot_reset_the_consumed_world_or_clock():
    extractor = attached()
    began = time.monotonic_ns() // 1000000 - 100
    extractor.adopt_captured_world(captured(10), began_monotonic_ms=began,
                                  received_monotonic_ms=began + 2)
    for lower, upper in ((began - 1, began + 3), (began + 1, began + 3)):
        with pytest.raises(ValueError, match='retrospective|overlaps'):
            extractor.adopt_captured_world(captured(11), began_monotonic_ms=lower,
                                           received_monotonic_ms=upper)
    assert extractor.sequence == 1
    assert extractor.source_clock.previous_tick == 10


def test_wrong_document_and_invalid_host_brackets_fail_closed():
    for lower, upper in ((True, 5), (float('nan'), 5), (5, False), (5, 4), (-1, 5)):
        extractor = attached()
        with pytest.raises(ValueError, match='host observation bracket'):
            extractor.adopt_captured_world(captured(10), began_monotonic_ms=lower,
                                           received_monotonic_ms=upper)
        assert extractor.sequence == 0
    extractor = attached()
    with pytest.raises(ValueError, match='document changed'):
        extractor.adopt_captured_world(dict(captured(10), document_time_origin=0),
                                       began_monotonic_ms=1, received_monotonic_ms=2)
    assert extractor.sequence == 0


def test_document_mismatch_invalidates_an_established_stream_without_rollback():
    extractor = attached()
    began = time.monotonic_ns() // 1000000 - 100
    extractor.adopt_captured_world(captured(10), began_monotonic_ms=began,
                                  received_monotonic_ms=began)
    with pytest.raises(ValueError, match='document changed'):
        extractor.adopt_captured_world(dict(captured(11), document_time_origin=0),
                                       began_monotonic_ms=began + 1,
                                       received_monotonic_ms=began + 2)
    assert extractor.source_clock.previous_tick is None
    assert extractor.force_tracker.scope is None
    assert extractor.lifecycle.identity is None
    with pytest.raises(ValueError, match='document changed'):
        extractor.adopt_captured_world(captured(11), began_monotonic_ms=began + 3,
                                       received_monotonic_ms=began + 4)


def test_submillisecond_retrospective_begin_is_rejected_without_rounding():
    extractor = attached()
    began = time.monotonic_ns() // 1000000 - 100
    extractor.adopt_captured_world(captured(10), began_monotonic_ms=began,
                                  received_monotonic_ms=began + 0.9)
    with pytest.raises(ValueError, match='overlaps'):
        extractor.adopt_captured_world(captured(11), began_monotonic_ms=began + 0.1,
                                       received_monotonic_ms=began + 1)
    assert extractor.sequence == 1
    assert extractor.source_clock.previous_tick == 10


def test_unobserved_lifecycle_gap_cannot_revive_the_previous_match_by_rollback():
    extractor = attached()
    began = time.monotonic_ns() // 1000000 - 2000
    extractor.adopt_captured_world(captured(10), began_monotonic_ms=began,
                                  received_monotonic_ms=began)
    with pytest.raises(ValueError, match='lifecycle continuity'):
        extractor.adopt_captured_world(captured(11), began_monotonic_ms=began + 1002,
                                       received_monotonic_ms=began + 1003)
    assert extractor.lifecycle.invalidated is True
    assert extractor.lifecycle.identity is None
    assert extractor.force_tracker.scope is None
    assert extractor.source_clock.previous_tick is None
    assert extractor.sequence == 1
    with pytest.raises(ValueError, match='lifecycle continuity'):
        extractor.adopt_captured_world(captured(12), began_monotonic_ms=began + 1004,
                                       received_monotonic_ms=began + 1005)


def test_failed_normalization_restores_match_clock_trackers_and_sequence():
    extractor = attached()
    began = time.monotonic_ns() // 1000000 - 100
    first, _ = extractor.adopt_captured_world(captured(10), began_monotonic_ms=began,
                                             received_monotonic_ms=began)
    with pytest.raises((KeyError, ValueError)):
        extractor.adopt_captured_world(dict(captured(11), forces=[{}]),
                                       began_monotonic_ms=began + 1,
                                       received_monotonic_ms=began + 2)
    assert extractor.sequence == 1
    assert extractor.source_clock.previous_tick == 10
    assert extractor.last_read_finished_ms == began
    second, _ = extractor.adopt_captured_world(captured(11), began_monotonic_ms=began + 3,
                                              received_monotonic_ms=began + 4)
    assert second.match_id.value == first.match_id.value
    assert second.sequence == 2


def test_identity_switch_partial_world_and_in_flight_read_cannot_be_adopted():
    extractor = attached()
    began = time.monotonic_ns() // 1000000 - 100
    extractor.adopt_captured_world(captured(10), began_monotonic_ms=began,
                                  received_monotonic_ms=began)
    for change in ({'player_id': 8}, {'root_candidate': 1001}, {'coverage': 'PARTIAL'},
                   {'tick': True}, {'tick': 9}, {'transport_mode': 'OFFLINE'}):
        with pytest.raises(ValueError):
            extractor.adopt_captured_world(dict(captured(11), **change),
                                           began_monotonic_ms=began + 1,
                                           received_monotonic_ms=began + 2)
        assert extractor.sequence == 1
    extractor._read_in_flight = True
    with pytest.raises(RuntimeError, match='overlap'):
        extractor.adopt_captured_world(captured(11), began_monotonic_ms=began + 1,
                                       received_monotonic_ms=began + 2)
