"""Fresh, outcome-free controls for the Goal013 typed policy boundary.

These tests exercise the public immutable view and action menu. They do not
call the transition evaluator, inspect episode outcomes, or reuse Goal006
reference cases.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from tools.v2_goal_decision_harness import (
    Action,
    ForceView,
    TowerView,
    VisiblePolicyState,
    visible_state,
)
from tools.v2_goal_typed_baselines import b1_or_wait, choose_b0, choose_b1


STRATA = (
    "S1_expansion",
    "S2_contested_expansion",
    "S3_threat_defense",
    "S4_reinforcement",
    "S5_combat_risk",
    "S6_uncertainty",
)

PRIMARY_CONTROL_IDS = (
    "S1-open-1101", "S1-open-1111",
    "S2-contested-1201", "S2-contested-1211",
    "S3-threat-1301", "S3-king-1311",
    "S4-donor-choice-1401", "S4-donor-choice-1411",
    "S5-robust-1501", "S5-risky-1511",
    "S6-unknown-force-1601", "S6-unknown-force-1611",
)
BOUNDARY_CONTROL_IDS = (
    "B0-neutral-tie-break", "B0-no-neutral-low-ratio",
    "B1-valid-wait", "force-hidden-marker", "force-rich-sentinel",
    "force-multiplicity-two", "permutation-canonical", "permutation-reversed",
    "raw-mapping-rejected", "incomplete-vector-rejected",
    "validated-menu-context-fallback", "unpressured-ruler-source",
    "supply-unknown-variant", "supply-known-variant",
    "shield-only-neutral", "exposed-source-no-shield-reserve",
    "mixed-single-many-rejected", "forged-empty-source-menu-rejected",
    "forged-nonown-source-menu-rejected", "forged-delayed-source-menu-rejected",
    "opening-early-index3", "opening-late-index6",
    "opening-raw-tick-no-history", "opening-u16-wrap",
)
FRESH_CONTROL_IDS = PRIMARY_CONTROL_IDS + BOUNDARY_CONTROL_IDS


def _tower(ident: int, xy: tuple[int, int], owner: int | None, *,
           kind: int = 7, shield: int = 0, soldier: int = 0,
           delay: int = 0, supply: bool = False) -> dict:
    units = [0] * 10
    units[0] = shield
    units[5] = soldier
    return {
        "id": ident, "xy": list(xy), "kind": kind, "owner": owner,
        "units": units, "delay": delay, "supply": supply,
        "visible": True,
    }


def _state(*towers: dict, forces: tuple[dict, ...] = (), tick: int = 100
           ) -> VisiblePolicyState:
    """Use the pinned public projection to derive the unmodified legal menu."""
    return visible_state({
        "player": 1,
        "start_tick": (tick + 1) & 0xFFFF,
        "towers": list(towers),
        "forces": list(forces),
    })


def _action(result: dict) -> Action:
    action = result.get("action")
    assert isinstance(action, Action), result
    return action


def _legal(state: VisiblePolicyState, result: dict) -> Action:
    action = _action(result)
    assert action in state.legal_choices
    if action.kind == "DEPLOY":
        source = next(t for t in state.towers if t.id == action.source)
        assert len(source.units) == 10
        assert any(source.units[i] for i in (1, 2, 3, 4, 5, 9))
    return action


def _six_stratum_views() -> list[tuple[str, VisiblePolicyState, Action, Action]]:
    """Small public-state decisions, with hand-stated menu actions only."""
    rows: list[tuple[str, VisiblePolicyState, Action, Action]] = []

    # S1: opening expansion, two independent source/target IDs.
    for ident, tick in ((1101, 101), (1111, 113)):
        view = _state(
            _tower(ident, (1, 1), 1, soldier=12),
            _tower(ident + 1, (1, 2), None), tick=tick)
        expected = Action("DEPLOY", ident, ident + 1)
        rows.append((STRATA[0], view, expected, expected))

    # S2: enemy and the player can both reach a neutral target.
    for ident, tick in ((1201, 127), (1211, 139)):
        view = _state(
            _tower(ident, (1, 1), 1, soldier=12),
            _tower(ident + 1, (1, 2), None),
            _tower(ident + 2, (2, 3), 2, soldier=4), tick=tick)
        expected = Action("DEPLOY", ident, ident + 1)
        rows.append((STRATA[1], view, expected, expected))

    # S3: exposed weak frontline reinforcement and a pressured King escape.
    view = _state(
        _tower(1301, (2, 3), 1, soldier=12),
        _tower(1302, (1, 2), 1, soldier=3),
        _tower(1303, (1, 1), 2, soldier=8), tick=151)
    expected = Action("DEPLOY", 1301, 1302)
    rows.append((STRATA[2], view, expected, expected))
    king = _tower(1311, (1, 2), 1)
    king["units"][9] = 1
    view = _state(
        king,
        _tower(1312, (2, 3), 1, soldier=4),
        _tower(1313, (1, 1), 2, soldier=1), tick=163)
    expected = Action("DEPLOY", 1311, 1312)
    rows.append((STRATA[2], view, expected, expected))

    # S4: two distinct legal donors can reinforce the same exposed weak tower.
    for ident, tick in ((1401, 181), (1411, 193)):
        view = _state(
            _tower(ident, (2, 3), 1, soldier=9),
            _tower(ident + 1, (1, 2), 1, soldier=2),
            _tower(ident + 2, (1, 3), 1, soldier=14),
            _tower(ident + 3, (1, 1), 2, soldier=8), tick=tick)
        rows.append((STRATA[3], view,
                     Action("DEPLOY", ident + 2, ident + 1),
                     Action("DEPLOY", ident, ident + 1)))

    # S5: one robust visible engagement and one visibly unfavorable matchup.
    for ident, tick in ((1501, 211), (1511, 223)):
        source_count, enemy_count = ((14, 2) if ident == 1501 else (5, 10))
        view = _state(
            _tower(ident, (1, 1), 1, shield=1, soldier=source_count),
            _tower(ident + 1, (1, 2), 2, soldier=enemy_count), tick=tick)
        expected = (Action("DEPLOY", ident, ident + 1)
                    if source_count / enemy_count >= 1.5 else Action("WAIT"))
        rows.append((STRATA[4], view, expected, expected))

    # S6: visible force markers have unknown route/composition and must not be
    # assigned to either endpoint or scored as an enemy threat.
    for ident, tick in ((1601, 241), (1611, 253)):
        view = _state(
            _tower(ident, (1, 1), 1, soldier=12),
            _tower(ident + 1, (1, 2), None),
            _tower(ident + 2, (2, 3), 2, soldier=7),
            forces=({"visible": True, "owner": None, "src": None,
                     "dst": None, "progress": None, "units": None},),
            tick=tick)
        expected = Action("WAIT")
        rows.append((STRATA[5], view, expected, expected))

    return rows


def _opening_contest(ident: int, tick: int) -> tuple[VisiblePolicyState, Action, Action]:
    view = _state(
        _tower(ident, (1, 1), 1, shield=1, soldier=14),
        _tower(ident + 1, (1, 2), 2, soldier=2),
        _tower(ident + 2, (0, 2), None), tick=tick)
    return (view, Action("DEPLOY", ident, ident + 2),
            Action("DEPLOY", ident, ident + 1))


def test_frozen_fresh_control_inventory_is_unique_and_stratified() -> None:
    assert len(PRIMARY_CONTROL_IDS) == 12
    assert len(BOUNDARY_CONTROL_IDS) == 24
    assert len(FRESH_CONTROL_IDS) == 36
    assert len(set(FRESH_CONTROL_IDS)) == len(FRESH_CONTROL_IDS)
    cases = _six_stratum_views()
    counts = {stratum: sum(row[0] == stratum for row in cases)
              for stratum in STRATA}
    assert counts == {stratum: 2 for stratum in STRATA}


@pytest.mark.parametrize("stratum,view,b0_expected,b1_expected", _six_stratum_views())
def test_fresh_stratum_controls_stay_inside_the_full_legal_menu(
        stratum: str, view: VisiblePolicyState,
        b0_expected: Action, b1_expected: Action) -> None:
    # Each row is an independent newly authored current-state control; the
    # expected choice is a typed intent, never a simulated outcome.
    assert stratum in STRATA
    assert b0_expected in view.legal_choices
    assert b1_expected in view.legal_choices
    assert _legal(view, choose_b0(view)) == b0_expected
    assert _legal(view, choose_b1(view)) == b1_expected
    for result in (choose_b0(view), choose_b1(view), b1_or_wait(view)):
        assert result["provider"] in {"B0", "B1", "B1_FALLBACK"}
        assert result["status"] in {"DECIDED", "UNKNOWN", "FALLBACK_WAIT"}
        if result["action"] is not None:
            assert _legal(view, result) == result["action"]
            assert not hasattr(result["action"], "amount")
            if result["action"].kind == "DEPLOY":
                assert result["evidence"]["action_amount"] == (
                    "ALL_CURRENT_MOBILE_BY_MENU")
        else:
            assert result["status"] == "UNKNOWN"


def test_b0_selects_only_a_legal_empty_neutral_deployment() -> None:
    view = _state(
        _tower(1701, (1, 1), 1, soldier=11),
        _tower(1702, (1, 2), None),
        _tower(1703, (2, 3), 1, soldier=14),
        _tower(1704, (1, 3), None), tick=271)
    result = choose_b0(view)
    assert _legal(view, result) == Action("DEPLOY", 1703, 1702)
    assert result["status"] == "DECIDED"


def test_b0_waits_when_no_neutral_target_exists() -> None:
    view = _state(
        _tower(1711, (1, 1), 1, shield=1, soldier=8),
        _tower(1712, (1, 2), 2, soldier=10), tick=283)
    result = choose_b0(view)
    assert _legal(view, result) == Action("WAIT")


def test_b1_opening_priority_requires_current_session_history() -> None:
    early, expansion, attack = _opening_contest(1811, 105)
    late, late_expansion, late_attack = _opening_contest(1821, 105)
    no_history, no_history_expansion, no_history_attack = _opening_contest(1831, 5)
    assert expansion in early.legal_choices and attack in early.legal_choices
    assert late_expansion in late.legal_choices and late_attack in late.legal_choices
    assert no_history_expansion in no_history.legal_choices
    assert no_history_attack in no_history.legal_choices
    assert _legal(early, choose_b1(early, decision_index=3,
                                   first_observed_tick=100)) == expansion
    assert _legal(late, choose_b1(late, decision_index=6,
                                 first_observed_tick=100)) == late_attack
    # A small raw world tick is not evidence of opening age.
    assert _legal(no_history, choose_b1(no_history)) == no_history_attack


def test_b1_opening_history_handles_u16_tick_wrap() -> None:
    wrapped, expansion, attack = _opening_contest(1841, 4)
    assert expansion in wrapped.legal_choices and attack in wrapped.legal_choices
    result = choose_b1(wrapped, decision_index=2, first_observed_tick=65530)
    assert _legal(wrapped, result) == expansion


def test_b1_fallback_is_an_explicit_legal_wait() -> None:
    view = _state(_tower(1721, (1, 1), 1), tick=293)
    result = b1_or_wait(view)
    assert result["status"] in {"DECIDED", "FALLBACK_WAIT"}
    assert _legal(view, result) == Action("WAIT")


def test_hidden_force_metadata_mutation_does_not_change_policy_decisions() -> None:
    view = _state(
        _tower(1731, (1, 1), 1, soldier=12),
        _tower(1732, (1, 2), None), tick=307)
    hidden_variant = replace(view, forces=(ForceView(),))
    rich_sentinel_variant = replace(view, forces=(ForceView(
        visible=True, owner=2, source=1731, target=1732, progress=255,
        units=(45, 0, 0, 0, 0, 10, 0, 0, 0, 0)),))
    assert len(hidden_variant.forces) == 1
    assert len(rich_sentinel_variant.forces) == 1
    assert choose_b0(hidden_variant) == choose_b0(rich_sentinel_variant)
    assert choose_b1(hidden_variant) == choose_b1(rich_sentinel_variant)
    for result in (choose_b0(rich_sentinel_variant),
                   choose_b1(rich_sentinel_variant)):
        assert result["evidence"]["unrouted_force_markers"] == 1
        assert result["evidence"].get("route_inference") == "NONE"
        assert result["action"] == Action("WAIT")


def test_unknown_force_multiplicity_is_preserved_without_attribution() -> None:
    view = _state(
        _tower(1735, (1, 1), 1, soldier=12),
        _tower(1736, (1, 2), None),
        forces=(
            {"visible": True, "owner": None, "src": None, "dst": None},
            {"visible": True, "owner": None, "src": None, "dst": None},
        ), tick=309)
    assert len(view.forces) == 2
    assert all(force.owner is None and force.source is None
               and force.target is None and force.progress is None
               and force.units is None for force in view.forces)
    for result in (choose_b0(view), choose_b1(view), b1_or_wait(view)):
        assert _legal(view, result) == Action("WAIT")
        assert result["evidence"]["unrouted_force_markers"] == 2
        assert result["evidence"].get("route_inference") == "NONE"


def test_permutation_of_public_view_rows_does_not_change_choice() -> None:
    view = _state(
        _tower(1741, (1, 1), 1, kind=3, soldier=20),
        _tower(1742, (1, 2), None),
        _tower(1743, (2, 3), 1, kind=3, soldier=17),
        _tower(1744, (2, 2), None), tick=313)
    reversed_rows = replace(view, towers=tuple(reversed(view.towers)))
    assert reversed_rows.legal_choices == view.legal_choices
    assert choose_b0(reversed_rows) == choose_b0(view)
    assert choose_b1(reversed_rows) == choose_b1(view)


@pytest.mark.parametrize("policy", (choose_b0, choose_b1, b1_or_wait))
def test_policy_refuses_untyped_raw_mapping(policy) -> None:
    result = policy({"player": 1, "towers": [], "forces": []})
    assert result["status"] == "UNKNOWN"
    assert result["action"] is None


@pytest.mark.parametrize("policy", (choose_b0, choose_b1, b1_or_wait))
def test_policy_refuses_incomplete_current_tower_vector(policy) -> None:
    view = _state(_tower(1751, (1, 1), 1, soldier=9), tick=331)
    broken_tower = replace(view.towers[0], units=(0, 0, 0, 0, 0, 9))
    broken = replace(view, towers=(broken_tower,))
    result = policy(broken)
    if policy is b1_or_wait:
        assert result["status"] == "UNKNOWN"
        assert result["action"] is None
    else:
        assert result["status"] == "UNKNOWN"
        assert result["action"] is None


def test_validated_menu_gets_explicit_wait_fallback_on_bad_context() -> None:
    view = _state(_tower(1755, (1, 1), 1, soldier=4), tick=337)
    result = b1_or_wait(view, decision_index=-1)
    assert result["provider"] == "B1_FALLBACK"
    assert result["status"] == "FALLBACK_WAIT"
    assert result["action"] == Action("WAIT")
    assert result["action"] in view.legal_choices


def test_unpressured_ruler_source_is_not_selected_for_expansion() -> None:
    row = _tower(1761, (1, 1), 1)
    row["units"][9] = 1
    view = _state(row, _tower(1762, (1, 2), None), tick=347)
    for result in (choose_b0(view), choose_b1(view), b1_or_wait(view)):
        if result["action"] is not None:
            action = _legal(view, result)
            assert action.kind == "WAIT"


def test_supply_field_does_not_change_a_tower_count_only_decision() -> None:
    view = _state(
        _tower(1771, (1, 1), 1, soldier=10),
        _tower(1772, (1, 2), None), tick=359)
    unknown_supply = replace(view.towers[0], supply=None)
    known_supply = replace(view.towers[0], supply=True)
    unknown_view = replace(view, towers=(unknown_supply, view.towers[1]))
    known_view = replace(view, towers=(known_supply, view.towers[1]))
    assert choose_b0(unknown_view)["action"] == choose_b0(known_view)["action"]
    assert choose_b1(unknown_view)["action"] == choose_b1(known_view)["action"]


def test_shield_only_source_does_not_expand_to_neutral() -> None:
    view = _state(
        _tower(1781, (1, 1), 1, kind=15, shield=5),
        _tower(1782, (1, 2), None), tick=367)
    assert Action("DEPLOY", 1781, 1782) in view.legal_choices
    for policy in (choose_b0, choose_b1):
        result = policy(view)
        assert _legal(view, result) == Action("WAIT")


def test_exposed_attack_source_without_stationary_shield_is_not_selected() -> None:
    view = _state(
        _tower(1785, (1, 1), 1, soldier=14),
        _tower(1786, (1, 2), 2, soldier=2), tick=369)
    assert Action("DEPLOY", 1785, 1786) in view.legal_choices
    for policy in (choose_b0, choose_b1):
        result = policy(view)
        assert _legal(view, result) == Action("WAIT")


def test_mixed_ruler_and_soldier_source_is_refused() -> None:
    row = _tower(1791, (1, 1), 1, soldier=3)
    row["units"][9] = 1
    view = _state(row, _tower(1792, (1, 2), None), tick=373)
    for policy in (choose_b0, choose_b1):
        result = policy(view)
        assert result["status"] == "UNKNOWN"
        assert result["action"] is None


def test_forged_deploy_from_empty_source_invalidates_the_menu() -> None:
    view = _state(
        _tower(1801, (1, 1), 1),
        _tower(1802, (1, 2), None), tick=383)
    forged = replace(
        view,
        legal_choices=view.legal_choices + (Action("DEPLOY", 1801, 1802),))
    for policy in (choose_b0, choose_b1):
        result = policy(forged)
        assert result["status"] == "UNKNOWN"
        assert result["action"] is None


@pytest.mark.parametrize(
    "source,invalid_action",
    (
        (_tower(1851, (1, 1), 2, soldier=5), Action("DEPLOY", 1851, 1852)),
        (_tower(1853, (1, 1), 1, soldier=5, delay=1), Action("DEPLOY", 1853, 1854)),
    ),
)
def test_forged_nonowned_or_delayed_deploy_rows_are_refused(
        source: dict, invalid_action: Action) -> None:
    target_id = invalid_action.target
    view = _state(source, _tower(target_id, (1, 2), None), tick=389)
    forged = replace(view, legal_choices=view.legal_choices + (invalid_action,))
    for policy in (choose_b0, choose_b1):
        result = policy(forged)
        assert result["status"] == "UNKNOWN"
        assert result["action"] is None
