import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import from_canonical, step
from tools.v2_sim_differential import signature
from tools.v2_controlled_transition_capture import collect_new_force_lineage


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/v2/controlled-transition-77636cad4e97.jsonl.gz"
RECEIPT = ROOT / "docs/V2_M2A_CONTROLLED_CAPTURE_VALIDATION.json"
EVENT_SHA256 = "0854dc24aa326fd2b6b027195582bedb368d97e96c752843265a9a813bd62d3b"
PATH_PROOF_SHA256 = "ae0c84e83674d78352792ffe07f825b0fa71e5713fdba50542e9b482eb2a536e"


def _json_signature(state):
    return json.loads(json.dumps(signature(state)))


def _recorded_states(events):
    result = {}
    for row in events:
        if row.get("kind") == "AFTER_DISTINCT_TICK":
            data = row["observation"]["state"]
            result[data["tick"]["value"]] = state_from_dict(data)
    return result


def test_one_controlled_capture_matches_complete_visible_transition_and_no_reset_diagnostic():
    compressed = FIXTURE.read_bytes()
    event_bytes = gzip.decompress(compressed)
    assert hashlib.sha256(event_bytes).hexdigest() == EVENT_SHA256
    events = [json.loads(line) for line in event_bytes.decode("utf8").splitlines()]
    intent = next(row for row in events if row.get("kind") == "BEFORE_INTENT")
    assert intent["tick"] == 65155
    assert intent["source"] == 14090505 and intent["destination"] == 14090504
    assert intent["scenario_class"] == "CAPTURE_ONLY"
    assert intent["typed_deployable"] == [[5, 4]]
    assert intent["selected_tower_none_confirmed"] is True
    assert intent["endpoint_hit_tests"] == {"source": True, "destination": True}
    assert intent["ui_command_branch_proof"].endswith(
        "normal selected Option absent selects deploy_force_from_path branch"
    )
    assert intent["source_supply_line_present"] is False
    intent_state = state_from_dict(intent["state"])
    intent_towers = {t.id: t for t in intent_state.towers}
    intent_source, intent_destination = intent_towers[intent["source"]], intent_towers[intent["destination"]]
    assert intent_source.visibility.value is True
    assert intent_source.owner.value == intent_state.player_id.value
    assert intent_source.relation.value == "SELF"
    assert tuple((i, n) for i, n in intent_source.deployable.value.counts if n) == ((5, 4),)
    assert intent_destination.visibility.value is True
    assert intent_destination.owner.value == 0 and intent_destination.relation.value == "NEUTRAL"
    assert not any(n for _, n in intent_destination.units.value.counts)

    proof_path = ROOT / "docs/V2_M2A_DIRECT_PATH_CERTIFICATE.md"
    assert hashlib.sha256(proof_path.read_bytes()).hexdigest() == PATH_PROOF_SHA256

    states = _recorded_states(events)
    assert sorted(states) == list(range(65156, 65196))
    before_intent = intent_state
    source_id, destination_id, player_id = intent["source"], intent["destination"], before_intent.player_id.value
    prior_ids = {f.id.value for f in (before_intent.forces.value or ()) if f.id.value}
    lineage = collect_new_force_lineage(
        [states[tick] for tick in range(65156, 65186)],
        source_id, destination_id, ((5, 4),), prior_ids, player_id,
    )
    assert len(lineage) == 1
    assert lineage[0]["birth_confidence"] == "NEW_TRACK"
    assert lineage[0]["birth_tick"] == 65157
    assert lineage[0]["birth_progress"] == 0
    assert lineage[0]["birth_quantity_matches_intent"] is True
    force_id = lineage[0]["id"]

    assert not (states[65156].forces.value or ())
    for tick in range(65157, 65186):
        forces = states[tick].forces.value or ()
        assert len(forces) == 1
        force = forces[0]
        assert force.id.value == force_id
        assert (force.owner.value, force.source.value, force.destination.value) == (
            player_id, source_id, destination_id
        )
        assert tuple((i, n) for i, n in force.units.value.counts if n) == ((5, 4),)
        assert force.confidence.value in ("NEW_TRACK", "UNIQUE_CONTINUATION")
    current_force = (states[65185].forces.value or ())[0]
    assert current_force.progress.value == 56
    assert current_force.accelerated.value is True
    assert current_force.confidence.value == "UNIQUE_CONTINUATION"
    assert not (states[65186].forces.value or ())

    # Route and fuel are sourced before the tested arrival: the route proof is
    # tied to BEFORE_INTENT; the pinned newborn first leg starts with fuel 150
    # and does not spend it. Only these two otherwise-unobserved fields are
    # supplied to the canonical 65185 force. Acceleration remains observed.
    start = from_canonical(states[65185])
    assert len(start.forces) == 1
    simulated_force = start.forces[0]
    assert (simulated_force.owner, simulated_force.source, simulated_force.destination) == (
        player_id, source_id, destination_id
    )
    assert simulated_force.units == (0, 0, 0, 0, 0, 4, 0, 0, 0, 0)
    assert simulated_force.progress == 56 and simulated_force.accelerated is True
    start = replace(start, forces=(replace(simulated_force, terminal=True, fuel=150),))
    predicted_capture = step(start)
    observed_capture = from_canonical(states[65186])
    predicted_signature = _json_signature(predicted_capture)
    observed_signature = _json_signature(observed_capture)
    assert predicted_signature == observed_signature
    assert predicted_capture.forces == ()
    assert len(predicted_capture.towers) == len(observed_capture.towers) == 35
    assert {t.id for t in predicted_capture.towers} == {t.id for t in observed_capture.towers}

    before_target = next(t for t in start.towers if t.id == destination_id)
    captured_target = next(t for t in predicted_capture.towers if t.id == destination_id)
    assert before_target.owner == 0 and not any(before_target.units)
    assert (captured_target.owner, captured_target.units[5], captured_target.relation) == (
        player_id, 4, "SELF"
    )
    assert captured_target.units[4] == 0 and not any(captured_target.units[6:10])
    assert captured_target.capacity == before_target.capacity
    assert captured_target.production == ((0, 20), (5, 24))
    assert captured_target.delay == 0 and captured_target.morale is False
    assert captured_target.supply_line_present is False

    # Continue from the predicted capture state, without resetting to the
    # observed capture. This is diagnostic only because dynamic aura/cache
    # freshness is not certified for a longer trajectory.
    predicted_next = step(predicted_capture)
    observed_next = from_canonical(states[65187])
    predicted_next_signature = _json_signature(predicted_next)
    observed_next_signature = _json_signature(observed_next)
    assert predicted_next_signature == observed_next_signature

    receipt = json.loads(RECEIPT.read_text(encoding="utf8"))
    assert receipt["manifest"]["frozen_recording"]["sha256"] == EVENT_SHA256
    assert receipt["manifest"]["before_only_path_certificate"]["sha256"] == PATH_PROOF_SHA256
    assert receipt["lineage"]["current_force_id"] == force_id
    assert receipt["capture"]["expected_signature"] == predicted_signature
    assert receipt["capture"]["observed_signature"] == observed_signature
    assert receipt["capture"]["simulation_signature_sha256"] == hashlib.sha256(
        json.dumps(predicted_signature, sort_keys=True, separators=(",", ":")).encode("utf8")
    ).hexdigest()
    assert receipt["capture"]["signature_equal"] is True
    assert receipt["next_tick_diagnostic"]["predicted_signature"] == predicted_next_signature
    assert receipt["next_tick_diagnostic"]["observed_signature_sha256"] == hashlib.sha256(
        json.dumps(observed_next_signature, sort_keys=True, separators=(",", ":")).encode("utf8")
    ).hexdigest()
    assert {key: receipt["counts"][key] for key in (
        "arrival", "reinforcement", "combat", "capture", "ownership_change", "categories_overlap"
    )} == {
        "arrival": 1, "reinforcement": 0, "combat": 0, "capture": 1,
        "ownership_change": 1, "categories_overlap": True,
    }
    assert "do not sum" in receipt["counts"]["counting_rule"]
