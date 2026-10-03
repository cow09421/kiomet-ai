"""Independent synthetic controls for normal inventory-based source binding.

These tests are local and deterministic. They exercise only the frozen Cliff
to Quarry certificate boundary, never replay or official-session outcomes.
"""
from dataclasses import replace
import asyncio
import time

import pytest
from playwright.async_api import async_playwright

from kiomet_ai.v2.observe import rules
from kiomet_ai.v2.state import Fact, GameState, Knowledge, Lifecycle, Relation, Tower, Units
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256
from tools.v2_goal_inventory_upgrade import bounded_candidate_rows, certify_inventory_panel
from tools.v2_goal_upgrade_probe import verify_upgrade
from tools.v2_goal_upgrade_probe import _inventory_selection_click, visible_blue_hints
import tools.v2_goal_inventory_upgrade as protocol


PLAYER = 17
SOURCE = 7
TARGET = 16
TICK = 400
RECEIVED = 50_000
SOURCE_COUNTS = (45, 0, 0, 0, 1, 2, 0, 0, 0, 0)


def known(value, *, at=RECEIVED, knowledge=Knowledge.OBSERVED):
    return Fact(value, knowledge, "frozen synthetic public-state control", at)


def unknown():
    return Fact()


def typed_units(counts=SOURCE_COUNTS):
    assert len(counts) == 10
    return Units(tuple(enumerate(counts)))


def tower(tower_id=100, *, source=SOURCE, owner=PLAYER,
          relation=Relation.SELF, visibility=True, counts=SOURCE_COUNTS,
          delay=0, morale=False, at=RECEIVED, owner_fact=None,
          type_fact=None, units_fact=None, capacity_fact=None,
          delay_fact=None, candidates_fact=None, locks_fact=None,
          effects_fact=None, production_fact=None):
    """A canonical own Cliff, with complete typed zeros and coherent facts."""
    vector = typed_units(counts)
    candidates = ((TARGET, ((26, 1, 1),), True),)
    locks = ((TARGET, False),)
    effects = (("MORALE_BOOST", morale),)
    return Tower(
        tower_id,
        visibility=known(visibility, at=at),
        owner=owner_fact if owner_fact is not None else known(owner, at=at),
        relation=known(relation, at=at),
        tower_type=type_fact if type_fact is not None else known(source, at=at),
        units=units_fact if units_fact is not None else known(vector, at=at),
        capacity=capacity_fact if capacity_fact is not None else known(rules.capacity(source, morale), at=at),
        production=production_fact if production_fact is not None else known(
            rules.production(source, vector, owner, delay, morale), at=at),
        delay_ticks=delay_fact if delay_fact is not None else known(delay, at=at),
        upgrade_candidates=candidates_fact if candidates_fact is not None else known(candidates, at=at),
        upgrade_locks=locks_fact if locks_fact is not None else known(locks, at=at),
        effects=effects_fact if effects_fact is not None else known(effects, at=at),
        position=known((tower_id, 3), at=at),
    )


def state(*, towers=None, coverage="PLAYER_VISIBLE_COMPLETE", tick=TICK,
          at=RECEIVED, coverage_evidence=None, resources=None):
    if towers is None:
        towers = (tower(at=at),)
    if resources is None:
        values = [0] * 27
        values[26] = 1
        resources = tuple(enumerate(values))
    if coverage_evidence is None:
        coverage_evidence = (("positive_refs", len(towers)),
                             ("tower_count", len(towers)),
                             ("visible_pending", coverage != "PLAYER_VISIBLE_COMPLETE"))
    return GameState(
        session_id="synthetic-session", document_id="synthetic-document",
        match_id=known("synthetic-match", at=at), sequence=tick + 1,
        sampled_at_ms=at, received_at_ms=at, client_sha256=CLIENT_SHA256,
        tick=known(tick, at=at), lifecycle=known(Lifecycle.IN_MATCH, at=at),
        player_id=known(PLAYER, at=at), source_mode=known("NETWORK", at=at),
        coverage=coverage,
        coverage_evidence=known(coverage_evidence, at=at),
        upgrade_resources=known(resources, at=at),
        world_sequence_observed_at_ms=known(at, at=at),
        towers=tuple(towers),
    )


def panel_dom(*, heading="Cliff", unit_rows=None, buttons=None, panels=None,
              global_headings=(), global_buttons=()):
    if unit_rows is None:
        unit_rows = [
            {"title": "Shield", "text": "45/30"},
            {"title": "Tank", "text": "1/2"},
            {"title": "Soldier", "text": "2/4"},
        ]
    if buttons is None:
        buttons = [{
            "title": "Upgrade to Quarry", "visible": True, "enabled": True,
            "pointer_events": True, "locked_glyph": False,
            "hidden_lock_icon": False, "bbox": [10, 20, 100, 40],
        }]
    if panels is None:
        panels = [{"headings": [heading], "unit_rows": unit_rows, "buttons": buttons}]
    return {"panels": panels, "headings": list(global_headings),
            "buttons": list(global_buttons)}


def candidate(state_, tower_id=100):
    return next((row for row in bounded_candidate_rows(state_)
                 if row.get("tower_id") == tower_id and row.get("target_type") == TARGET), None)


def observation(tick, *, tower_id=100, source=SOURCE, delay=0, counts=SOURCE_COUNTS,
                at=None, **tower_changes):
    sampled = RECEIVED + tick - TICK if at is None else at
    source_tower = tower(tower_id, source=source, delay=delay, counts=counts,
                         at=sampled, **tower_changes)
    return state(towers=(source_tower,), tick=tick, at=sampled)


def valid_verified_ui(before):
    certificate = certify_inventory_panel(before, panel_dom(), 100)
    return {
        "click_status": "SUCCESS", "dom_guard_passed": True,
        "selected_tower_id": 100, "target_type": TARGET,
        "source_heading": "Cliff", "upgrade_title": "Upgrade to Quarry",
        "button_visible": True, "button_enabled": True, "pointer_events": True,
        "locked_glyph": False, "hidden_lock_icon": False,
        "public_source_certificate": certificate, "fresh_panel_barrier": True,
    }


def test_unique_complete_own_inventory_certifies_cliff_to_quarry_with_exact_twenty_shield_loss():
    current = state()
    row = candidate(current)
    assert row is not None and row["eligible"] is True
    assert row["source_type"] == SOURCE and row["target_type"] == TARGET
    assert row["shield_before"] == 30 and row["shield_after"] == 10
    assert row["shield_after_max_with_overflow"] == 25
    assert row["shield_loss_at_current_inventory"] == 20
    assert row["nonshield_units_preserved"] is True
    result = certify_inventory_panel(current, panel_dom(), 100)
    assert result["eligible"] is True
    assert result["tower_id"] == 100


def test_inventory_protocol_verifies_target_type_with_coherent_non_unit_tick_countdown():
    before = observation(400)
    after = [observation(402, source=TARGET, delay=79, counts=(25, 0, 0, 0, 1, 2, 0, 0, 0, 0)),
             observation(403, source=TARGET, delay=78, counts=(25, 0, 0, 0, 1, 2, 0, 0, 0, 0))]
    result = verify_upgrade(before, valid_verified_ui(before), after, TARGET,
                            candidate_fn=bounded_candidate_rows)
    assert result["status"] == "SUCCESS"


@pytest.mark.parametrize("after_types", [
    (SOURCE, SOURCE), (SOURCE, TARGET), (17, 17),
])
def test_source_or_wrong_target_type_transition_never_verifies_success(after_types):
    before = observation(400)
    after = [observation(402, source=after_types[0], delay=79),
             observation(403, source=after_types[1], delay=78)]
    result = verify_upgrade(before, valid_verified_ui(before), after, TARGET,
                            candidate_fn=bounded_candidate_rows)
    assert result["status"] != "SUCCESS"


@pytest.mark.parametrize("ui_change", [
    {"public_source_certificate": None},
    {"public_source_certificate": {"eligible": True, "tower_id": 101}},
    {"fresh_panel_barrier": False},
])
def test_missing_mismatched_or_unfresh_source_certificate_cannot_verify(ui_change):
    before = observation(400)
    after = [observation(402, source=TARGET, delay=79),
             observation(403, source=TARGET, delay=78)]
    ui = valid_verified_ui(before) | ui_change
    result = verify_upgrade(before, ui, after, TARGET, candidate_fn=bounded_candidate_rows)
    assert result["status"] == "UNKNOWN"


@pytest.mark.parametrize("bad_before", [
    observation(400, type_fact=known(SOURCE, at=RECEIVED - 5_001)),
    observation(400, units_fact=known(typed_units(), at=RECEIVED - 5_001)),
    observation(400, owner_fact=unknown()),
    observation(400, units_fact=unknown()),
    observation(400, capacity_fact=unknown()),
])
def test_stale_or_unknown_before_facts_cannot_verify_upgrade(bad_before):
    after = [observation(402, source=TARGET, delay=79),
             observation(403, source=TARGET, delay=78)]
    ui = valid_verified_ui(bad_before)
    result = verify_upgrade(bad_before, ui, after, TARGET, candidate_fn=bounded_candidate_rows)
    assert result["status"] == "UNKNOWN"


@pytest.mark.parametrize("bad_after", [
    observation(402, source=TARGET, delay=79,
                type_fact=known(TARGET, at=RECEIVED - 5_001)),
    observation(402, source=TARGET, delay=79, type_fact=unknown()),
    observation(402, source=TARGET, delay=79, delay_fact=unknown()),
])
def test_stale_or_unknown_after_facts_cannot_verify_upgrade(bad_after):
    before = observation(400)
    after = [bad_after, observation(403, source=TARGET, delay=78)]
    result = verify_upgrade(before, valid_verified_ui(before), after, TARGET,
                            candidate_fn=bounded_candidate_rows)
    assert result["status"] == "UNKNOWN"


def test_scoped_panel_ignores_unrelated_global_heading_and_upgrade_title():
    current = state()
    dom = panel_dom(global_headings=("Village",), global_buttons=(
        {"title": "Upgrade to Town", "visible": True, "enabled": True,
         "pointer_events": True, "locked_glyph": False,
         "hidden_lock_icon": False, "bbox": [0, 0, 20, 20]},))
    assert certify_inventory_panel(current, dom, 100)["eligible"] is True


def test_identical_inventory_on_two_positively_owned_cliffs_is_ambiguous():
    current = state(towers=(tower(100), tower(101)))
    assert certify_inventory_panel(current, panel_dom(), 100)["eligible"] is False


def test_unknown_owner_cliff_is_a_potential_duplicate_and_blocks_binding():
    possible_own = tower(101, owner_fact=unknown())
    current = state(towers=(tower(100), possible_own))
    assert certify_inventory_panel(current, panel_dom(), 100)["eligible"] is False


def test_known_enemy_with_same_typed_signature_is_not_a_second_own_candidate():
    enemy = tower(101, owner=23, relation=Relation.ENEMY)
    current = state(towers=(tower(100), enemy))
    assert certify_inventory_panel(current, panel_dom(), 100)["eligible"] is True


@pytest.mark.parametrize("coverage", ["PARTIAL", "PLAYER_VISIBLE_PENDING", "UNKNOWN"])
def test_incomplete_or_pending_player_coverage_never_certifies_unique_identity(coverage):
    assert certify_inventory_panel(state(coverage=coverage), panel_dom(), 100)["eligible"] is False


def test_nonmatching_source_type_heading_refuses_otherwise_matching_inventory():
    assert certify_inventory_panel(state(), panel_dom(heading="Village"), 100)["eligible"] is False


def test_known_typed_count_mismatch_refuses_panel_identity():
    dom = panel_dom(unit_rows=[
        {"title": "Shield", "text": "44/30"},
        {"title": "Tank", "text": "1/2"},
        {"title": "Soldier", "text": "2/4"},
    ])
    assert certify_inventory_panel(state(), dom, 100)["eligible"] is False


def test_capacity_denominator_mismatch_refuses_panel_identity():
    dom = panel_dom(unit_rows=[
        {"title": "Shield", "text": "45/29"},
        {"title": "Tank", "text": "1/2"},
        {"title": "Soldier", "text": "2/4"},
    ])
    assert certify_inventory_panel(state(), dom, 100)["eligible"] is False


def test_missing_expected_nonzero_unit_row_refuses_panel_identity():
    dom = panel_dom(unit_rows=[
        {"title": "Shield", "text": "30/30"},
        {"title": "Tank", "text": "1/2"},
    ])
    assert certify_inventory_panel(state(), dom, 100)["eligible"] is False


def test_unrecognized_extra_unit_row_refuses_panel_identity():
    rows = panel_dom()["panels"][0]["unit_rows"] + [{"title": "Mystery", "text": "1/1"}]
    assert certify_inventory_panel(state(), panel_dom(unit_rows=rows), 100)["eligible"] is False


def test_duplicate_typed_unit_rows_refuse_panel_identity():
    rows = panel_dom()["panels"][0]["unit_rows"] + [{"title": "Soldier", "text": "2/4"}]
    assert certify_inventory_panel(state(), panel_dom(unit_rows=rows), 100)["eligible"] is False


def test_unknown_owner_on_selected_source_is_not_treated_as_own():
    current = state(towers=(tower(100, owner_fact=unknown()),))
    assert certify_inventory_panel(current, panel_dom(), 100)["eligible"] is False


def test_stale_typed_inventory_is_not_matched_to_current_panel():
    stale = tower(units_fact=known(typed_units(), at=RECEIVED - 5_001))
    current = state(towers=(stale,))
    assert certify_inventory_panel(current, panel_dom(), 100)["eligible"] is False


def test_unknown_unit_slot_prevents_absence_from_becoming_a_zero_row():
    partial = Units(tuple((i, n) for i, n in enumerate(SOURCE_COUNTS) if i != 5))
    incomplete = tower(units_fact=known(partial))
    assert certify_inventory_panel(state(towers=(incomplete,)), panel_dom(), 100)["eligible"] is False


def test_unknown_capacity_vector_cannot_be_replaced_by_a_public_default():
    incomplete = tower(capacity_fact=unknown())
    current = state(towers=(incomplete,))
    row = candidate(current)
    assert (row is None or row["eligible"] is False
            or certify_inventory_panel(current, panel_dom(), 100)["eligible"] is False)


def test_unknown_morale_or_nonzero_delay_cannot_be_assumed_ordinary():
    unknown_morale = tower(effects_fact=unknown())
    delayed = tower(delay=1)
    for sample in (state(towers=(unknown_morale,)), state(towers=(delayed,))):
        row = candidate(sample)
        assert (row is None or row["eligible"] is False
                or certify_inventory_panel(sample, panel_dom(), 100)["eligible"] is False)


def test_known_locked_quarry_target_is_not_actionable():
    locked = tower(locks_fact=known(((TARGET, True),)))
    current = state(towers=(locked,))
    row = candidate(current)
    assert (row is None or row["eligible"] is False
            or certify_inventory_panel(current, panel_dom(), 100)["eligible"] is False)


def test_nonzero_ruler_is_refused_even_if_the_panel_signature_matches():
    counts = list(SOURCE_COUNTS)
    counts[9] = 1
    current = state(towers=(tower(counts=tuple(counts)),))
    row = candidate(current)
    assert (row is None or row["eligible"] is False
            or certify_inventory_panel(current, panel_dom(), 100)["eligible"] is False)


def test_unknown_ruler_slot_does_not_certify_nonruler_premise():
    partial = Units(tuple((i, n) for i, n in enumerate(SOURCE_COUNTS) if i != 9))
    current = state(towers=(tower(units_fact=known(partial)),))
    row = candidate(current)
    assert (row is None or row["eligible"] is False
            or certify_inventory_panel(current, panel_dom(), 100)["eligible"] is False)


def test_known_inventory_above_cliff_capacity_is_refused():
    counts = list(SOURCE_COUNTS)
    counts[0] = 46
    current = state(towers=(tower(counts=tuple(counts)),))
    row = candidate(current)
    assert (row is None or row["eligible"] is False
            or certify_inventory_panel(current, panel_dom(), 100)["eligible"] is False)


def test_shell_or_other_zero_capacity_special_inventory_is_refused():
    counts = list(SOURCE_COUNTS)
    counts[6] = 1
    current = state(towers=(tower(counts=tuple(counts)),))
    row = candidate(current)
    assert (row is None or row["eligible"] is False
            or certify_inventory_panel(current, panel_dom(), 100)["eligible"] is False)


@pytest.mark.parametrize("change", [
    {"enabled": False}, {"pointer_events": False},
    {"locked_glyph": True}, {"hidden_lock_icon": True},
])
def test_disabled_or_locked_target_button_cannot_certify(change):
    button = panel_dom()["panels"][0]["buttons"][0] | change
    assert certify_inventory_panel(state(), panel_dom(buttons=[button]), 100)["eligible"] is False


def test_wrong_upgrade_target_title_cannot_certify_cliff_quarry():
    button = panel_dom()["panels"][0]["buttons"][0] | {"title": "Upgrade to Rampart"}
    assert certify_inventory_panel(state(), panel_dom(buttons=[button]), 100)["eligible"] is False


def test_two_matching_scoped_panels_are_not_resolved_by_dom_order():
    one = panel_dom()["panels"][0]
    assert certify_inventory_panel(state(), panel_dom(panels=[one, one]), 100)["eligible"] is False


def test_offscreen_source_remains_matchable_from_complete_current_visible_inventory():
    offscreen = replace(tower(), position=known((100_000, -100_000)))
    current = state(towers=(offscreen,))
    assert certify_inventory_panel(current, panel_dom(), 100)["eligible"] is True


def test_actual_blank_local_dom_scopes_nested_inventory_rows_and_target_to_one_opaque_panel():
    async def exercise():
        html = """<!doctype html><html><head><style>
          body{margin:0;background:white}
          .q7a2{position:absolute;left:20px;top:20px;width:220px;height:180px}
          .n4p1{display:block;width:200px;height:170px;color:#111}
          .c8v3{cursor:pointer;width:120px;height:24px}
          .p2x6{height:3px;width:30px;background:#888}
        </style></head><body>
          <h2>Village</h2><p title="Shield">1/10</p>
          <button title="Upgrade to Town">unrelated</button>
          <div class="q7a2"><div class="n4p1">
            <h2>Cliff</h2>
            <p title="Shield">45/30</p>
            <p title="Tank">1/2</p>
            <p title="Soldier">2/4</p>
            <div class="c8v3" title="Upgrade to Quarry">
              <span>Quarry</span><div class="p2x6"></div>
            </div>
          </div></div>
        </body></html>"""
        manager = await async_playwright().start()
        browser = await manager.chromium.launch(
            executable_path=manager.chromium.executable_path,
            headless=True, args=["--mute-audio"])
        try:
            page = await browser.new_page()
            await page.set_content(html)
            dom = await protocol.async_dom_snapshot(page)
            assert dom.get("errors", []) == []
            assert len(dom["panels"]) == 1
            assert dom["panels"][0]["headings"] == ["Cliff"]
            assert dom["panels"][0]["unit_rows"] == [
                {"title": "Shield", "text": "45/30"},
                {"title": "Tank", "text": "1/2"},
                {"title": "Soldier", "text": "2/4"},
            ]
            certified = certify_inventory_panel(state(), dom, 100)
            assert certified["eligible"] is True
            assert certified["upgrade_title"] == "Upgrade to Quarry"
        finally:
            await browser.close()
            await manager.stop()
    asyncio.run(exercise())


def test_visible_pixel_hints_return_only_bounded_page_coordinates_from_blank_canvas():
    async def exercise():
        manager = await async_playwright().start()
        browser = await manager.chromium.launch(
            executable_path=manager.chromium.executable_path,
            headless=True, args=["--mute-audio"])
        try:
            page = await browser.new_page(viewport={"width": 160, "height": 100})
            await page.set_content("""<style>html,body{margin:0;padding:0}</style>
              <canvas id="board" width="160" height="100"></canvas>
              <script>const c=document.querySelector('#board').getContext('2d');
              c.fillStyle='#ffffff';c.fillRect(0,0,160,100);
              c.fillStyle='#168bff';c.fillRect(38,28,12,12);
              c.fillStyle='#168bff';c.fillRect(112,64,12,12);</script>""")
            png = await page.screenshot(type="png")
            hints = visible_blue_hints(png)
            assert 1 <= len(hints) <= 6
            assert all(type(x) in (int, float) and type(y) in (int, float)
                       and 0 <= x < 160 and 0 <= y < 100 for x, y in hints)
            assert any(abs(x - 43.5) < 2 and abs(y - 33.5) < 2 for x, y in hints)
        finally:
            await browser.close()
            await manager.stop()
    asyncio.run(exercise())


def test_stationary_inventory_selection_requires_absent_panel_and_releases_mouse():
    class Mouse:
        def __init__(self):
            self.events = []

        async def move(self, x, y):
            self.events.append(("move", x, y))

        async def down(self):
            self.events.append(("down",))

        async def up(self):
            self.events.append(("up",))

    class Page:
        def __init__(self, mouse):
            self.mouse = mouse

        async def evaluate(self, _script):
            self.mouse.events.append(("frame",))

    class Protocol:
        def __init__(self, result):
            self.result = result
            self.calls = 0

        async def dom_snapshot(self, _page):
            self.calls += 1
            return self.result

    async def exercise():
        mouse = Mouse()
        page = Page(mouse)
        protocol_result = Protocol({"panels": [], "errors": False})
        fresh = await _inventory_selection_click(page, 43.5, 33.5,
                                                 time.monotonic() + 2, protocol_result)
        assert fresh is True and protocol_result.calls == 1
        assert mouse.events[0] == ("move", 43.5, 33.5)
        assert mouse.events[1] == ("down",)
        assert mouse.events.count(("up",)) == 1

        mouse = Mouse()
        page = Page(mouse)
        still_present = Protocol({"panels": [{"headings": ["Cliff"]}], "errors": False})
        fresh = await _inventory_selection_click(page, 43.5, 33.5,
                                                 time.monotonic() + 2, still_present)
        assert fresh is False
        assert mouse.events.count(("up",)) == 1
    asyncio.run(exercise())


def test_stationary_inventory_selection_releases_mouse_when_panel_snapshot_fails():
    class Mouse:
        def __init__(self):
            self.released = False

        async def move(self, _x, _y):
            return None

        async def down(self):
            return None

        async def up(self):
            self.released = True

    class Page:
        def __init__(self, mouse):
            self.mouse = mouse

        async def evaluate(self, _script):
            return None

    class Protocol:
        async def dom_snapshot(self, _page):
            raise RuntimeError("synthetic local DOM failure")

    async def exercise():
        mouse = Mouse()
        with pytest.raises(RuntimeError, match="synthetic local DOM failure"):
            await _inventory_selection_click(Page(mouse), 5, 5,
                                             time.monotonic() + 2, Protocol())
        assert mouse.released is True
    asyncio.run(exercise())
