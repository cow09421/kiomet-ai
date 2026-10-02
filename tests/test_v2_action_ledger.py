from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools import v2_action_ledger as ledger
from tools import v2_controlled_transition_capture as capture


def _fact(value):
    return SimpleNamespace(value=value)


def _state(tick, *, document="doc", match="match", player=4):
    return SimpleNamespace(
        sequence=100 + tick, tick=_fact(tick),
        world_sequence_observed_at_ms=_fact(5000 + tick),
        document_id=document, match_id=_fact(match), player_id=_fact(player),
        lifecycle=_fact("IN_MATCH"), client_sha256="a" * 64,
        coverage="PLAYER_VISIBLE_COMPLETE", forces=_fact(()),
    )


def _tower(identifier, tower_type, relation="SELF"):
    return SimpleNamespace(id=identifier, tower_type=_fact(tower_type),
                           relation=_fact(relation))


def _intent():
    state = _state(65534)
    state.forces = _fact((SimpleNamespace(id=_fact("old-force")),))
    return ledger.build_action_intent(
        run_id="cohort-1", state=state, source=_tower(10, 2),
        destination=_tower(11, 3), intended_vector=((5, 7),),
        ui_action_type="ordinary_manual_deploy_force_canvas_drag",
        host_monotonic_ms=80000, prior_force_ids={"old-force"},
        preexisting_visible_inbound_force_to_source=False,
        source_supply_line_present=False)


def _ui_result(intent, status="SUCCESS"):
    return {"intent_id": intent["intent_id"], "ui_delivery_status": status}


def test_intent_records_unique_epoch_clock_and_all_current_vector_policy():
    one, two = _intent(), _intent()
    assert one["intent_id"] != two["intent_id"]
    assert one["snapshot_sequence"] == 65634
    assert one["world_sequence"] == 65534
    assert one["world_sequence_observed_at_host_monotonic_ms"] == 70534
    assert one["match_epoch"] == {"document_id": "doc", "match_id": "match",
                                  "player_id": 4, "lifecycle": "IN_MATCH"}
    assert one["intended_action"] == "ALL_CURRENT_DEPLOYABLE"
    assert one["intended_unit_vector"] == [[5, 7]]
    assert one["association_window_world_offsets"] == [1, 2]
    assert one["prior_force_ids"] == ["old-force"]
    assert one["preexisting_visible_inbound_force_to_source"] is False


def test_intent_rejects_special_unit_vectors_and_future_observation_clock():
    with pytest.raises(ValueError, match="complete positive typed intent vector"):
        ledger.build_action_intent(
            run_id="cohort", state=_state(10), source=_tower(1, 2), destination=_tower(2, 3),
            intended_vector=((8, 1),), ui_action_type="mouse", host_monotonic_ms=6000,
            prior_force_ids=set(), preexisting_visible_inbound_force_to_source=False,
            source_supply_line_present=False)
    with pytest.raises(ValueError, match="first-observation time"):
        ledger.build_action_intent(
            run_id="cohort", state=_state(10), source=_tower(1, 2), destination=_tower(2, 3),
            intended_vector=((5, 1),), ui_action_type="mouse", host_monotonic_ms=5000,
            prior_force_ids=set(), preexisting_visible_inbound_force_to_source=False,
            source_supply_line_present=False)


def test_intent_rejects_unknown_or_duplicate_prior_force_ids():
    state = _state(10)
    state.forces = _fact((SimpleNamespace(id=_fact(None)),))
    kwargs = dict(run_id="cohort", state=state, source=_tower(1, 2),
        destination=_tower(2, 3), intended_vector=((5, 1),),
        ui_action_type="mouse", host_monotonic_ms=6000,
        preexisting_visible_inbound_force_to_source=False,
        source_supply_line_present=False)
    with pytest.raises(ValueError, match="unknown pre-action force identity"):
        ledger.build_action_intent(prior_force_ids=set(), **kwargs)
    state.forces = _fact((SimpleNamespace(id=_fact("same")),
                          SimpleNamespace(id=_fact("same"))))
    with pytest.raises(ValueError, match="duplicate pre-action force identity"):
        ledger.build_action_intent(prior_force_ids={"same"}, **kwargs)


def test_missing_fixed_tick_and_ui_failure_stay_in_denominator():
    intent = _intent()
    missing = ledger.associate_fixed_window(intent,
        _ui_result(intent), [_state(65535)], {"old-force"}, 4)
    failed = ledger.associate_fixed_window(intent,
        _ui_result(intent, "FAILURE"), [_state(65535), _state(0)], {"old-force"}, 4)
    assert missing["status"] == "UNRESOLVED"
    assert missing["reason"] == "FIXED_WINDOW_MISSING_TICKS"
    assert failed["status"] == "UNRESOLVED"
    assert failed["reason"] == "UI_DELIVERY_NOT_SUCCESSFUL"


def test_ui_result_must_carry_the_exact_intent_id():
    intent = _intent()
    rows = [_state(65535), _state(0)]
    wrong = {"intent_id": "some-other-action", "ui_delivery_status": "SUCCESS"}
    missing = {"ui_delivery_status": "SUCCESS"}
    for ui in (wrong, missing):
        result = ledger.associate_fixed_window(intent, ui, rows, {"old-force"}, 4)
        assert result["status"] == "UNRESOLVED"
        assert result["reason"] == "UI_RESULT_INTENT_ID_MISMATCH"


def test_epoch_change_and_duplicate_tick_are_rejected(monkeypatch):
    intent = _intent()
    monkeypatch.setattr(capture, "collect_new_force_births",
                        lambda *args: {"eligible": True, "candidates": [{}], "ambiguity_reasons": []})
    ui = _ui_result(intent)
    changed = ledger.associate_fixed_window(intent, ui,
        [_state(65535, match="other"), _state(0, match="other")], {"old-force"}, 4)
    duplicate = ledger.associate_fixed_window(intent, ui,
        [_state(65535), _state(65535)], {"old-force"}, 4)
    assert changed["reason"] == "DOCUMENT_MATCH_OR_PLAYER_EPOCH_CHANGED"
    assert duplicate["reason"] == "DUPLICATE_FIXED_WINDOW_TICKS"


def test_association_player_must_match_intent_and_match_epoch():
    intent = _intent()
    result = ledger.associate_fixed_window(intent, _ui_result(intent),
        [_state(65535), _state(0)], {"old-force"}, 9)
    assert result["status"] == "UNRESOLVED"
    assert result["reason"] == "INTENT_PLAYER_ID_MISMATCH"
    intent["match_epoch"]["player_id"] = 9
    result = ledger.associate_fixed_window(intent, _ui_result(intent),
        [_state(65535), _state(0)], {"old-force"}, 4)
    assert result["status"] == "UNRESOLVED"
    assert result["reason"] == "INTENT_PLAYER_ID_MISMATCH"


def test_pair_lineage_is_selected_before_quantity_comparison(monkeypatch):
    intent = _intent()
    candidate = {"id": "force-1", "owner": 4, "source": 10, "destination": 11,
                 "birth_tick": 65535, "birth_progress": 0,
                 "birth_confidence": "NEW_TRACK", "birth_units": ((5, 6),),
                 "ambiguous": False}
    monkeypatch.setattr(capture, "collect_new_force_births",
        lambda states, source, destination, prior_ids, player: {
            "eligible": True, "candidates": [candidate], "ambiguity_reasons": []})
    result = ledger.associate_fixed_window(intent, _ui_result(intent),
        [_state(65535), _state(0)], {"old-force"}, 4)
    assert result["selected_force"]["observer_id"] == "force-1"
    assert result["quantity_matches_intent"] is False
    assert result["status"] == "UNRESOLVED"
    assert result["reason"] == "UNIQUE_BIRTH_QUANTITY_DIFFERS_FROM_INTENT"


def test_unique_birth_on_pair_in_window_is_only_candidate_matched(monkeypatch):
    intent = _intent()
    candidate = {"id": "force-2", "owner": 4, "source": 10, "destination": 11,
                 "birth_tick": 0, "birth_progress": 0,
                 "birth_confidence": "NEW_TRACK", "birth_units": ((5, 7),),
                 "ambiguous": False}
    monkeypatch.setattr(capture, "collect_new_force_births",
        lambda *args: {"eligible": True, "candidates": [candidate], "ambiguity_reasons": []})
    result = ledger.associate_fixed_window(intent, _ui_result(intent),
        [_state(65535), _state(0)], {"old-force"}, 4)
    assert result["status"] == "CANDIDATE_MATCHED"
    assert result["causal_attribution"] == "NOT_YET_VALIDATED_SOURCE_CONSERVATION"
    assert result["formal_credit"] == 0


def test_preexisting_inbound_birth_stays_ambiguous():
    intent = _intent()
    intent["preexisting_visible_inbound_force_to_source"] = True
    result = ledger.associate_fixed_window(intent, _ui_result(intent),
        [_state(65535), _state(0)], {"old-force"}, 4)
    assert result["status"] == "AMBIGUOUS"
    assert result["reason"] == "AMBIGUOUS_ALTERNATIVE_BIRTH_FROM_SUPPLY_LINE_OR_INBOUND_FORCE"


def test_action_ledger_cli_requires_execute_and_excludes_buffered_observer():
    with pytest.raises(SystemExit):
        capture.parse_args(["--action-ledger"])
    with pytest.raises(SystemExit):
        capture.parse_args(["--execute", "--source", "1", "--destination", "2",
                            "--action-ledger", "--input-entry-observer"])
