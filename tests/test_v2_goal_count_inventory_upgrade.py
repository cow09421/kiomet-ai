"""Fresh, pure controls for explicit-count panel identity (Goal-017).

Every paired case uses a new ID, count vector, and tick.  The panel supplies
only the numerator constraints that were actually captured; its denominator
is syntactic input and is never treated as a capacity fact.  These controls
exercise the typed boundary only and never start a browser or a game session.
"""
from dataclasses import fields

import pytest

from kiomet_ai.v2.observe import rules
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256
from kiomet_ai.v2.state import Fact, GameState, Knowledge, Lifecycle, Relation, Tower, Units
from tools.v2_goal_count_inventory_upgrade import (
    certify_count_inventory_panel,
    count_candidate_rows,
)
from tools.v2_goal_inventory_upgrade import certify_inventory_panel as legacy_certificate


PLAYER = 41
CLIFF = 7
QUARRY = 16
BASE_ID = 81_001
BASE_TICK = 1_200
BASE_AT = 80_000
UNIT_LABELS = {
    0: "Shield", 1: "Fighter", 2: "Chopper", 3: "Bomber", 4: "Tank",
    5: "Soldier", 6: "Shell", 7: "EMP", 8: "Nuke", 9: "Ruler",
}
DENOMINATORS = (30, 31, 40, 45, 52, 101, 255, 0)
_TOWER_TRUTH = {}


def fact(value, *, at, knowledge=Knowledge.OBSERVED):
    return Fact(value, knowledge, "Goal-017 fresh synthetic control", at)


def unknown():
    return Fact()


def vector(counts):
    assert len(counts) == 10
    return Units(tuple(enumerate(counts)))


def resources_for_quarry():
    # Every complete synthetic world includes exactly one supporting Village.
    # The candidate fact needs only the target's required resource counts.
    return tuple((unit, 1 if unit == 26 else 0) for unit in range(27))


def direct_quarry_prerequisite_rows(resources):
    available = dict(resources)
    required = rules.PREREQUISITES[QUARRY]
    exact = tuple((unit, available[unit], need)
                  for unit, need in enumerate(required) if need)
    return ((QUARRY, exact, True),)


def make_tower(tower_id, *, at, counts, source=CLIFF, owner=PLAYER,
               relation=Relation.SELF, delay=0, morale=False,
               owner_fact=None, relation_fact=None, type_fact=None,
               visibility_fact=None, units_fact=None, capacity_fact=None,
               delay_fact=None, candidates_fact=None, locks_fact=None,
               effects_fact=None):
    resources = resources_for_quarry()
    current_units = vector(counts)
    tower = Tower(
        tower_id,
        visibility=visibility_fact or fact(True, at=at),
        owner=owner_fact or fact(owner, at=at),
        relation=relation_fact or fact(relation, at=at),
        tower_type=type_fact or fact(source, at=at),
        units=units_fact or fact(current_units, at=at),
        capacity=capacity_fact if capacity_fact is not None else
            fact(rules.capacity(source, morale), at=at),
        production=fact((), at=at),
        delay_ticks=delay_fact if delay_fact is not None else fact(delay, at=at),
        upgrade_candidates=candidates_fact if candidates_fact is not None else
            fact(direct_quarry_prerequisite_rows(resources), at=at),
        upgrade_locks=locks_fact if locks_fact is not None else
            fact(((QUARRY, False),), at=at),
        effects=effects_fact if effects_fact is not None else
            fact((("MORALE_BOOST", morale),), at=at),
        position=fact((tower_id % 511, (tower_id + 19) % 509), at=at),
    )
    _TOWER_TRUTH[id(tower)] = (source, owner, tuple(counts), tower)
    return tower


def make_world(index, towers, *, player=PLAYER, client_sha=CLIENT_SHA256,
               lifecycle=Lifecycle.IN_MATCH, source_mode="NETWORK",
               tick=None, at=None, coverage="PLAYER_VISIBLE_COMPLETE",
               match_fact=None, player_fact=None, lifecycle_fact=None,
               source_mode_fact=None, tick_fact=None, tick_observed_at=None,
               unlocked_fact=None):
    if tick is None:
        tick = BASE_TICK + index * 8
    if at is None:
        at = BASE_AT + index * 307
    towers = tuple(towers)
    if type(player) is int and 1 <= player <= 65535:
        has_supporting_village = any(
            (truth := _TOWER_TRUTH.get(id(tower))) is not None and
                truth[0] == 26 and truth[1] == player and truth[2] == (1,) + (0,) * 9
            for tower in towers
        )
        if not has_supporting_village:
            support = make_tower(
                BASE_ID + 2_500_000 + index * 47,
                at=at, source=26, owner=player, counts=(1,) + (0,) * 9,
            )
            towers += (support,)
    type_counts = [0] * 27
    for tower in towers:
        truth = _TOWER_TRUTH.get(id(tower))
        if truth is None:
            continue
        tower_type, owner, _counts = truth[:3]
        if (type(player) is int and 1 <= player <= 65535 and
                type(owner) is int and 1 <= owner <= 65535 and owner == player and
                type(tower_type) is int and 0 <= tower_type < len(type_counts)):
            type_counts[tower_type] += 1
    resources = tuple(enumerate(type_counts))
    return GameState(
        session_id=f"goal017-session-{index}",
        document_id=f"goal017-document-{index}",
        match_id=match_fact if match_fact is not None else
            fact(f"goal017-match-{index}", at=at),
        sequence=index + 1,
        sampled_at_ms=at,
        received_at_ms=at,
        client_sha256=client_sha,
        tick=tick_fact if tick_fact is not None else fact(tick, at=at),
        lifecycle=lifecycle_fact if lifecycle_fact is not None else fact(lifecycle, at=at),
        player_id=player_fact if player_fact is not None else fact(player, at=at),
        source_mode=source_mode_fact if source_mode_fact is not None else
            fact(source_mode, at=at),
        coverage=coverage,
        coverage_evidence=fact((("positive_sensor_slots", len(towers)),
                               ("decoded_current_towers", len(towers))), at=at),
        upgrade_resources=fact(resources, at=at),
        unlocked_tower_types=unlocked_fact if unlocked_fact is not None else
            fact((QUARRY,), at=at),
        world_sequence_observed_at_ms=fact(
            at if tick_observed_at is None else tick_observed_at, at=at),
        towers=tuple(towers),
    )


def panel_rows(counts, unit_ids=(0, 4, 5), *, salt=0):
    rows = []
    for unit in unit_ids:
        denominator = DENOMINATORS[(salt + unit) % len(DENOMINATORS)]
        rows.append({"title": UNIT_LABELS[unit],
                     "text": f"{counts[unit]}/{denominator}"})
    return rows


def panel_dom(counts, unit_ids=(0, 4, 5), *, salt=0, heading="Cliff",
              buttons=None, panels=None, rows=None, errors=None):
    if rows is None:
        rows = panel_rows(counts, unit_ids, salt=salt)
    if buttons is None:
        buttons = [{
            "title": "Upgrade to Quarry", "visible": True, "enabled": True,
            "pointer_events": True, "locked_glyph": False,
            "hidden_lock_icon": False, "bbox": [31, 47, 93, 29],
        }]
    if panels is None:
        panels = [{"headings": [heading], "unit_rows": rows, "buttons": buttons}]
    result = {"panels": panels, "headings": [heading], "buttons": buttons}
    if errors is not None:
        result["errors"] = list(errors)
    return result


def fixture(index, *, unit_ids=(0, 4, 5), morale=False,
            capacity_known=True, player=PLAYER):
    # A long nonrepeating sequence of complete vectors, IDs, and ticks, all
    # within the registered source bounds (Shield 30..45, Tank 3..7).
    counts = (30 + index % 16, 0, 0, 0,
              3 + (index // 16) % 5, 5 + (index // 80) % 10,
              0, 0, 0, 0)
    # Cross-type rivals remain within each declared public overflow bound.
    if index in (3, 4, 21):
        counts = (12 + index % 10, 0, 0, 0, 3, 5, 0, 0, 0, 0)
    if index in (203, 204, 221):
        shield = {203: 15, 204: 16, 221: 13}[index]
        counts = (shield, 0, 0, 0, 3, 7, 0, 0, 0, 0)
    elif index in (230, 231, 232):
        shield = {230: 27, 231: 28, 232: 29}[index]
        counts = (shield, 0, 0, 0, 7, 7, 0, 0, 0, 0)
    tower_id = BASE_ID + index * 37
    at = BASE_AT + index * 307
    current = make_tower(
        tower_id, at=at, counts=counts, morale=morale,
        capacity_fact=(fact(rules.capacity(CLIFF, morale), at=at)
                       if capacity_known else unknown()),
    )
    world = make_world(index, (current,), player=player, tick=BASE_TICK + index * 8, at=at)
    dom = panel_dom(counts, unit_ids, salt=index)
    return world, dom, current, counts, at


def _unchecked_tower(original, **changes):
    """Build malformed-but-readable producer rows to test fail-closed gates."""
    clone = object.__new__(Tower)
    for item in fields(Tower):
        object.__setattr__(clone, item.name,
                           changes.get(item.name, getattr(original, item.name)))
    if id(original) in _TOWER_TRUTH:
        tower_type, owner, counts, _original_ref = _TOWER_TRUTH[id(original)]
        _TOWER_TRUTH[id(clone)] = (tower_type, owner, counts, clone)
    return clone


def _unchecked_world_with_towers(original, towers):
    """Bypass GameState's duplicate-ID constructor guard for helper defense."""
    towers = tuple(towers)
    truth_actors = [
        tower for tower in original.towers
        if (truth := _TOWER_TRUTH.get(id(tower))) is not None and
        truth[0] == 26 and truth[2] == (1,) + (0,) * 9 and
        all(tower is not existing for existing in towers)
    ]
    towers += tuple(truth_actors)
    clone = object.__new__(GameState)
    for item in fields(GameState):
        object.__setattr__(clone, item.name,
                           tuple(towers) if item.name == "towers"
                           else getattr(original, item.name))
    return clone


def _set_denominators(dom, shift):
    changed = {**dom, "panels": [dict(dom["panels"][0])],
               "headings": list(dom["headings"]), "buttons": list(dom["buttons"])}
    changed["panels"][0]["unit_rows"] = []
    for row in dom["panels"][0]["unit_rows"]:
        numerator, denominator = row["text"].split("/")
        changed["panels"][0]["unit_rows"].append(
            {"title": row["title"],
             "text": f"{numerator}/{(int(denominator) + shift) % 256}"})
    return changed


def _candidate_row(state, tower_id):
    return next((row for row in count_candidate_rows(state)
                 if row.get("tower_id") == tower_id and
                 row.get("target_type") == QUARRY), None)


def _tower_with_hidden_count(original, *, tower_id, at, unit, value):
    original_counts = dict(original.units.value.counts)
    original_counts[unit] = value
    counts = tuple(original_counts[index] for index in range(10))
    return make_tower(tower_id, at=at, counts=counts)


PAIR_SCENARIOS = (
    "numerator_mismatch", "same_source_duplicate", "nonown_duplicate",
    "cross_kind_quarry", "cross_kind_village", "delay_duplicate",
    "omitted_fighter_duplicate", "omitted_ruler_duplicate",
    "unknown_owner_duplicate", "unknown_relation_duplicate",
    "unknown_type_duplicate", "stale_vector_duplicate",
    "partial_vector_duplicate", "malformed_vector_duplicate",
    "unknown_visibility_duplicate", "duplicate_id_duplicate",
    "same_projection_other_tank", "same_projection_other_soldier",
    "ineligible_lock_duplicate", "ineligible_prerequisite_duplicate",
    "second_nonown_duplicate", "second_cross_kind_duplicate",
    "bad_heading", "duplicate_explicit_row", "malformed_count_text",
    "wrong_upgrade_title", "multiple_panel_roots", "wrong_client_version",
    "unknown_match_epoch", "incomplete_visible_coverage",
    "omitted_shell_duplicate", "omitted_emp_duplicate", "omitted_nuke_duplicate",
)


def _counterfactual(index, scenario, positive_state, dom, source, counts, at):
    if scenario == "numerator_mismatch":
        changed = {**dom, "panels": [dict(dom["panels"][0])]}
        changed["panels"][0]["unit_rows"] = [dict(row) for row in dom["panels"][0]["unit_rows"]]
        numerator, denominator = changed["panels"][0]["unit_rows"][0]["text"].split("/")
        changed["panels"][0]["unit_rows"][0]["text"] = f"{int(numerator) + 1}/{denominator}"
        return positive_state, changed
    if scenario in {"bad_heading", "wrong_upgrade_title", "duplicate_explicit_row",
                    "malformed_count_text", "multiple_panel_roots"}:
        changed = {**dom, "panels": [dict(dom["panels"][0])]}
        changed["panels"][0]["unit_rows"] = [dict(row) for row in dom["panels"][0]["unit_rows"]]
        changed["panels"][0]["buttons"] = [dict(button) for button in dom["panels"][0]["buttons"]]
        if scenario == "bad_heading":
            changed["panels"][0]["headings"] = ["Quarry"]
        elif scenario == "wrong_upgrade_title":
            changed["panels"][0]["buttons"][0]["title"] = "Upgrade to Rampart"
        elif scenario == "duplicate_explicit_row":
            changed["panels"][0]["unit_rows"].append(
                dict(changed["panels"][0]["unit_rows"][0]))
        elif scenario == "malformed_count_text":
            row = changed["panels"][0]["unit_rows"][0]
            numerator, denominator = row["text"].split("/")
            row["text"] = f"0{numerator}/{denominator}"
        else:
            changed["panels"].append(dict(changed["panels"][0]))
        return positive_state, changed
    if scenario == "wrong_client_version":
        base = make_world(index, (source,), player=PLAYER,
                          client_sha="a" * 64, tick=BASE_TICK + index * 8, at=at)
        return base, dom
    if scenario == "unknown_match_epoch":
        base = make_world(index, (source,), tick=BASE_TICK + index * 8, at=at,
                          match_fact=unknown())
        return base, dom
    if scenario == "incomplete_visible_coverage":
        base = make_world(index, (source,), tick=BASE_TICK + index * 8, at=at,
                          coverage="PLAYER_VISIBLE_PENDING")
        return base, dom

    blocker_id = source.id + 6_000_001
    blocker = make_tower(blocker_id, at=at, counts=counts)
    towers = (source, blocker)
    if scenario == "same_source_duplicate":
        pass
    elif scenario in {"nonown_duplicate", "second_nonown_duplicate"}:
        blocker = make_tower(blocker_id, at=at, counts=counts, owner=player_enemy(index),
                             relation=Relation.ENEMY)
        towers = (source, blocker)
    elif scenario in {"cross_kind_quarry", "cross_kind_village",
                      "second_cross_kind_duplicate"}:
        other_type = QUARRY if scenario != "cross_kind_village" else 26
        # The Village rival is non-own, so the owned Village resource remains
        # exactly one in both snapshots. Cross-kind own Quarry rivals are also
        # covered; identity must consider this non-own Village before filters.
        extra = ({"owner": player_enemy(index), "relation": Relation.ENEMY}
                 if other_type == 26 else {})
        blocker = make_tower(blocker_id, at=at, counts=counts, source=other_type, **extra)
        towers = (source, blocker)
    elif scenario == "delay_duplicate":
        blocker = make_tower(blocker_id, at=at, counts=counts, delay=2)
        towers = (source, blocker)
    elif scenario == "omitted_fighter_duplicate":
        blocker = _tower_with_hidden_count(source, tower_id=blocker_id, at=at,
                                           unit=1, value=2 + index % 3)
        towers = (source, blocker)
    elif scenario == "omitted_ruler_duplicate":
        hidden = dict(enumerate(counts))
        for unit in range(1, 6):
            hidden[unit] = 0
        hidden[9] = 1
        blocker = make_tower(blocker_id, at=at,
                             counts=tuple(hidden[unit] for unit in range(10)))
        towers = (source, blocker)
    elif scenario in {"omitted_shell_duplicate", "omitted_emp_duplicate",
                      "omitted_nuke_duplicate"}:
        unit, tower_type = {
            "omitted_shell_duplicate": (6, 2),
            "omitted_emp_duplicate": (7, 13),
            "omitted_nuke_duplicate": (8, 24),
        }[scenario]
        special = [0] * 10
        special[0] = counts[0]
        special[unit] = 1
        blocker = make_tower(
            blocker_id, at=at, counts=tuple(special), source=tower_type)
        towers = (source, blocker)
    elif scenario == "unknown_owner_duplicate":
        blocker = make_tower(blocker_id, at=at, counts=counts, owner_fact=unknown())
        towers = (source, blocker)
    elif scenario == "unknown_relation_duplicate":
        blocker = make_tower(blocker_id, at=at, counts=counts, relation_fact=unknown())
        towers = (source, blocker)
    elif scenario == "unknown_type_duplicate":
        blocker = make_tower(blocker_id, at=at, counts=counts, type_fact=unknown())
        towers = (source, blocker)
    elif scenario == "stale_vector_duplicate":
        blocker = make_tower(blocker_id, at=at, counts=counts,
                             units_fact=fact(vector(counts), at=at - 9_001))
        towers = (source, blocker)
    elif scenario == "partial_vector_duplicate":
        partial = Units(tuple((unit, count) for unit, count in enumerate(counts)
                              if unit != 2))
        blocker = make_tower(blocker_id, at=at, counts=counts,
                             units_fact=fact(partial, at=at))
        towers = (source, blocker)
    elif scenario == "malformed_vector_duplicate":
        malformed = list(counts)
        malformed[2] = 256
        blocker = make_tower(blocker_id, at=at, counts=counts,
                             units_fact=fact(vector(tuple(malformed)), at=at))
        towers = (source, blocker)
    elif scenario == "unknown_visibility_duplicate":
        blocker = _unchecked_tower(blocker, visibility=unknown())
        towers = (source, blocker)
    elif scenario == "duplicate_id_duplicate":
        blocker = make_tower(source.id, at=at, counts=counts)
        towers = (source, blocker)
    elif scenario == "same_projection_other_tank":
        changed = list(counts)
        changed[4] = min(7, changed[4] + 1)
        blocker = make_tower(blocker_id, at=at, counts=tuple(changed))
        towers = (source, blocker)
    elif scenario == "same_projection_other_soldier":
        changed = list(counts)
        changed[5] = min(14, changed[5] + 1)
        blocker = make_tower(blocker_id, at=at, counts=tuple(changed))
        towers = (source, blocker)
    elif scenario == "ineligible_lock_duplicate":
        blocker = make_tower(blocker_id, at=at, counts=counts,
                             locks_fact=fact(((QUARRY, True),), at=at))
        towers = (source, blocker)
    elif scenario == "ineligible_prerequisite_duplicate":
        blocker = make_tower(blocker_id, at=at, counts=counts,
                             candidates_fact=fact(((QUARRY, (), False),), at=at))
        towers = (source, blocker)
    else:
        raise AssertionError(f"unhandled registered pair control: {scenario}")

    if scenario == "duplicate_id_duplicate":
        blocked_state = _unchecked_world_with_towers(positive_state, towers)
    else:
        blocked_state = make_world(index, towers, tick=BASE_TICK + index * 8, at=at)
    return blocked_state, dom


def player_enemy(index):
    return 1 + ((PLAYER + 17 + index) % 65_534)


def _assert_pair_control(index, scenario):
    assert len(PAIR_SCENARIOS) >= 33
    unit_projection = ((0, 4, 5), (0,), (0, 4), (0, 5))[index % 4]
    if scenario == "omitted_ruler_duplicate":
        unit_projection = (0,)
    elif scenario == "same_projection_other_tank":
        unit_projection = (0, 5)
    elif scenario == "same_projection_other_soldier":
        unit_projection = (0, 4)
    elif scenario in {"omitted_shell_duplicate", "omitted_emp_duplicate",
                      "omitted_nuke_duplicate"}:
        unit_projection = (0,)
    morale = index % 3 == 1
    capacity_known = index % 4 != 2
    positive, dom, source, counts, at = fixture(
        index, unit_ids=unit_projection, morale=morale,
        capacity_known=capacity_known)

    accepted = certify_count_inventory_panel(positive, dom, source.id)
    assert accepted["eligible"] is True
    assert accepted["tower_id"] == source.id
    assert set(accepted["signature_match_ids"]) == {source.id}
    assert _candidate_row(positive, source.id)["eligible"] is True

    # Denominators remain syntactically parsed but cannot change identity.
    changed_denominators = _set_denominators(dom, 73)
    denominator_result = certify_count_inventory_panel(
        positive, changed_denominators, source.id)
    assert denominator_result["eligible"] is True
    assert denominator_result["tower_id"] == source.id

    blocked_state, blocked_dom = _counterfactual(
        index, scenario, positive, dom, source, counts, at)
    refused = certify_count_inventory_panel(blocked_state, blocked_dom, source.id)
    assert refused["eligible"] is False
    if scenario in {"omitted_shell_duplicate", "omitted_emp_duplicate",
                    "omitted_nuke_duplicate"}:
        special_unit, special_type = {
            "omitted_shell_duplicate": (6, 2),
            "omitted_emp_duplicate": (7, 13),
            "omitted_nuke_duplicate": (8, 24),
        }[scenario]
        rival = next(tower for tower in blocked_state.towers
                     if tower.id == source.id + 6_000_001)
        expected = [0] * 10
        expected[0] = counts[0]
        expected[special_unit] = 1
        assert rival.tower_type.value == special_type
        assert tuple(value for _unit, value in rival.units.value.counts) == tuple(expected)
        assert [row["title"] for row in blocked_dom["panels"][0]["unit_rows"]] == ["Shield"]

    if scenario in {
        "same_source_duplicate", "nonown_duplicate", "cross_kind_quarry",
        "cross_kind_village", "delay_duplicate", "omitted_fighter_duplicate",
        "omitted_ruler_duplicate", "same_projection_other_tank",
        "same_projection_other_soldier", "unknown_owner_duplicate",
        "unknown_relation_duplicate", "unknown_type_duplicate",
        "second_nonown_duplicate", "second_cross_kind_duplicate",
        "ineligible_lock_duplicate", "ineligible_prerequisite_duplicate",
        "omitted_shell_duplicate", "omitted_emp_duplicate",
        "omitted_nuke_duplicate",
    }:
        assert set(refused["signature_match_ids"]) == {
            source.id, source.id + 6_000_001,
        }
        assert refused["tower_id"] is None


@pytest.mark.parametrize("index,scenario", tuple(enumerate(PAIR_SCENARIOS)),
                         ids=lambda value: f"diag-pair-{value}")
def test_diagnostic_thirty_three_explicit_count_pairs(index, scenario):
    _assert_pair_control(index, scenario)


@pytest.mark.parametrize("offset,scenario", tuple(enumerate(PAIR_SCENARIOS)),
                         ids=lambda value: f"confirmation-pair-{value}")
def test_frozen_confirmation_thirty_three_fresh_pairs(offset, scenario):
    assert len(PAIR_SCENARIOS) >= 33
    _assert_pair_control(200 + offset, scenario)


def _assert_morale_capacity(index):
    current, dom, source, counts, _at = fixture(
        index, unit_ids=(0, 4), morale=True, capacity_known=False)
    capacity_fact = source.capacity
    capacity_value = source.capacity.value
    morale_fact = source.effects
    morale_value = source.effects.value
    candidate_rows_before = count_candidate_rows(current)
    result = certify_count_inventory_panel(current, dom, source.id)
    assert result["eligible"] is True and result["tower_id"] == source.id
    row = next(row for row in candidate_rows_before
               if row.get("tower_id") == source.id and
               row.get("target_type") == QUARRY)
    assert row["eligible"] is True
    assert row["shield_before"] is None and row["shield_after"] is None
    assert row["shield_before_max_with_overflow"] is None
    assert row["shield_after_max_with_overflow"] is None
    assert row["shield_loss_at_current_inventory"] is None
    assert row["public_clamp_source_raw_capacity"] == 30
    assert row["public_clamp_target_raw_capacity"] == 10
    assert row["public_clamp_source_with_overflow"] == 45
    assert row["public_clamp_target_with_overflow"] == 25
    assert row["public_clamp_shield_loss_upper_bound"] == max(0, counts[0] - 25)
    assert row["public_clamp_provenance"] == (
        "pinned public raw TowerType capacity plus fixed overflow rule; "
        "conservative clamp only, not an observed current UI capacity"
    )
    assert source.capacity is capacity_fact
    assert source.capacity == capacity_fact
    assert source.capacity.value is capacity_value
    assert source.capacity.value == capacity_value
    assert source.effects is morale_fact
    assert source.effects == morale_fact
    assert source.effects.value is morale_value
    assert source.effects.value == morale_value

    # Existing default mode remains a separate, conservative compatibility path.
    legacy_rows = [
        {"title": "Shield", "text": f"{counts[0]}/30"},
        {"title": "Tank", "text": f"{counts[4]}/2"},
        {"title": "Soldier", "text": f"{counts[5]}/4"},
    ]
    assert legacy_certificate(
        current, panel_dom(counts, rows=legacy_rows), source.id)["eligible"] is False


def test_diagnostic_morale_true_and_unknown_observer_capacity_are_positive():
    _assert_morale_capacity(31)


def test_frozen_confirmation_morale_capacity_uses_fresh_fixture():
    _assert_morale_capacity(240)


def test_partial_count_projection_can_still_be_unique_when_other_visible_tower_differs_on_a_shown_count():
    current, dom, source, counts, at = fixture(32, unit_ids=(0,))
    other_counts = list(counts)
    other_counts[0] -= 1
    other = make_tower(source.id + 4_000_003, at=at,
                       counts=tuple(other_counts))
    world = make_world(32, (source, other), at=at,
                       tick=BASE_TICK + 32 * 8)
    result = certify_count_inventory_panel(world, dom, source.id)
    assert result["eligible"] is True and result["tower_id"] == source.id
    assert set(result["signature_match_ids"]) == {source.id}

    # When the other visible vector agrees on the explicit Shield numerator,
    # its omitted Tank/Soldier counts cannot be used to resolve the tie.
    other_counts[0] = counts[0]
    ambiguous = make_tower(source.id + 4_000_003, at=at,
                           counts=tuple(other_counts))
    tied_world = make_world(32, (source, ambiguous), at=at,
                            tick=BASE_TICK + 32 * 8)
    tied = certify_count_inventory_panel(tied_world, dom, source.id)
    assert tied["eligible"] is False and tied["tower_id"] is None
    assert set(tied["signature_match_ids"]) == {source.id, ambiguous.id}


def test_omitted_nonzero_rows_do_not_imply_zero_but_hidden_ruler_difference_blocks_uniqueness():
    current, dom, source, counts, at = fixture(33, unit_ids=(0,))
    result = certify_count_inventory_panel(current, dom, source.id)
    assert result["eligible"] is True
    assert counts[4] > 0 and counts[5] > 0

    ruler_counts = list(counts)
    for unit in range(1, 6):
        ruler_counts[unit] = 0
    ruler_counts[9] = 1
    other = make_tower(source.id + 4_000_019, at=at,
                       counts=tuple(ruler_counts))
    ambiguous = make_world(33, (source, other), at=at,
                           tick=BASE_TICK + 33 * 8)
    refused = certify_count_inventory_panel(ambiguous, dom, source.id)
    assert refused["eligible"] is False
    assert set(refused["signature_match_ids"]) == {source.id, other.id}


def test_local_ruler_positive_on_the_unique_source_keeps_identity_but_fails_action_gate():
    current, dom, source, counts, at = fixture(34, unit_ids=(0,))
    ruler_counts = list(counts)
    for unit in range(1, 6):
        ruler_counts[unit] = 0
    ruler_counts[9] = 1
    ruler_source = make_tower(source.id, at=at, counts=tuple(ruler_counts))
    ruler_world = make_world(34, (ruler_source,), at=at,
                             tick=BASE_TICK + 34 * 8)
    ruler_dom = panel_dom(tuple(ruler_counts), (0, 9), salt=34)
    refused = certify_count_inventory_panel(ruler_world, ruler_dom, ruler_source.id)
    assert refused["eligible"] is False
    assert refused["tower_id"] == ruler_source.id
    assert set(refused["signature_match_ids"]) == {ruler_source.id}


def test_shield_loss_boundary_uses_named_conservative_bound_and_keeps_legacy_capacity_unknown():
    at = BASE_AT + 35 * 307
    counts = (45, 0, 0, 0, 7, 14, 0, 0, 0, 0)
    source = make_tower(BASE_ID + 35 * 37, at=at, counts=counts,
                        morale=True, capacity_fact=unknown())
    current = make_world(35, (source,), at=at, tick=BASE_TICK + 35 * 8)
    dom = panel_dom(counts, (0, 4, 5), salt=35)
    result = certify_count_inventory_panel(current, dom, source.id)
    assert result["eligible"] is True
    row = _candidate_row(current, source.id)
    assert row["public_clamp_shield_loss_upper_bound"] == 20
    assert row["shield_before"] is None and row["shield_after"] is None


@pytest.mark.parametrize("bad_unit,amount", [
    (0, 46), (1, 5), (2, 3), (3, 3), (4, 8), (5, 15),
    (6, 1), (7, 1), (8, 1), (9, 1),
])
def test_full_vector_source_limits_special_units_and_ruler_refuse_actionability(bad_unit, amount):
    index = 40 + bad_unit
    at = BASE_AT + index * 307
    counts = ((42, 0, 0, 0, 0, 0, 0, 0, 0, 0) if bad_unit >= 6 else
              (42, 0, 0, 0, 4, 7, 0, 0, 0, 0))
    changed = list(counts)
    changed[bad_unit] = amount
    changed = tuple(changed)
    tower = make_tower(BASE_ID + index * 37, at=at, counts=changed)
    world = make_world(index, (tower,), at=at, tick=BASE_TICK + index * 8)
    visible_rows = tuple(unit for unit, count in enumerate(changed) if count > 0)
    dom = panel_dom(changed, visible_rows, salt=index)
    result = certify_count_inventory_panel(world, dom, tower.id)
    assert result["eligible"] is False
    assert result["tower_id"] == tower.id
    assert set(result["signature_match_ids"]) == {tower.id}


ACTION_GUARD_CASES = (
    "target_prerequisite_missing", "target_prerequisite_counts_wrong",
    "target_lock_true", "target_lock_unknown", "target_lock_row_missing",
    "wrong_source_type", "wrong_owner", "wrong_relation", "source_delay",
    "wrong_heading", "wrong_title", "disabled_button", "pointer_events_false",
    "zero_button_bounds", "visible_lock_glyph", "hidden_lock_marker",
    "empty_panel", "duplicate_panel", "dom_error",
)


@pytest.mark.parametrize("offset,bad_change", tuple(enumerate(ACTION_GUARD_CASES)))
def test_unique_count_match_still_requires_every_bounded_action_guard(offset, bad_change):
    index = 60 + offset
    at = BASE_AT + index * 307
    counts = (43, 0, 0, 0, 5, 9, 0, 0, 0, 0)
    base = make_tower(BASE_ID + index * 37, at=at, counts=counts)
    current = make_world(index, (base,), at=at, tick=BASE_TICK + index * 8)
    dom = panel_dom(counts, (0, 4, 5), salt=index)
    tower_changes = {}
    world_changes = {}
    changed_dom = dom
    if bad_change == "target_prerequisite_missing":
        tower_changes["candidates_fact"] = fact((), at=at)
    elif bad_change == "target_prerequisite_counts_wrong":
        tower_changes["candidates_fact"] = fact(((QUARRY, (), True),), at=at)
    elif bad_change == "target_lock_true":
        tower_changes["locks_fact"] = fact(((QUARRY, True),), at=at)
    elif bad_change == "target_lock_unknown":
        tower_changes["locks_fact"] = unknown()
    elif bad_change == "target_lock_row_missing":
        tower_changes["locks_fact"] = fact((), at=at)
    elif bad_change == "wrong_source_type":
        tower_changes["source"] = QUARRY
    elif bad_change == "wrong_owner":
        tower_changes["owner"] = PLAYER + 3
        tower_changes["relation"] = Relation.ENEMY
    elif bad_change == "wrong_relation":
        tower_changes["relation_fact"] = fact(Relation.ALLY, at=at)
    elif bad_change == "source_delay":
        tower_changes["delay"] = 1
    elif bad_change == "wrong_heading":
        changed_dom = panel_dom(counts, (0, 4, 5), salt=index, heading="Quarry")
    elif bad_change == "wrong_title":
        button = dict(dom["panels"][0]["buttons"][0])
        button["title"] = "Upgrade to Rampart"
        changed_dom = panel_dom(counts, (0, 4, 5), salt=index, buttons=[button])
    elif bad_change == "disabled_button":
        button = dict(dom["panels"][0]["buttons"][0])
        button["enabled"] = False
        changed_dom = panel_dom(counts, (0, 4, 5), salt=index, buttons=[button])
    elif bad_change == "pointer_events_false":
        button = dict(dom["panels"][0]["buttons"][0])
        button["pointer_events"] = False
        changed_dom = panel_dom(counts, (0, 4, 5), salt=index, buttons=[button])
    elif bad_change == "zero_button_bounds":
        button = dict(dom["panels"][0]["buttons"][0])
        button["bbox"] = [31, 47, 0, 29]
        changed_dom = panel_dom(counts, (0, 4, 5), salt=index, buttons=[button])
    elif bad_change == "visible_lock_glyph":
        button = dict(dom["panels"][0]["buttons"][0])
        button["locked_glyph"] = True
        changed_dom = panel_dom(counts, (0, 4, 5), salt=index, buttons=[button])
    elif bad_change == "hidden_lock_marker":
        button = dict(dom["panels"][0]["buttons"][0])
        button["hidden_lock_icon"] = True
        changed_dom = panel_dom(counts, (0, 4, 5), salt=index, buttons=[button])
    elif bad_change == "empty_panel":
        changed_dom = panel_dom(counts, panels=[])
    elif bad_change == "duplicate_panel":
        one = dict(dom["panels"][0])
        changed_dom = panel_dom(counts, panels=[one, dict(one)])
    elif bad_change == "dom_error":
        changed_dom = panel_dom(counts, errors=("snapshot",))
    if tower_changes:
        base = make_tower(base.id, at=at, counts=counts,
                          **tower_changes)
        current = make_world(index, (base,), at=at,
                             tick=BASE_TICK + index * 8,
                             **world_changes)
    elif world_changes:
        current = make_world(index, (base,), at=at,
                             tick=BASE_TICK + index * 8,
                             **world_changes)

    result = certify_count_inventory_panel(current, changed_dom, base.id)
    assert result["eligible"] is False


@pytest.mark.parametrize("offset,fact_name", tuple(enumerate(
    ("owner", "relation", "tower_type", "visibility"))))
def test_unknown_identity_facts_on_selected_current_tower_refuse(offset, fact_name):
    current, dom, source, _counts, _at = fixture(90 + offset)
    changes = {"owner": source.owner, "relation": source.relation,
               "tower_type": source.tower_type, "visibility": source.visibility}
    changes[{"owner": "owner", "relation": "relation",
             "tower_type": "tower_type", "visibility": "visibility"}[fact_name]] = unknown()
    malformed = _unchecked_tower(source, **changes)
    broken = _unchecked_world_with_towers(current, (malformed,))
    result = certify_count_inventory_panel(broken, dom, source.id)
    assert result["eligible"] is False


@pytest.mark.parametrize("offset,fact_name", tuple(enumerate(
    ("owner", "relation", "tower_type", "visibility"))))
def test_stale_identity_facts_on_a_potential_current_tower_refuse(offset, fact_name):
    current, dom, source, _counts, at = fixture(95 + offset)
    field_name = {"owner": "owner", "relation": "relation",
                  "tower_type": "tower_type", "visibility": "visibility"}[fact_name]
    original = getattr(source, field_name)
    stale = Fact(original.value, Knowledge.OBSERVED,
                 "stale Goal-017 identity control", at - 9_003)
    malformed = _unchecked_tower(source, **{field_name: stale})
    broken = _unchecked_world_with_towers(current, (malformed,))
    assert certify_count_inventory_panel(broken, dom, source.id)["eligible"] is False


BAD_VECTOR_CASES = ("unknown", "partial", "stale", "out_of_order", "over_255")


@pytest.mark.parametrize("offset,bad_vector", tuple(enumerate(BAD_VECTOR_CASES)))
def test_selected_tower_requires_a_fresh_well_formed_complete_ten_slot_vector(offset, bad_vector):
    current, dom, source, counts, at = fixture(100 + offset)
    if bad_vector == "unknown":
        units_fact = unknown()
    elif bad_vector == "partial":
        units_fact = fact(Units(tuple((i, n) for i, n in enumerate(counts) if i != 8)), at=at)
    elif bad_vector == "stale":
        units_fact = fact(vector(counts), at=at - 9_002)
    elif bad_vector == "out_of_order":
        units_fact = fact(Units(tuple(reversed(tuple(enumerate(counts))))), at=at)
    else:
        malformed = list(counts)
        malformed[3] = 256
        units_fact = fact(vector(tuple(malformed)), at=at)
    broken_tower = make_tower(source.id, at=at, counts=counts,
                              units_fact=units_fact)
    broken = make_world(100 + offset, (broken_tower,), at=at,
                        tick=BASE_TICK + (100 + offset) * 8)
    assert certify_count_inventory_panel(broken, dom, source.id)["eligible"] is False


BAD_OWNER_CASES = ("bool_player", "zero_player", "bool_owner", "zero_owner")


@pytest.mark.parametrize("offset,bad_identity", tuple(enumerate(BAD_OWNER_CASES)))
def test_positive_ownership_requires_exact_nonboolean_player_ids_in_range(offset, bad_identity):
    index = 120 + offset
    at = BASE_AT + index * 307
    counts = (41, 0, 0, 0, 4, 6, 0, 0, 0, 0)
    if bad_identity in {"bool_player", "bool_owner"}:
        player = 1
        owner = 1
    else:
        player = 0
        owner = 0
    base = make_tower(BASE_ID + index * 37, at=at, counts=counts,
                      owner=owner)
    if bad_identity == "bool_owner":
        base = _unchecked_tower(base, owner=fact(True, at=at))
    player_fact = fact(True, at=at) if bad_identity == "bool_player" else fact(player, at=at)
    current = make_world(index, (base,), player=player, at=at,
                         tick=BASE_TICK + index * 8, player_fact=player_fact)
    dom = panel_dom(counts, (0, 4, 5), salt=index)
    assert certify_count_inventory_panel(current, dom, base.id)["eligible"] is False


STATE_IDENTITY_CASES = (
    "unknown_tick", "stale_world_tick", "unknown_lifecycle", "offline_source",
    "unknown_player", "partial_coverage", "unknown_coverage_evidence",
)


@pytest.mark.parametrize("offset,state_change", tuple(enumerate(STATE_IDENTITY_CASES)))
def test_current_epoch_version_tick_and_coverage_are_fail_closed(offset, state_change):
    index = 140 + offset
    at = BASE_AT + index * 307
    counts = (44, 0, 0, 0, 6, 12, 0, 0, 0, 0)
    source = make_tower(BASE_ID + index * 37, at=at, counts=counts)
    args = {}
    if state_change == "unknown_tick":
        args["tick_fact"] = unknown()
    elif state_change == "stale_world_tick":
        args["tick_observed_at"] = at - 60_001
    elif state_change == "unknown_lifecycle":
        args["lifecycle_fact"] = unknown()
    elif state_change == "offline_source":
        args["source_mode"] = "OFFLINE"
    elif state_change == "unknown_player":
        args["player_fact"] = unknown()
    elif state_change == "partial_coverage":
        args["coverage"] = "PARTIAL"
    current = make_world(index, (source,), at=at,
                         tick=BASE_TICK + index * 8, **args)
    if state_change == "unknown_coverage_evidence":
        current = _unchecked_world_with_towers(current, (source,))
        object.__setattr__(current, "coverage_evidence", unknown())
    dom = panel_dom(counts, (0, 4, 5), salt=index)
    assert certify_count_inventory_panel(current, dom, source.id)["eligible"] is False


def test_duplicate_tower_ids_refuse_even_when_count_signature_is_single_after_id_collapse():
    current, dom, source, counts, at = fixture(155, unit_ids=(0, 4))
    duplicated = make_tower(source.id, at=at, counts=counts)
    malformed = _unchecked_world_with_towers(current, (source, duplicated))
    result = certify_count_inventory_panel(malformed, dom, source.id)
    assert result["eligible"] is False


def test_capacity_denominator_is_syntax_only_even_when_it_disagrees_with_every_static_capacity_table():
    current, dom, source, counts, _at = fixture(156, unit_ids=(0, 4, 5), morale=True,
                                                capacity_known=False)
    intentionally_uninterpreted = panel_dom(
        counts, (0, 4, 5), salt=156,
        rows=[{"title": "Shield", "text": f"{counts[0]}/1"},
              {"title": "Tank", "text": f"{counts[4]}/0"},
              {"title": "Soldier", "text": f"{counts[5]}/255"}],
    )
    result = certify_count_inventory_panel(
        current, intentionally_uninterpreted, source.id)
    assert result["eligible"] is True and result["tower_id"] == source.id


def test_malformed_or_untyped_panel_rows_never_create_a_count_signature():
    current, dom, source, _counts, _at = fixture(157)
    invalid_rows = (
        [{"title": "Mystery", "text": "41/30"}],
        [{"title": "Shield", "text": "-1/30"}],
        [{"title": "Shield", "text": "256/30"}],
        [{"title": "Shield", "text": "41/256"}],
        [{"title": "Shield", "text": "41/30"},
         {"title": "Shield", "text": "41/40"}],
        [None],
    )
    for rows in invalid_rows:
        result = certify_count_inventory_panel(
            current, panel_dom(_counts, rows=rows), source.id)
        assert result["eligible"] is False


def test_requested_tower_must_be_the_unique_explicit_count_match():
    current, dom, source, counts, at = fixture(158, unit_ids=(0,))
    other_counts = list(counts)
    other_counts[0] -= 1
    other = make_tower(source.id + 4_000_041, at=at,
                       counts=tuple(other_counts))
    world = make_world(158, (source, other), at=at,
                       tick=BASE_TICK + 158 * 8)
    mismatched_request = certify_count_inventory_panel(world, dom, other.id)
    assert mismatched_request["eligible"] is False
    assert mismatched_request["tower_id"] == source.id


def test_known_false_target_lock_is_sufficient_without_global_unlocked_list():
    current, dom, source, _counts, at = fixture(159)
    world = make_world(159, (source,), at=at,
                       tick=BASE_TICK + 159 * 8, unlocked_fact=unknown())
    result = certify_count_inventory_panel(world, dom, source.id)
    assert result["eligible"] is True and result["tower_id"] == source.id


def test_probe_cli_routes_default_legacy_and_count_mode_without_starting_a_browser(monkeypatch, capsys):
    from tools import (v2_goal_count_inventory_upgrade as count_protocol,
                       v2_goal_inventory_upgrade as legacy_protocol,
                       v2_goal_upgrade_probe as probe)

    calls = []

    async def fake_run_probe(args, protocol=None):
        calls.append((args, protocol))
        return {"status": "READ_ONLY"}

    monkeypatch.setattr(probe, "run_probe", fake_run_probe)
    assert probe.main([]) == 0
    assert calls[-1][1] is None
    assert probe.main(["--inventory-cliff-quarry"]) == 0
    assert calls[-1][1] is legacy_protocol
    assert probe.main(["--count-inventory-cliff-quarry"]) == 0
    assert calls[-1][1] is count_protocol
    assert len(calls) == 3

    with pytest.raises(SystemExit) as error:
        probe.main(["--inventory-cliff-quarry", "--count-inventory-cliff-quarry"])
    assert error.value.code == 2
    assert len(calls) == 3
    capsys.readouterr()
