import asyncio
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

from kiomet_ai.v2.state import Lifecycle, Relation
from tools.v2_controlled_transition_capture import (
    _ui_quantity_evidence, capture_distinct_ticks, collect_new_force_births,
    collect_new_force_lineage,
    durable_before, force_lineage_credit, is_project_headless_browser_process,
    record_before_gesture, supply_line_guard_passed, validate_fresh_intent,
    validate_scenario,
)


def fact(value):
    return NS(value=value)


def units(**values):
    names = {"shield": 0, "fighter": 1, "chopper": 2, "bomber": 3,
             "tank": 4, "soldier": 5, "shell": 6, "emp": 7,
             "nuke": 8, "ruler": 9}
    return fact(NS(counts=tuple((i, values.get(name, 0)) for name, i in names.items())))


def tower(ident, owner, relation, *, neighbor=(), mobile=None, inventory=None,
          cap=None, morale=False, ruler=0):
    inv = {"fighter": 3} if inventory is None else inventory
    dep = {"fighter": 3} if mobile is None else mobile
    capacity = {"fighter": 10} if cap is None else cap
    if ruler:
        inv = {**inv, "ruler": ruler}
    return NS(id=ident, owner=fact(owner), relation=fact(relation),
              neighbors=fact(tuple(neighbor)), deployable=units(**dep),
              units=units(**inv), capacity=units(**capacity),
              effects=fact((("MORALE_BOOST", morale),)),
              position=fact((ident * 10, 0)), supply_line_present=fact(False),
              tower_type=fact(11), delay_ticks=fact(0))


def state(source=None, destination=None):
    source = source or tower(1, 7, Relation.SELF, neighbor=(2,))
    destination = destination or tower(2, 0, Relation.NEUTRAL, inventory={})
    return NS(lifecycle=fact(Lifecycle.IN_MATCH), match_id=fact("match-A"),
              player_id=fact(7), coverage="PLAYER_VISIBLE_COMPLETE",
              forces=fact(()), towers=(source, destination))


def test_plan_requires_adjacent_visible_own_source_and_empty_neutral_destination():
    planned = validate_scenario(state(), 1, 2)
    assert planned["scenario"] == "neutral_capture"
    assert planned["typed_deployable"] == ((1, 3),)
    assert validate_scenario(state(), 1, 9) == "endpoint_not_currently_visible"
    assert validate_scenario(state(), 1, 1) == "destination_not_adjacent"


def test_refuses_nonempty_neutral_weapons_ruler_morale_and_overflow():
    occupied = tower(2, 0, Relation.NEUTRAL, inventory={"fighter": 1})
    assert validate_scenario(state(destination=occupied), 1, 2) == "neutral_destination_not_empty"
    armed_source = tower(1, 7, Relation.SELF, neighbor=(2,), mobile={"fighter": 3, "nuke": 1})
    assert validate_scenario(state(source=armed_source), 1, 2) == "source_contains_unsupported_deployable"
    ruler_source = tower(1, 7, Relation.SELF, neighbor=(2,), ruler=1)
    assert validate_scenario(state(source=ruler_source), 1, 2) == "source_contains_ruler"
    boosted = tower(1, 7, Relation.SELF, neighbor=(2,), morale=True)
    boosted_plan = validate_scenario(state(source=boosted), 1, 2)
    assert boosted_plan["scenario_class"] == "CAPTURE_ONLY"
    assert "morale_boosted_combat_speed_unproven" in boosted_plan["scenario_ineligible_reasons"]
    unknown = tower(1, 7, Relation.SELF, neighbor=(2,))
    unknown.effects = fact(None)
    assert validate_scenario(state(source=unknown), 1, 2) == "source_morale_boost_unknown"
    overflow = tower(1, 7, Relation.SELF, neighbor=(2,), inventory={"fighter": 11}, cap={"fighter": 10})
    assert validate_scenario(state(source=overflow), 1, 2) == "source_capacity_overflow"


def test_ui_quantity_must_be_visible_and_match_typed_inventory():
    typed = ((1, 3),)
    good = {"headings": ["總部"], "rows": [{"unit": "戰鬥機", "text": "3/10"}]}
    assert _ui_quantity_evidence(good, typed, 11, False)
    assert _ui_quantity_evidence({**good, "rows": [{"unit": "戰鬥機", "text": "2/10"}]}, typed, 11, False) is None
    assert _ui_quantity_evidence({**good, "rows": good["rows"] * 2}, typed, 11, False) is None
    assert _ui_quantity_evidence({"headings": ["總部", "村莊"], "rows": good["rows"]}, typed, 11, False) is None
    assert _ui_quantity_evidence({"headings": ["總部"], "rows": [{"unit": "未知", "text": "3/10"}]}, typed, 11, False) is None
    # Ordinary towers can visibly hold non-mobile shields; only Projectors
    # expose shields in the pinned mobile inventory rule.
    rows = [{"unit": "戰鬥機", "text": "3/10"}, {"unit": "護盾", "text": "5/10"}]
    direct = {"headings": ["總部"], "rows": rows,
              "nested_rows": [{"unit": "村莊", "text": "1/1"}, {"unit": "兵營", "text": "0/2"}]}
    assert _ui_quantity_evidence(direct, typed, 11, False)
    assert "nested_requirement_rows" in _ui_quantity_evidence(direct, typed, 11, False)
    morale_row = {"unit": "你的國王就在附近：產量加倍，出發的單位在途中移動更快、作戰更猛",
                  "text": "士氣高昂"}
    assert _ui_quantity_evidence({"headings": ["總部"], "rows": [*rows, morale_row]}, typed, 11, True)
    assert _ui_quantity_evidence({"headings": ["投射器"], "rows": rows},
                                 ((0, 5), (1, 3)), 15, False)
    assert _ui_quantity_evidence({"headings": ["投射器"], "rows": rows}, typed, 15, False) is None


def test_fresh_deployable_change_or_selected_source_refuses_dispatch(monkeypatch):
    monkeypatch.setattr("tools.v2_controlled_transition_capture.control_readiness_gaps",
                        lambda *_args: ())
    base = state()
    assert isinstance(validate_fresh_intent(base, 1, 2, ((1, 3),), None, 1000), dict)
    changed_source = tower(1, 7, Relation.SELF, neighbor=(2,), mobile={"fighter": 2},
                           inventory={"fighter": 2})
    changed = state(source=changed_source)
    fresh = validate_fresh_intent(changed, 1, 2, ((1, 3),), None, 1000)
    assert isinstance(fresh, dict) and fresh["typed_deployable"] == ((1, 2),)
    assert validate_fresh_intent(base, 1, 2, ((1, 3),), 1, 1000) == "selection_not_none_before_force_gesture"


def test_lineage_aggregates_arrived_before_last_sample_and_rejects_ambiguity():
    vector = units(fighter=3).value

    def force(confidence, ident="match-A:f:new", owner=7):
        return NS(id=fact(ident), source=fact(1), destination=fact(2),
                  owner=fact(owner), units=fact(vector), progress=fact(0),
                  confidence=fact(confidence), first_seen_ms=fact(100))

    appeared = NS(tick=fact(5), forces=fact((force("NEW_TRACK"),)))
    disappeared = NS(tick=fact(6), forces=fact(()))
    rows = collect_new_force_lineage([appeared, disappeared], 1, 2, ((1, 3),), set(), 7)
    assert len(rows) == 1 and rows[0]["quantity_matches_intent"] is True
    assert rows[0]["candidate_application_tick"] == 5
    assert rows[0]["birth_progress"] == 0 and force_lineage_credit(rows, True)
    assert not force_lineage_credit(rows, False)
    later_ambiguous = NS(tick=fact(6), forces=fact((force("AMBIGUOUS"),)))
    assert collect_new_force_lineage([appeared, later_ambiguous, disappeared], 1, 2,
                                     ((1, 3),), set(), 7) == []
    second = NS(tick=fact(6), forces=fact((force("NEW_TRACK", "match-A:f:second"),)))
    multiple = collect_new_force_lineage([appeared, second], 1, 2, ((1, 3),), set(), 7)
    assert len(multiple) == 2 and not force_lineage_credit(multiple, True)
    wrong_owner = NS(tick=fact(6), forces=fact((force("NEW_TRACK", owner=8),)))
    assert collect_new_force_lineage([wrong_owner], 1, 2, ((1, 3),), set(), 7) == []


def test_birth_detection_is_quantity_independent_and_retains_continuations():
    def force(ident, *, confidence="NEW_TRACK", owner=7, count=5, progress=0):
        return NS(id=fact(ident), source=fact(1), destination=fact(2),
                  owner=fact(owner), units=units(fighter=count), progress=fact(progress),
                  confidence=fact(confidence), first_seen_ms=fact(100))

    first = state()
    first.tick = fact(10)
    first.forces = fact((force("match-A:f:new"),))
    continuation = state()
    continuation.tick = fact(11)
    continuation.forces = fact((force("match-A:f:new", confidence="UNIQUE_CONTINUATION",
                                      count=5, progress=4),))
    # A prior UI typed observation of three units is deliberately not supplied
    # as a candidate filter: the actual birth vector is retained as evidence.
    analysis = collect_new_force_births([first, continuation], 1, 2, set(), 7)
    assert analysis["eligible"] and not analysis["ambiguity_reasons"]
    assert len(analysis["candidates"]) == 1
    birth = analysis["candidates"][0]
    assert birth["birth_tick"] == 10 and birth["birth_progress"] == 0
    assert birth["birth_units"] == ((1, 5),)
    assert birth["later_observations"] == [{"tick": 11, "progress": 4,
        "confidence": "UNIQUE_CONTINUATION", "units": ((1, 5),)}]
    unknown_continuation = state()
    unknown_continuation.tick = fact(12)
    unknown_force = force("match-A:f:new", confidence="UNIQUE_CONTINUATION", progress=5)
    unknown_force.units = fact(None)
    unknown_continuation.forces = fact((unknown_force,))
    incomplete = collect_new_force_births([first, unknown_continuation], 1, 2, set(), 7)
    assert not incomplete["eligible"]
    assert "continuation_unit_vector_unknown" in incomplete["ambiguity_reasons"]


def test_birth_detection_rejects_multiple_ambiguous_wrong_owner_prior_and_incomplete():
    def force(ident, *, confidence="NEW_TRACK", owner=7, count=5):
        return NS(id=fact(ident), source=fact(1), destination=fact(2),
                  owner=fact(owner), units=units(fighter=count), progress=fact(0),
                  confidence=fact(confidence), first_seen_ms=fact(100))

    def observed(*forces, tick=10, coverage="PLAYER_VISIBLE_COMPLETE"):
        item = state()
        item.tick = fact(tick)
        item.forces = fact(tuple(forces))
        item.coverage = coverage
        return item

    multiple = collect_new_force_births([observed(force("new-1", count=5), force("new-2", count=4))],
                                        1, 2, set(), 7)
    assert not multiple["eligible"] and len(multiple["candidates"]) == 2
    assert "multiple_distinct_new_force_ids" in multiple["ambiguity_reasons"]

    ambiguous = collect_new_force_births([observed(force("new", confidence="AMBIGUOUS"))],
                                         1, 2, set(), 7)
    assert not ambiguous["eligible"] and not ambiguous["candidates"]
    wrong_owner = collect_new_force_births([observed(force("new", owner=8))], 1, 2, set(), 7)
    assert not wrong_owner["eligible"] and "matching_endpoint_force_has_wrong_owner" in wrong_owner["ambiguity_reasons"]
    prior = collect_new_force_births([observed(force("old"))], 1, 2, {"old"}, 7)
    assert not prior["eligible"] and "matching_endpoint_force_id_was_present_before_intent" in prior["ambiguity_reasons"]
    incomplete = collect_new_force_births([observed(force("new"), coverage="PARTIAL")], 1, 2, set(), 7)
    assert not incomplete["eligible"] and incomplete["ambiguity_reasons"] == ["force_coverage_incomplete"]


def test_tick_capture_records_after_arrival_until_deadline():
    clock = [0.0]
    ticks = iter((1, 2, 3))
    sampled = []

    async def metadata():
        tick = next(ticks, 3)
        return {"tick": tick, "derived_match_id": "match-A",
                "derived_lifecycle": "IN_MATCH", "player_id": 7}

    async def sample():
        tick = sampled[-1] + 1 if sampled else 2
        sampled.append(tick)
        return NS(document_id="doc", match_id=fact("match-A"), player_id=fact(7),
                  tick=fact(tick)), {}

    async def sleep(seconds):
        clock[0] += seconds

    states, errors, arrival, completion = asyncio.run(capture_distinct_ticks(
        metadata, sample, 1, 10, ("doc", "match-A", 7), lambda s: s.tick.value == 2,
        now=lambda: clock[0], sleep=sleep))
    assert [state.tick.value for _at, state in states] == [2, 3]
    assert arrival["tick"] == 2 and completion == "seconds_bound" and not errors

    clock[0] = 0.0
    async def unchanged_metadata():
        return {"tick": 4, "derived_match_id": "match-A",
                "derived_lifecycle": "IN_MATCH", "player_id": 7}
    states, errors, arrival, completion = asyncio.run(capture_distinct_ticks(
        unchanged_metadata, sample, 4, .25, ("doc", "match-A", 7), lambda s: False,
        now=lambda: clock[0], sleep=sleep))
    assert not states and arrival is None and completion == "seconds_bound"


def test_before_intent_is_durable_before_mouse_gesture():
    seen = []

    class DurableBuffer:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def write(self, value):
            return self.wrapped.write(value)

        def fileno(self):
            return self.wrapped.fileno()

        def getvalue(self):
            self.wrapped.flush()
            self.wrapped.seek(0)
            return self.wrapped.read()

        def flush(self):
            self.wrapped.flush()
            seen.append("flush")

    backing = tempfile.TemporaryFile(mode="w+t", encoding="utf8")
    stream = DurableBuffer(backing)
    intent = {"kind": "BEFORE_INTENT", "QUESTION": "Does this ordinary deployment capture or reinforce?",
              "BEFORE": {"tick": 4, "typed_deployable": [[1, 3]]},
              "ACTION": {"source": 1, "destination": 2, "typed_deployable": [[1, 3]]},
              "EXPECTED": {"manual_newborn": {"progress": 0, "accelerated": True, "fuel": 150},
                           "future_route": "UNKNOWN", "future_fuel_cost": "UNKNOWN"},
              "input_sent": False}

    async def gesture():
        seen.append("gesture")
        persisted = json.loads(stream.getvalue().splitlines()[0])
        assert persisted == intent
        assert all(key in persisted for key in ("QUESTION", "BEFORE", "ACTION", "EXPECTED"))
        assert not any(key in persisted for key in ("OBSERVED", "SIMULATED", "DIFF", "VERDICT"))
        return "released"

    assert asyncio.run(record_before_gesture(stream, intent, gesture)) == "released"
    assert seen == ["flush", "gesture"]
    backing.close()


def test_durable_before_writes_complete_record():
    with tempfile.TemporaryFile(mode="w+t", encoding="utf8") as stream:
        durable_before(stream, {"kind": "BEFORE_INTENT", "input_sent": False})
        stream.seek(0)
        assert json.loads(stream.read()) == {"kind": "BEFORE_INTENT", "input_sent": False}


def test_host_profile_check_accepts_only_main_chromium_not_gpu_child():
    project = Path.cwd()
    profile = str(project / "test-browser-profile")
    main = ["chrome.exe", "--headless=new", f"--user-data-dir={profile}"]
    gpu = [*main, "--type=gpu-process"]
    assert is_project_headless_browser_process("chrome.exe", main, profile)
    assert not is_project_headless_browser_process("chrome.exe", gpu, profile)
    assert not is_project_headless_browser_process("chrome.exe", main, str(project / "other-profile"))


def test_preserved_live_receipt_replays_lineage_and_supply_line_guard_offline():
    from kiomet_ai.v2.serialization import state_from_dict

    root = Path(__file__).resolve().parents[1]
    fixture_root = root / "tests/fixtures/v2"
    event_bytes = gzip.decompress((fixture_root / "controlled-transition-77636cad4e97.jsonl.gz").read_bytes())
    report_bytes = gzip.decompress((fixture_root / "controlled-transition-77636cad4e97.json.gz").read_bytes())
    assert hashlib.sha256(event_bytes).hexdigest() == "0854dc24aa326fd2b6b027195582bedb368d97e96c752843265a9a813bd62d3b"
    assert hashlib.sha256(report_bytes).hexdigest() == "7154c3bee2966217da3b36d555ee666a9c907da27161d0ee809d4f109a17791e"
    events = [json.loads(line) for line in event_bytes.decode("utf8").splitlines()]
    before_row = next(row for row in events if row["kind"] == "BEFORE_INTENT")
    before = state_from_dict(before_row["state"])
    observations = [row["observation"] for row in events if row["kind"] == "AFTER_DISTINCT_TICK"]
    states = [state_from_dict(row["state"]) for row in observations]
    assert len(states) == 40
    assert [state.tick.value for state in states] == list(range(65156, 65196))
    source_id, destination_id = before_row["source"], before_row["destination"]
    assert supply_line_guard_passed(states, source_id, destination_id, False)
    prior_ids = {f.id.value for f in (before.forces.value or ()) if f.id.value}
    typed = tuple(tuple(pair) for pair in before_row["typed_deployable"])
    lineage = collect_new_force_lineage(states, source_id, destination_id, typed,
                                        prior_ids, before.player_id.value)
    assert len(lineage) == 1
    assert lineage[0]["candidate_application_tick"] == 65157
    assert lineage[0]["birth_progress"] == 0
    assert force_lineage_credit(lineage, True)
    assert next(t for t in states[30].towers if t.id == destination_id).owner.value == before.player_id.value
    original_report = json.loads(report_bytes.decode("utf8"))
    assert original_report["status"] == "PARTIAL"
    assert any("tuple" in error and "towers" in error for error in original_report["errors"])
