from __future__ import annotations

from copy import deepcopy

from tools.v2_goal_action_verifier import verify_case


def f(value, knowledge="OBSERVED"):
    return {"value": value, "knowledge": knowledge}


def units(**counts):
    values = {k: 0 for k in range(10)}
    values.update({int(kind): value for kind, value in counts.items()})
    pairs = [[kind, value] for kind, value in values.items()]
    return f({"counts": pairs})


def tower(ident, owner, soldier, *, production=(), supply=False):
    return {"id": ident, "visibility": f(True), "owner": f(owner), "tower_type": f(1),
            "delay_ticks": f(0), "effects": f([]), "production": f(list(production)),
            "units": units(**({"5": soldier} if soldier else {})),
            "deployable": units(**({"5": soldier} if ident == 10 and soldier else {})),
            "capacity": units(**{"0": 20, "1": 20, "2": 20, "3": 20,
                                  "4": 20, "5": 20, "6": 20, "7": 20,
                                  "8": 20, "9": 20}),
            "supply_line_present": f(supply)}


def state(tick, *, source_soldier, destination_soldier, force_rows=(),
          dest_owner=7, source_production=(), dest_production=(),
          endpoint_ids_known=True):
    return {"document_id": "doc-A", "client_sha256": "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c", "match_id": f("match-A"), "player_id": f(7),
            "lifecycle": f("IN_MATCH"), "tick": f(tick), "coverage": "PLAYER_VISIBLE_COMPLETE",
            "source_mode": f("NETWORK"),
            "towers": [tower(10, 7, source_soldier, production=source_production),
                       tower(20, dest_owner, destination_soldier, production=dest_production)],
            "forces": f(list(force_rows))}


def force(ident="new-force", *, source=10, destination=20, owner=7,
          soldier=2, progress=0, confidence="NEW_TRACK"):
    return {"id": f(ident), "visibility": f(True), "owner": f(owner),
            "source": f(source) if source is not None else f(None, "UNKNOWN"),
            "destination": f(destination) if destination is not None else f(None, "UNKNOWN"),
            "units": units(**({"5": soldier} if soldier is not None else {})),
            "progress": f(progress), "confidence": f(confidence)}


def valid_records():
    before = state(65534, source_soldier=2, destination_soldier=0)
    birth = state(65535, source_soldier=0, destination_soldier=0,
                  force_rows=[force()])
    arrival = state(0, source_soldier=0, destination_soldier=2)
    intent = {"kind": "ACTION_INTENT", "command_index": 1, "intent_id": "i-1",
              "document_id": "doc-A", "client_sha256": "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c",
              "match_epoch": {"document_id": "doc-A", "match_id": "match-A", "player_id": 7, "lifecycle": "IN_MATCH"},
              "world_sequence": 65534,
              "source": {"tower_id": 10, "tower_type": 1}, "destination": {"tower_id": 20, "tower_type": 1},
              "player_id": 7, "intended_unit_vector": [[5, 2]],
              "input_method": "official Playwright page mouse", "intended_action": "ALL_CURRENT_DEPLOYABLE",
              "ui_action_type": "ordinary_manual_deploy_force_canvas_drag",
              "selected_tower_none_confirmed": True,
              "prior_force_ids": [], "pre_action_source_supply_line_present": False,
              "preexisting_visible_inbound_force_to_source": False}
    return [
        {"kind": "BEFORE_INTENT", "command_index": 1, "state": before,
         "source": 10, "destination": 20, "tick": 65534,
         "BEFORE": {"source": 10, "destination": 20},
         "before_only_route_certificate": {"qualified": True, "scope": "BEFORE_SNAPSHOT_ONLY"}}, intent,
        {"kind": "UI_ACTION_RESULT", "command_index": 1, "intent_id": "i-1",
         "ui_delivery_status": "SUCCESS", "mouse_down_host_monotonic_ms": 100,
         "mouse_up_host_monotonic_ms": 120},
        {"kind": "AFTER_DISTINCT_TICK", "command_index": 1,
         "observation": {"tick": 65535, "state": birth}},
        {"kind": "AFTER_DISTINCT_TICK", "command_index": 1,
         "observation": {"tick": 0, "state": arrival}},
        {"kind": "COMMAND_RESULT", "command_index": 1, "supply_line_guard_passed": True,
         "arrival_cue": {"tick": 0, "basis": "visible endpoint change and matching force absent"},
         "action_ledger_association": {"status": "CANDIDATE_MATCHED"}},
    ]


def test_complete_evidence_is_success_even_with_candidate_diagnostic():
    result = verify_case(valid_records())
    assert result["status"] == "SUCCESS"
    assert result["candidate_birth_offset"] == 1


def test_ui_success_and_candidate_match_do_not_replace_source_or_arrival_proof():
    rows = valid_records()
    rows[3]["observation"]["state"]["towers"][0]["units"] = units(**{"5": 2})
    rows[5]["arrival_cue"] = None
    result = verify_case(rows)
    assert result["status"] == "UNKNOWN"
    assert "SOURCE_DEPLETION_DOES_NOT_EQUAL_BIRTH_VECTOR" in result["reasons"]
    assert "DESTINATION_ARRIVAL_CUE_NOT_BOUND_TO_SNAPSHOT" in result["reasons"]


def test_unknown_endpoint_alias_blocks_unique_birth_claim():
    rows = valid_records()
    rows[3]["observation"]["state"]["forces"]["value"].append(
        force("possible-alias", source=None, destination=None, soldier=1))
    result = verify_case(rows)
    assert result["status"] == "UNKNOWN"
    assert "UNKNOWN_ENDPOINT_OWN_FORCE_ALIAS" in result["reasons"]


def test_source_production_or_supply_ambiguity_is_unknown():
    rows = valid_records()
    rows[0]["state"]["towers"][0]["production"] = f([[5, 4]])
    result = verify_case(rows)
    assert result["status"] == "UNKNOWN"
    assert "SOURCE_PRODUCTION_COULD_EXPLAIN_BIRTH" in result["reasons"]


def test_destination_production_and_force_persistence_block_success():
    rows = valid_records()
    rows[5]["arrival_cue"]["tick"] = 0
    rows[4]["observation"]["state"]["towers"][1]["production"] = f([[5, 4]])
    rows[4]["observation"]["state"]["forces"]["value"] = [force(progress=1, confidence="TRACKED")]
    result = verify_case(rows)
    assert result["status"] == "UNKNOWN"
    assert "DESTINATION_PRODUCTION_COULD_EXPLAIN_INVENTORY_CHANGE" in result["reasons"]
    assert "MATCHED_FORCE_NOT_KNOWN_DISAPPEARED_AT_ARRIVAL" in result["reasons"]


def test_epoch_or_tick_discontinuity_is_not_success():
    rows = valid_records()
    rows[3]["observation"]["state"]["tick"] = f(1)
    result = verify_case(rows)
    assert result["status"] == "UNKNOWN"
    assert "NONCONSECUTIVE_WORLD_TICKS" in result["reasons"]


def test_unknown_stale_inventory_does_not_count_as_conservation():
    rows = valid_records()
    rows[3]["observation"]["state"]["towers"][0]["units"]["knowledge"] = "UNKNOWN"
    result = verify_case(rows)
    assert result["status"] == "UNKNOWN"
    assert "SOURCE_INVENTORY_UNKNOWN" in result["reasons"]


def test_capacity_loss_cannot_mimic_source_depletion():
    rows = valid_records()
    rows[3]["observation"]["state"]["towers"][0]["capacity"] = units(**{"5": 1})
    result = verify_case(rows)
    assert result["status"] == "UNKNOWN"
    assert "SOURCE_CAPACITY_CHANGED_DURING_BIRTH" in result["reasons"]


def test_malformed_after_snapshot_and_force_gap_do_not_get_skipped():
    malformed = valid_records()
    malformed[3]["observation"] = {}
    assert "AFTER_TICK_STATE_MISSING_OR_MALFORMED" in verify_case(malformed)["reasons"]

    gap = valid_records()
    missing = deepcopy(gap[4])
    missing["observation"]["state"]["tick"] = f(0)
    missing["observation"]["state"]["towers"][1]["units"] = units()
    later = state(1, source_soldier=0, destination_soldier=2)
    gap.append({"kind": "AFTER_DISTINCT_TICK", "command_index": 1,
                "observation": {"tick": 1, "state": later}})
    gap[4] = missing
    gap[5]["arrival_cue"]["tick"] = 1
    result = verify_case(gap)
    assert result["status"] == "UNKNOWN"
    assert "FORCE_CONTINUATION_GAP_OR_AMBIGUITY_BEFORE_ARRIVAL" in result["reasons"]


def test_persistent_unique_continuation_is_one_birth_not_multiple():
    rows = valid_records()
    continuation = state(0, source_soldier=0, destination_soldier=0,
                         force_rows=[force(progress=1, confidence="UNIQUE_CONTINUATION")])
    rows[4]["observation"] = {"tick": 0, "state": continuation}
    arrival = state(1, source_soldier=0, destination_soldier=2)
    rows.insert(5, {"kind": "AFTER_DISTINCT_TICK", "command_index": 1,
                    "observation": {"tick": 1, "state": arrival}})
    rows[-1]["arrival_cue"]["tick"] = 1
    assert verify_case(rows)["status"] == "SUCCESS"
    rows[4]["observation"]["state"]["forces"]["value"][0]["confidence"] = f("NEW_TRACK")
    assert verify_case(rows)["status"] == "UNKNOWN"

def test_empty_or_missing_intent_vector_is_never_zero():
    for value in (None, [], "unknown"):
        rows = valid_records()
        rows[1]["intended_unit_vector"] = value
        result = verify_case(rows)
        assert result["status"] == "UNKNOWN"
        assert "INTENDED_VECTOR_UNKNOWN_OR_INVALID" in result["reasons"]

def test_route_pin_network_and_coverage_are_required():
    cases = []
    no_route = valid_records()
    no_route[0].pop("before_only_route_certificate")
    cases.append(no_route)
    wrong_pin = valid_records()
    wrong_pin[0]["state"]["client_sha256"] = "other-build"
    cases.append(wrong_pin)
    partial = valid_records()
    partial[3]["observation"]["state"]["coverage"] = "PARTIAL"
    cases.append(partial)
    offline = valid_records()
    offline[3]["observation"]["state"]["source_mode"] = f("OFFLINE")
    cases.append(offline)
    for rows in cases:
        assert verify_case(rows)["status"] == "UNKNOWN"

def test_external_or_unknown_inbound_is_competing_even_when_it_disappears():
    for owner, destination in ((99, 20), (99, None)):
        rows = valid_records()
        rival = force("rival", owner=owner, source=30, destination=destination, progress=1)
        rows[0]["state"]["forces"]["value"] = [rival]
        rows[1]["prior_force_ids"] = ["rival"]
        result = verify_case(rows)
        assert result["status"] == "UNKNOWN"
        assert "COMPETING_OR_UNKNOWN_DESTINATION_INBOUND" in result["reasons"]


def test_same_result_epoch_cannot_be_used_as_in_match_action_evidence():
    rows = valid_records()
    rows[0]["state"]["lifecycle"] = f("RESULT")
    rows[1]["match_epoch"]["lifecycle"] = "RESULT"
    for row in rows:
        if row.get("kind") == "AFTER_DISTINCT_TICK":
            row["observation"]["state"]["lifecycle"] = f("RESULT")
    assert verify_case(rows)["status"] == "UNKNOWN"
