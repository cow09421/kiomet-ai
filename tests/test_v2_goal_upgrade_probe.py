from dataclasses import replace
import asyncio
import json
from contextlib import contextmanager
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from kiomet_ai.v2.observe import rules
from kiomet_ai.v2.state import Fact, GameState, Knowledge, Lifecycle, Relation, Tower, Units
from tools.v2_goal_upgrade_probe import candidate_rows, inspect_upgrade_dom, verify_upgrade
import tools.v2_goal_upgrade_probe as probe
from kiomet_ai.v2.observe.extractor import CLIENT_SHA256


NOW = 10_000
PLAYER = 7
TOWER_ID = 42
SOURCE = 0
TARGET = 12
NOMINAL = rules.UPGRADE_DELAY[TARGET]


def fact(value, at=NOW):
    return Fact(value, Knowledge.OBSERVED, "synthetic positive visible fixture", at)


def unknown():
    return Fact()


def units(shield=0, ruler=0):
    return Units(tuple((i, shield if i == 0 else ruler if i == 9 else 0) for i in range(10)))


def make_tower(*, tower_id=TOWER_ID, source=SOURCE, owner=PLAYER,
               relation=Relation.SELF, visibility=True, delay=0,
               candidates=None, locks=None, capacity=None, effects=None,
               at=NOW,
               tower_type_known=True, owner_known=True, relation_known=True,
               visibility_known=True, delay_known=True, candidates_known=True,
               locks_known=True, capacity_known=True, effects_known=True):
    counts = [0] * 27
    counts[1], counts[9] = 2, 3  # target 12 direct prerequisites
    computed_candidates = rules.upgrade_candidates(source, tuple(counts), delay)
    lock_values = ((TARGET, False),)
    tower_capacity = rules.capacity(source, False)
    tower_effects = (("MORALE_BOOST", False),)
    return Tower(
        tower_id,
        visibility=(fact(visibility, at) if visibility_known else unknown()),
        owner=(fact(owner, at) if owner_known else unknown()),
        relation=(fact(relation, at) if relation_known else unknown()),
        tower_type=(fact(source, at) if tower_type_known else unknown()),
        units=fact(units(), at),
        capacity=(fact(capacity if capacity is not None else tower_capacity, at)
                  if capacity_known else unknown()),
        delay_ticks=(fact(delay, at) if delay_known else unknown()),
        upgrade_candidates=(fact(candidates if candidates is not None else computed_candidates, at)
                            if candidates_known else unknown()),
        upgrade_locks=(fact(locks if locks is not None else lock_values, at)
                       if locks_known else unknown()),
        effects=(fact(effects if effects is not None else tower_effects, at)
                 if effects_known else unknown()),
    )


def make_state(*, tower=None, tick=100, coverage="PARTIAL", match="match-a",
               document="document-a", player=PLAYER, lifecycle=Lifecycle.IN_MATCH,
               source_mode="NETWORK", client=CLIENT_SHA256, resources=None):
    own_counts = [0] * 27
    own_counts[1], own_counts[9] = 2, 3
    resource_value = tuple(enumerate(own_counts)) if resources is None else resources
    observed_at = NOW + tick
    if tower is None:
        tower = make_tower(at=observed_at)
    else:
        changes = {}
        for name in ("visibility", "owner", "relation", "tower_type", "units", "capacity",
                     "delay_ticks", "upgrade_candidates", "upgrade_locks", "effects"):
            value = getattr(tower, name)
            if value.knowledge != Knowledge.UNKNOWN:
                changes[name] = replace(value, observed_at_ms=observed_at)
        tower = replace(tower, **changes)
    return GameState(
        session_id="session-a", document_id=document,
        match_id=fact(match, observed_at), sequence=tick + 1, sampled_at_ms=observed_at,
        received_at_ms=observed_at, client_sha256=client,
        tick=fact(tick, observed_at), lifecycle=fact(lifecycle, observed_at),
        player_id=fact(player, observed_at), source_mode=fact(source_mode, observed_at), coverage=coverage,
        upgrade_resources=fact(resource_value, observed_at),
        world_sequence_observed_at_ms=fact(observed_at, observed_at),
        towers=(tower,),
    )


def target_row(state, target=TARGET):
    return next(row for row in candidate_rows(state) if row["target_type"] == target)


def valid_dom():
    return {
        "headings": ["Airfield"],
        "buttons": [{
            "title": "Upgrade to Helipad", "visible": True, "enabled": True,
            "pointer_events": True, "locked_glyph": False,
            "hidden_lock_icon": False, "bbox": [10, 20, 100, 40],
        }],
    }


def valid_ui_result():
    return {
        "click_status": "SUCCESS", "selected_tower_id": TOWER_ID,
        "target_type": TARGET, "source_heading": "Airfield",
        "upgrade_title": "Upgrade to Helipad", "dom_guard_passed": True,
        "button_visible": True, "button_enabled": True, "pointer_events": True,
        "locked_glyph": False, "hidden_lock_icon": False,
    }


def after_state(tick, typ=TARGET, delay=NOMINAL, **kwargs):
    tower = make_tower(source=typ, delay=delay, at=NOW + tick)
    return make_state(tower=tower, tick=tick, **kwargs)


def barracks_state(tick=100):
    source, target = 3, 1
    counts = [0] * 27
    counts[9], counts[14] = 1, 1
    candidates = ((target, ((9, 1, 1), (14, 1, 1)), True),)
    tower = make_tower(source=source, candidates=candidates, locks=((target, False),),
                       capacity=rules.capacity(source, False), at=NOW + tick)
    return make_state(tower=tower, tick=tick, resources=tuple(enumerate(counts)))


def barracks_ui_result():
    return {
        "click_status": "SUCCESS", "selected_tower_id": TOWER_ID,
        "target_type": 1, "source_heading": "Barracks",
        "upgrade_title": "Upgrade to 軍械庫", "dom_guard_passed": True,
        "button_visible": True, "button_enabled": True, "pointer_events": True,
        "locked_glyph": False, "hidden_lock_icon": False,
    }


def test_partial_coverage_does_not_block_positive_visible_own_candidate():
    row = target_row(make_state(coverage="PARTIAL"))
    assert row["eligible"] is True
    assert row["source_type"] == SOURCE
    assert row["target_type"] == TARGET
    assert row["nominal_delay"] == NOMINAL


@pytest.mark.parametrize(("unit_case", "expected_eligible", "expected_reason"), [
    ("known_zero", True, None),
    ("ruler_present", False, "SOURCE_HAS_RULER"),
    ("unknown", False, "SOURCE_UNITS_UNKNOWN"),
    ("partial_vector", False, "SOURCE_UNITS_VECTOR_INCOMPLETE"),
    ("stale", False, "SOURCE_UNITS_UNKNOWN"),
])
def test_upgrade_requires_fresh_complete_known_zero_ruler(unit_case, expected_eligible, expected_reason):
    state = make_state()
    tower = state.towers[0]
    sampled = state.sampled_at_ms
    if unit_case == "known_zero":
        units_fact = fact(units(), sampled)
    elif unit_case == "ruler_present":
        units_fact = fact(units(ruler=1), sampled)
    elif unit_case == "unknown":
        units_fact = unknown()
    elif unit_case == "partial_vector":
        partial = Units(tuple((i, 0) for i in range(9)))
        units_fact = fact(partial, sampled)
    else:
        units_fact = fact(units(), sampled - probe.MAX_FACT_AGE_MS - 1)
    state = replace(state, towers=(replace(tower, units=units_fact),))

    row = target_row(state)
    assert row["eligible"] is expected_eligible
    if expected_reason is None:
        assert "SOURCE_HAS_RULER" not in row["reasons"]
    else:
        assert expected_reason in row["reasons"]


@pytest.mark.parametrize("field", ["owner", "relation", "visibility"])
def test_unknown_or_nonself_ownership_evidence_never_admits_candidate(field):
    options = {"owner_known": True, "relation_known": True, "visibility_known": True}
    if field == "owner":
        options["owner_known"] = False
    elif field == "relation":
        options["relation_known"] = False
    else:
        # Tower enforces positively visible instances, so exercise the public helper
        # with the same fact contract before construction of canonical Tower.
        state = SimpleNamespace(player_id=fact(PLAYER), sampled_at_ms=NOW, received_at_ms=NOW,
            towers=(SimpleNamespace(
            id=TOWER_ID, visibility=unknown(), owner=fact(PLAYER),
            relation=fact(Relation.SELF), tower_type=fact(SOURCE),
            delay_ticks=fact(0), upgrade_candidates=fact(()),
            upgrade_locks=fact(((TARGET, False),)), capacity=fact(rules.capacity(SOURCE, False)),
            effects=fact((("MORALE_BOOST", False),))),))
        assert candidate_rows(state) == []
        return
    state = make_state(tower=make_tower(**options))
    assert candidate_rows(state) == []


@pytest.mark.parametrize("field", ["tower_type_known", "delay_known", "candidates_known",
                                     "locks_known", "capacity_known", "effects_known"])
def test_unknown_local_source_or_eligibility_facts_refuse_candidate(field):
    rows = [r for r in candidate_rows(make_state(tower=make_tower(**{field: False})))
            if r["target_type"] == TARGET]
    assert not rows or all(not row["eligible"] for row in rows)


def test_known_locked_target_is_not_eligible():
    locked = make_tower(locks=((TARGET, True),))
    rows = [r for r in candidate_rows(make_state(tower=locked)) if r["target_type"] == TARGET]
    assert not rows or all(not row["eligible"] for row in rows)


def test_known_direct_prerequisite_failure_is_not_eligible():
    candidates = ((TARGET, ((1, 1, 2), (9, 3, 3)), False),)
    rows = [r for r in candidate_rows(make_state(tower=make_tower(candidates=candidates)))
            if r["target_type"] == TARGET]
    assert not rows or all(not row["eligible"] for row in rows)


def test_lower_known_shield_capacity_target_is_refused():
    source = 7
    target = 16
    counts = [0] * 27
    counts[26] = 1
    candidate = ((target, ((26, 1, 1),), True),)
    tower = make_tower(source=source, candidates=candidate,
                       locks=((target, False),), capacity=rules.capacity(source, False))
    resources = [0] * 27
    resources[26] = 1
    rows = [r for r in candidate_rows(make_state(tower=tower,
                                                  resources=tuple(enumerate(resources))))
            if r["target_type"] == target]
    assert not rows or all(not row["eligible"] for row in rows)
    if rows:
        assert rows[0]["shield_before"] > rows[0]["shield_after"]


def test_dom_requires_one_exact_visible_enabled_unlocked_title_and_source_heading():
    result = inspect_upgrade_dom(valid_dom(), SOURCE, TARGET)
    assert result["eligible"] is True
    assert result["exact_title"] == "Upgrade to Helipad"


@pytest.mark.parametrize("mutation", [
    {"visible": False}, {"enabled": False}, {"pointer_events": False},
    {"locked_glyph": True}, {"hidden_lock_icon": True},
    {"bbox": [1, 2, 0, 20]},
])
def test_dom_guard_refuses_hidden_disabled_locked_or_unhittable_button(mutation):
    dom = valid_dom()
    dom["buttons"][0].update(mutation)
    assert inspect_upgrade_dom(dom, SOURCE, TARGET)["eligible"] is False


def test_dom_guard_refuses_wrong_or_ambiguous_button_and_wrong_heading():
    wrong = valid_dom()
    wrong["buttons"][0]["title"] = "Upgrade to Watchtower"
    assert inspect_upgrade_dom(wrong, SOURCE, TARGET)["eligible"] is False
    duplicate = valid_dom()
    duplicate["buttons"].append(dict(duplicate["buttons"][0]))
    assert inspect_upgrade_dom(duplicate, SOURCE, TARGET)["eligible"] is False
    wrong_heading = valid_dom()
    wrong_heading["headings"] = ["Helipad"]
    assert inspect_upgrade_dom(wrong_heading, SOURCE, TARGET)["eligible"] is False
    duplicate_heading = valid_dom()
    duplicate_heading["headings"] = ["Airfield", "Airfield"]
    assert inspect_upgrade_dom(duplicate_heading, SOURCE, TARGET)["eligible"] is False


def test_dom_guard_refuses_unverified_language_label():
    unknown_language = valid_dom()
    unknown_language["buttons"][0]["title"] = "Upgrade in an unverified language"
    assert inspect_upgrade_dom(unknown_language, SOURCE, TARGET)["eligible"] is False


@pytest.mark.parametrize("field,value", [
    ("selected_tower_id", TOWER_ID + 1),
    ("source_heading", "Helipad"),
    ("upgrade_title", "Upgrade in an unverified language"),
    ("locked_glyph", True),
    ("hidden_lock_icon", True),
    ("button_enabled", False),
])
def test_ui_identity_heading_title_or_lock_mismatch_never_verifies(field, value):
    before = make_state(tick=100)
    ui = valid_ui_result()
    ui[field] = value
    result = verify_upgrade(before, ui,
                            [after_state(101), after_state(102, delay=NOMINAL - 1)], TARGET)
    assert result["status"] == "UNKNOWN"


def test_unverified_chinese_upgrade_title_stays_unknown():
    dom = {
        "headings": ["Barracks"],
        "buttons": [{"title": "Upgrade to 軍械庫", "visible": True, "enabled": True,
                     "pointer_events": True, "locked_glyph": False,
                     "hidden_lock_icon": False, "bbox": [10, 20, 100, 40]}],
    }
    assert inspect_upgrade_dom(dom, 3, 1)["eligible"] is False
    before = barracks_state(100)
    ui = barracks_ui_result()
    after1 = after_state(101, typ=1, delay=rules.UPGRADE_DELAY[1])
    after2 = after_state(102, typ=1, delay=rules.UPGRADE_DELAY[1] - 1)
    assert verify_upgrade(before, ui, [after1, after2], 1)["status"] == "UNKNOWN"


def _run_selection_roundtrip(monkeypatch, tmp_file, before, after, before_id, after_id,
                             dom=None, identity=None):
    class FakeExtractor:
        def __init__(self):
            self.samples = iter(((before, {"selected_tower": before_id}),
                                 (after, {"selected_tower": after_id})))

        async def sample(self):
            return next(self.samples)

    async def get_dom(_page):
        return valid_dom() if dom is None else dom

    monkeypatch.setattr(probe, "_dom_snapshot", get_dom)
    expected_identity = probe._state_identity(before) if identity is None else identity
    with tmp_file.open("x", encoding="utf-8") as stream:
        result = asyncio.run(probe._selection_roundtrip(
            FakeExtractor(), object(), stream, TOWER_ID, SOURCE, expected_identity,
            time.monotonic() + 0.02))
    rows = [json.loads(line) for line in tmp_file.read_text(encoding="utf-8").splitlines()]
    tmp_file.unlink()
    return result, rows


def test_roundtrip_requires_stable_selected_id_around_dom_and_writes_failure_immediately(monkeypatch):
    evidence = Path(__file__).parents[1] / "runtime" / "cache" / "pytest" / f"selection-{uuid4().hex}.jsonl"
    before = make_state(tick=100)
    after = make_state(tick=101)
    result, rows = _run_selection_roundtrip(monkeypatch, evidence, before, after,
                                            TOWER_ID, TOWER_ID + 1)
    assert result["matched"] is False
    assert rows[0]["kind"] == "SELECTION_WITNESS_ATTEMPT"
    assert rows[0]["after_selected_tower_id"] == TOWER_ID + 1
    assert "SELECTED_TOWER_ID_CHANGED_DURING_DOM_READ" in rows[0]["reasons"]


def test_roundtrip_rejects_identity_change_during_dom_and_persists_reason(monkeypatch):
    evidence = Path(__file__).parents[1] / "runtime" / "cache" / "pytest" / f"selection-{uuid4().hex}.jsonl"
    before = make_state(tick=100)
    after = make_state(tick=101, document="document-b")
    result, rows = _run_selection_roundtrip(monkeypatch, evidence, before, after,
                                            TOWER_ID, TOWER_ID)
    assert result["matched"] is False
    assert "EPOCH_OR_NETWORK_IDENTITY_CHANGED_DURING_DOM_READ" in rows[0]["reasons"]


def test_roundtrip_rejects_wrong_heading_and_accepts_stable_english_witness(monkeypatch):
    workspace = Path(__file__).parents[1] / "runtime" / "cache" / "pytest"
    before = make_state(tick=100)
    after = make_state(tick=101)
    bad_dom = {"headings": ["Helipad"], "buttons": valid_dom()["buttons"]}
    result, rows = _run_selection_roundtrip(monkeypatch, workspace / f"selection-{uuid4().hex}.jsonl",
                                            before, after, TOWER_ID, TOWER_ID, dom=bad_dom)
    assert result["matched"] is False
    assert "SOURCE_HEADING_NOT_EXACT" in rows[0]["reasons"]
    result, rows = _run_selection_roundtrip(monkeypatch, workspace / f"selection-{uuid4().hex}.jsonl",
                                            before, after, TOWER_ID, TOWER_ID)
    assert result["matched"] is True
    assert result["source_heading"] == "Airfield"
    assert rows[0]["matched"] is True


def test_roundtrip_rejects_ambiguous_source_heading_and_keeps_titles_diagnostic_only(monkeypatch):
    workspace = Path(__file__).parents[1] / "runtime" / "cache" / "pytest"
    before = make_state(tick=100)
    after = make_state(tick=101)
    ambiguous_dom = {"headings": ["Airfield", "Airfield"], "buttons": valid_dom()["buttons"]}
    result, rows = _run_selection_roundtrip(monkeypatch, workspace / f"selection-{uuid4().hex}.jsonl",
                                            before, after, TOWER_ID, TOWER_ID, dom=ambiguous_dom)
    assert result["matched"] is False
    assert rows[0]["matched"] is False
    assert rows[0]["visible_upgrade_titles"] == ["Upgrade to Helipad"]
    assert all(not guard["eligible"] for guard in rows[0]["candidate_title_guards"])
    assert "SOURCE_HEADING_NOT_UNIQUE" in rows[0]["reasons"]


def test_dom_click_or_progress_alone_is_not_success():
    before = make_state(tick=100)
    after0 = after_state(101)
    after1 = after_state(102, delay=NOMINAL - 1)
    ui = valid_ui_result()
    ui["dom_guard_passed"] = False
    assert verify_upgrade(before, ui, [after0, after1], TARGET)["status"] != "SUCCESS"
    assert verify_upgrade(before, valid_ui_result(), [], TARGET)["status"] != "SUCCESS"


def test_success_requires_target_type_nominal_delay_then_consecutive_countdown():
    before = make_state(tick=100)
    result = verify_upgrade(before, valid_ui_result(),
                            [after_state(101, delay=NOMINAL),
                             after_state(102, delay=NOMINAL - 1)], TARGET)
    assert result["status"] == "SUCCESS"


@pytest.mark.parametrize("after_ticks", [
    [101, 103], [102, 103],
])
def test_missing_or_nonconsecutive_ticks_never_succeed(after_ticks):
    before = make_state(tick=100)
    states = [after_state(after_ticks[0], delay=NOMINAL),
              after_state(after_ticks[1], delay=NOMINAL - 1)]
    assert verify_upgrade(before, valid_ui_result(), states, TARGET)["status"] != "SUCCESS"


@pytest.mark.parametrize("kwargs", [
    {"match": "other-match"}, {"document": "other-document"},
    {"player": PLAYER + 1}, {"source_mode": "OFFLINE"},
    {"client": "0" * 64}, {"lifecycle": Lifecycle.RESULT},
])
def test_epoch_player_lifecycle_or_client_change_never_succeeds(kwargs):
    before = make_state(tick=100)
    states = [after_state(101, delay=NOMINAL, **kwargs),
              after_state(102, delay=NOMINAL - 1, **kwargs)]
    assert verify_upgrade(before, valid_ui_result(), states, TARGET)["status"] != "SUCCESS"


@pytest.mark.parametrize("mutate", [
    lambda s: replace(s, tick=unknown()),
    lambda s: replace(s, source_mode=unknown()),
    lambda s: replace(s, lifecycle=unknown()),
    lambda s: replace(s, match_id=unknown()),
    lambda s: replace(s, player_id=unknown()),
])
def test_unknown_or_stale_epoch_facts_never_succeed(mutate):
    before = make_state(tick=100)
    unknown_before = mutate(before)
    assert verify_upgrade(unknown_before, valid_ui_result(),
                          [after_state(101), after_state(102, delay=NOMINAL - 1)], TARGET)["status"] != "SUCCESS"


def test_stale_before_type_and_prerequisite_facts_cannot_admit_or_verify():
    state = make_state(tick=100)
    tower = state.towers[0]
    stale_at = state.received_at_ms - 5001
    stale_tower = replace(
        tower,
        tower_type=Fact(SOURCE, Knowledge.OBSERVED, "stale prior sample", stale_at),
        upgrade_candidates=Fact(tower.upgrade_candidates.value, Knowledge.DERIVED,
                                "stale prerequisite sample", stale_at),
    )
    stale_state = replace(state, towers=(stale_tower,))
    assert target_row(stale_state)["eligible"] is False
    assert verify_upgrade(stale_state, valid_ui_result(),
                          [after_state(101), after_state(102, delay=NOMINAL - 1)], TARGET)["status"] != "SUCCESS"


def test_stale_after_delay_fact_cannot_verify_success():
    before = make_state(tick=100)
    first = after_state(101)
    stale_delay = Fact(NOMINAL, Knowledge.OBSERVED, "stale prior sample",
                       first.received_at_ms - 5001)
    stale_first = replace(first, towers=(replace(first.towers[0], delay_ticks=stale_delay),))
    second = after_state(102, delay=NOMINAL - 1)
    assert verify_upgrade(before, valid_ui_result(), [stale_first, second], TARGET)["status"] != "SUCCESS"


def test_future_incoherent_candidate_fact_cannot_admit_candidate():
    state = make_state(tick=100)
    tower = state.towers[0]
    future_candidates = Fact(tower.upgrade_candidates.value, Knowledge.DERIVED,
                              "future impossible sample", state.received_at_ms + 1)
    incoherent = replace(state, towers=(replace(tower, upgrade_candidates=future_candidates),))
    assert target_row(incoherent)["eligible"] is False


def test_stale_known_world_tick_cannot_verify_success():
    before = make_state(tick=100)
    stale_tick = Fact(100, Knowledge.OBSERVED, "stale world sequence", before.received_at_ms - 5001)
    before = replace(before, tick=stale_tick)
    assert verify_upgrade(before, valid_ui_result(),
                          [after_state(101), after_state(102, delay=NOMINAL - 1)], TARGET)["status"] != "SUCCESS"


def test_stale_world_sequence_observation_cannot_verify_success():
    before = make_state(tick=100)
    stale_observation = Fact(before.received_at_ms - 1001, Knowledge.OBSERVED,
                             "stale source tick observation", before.received_at_ms)
    before = replace(before, world_sequence_observed_at_ms=stale_observation)
    assert verify_upgrade(before, valid_ui_result(),
                          [after_state(101), after_state(102, delay=NOMINAL - 1)], TARGET)["status"] != "SUCCESS"


@pytest.mark.parametrize("forged", [
    ((TARGET, (), True),),
    ((TARGET, ((1, 0, 2), (9, 3, 3)), True),),
    ((TARGET, ((1, 2, 2), (9, 0, 3)), True),),
])
def test_claimed_prerequisite_boolean_cannot_override_missing_or_insufficient_counts(forged):
    tower = make_tower(candidates=forged)
    rows = [r for r in candidate_rows(make_state(tower=tower)) if r["target_type"] == TARGET]
    assert not rows or all(not row["eligible"] for row in rows)


def test_claimed_direct_upgrade_cannot_override_pinned_downgrade_relation():
    # Type 3 has no direct parent in the pinned table, even when its own
    # prerequisite tuple is exactly the (empty) pinned tuple.
    false_direct = ((3, (), True),)
    tower = make_tower(candidates=false_direct, locks=((3, False),))
    rows = [r for r in candidate_rows(make_state(tower=tower)) if r["target_type"] == 3]
    assert rows and all(not row["eligible"] for row in rows)
    assert all("TARGET_NOT_DIRECT_UPGRADE" in row["reasons"] for row in rows)


def test_prerequisite_observation_must_match_known_own_resource_snapshot():
    tower = make_tower(candidates=((TARGET, ((1, 2, 2), (9, 3, 3)), True),))
    resources = [0] * 27  # claims in tower candidate are unsupported by current own-count snapshot
    state = make_state(tower=tower, resources=tuple(enumerate(resources)))
    rows = [r for r in candidate_rows(state) if r["target_type"] == TARGET]
    assert not rows or all(not row["eligible"] for row in rows)


def test_sync_output_file_context_is_not_used_with_async_with():
    import ast

    source = Path(__file__).parents[1].joinpath("tools", "v2_goal_upgrade_probe.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncWith):
            for item in node.items:
                expr = item.context_expr
                if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
                    assert not (expr.func.attr == "open" and
                                isinstance(expr.func.value, ast.Name) and expr.func.value.id == "out")


def test_probe_keeps_six_selection_and_one_upgrade_click_bounds():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(probe.run_probe))
    selection_bound = any(
        isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "tries" and
        len(node.ops) == 1 and isinstance(node.ops[0], ast.GtE) and
        len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant) and
        node.comparators[0].value == 6
        for node in ast.walk(tree))
    upgrade_clicks = [node for node in ast.walk(tree)
                      if isinstance(node, ast.Await) and isinstance(node.value, ast.Call) and
                      isinstance(node.value.func, ast.Name) and node.value.func.id == "_page_click" and
                      len(node.value.args) >= 3 and isinstance(node.value.args[1], ast.Name) and
                      node.value.args[1].id == "click_x" and isinstance(node.value.args[2], ast.Name) and
                      node.value.args[2].id == "click_y"]
    assert selection_bound
    assert len(upgrade_clicks) == 1


def test_read_only_runtime_denial_writes_durable_unknown_without_browser(monkeypatch):
    workspace = Path(__file__).parents[1]
    tmp_root = workspace / "runtime" / "cache" / "pytest" / f"upgrade-smoke-{uuid4().hex}"
    monkeypatch.setattr(probe, "ROOT", tmp_root)
    monkeypatch.setattr(probe, "_lease_guard", lambda _seconds: (_ for _ in ()).throw(
        ValueError("synthetic lease refusal before browser access")))
    monkeypatch.setattr(probe, "async_playwright", lambda: (_ for _ in ()).throw(
        AssertionError("Playwright must not start before a valid lease")))
    destination = tmp_root / "runtime" / "research" / "v2" / "goal" / "upgrade-probe.jsonl"
    try:
        result = asyncio.run(probe.run_probe(SimpleNamespace(seconds=1, out=destination, execute=False)))
        assert result["status"] == "UNKNOWN"
        rows = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1
        assert rows[0]["kind"] == "PROBE_ABORTED"
        assert "synthetic lease refusal" in rows[0]["reason"]
    finally:
        if tmp_root.exists():
            shutil.rmtree(tmp_root)


def test_writer_lease_releases_reserved_token_on_exit(monkeypatch):
    reserved = []
    released = []
    workspace = Path(__file__).parents[1]
    tmp_root = workspace / "runtime" / "cache" / "pytest" / f"writer-smoke-{uuid4().hex}"
    monkeypatch.setattr(probe, "ROOT", tmp_root)
    monkeypatch.setattr(probe, "_lease_guard", lambda _seconds: {"valid": True})
    monkeypatch.setattr(probe, "reserve_writer",
                        lambda path, pid, profile, deadline: reserved.append((path, pid, profile, deadline)) or "token")
    monkeypatch.setattr(probe, "release_writer", lambda path, token: released.append((path, token)))
    with probe._writer_lease(1):
        assert len(reserved) == 1
        assert released == []
    assert released == [(reserved[0][0], "token")]


def test_runtime_stops_started_playwright_and_releases_writer_on_no_page(monkeypatch):
    workspace = Path(__file__).parents[1]
    tmp_root = workspace / "runtime" / "cache" / "pytest" / f"runtime-cleanup-{uuid4().hex}"
    destination = tmp_root / "runtime" / "research" / "v2" / "goal" / "probe.jsonl"
    events = []

    class FakePlaywright:
        def __init__(self):
            self.stopped = False

        async def stop(self):
            self.stopped = True

    class FakePlaywrightContext:
        def __init__(self):
            self.value = FakePlaywright()

        async def start(self):
            return self.value
        # Deliberately no stop(); cleanup belongs to the started Playwright object.

    class EmptyBrowser:
        contexts = []

    manager = FakePlaywrightContext()

    @contextmanager
    def writer_lease(_seconds):
        events.append("writer-enter")
        try:
            yield
        finally:
            events.append("writer-exit")

    async def connect(_pw, _root):
        return EmptyBrowser()

    monkeypatch.setattr(probe, "ROOT", tmp_root)
    monkeypatch.setattr(probe, "async_playwright", lambda: manager)
    monkeypatch.setattr(probe, "_writer_lease", writer_lease)
    monkeypatch.setattr(probe, "connect_dedicated", connect)
    try:
        result = asyncio.run(probe.run_probe(SimpleNamespace(seconds=1, out=destination, execute=False)))
        assert result["status"] == "UNKNOWN"
        assert manager.value.stopped is True
        assert events == ["writer-enter", "writer-exit"]
        rows = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
        assert rows[-1]["kind"] == "PROBE_ABORTED"
        assert "expected exactly one owned official-client page" in rows[-1]["reason"]
    finally:
        if tmp_root.exists():
            shutil.rmtree(tmp_root)


@pytest.mark.parametrize("observed", [(TARGET, NOMINAL - 1), (SOURCE, NOMINAL),
                                       (TARGET, NOMINAL - 2)])
def test_wrong_type_or_delay_effect_never_succeeds(observed):
    typ, delay = observed
    before = make_state(tick=100)
    result = verify_upgrade(before, valid_ui_result(),
                            [after_state(101, typ=typ, delay=delay),
                             after_state(102, typ=TARGET, delay=NOMINAL - 1)], TARGET)
    assert result["status"] != "SUCCESS"
