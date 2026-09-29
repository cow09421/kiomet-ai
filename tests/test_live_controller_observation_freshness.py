"""Live observation blockers retain same-match freshness without guessing."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

from kiomet_ai.live_controller import LiveController


def make_controller(tmp_path, *, state="IN_MATCH", match_id="match-a"):
    app = SimpleNamespace(
        root=Path(tmp_path),
        browser=SimpleNamespace(game={
            "state": state,
            "match": {"id": match_id},
        }),
        gate=SimpleNamespace(authorized=False, state="RUNNING"),
    )
    controller = LiveController(app)
    controller.cycle_seq = 7
    return controller


def test_anchor_unavailable_fails_closed_without_running_research_tools(tmp_path):
    controller = make_controller(tmp_path)

    async def forbidden_tool(*_args, **_kwargs):
        raise AssertionError("hidden-memory research tools must stay disabled")

    controller._run_tool = forbidden_tool

    assert asyncio.run(controller.ensure_anchor("match-a")) is None


def test_missing_visible_world_map_is_reported_as_observation_blocker(tmp_path):
    controller = make_controller(tmp_path)

    async def no_anchor(_match_id):
        return None

    controller.ensure_anchor = no_anchor
    phase, info = asyncio.run(controller.cycle_once())

    blocker = controller.journal["observation_blocker"]
    assert phase == "NO_SAFE_PROPOSAL"
    assert info["reason"] == "anchor_unavailable"
    assert controller.normalize_reason(info["reason"]) == "OBSERVATION_STALE"
    assert blocker["status"] == "OBSERVATION_STALE"
    assert blocker["category"] == "OBSERVATION_STALE"
    assert blocker["match_id"] == "match-a"
    assert blocker["blocking_component"] == "visible-world-map"
    assert blocker["reason"] == "trusted-visible-world-map-unavailable"
    assert blocker["last_good_timestamp"] == "UNKNOWN"
    assert blocker["age_seconds"] == "UNKNOWN"
    assert blocker["first_bad_timestamp"] > 0
    assert blocker["blocked_for_seconds"] >= 0
    assert controller.journal["sent_actions"] == 0


def test_same_blocker_preserves_first_bad_and_last_good_timestamp(tmp_path):
    controller = make_controller(tmp_path)
    controller._set_observation_fresh("match-a", now=100)

    first = controller._set_observation_blocker(
        "OBSERVATION_STALE", "visible-world-map", "map-unavailable",
        "match-a", now=110)
    repeated = controller._set_observation_blocker(
        "OBSERVATION_STALE", "visible-world-map", "map-unavailable",
        "match-a", now=115)

    assert first["first_bad_timestamp"] == repeated["first_bad_timestamp"] == 110
    assert repeated["last_good_timestamp"] == 100
    assert repeated["age_seconds"] == 15
    assert repeated["blocked_for_seconds"] == 5


def test_match_change_does_not_carry_previous_match_freshness(tmp_path):
    controller = make_controller(tmp_path)
    controller._set_observation_fresh("match-a", now=100)

    blocker = controller._set_observation_blocker(
        "OBSERVATION_STALE", "visible-world-map", "map-unavailable",
        "match-b", now=120)

    assert blocker["match_id"] == "match-b"
    assert blocker["last_good_timestamp"] == "UNKNOWN"
    assert blocker["age_seconds"] == "UNKNOWN"
    assert blocker["first_bad_timestamp"] == 120


def test_non_match_is_classified_separately_from_missing_anchor(tmp_path):
    controller = make_controller(tmp_path, state="RESULT", match_id=None)

    phase, info = asyncio.run(controller.cycle_once())

    assert phase == "NO_SAFE_PROPOSAL"
    assert info["reason"] == "not_in_match"
    blocker = controller.journal["observation_blocker"]
    assert blocker["status"] == "MATCH_STALE"
    assert blocker["blocking_component"] == "match"
    assert blocker["match_id"] is None


def test_cycle_record_carries_structured_blocker(tmp_path):
    controller = make_controller(tmp_path)
    blocker = controller._set_observation_blocker(
        "OBSERVATION_STALE", "visible-world-map", "map-unavailable",
        "match-a", now=120)

    controller._record_cycle(8, 121, "NO_SAFE_PROPOSAL", {
        "match_id": "match-a", "reason": "anchor_unavailable"})

    assert controller.journal["last_cycle"]["observation_blocker"] == blocker


def test_invalid_category_and_unknown_timestamp_never_become_zero(tmp_path):
    controller = make_controller(tmp_path)

    blocker = controller._set_observation_blocker(
        "STALE_WORLD", "", "", "match-a", now=200)

    assert blocker["category"] == "UNKNOWN_STALE"
    assert blocker["blocking_component"] == "UNKNOWN"
    assert blocker["reason"] == "UNKNOWN"
    assert blocker["last_good_timestamp"] == "UNKNOWN"
    assert blocker["age_seconds"] == "UNKNOWN"
