import json
import math

import pytest

from kiomet_ai.black_box import (
    DEFAULT_WINDOW_SECONDS,
    MAX_EVENT_BYTES,
    PROJECT_ROOT,
    SCHEMA_VERSION,
    BlackBoxRecorder,
)


class FakeClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


def snapshot(cycle, **overrides):
    value = {
        "game_lifecycle": "IN_MATCH",
        "match": {"id": "match-1", "state": "IN_MATCH"},
        "cycle": {"id": cycle},
        "world_freshness": {"status": "FRESH", "age_seconds": 0.2},
        "threats": [],
        "proposal": None,
        "action": None,
        "reservation": None,
        "verification": None,
        "renderer_health": {"status": "OK"},
    }
    value.update(overrides)
    return value


def recorder_for(clock, **kwargs):
    return BlackBoxRecorder(
        monotonic_clock=clock,
        wall_clock=lambda: 1_800_000_000 + clock(),
        **kwargs,
    )


def test_retains_only_the_last_120_seconds_and_does_not_write_until_freeze(
    tmp_path,
):
    clock = FakeClock(0)
    output = tmp_path / "black-box.json"
    recorder = recorder_for(clock, output_path=output)

    assert recorder.record(snapshot(1)) is True
    clock.value = DEFAULT_WINDOW_SECONDS
    assert recorder.record(snapshot(2)) is True
    clock.value = DEFAULT_WINDOW_SECONDS + 0.01
    assert recorder.record(snapshot(3)) is True

    assert [event["cycle"]["id"] for event in recorder.buffered_events()] == [2, 3]
    assert recorder.buffered_event_count == 2
    assert output.exists() is False
    assert list(tmp_path.iterdir()) == []


def test_max_event_count_bounds_memory_even_during_a_burst():
    clock = FakeClock()
    recorder = recorder_for(clock, max_events=3)
    for cycle in range(5):
        recorder.record(snapshot(cycle))

    assert recorder.buffered_event_count == 3
    assert [event["cycle"]["id"] for event in recorder.buffered_events()] == [2, 3, 4]


@pytest.mark.parametrize("trigger", ["crash", "combat_action"])
def test_trigger_freezes_and_atomically_overwrites_one_bounded_artifact(
    tmp_path, trigger,
):
    clock = FakeClock(3)
    output = tmp_path / "nested" / "black-box.json"
    recorder = recorder_for(clock, output_path=output)
    recorder.record(snapshot(7, action={"kind": "ATTACK_ENEMY"}))

    clock.value = 4
    assert recorder.record(snapshot(8), trigger=trigger) is True
    assert recorder.is_frozen is True
    frozen = json.loads(output.read_text(encoding="utf-8"))
    assert frozen == recorder.freeze(trigger)
    assert frozen["schema_version"] == SCHEMA_VERSION
    assert frozen["window_seconds"] == DEFAULT_WINDOW_SECONDS
    assert frozen["trigger"] == trigger
    assert [event["cycle"]["id"] for event in frozen["events"]] == [7, 8]
    assert frozen["events"][1]["renderer_health"] == {"status": "OK"}
    assert len(list(output.parent.iterdir())) == 1

    frozen["events"].clear()
    assert len(recorder.freeze(trigger)["events"]) == 2
    assert recorder.record(snapshot(9)) is False
    assert len(json.loads(output.read_text(encoding="utf-8"))["events"]) == 2
    assert len(list(output.parent.iterdir())) == 1


def test_snapshot_is_copied_and_unknown_fields_are_rejected():
    clock = FakeClock()
    recorder = recorder_for(clock)
    state = snapshot(1)
    recorder.record(state)
    state["cycle"]["id"] = 99
    assert recorder.buffered_events()[0]["cycle"]["id"] == 1

    with pytest.raises(ValueError, match="unsupported fields"):
        recorder.record(snapshot(2, screenshot=b"not stored"))
    assert recorder.buffered_event_count == 1


@pytest.mark.parametrize(
    "invalid",
    [
        {"cycle": {1: "non-string key"}},
        {"cycle": {"value": math.nan}},
        {"cycle": {"value": object()}},
    ],
)
def test_non_json_or_non_finite_snapshot_is_rejected_without_mutation(invalid):
    clock = FakeClock()
    recorder = recorder_for(clock)
    with pytest.raises(ValueError, match="finite JSON values"):
        recorder.record(invalid)
    assert recorder.buffered_event_count == 0


def test_event_size_and_output_location_are_bounded():
    clock = FakeClock()
    recorder = recorder_for(clock)
    too_large = {"proposal": "x" * MAX_EVENT_BYTES}
    with pytest.raises(ValueError, match="byte limit"):
        recorder.record(too_large)

    outside = PROJECT_ROOT.parent / "black-box-outside.json"
    with pytest.raises(ValueError, match="inside the project"):
        recorder_for(clock, output_path=outside)
    assert not outside.exists()


@pytest.mark.parametrize(
    "options",
    [
        {"window_seconds": 120.01},
        {"window_seconds": 10**1000},
        {"max_events": 513},
        {"max_events": 0},
    ],
)
def test_recorder_configuration_cannot_expand_memory_or_time_bounds(options):
    with pytest.raises(ValueError):
        BlackBoxRecorder(**options)


def test_invalid_trigger_fails_closed():
    recorder = recorder_for(FakeClock())
    with pytest.raises(ValueError, match="trigger must be"):
        recorder.record(snapshot(1), trigger=["crash"])
    with pytest.raises(ValueError, match="trigger must be"):
        recorder.freeze({"crash": True})
    assert recorder.is_frozen is False
    assert recorder.buffered_event_count == 0


def test_normal_recording_is_memory_only_and_freeze_without_events_is_valid(
    tmp_path,
):
    clock = FakeClock(12)
    output = tmp_path / "black-box.json"
    recorder = recorder_for(clock, output_path=output)
    recorder.record(snapshot(12))
    assert output.exists() is False

    clock.value = 13
    frozen = recorder.freeze("crash")
    assert frozen["trigger"] == "crash"
    assert output.exists() is True
