from __future__ import annotations

from collections import Counter
import pytest

from tools import v2_post_arrival_inventory_disposition as disposition


TARGET = 1001
NEW_OWNER = 7
INCOMING = [5, 0, 0, 0, 0, 0, 0, 0, 0, 0]
ZERO = [0] * 10
SCOPE = ["doc", "match", 7, 100.0]


def fact(value, knowledge="OBSERVED"):
    return {"value": value, "knowledge": knowledge, "source": "synthetic negative control"}


def units(vector):
    return {"counts": [[index, value] for index, value in enumerate(vector)]}


def tower(owner=NEW_OWNER, inventory=INCOMING):
    return {
        # Real projected tower IDs are scalar integers, unlike fact-wrapped fields.
        "id": TARGET, "visibility": fact(True), "owner": fact(owner),
        "units": fact(units(inventory)), "capacity": fact(units([20] + [0] * 9)),
        "production": fact([]), "delay_ticks": fact(0),
        "supply_line_present": fact(None, "UNKNOWN"), "effects": fact([]),
    }


def force(*, owner=NEW_OWNER, source=TARGET, destination=2002, vector=None,
          observer_id="observer-1", source_knowledge="OBSERVED",
          owner_knowledge="OBSERVED", vector_knowledge="OBSERVED"):
    return {
        "id": fact(observer_id, "DERIVED"), "visibility": fact(True),
        "owner": fact(owner, owner_knowledge),
        "source": fact(source, source_knowledge), "destination": fact(destination),
        "units": fact(units(vector if vector is not None else [2] + [0] * 9), vector_knowledge),
        "progress": fact(17),
    }


def snapshot(tick, *, scope=None, towers=None, forces=None, coverage="PLAYER_VISIBLE_COMPLETE"):
    return {
        "provenance": {"scope": list(SCOPE if scope is None else scope),
                       "tick": tick, "coverage": coverage},
        "towers": list(towers if towers is not None else [tower()]),
        "forces": list(forces or []),
    }


def case(snapshots, *, incoming=INCOMING):
    return {
        "case_id": "synthetic:1", "cohort": "synthetic", "split": "development",
        "target_id": TARGET,
        "incoming_signature": [NEW_OWNER, 88, TARGET, list(incoming)],
        "classification": "MISMATCH",
        "disposition_snapshots": snapshots,
    }


def contiguous_snapshots(*, arrival_inventory=INCOMING, before_forces=None,
                         offset0_forces=None, offset1_forces=None, offset2_forces=None,
                         start=65534):
    # before=a-1, offset0=a; wraparound is intentional and must remain valid.
    return {
        "before": snapshot(start, towers=[tower(NEW_OWNER, ZERO)], forces=before_forces),
        "offset_0": snapshot((start + 1) % 65536,
                             towers=[tower(NEW_OWNER, arrival_inventory)], forces=offset0_forces),
        "offset_1": snapshot((start + 2) % 65536, forces=offset1_forces),
        "offset_2": snapshot((start + 3) % 65536, forces=offset2_forces),
    }


def test_outgoing_accounting_preserves_negative_residual_without_clipping():
    oversized = [6] + [0] * 9
    result = disposition.account_outgoing(INCOMING, ZERO, [oversized])

    assert result["status"] == "MISMATCH"
    assert result["expected_inventory_unclipped"] == [-1] + [0] * 9
    assert result["negative_components_retained"] is True


def test_negative_supplied_typed_counts_are_unknown_but_negative_residual_is_not():
    negative = [-1] + [0] * 9
    assert disposition.account_outgoing(negative, ZERO, [])["status"] == "UNKNOWN"
    assert disposition.account_outgoing(INCOMING, negative, [])["status"] == "UNKNOWN"
    assert disposition.account_outgoing(INCOMING, ZERO, [negative])["status"] == "UNKNOWN"

    # The prior oversized-vector control covers a derived -1 residual, which
    # must remain a mismatch rather than being clipped to zero.
    oversized = disposition.account_outgoing(
        INCOMING, ZERO, [[6] + [0] * 9])
    assert oversized["expected_inventory_unclipped"][0] == -1
    assert oversized["status"] == "MISMATCH"


def test_invalid_vector_or_incomplete_census_is_unknown_not_cherry_picked():
    malformed = [2] * 9
    incomplete = disposition.account_outgoing(INCOMING, ZERO, [malformed])
    censored = disposition.account_outgoing(INCOMING, INCOMING, [], accounting_complete=False)

    assert incomplete["status"] == "UNKNOWN"
    assert incomplete["observed_only_status"] == "UNKNOWN"
    assert censored["status"] == "UNKNOWN"
    assert censored["observed_only_status"] == "EXACT"


def test_same_signature_persistence_is_deduplicated_but_simultaneous_multiplicity_counts():
    outgoing = force(vector=[2] + [0] * 9, observer_id="id-a")
    same_signature_new_id = force(vector=[2] + [0] * 9, observer_id="id-b")
    snaps = contiguous_snapshots(
        arrival_inventory=[3] + [0] * 9,
        offset0_forces=[outgoing], offset1_forces=[same_signature_new_id],
    )

    result = disposition.analyze_case(case(snaps))
    assert result["target_context_by_offset"]["offset_0"]["status"] == "OBSERVED"
    assert result["primary_arrival_accounting"]["status"] == "EXACT"
    assert result["primary_arrival_accounting"]["outgoing_vector_count"] == 1
    assert result["new_outgoing_first_offset_case"] == 0
    assert len(result["first_observed_new_outgoing_0_2"]) == 1
    assert result["first_observed_new_outgoing_0_2"][0]["observer_id_supplemental"] == "id-a"

    duplicate = force(vector=[2] + [0] * 9, observer_id="id-c")
    multi = disposition.analyze_case(case(contiguous_snapshots(
        arrival_inventory=[1] + [0] * 9, offset0_forces=[outgoing, duplicate])))
    assert multi["primary_arrival_accounting"]["outgoing_vector_count"] == 2
    assert multi["primary_arrival_accounting"]["outgoing_sum"] == [4] + [0] * 9
    assert multi["primary_arrival_accounting"]["status"] == "EXACT"


def test_wrong_owner_outgoing_is_retained_but_not_subtracted():
    foreign = force(owner=9, vector=[3] + [0] * 9)
    result = disposition.analyze_case(case(contiguous_snapshots(
        offset0_forces=[foreign])))

    assert len(result["all_visible_outgoing_by_offset"]["offset_0"]) == 1
    assert result["first_observed_new_outgoing_0_2"][0]["same_owner_as_new_target"] is False
    assert result["primary_arrival_accounting"]["outgoing_vector_count"] == 0
    assert result["primary_arrival_accounting"]["status"] == "EXACT"


def test_wrong_source_force_is_not_misbound_to_captured_target():
    other_source = force(source=TARGET + 1)
    result = disposition.analyze_case(case(contiguous_snapshots(
        arrival_inventory=[3] + [0] * 9, offset0_forces=[other_source])))

    assert result["all_visible_outgoing_by_offset"]["offset_0"] == []
    assert result["first_observed_new_outgoing_0_2"] == []
    assert result["primary_arrival_accounting"]["status"] == "MISMATCH"


def test_unknown_source_owner_or_vector_alias_blocks_complete_accounting():
    unknown_source = force(source=TARGET, source_knowledge="UNKNOWN")
    source_result = disposition.analyze_case(case(contiguous_snapshots(
        offset0_forces=[unknown_source])))
    assert source_result["unknown_alias_completeness_block"] is True
    assert source_result["primary_arrival_accounting"]["status"] == "UNKNOWN"

    unknown_owner = force(owner=NEW_OWNER, owner_knowledge="UNKNOWN")
    owner_result = disposition.analyze_case(case(contiguous_snapshots(
        arrival_inventory=[3] + [0] * 9, offset0_forces=[unknown_owner])))
    assert owner_result["primary_arrival_accounting"]["status"] == "UNKNOWN"
    assert owner_result["primary_arrival_accounting"]["outgoing_vector_count"] == 0

    unknown_vector = force(vector=[2] + [0] * 9, vector_knowledge="UNKNOWN")
    unknown_vector["units"] = fact(None, "UNKNOWN")
    vector_result = disposition.analyze_case(case(contiguous_snapshots(
        arrival_inventory=[3] + [0] * 9, offset0_forces=[unknown_vector])))
    assert vector_result["primary_arrival_accounting"]["status"] == "UNKNOWN"
    assert vector_result["primary_arrival_accounting"]["outgoing_vector_count"] == 0


def test_before_existing_force_is_excluded_and_unknown_before_alias_is_reported():
    existing = force(vector=[2] + [0] * 9)
    snaps = contiguous_snapshots(before_forces=[existing], offset0_forces=[existing])
    result = disposition.analyze_case(case(snaps))

    assert result["before_existing_outgoing_multiplicity"]["known_signature_count"] == 1
    assert result["first_observed_new_outgoing_0_2"] == []
    assert result["primary_arrival_accounting"]["outgoing_vector_count"] == 0

    alias = force(source=TARGET, source_knowledge="UNKNOWN", vector=INCOMING)
    alias_result = disposition.analyze_case(case(contiguous_snapshots(before_forces=[alias])))
    assert alias_result["before_existing_outgoing_multiplicity"]["unknown_source_aliases"] == 1
    assert alias_result["before_existing_outgoing_multiplicity"]["plausible_same_owner_unknown_source_aliases"] == 1
    alias_row = alias_result["before_existing_outgoing_multiplicity"]["unknown_source_alias_rows"][0]
    assert alias_row["exact_incoming_vector_alias"] is True
    assert alias_row["first_appearance_uncertain"] is True
    assert alias_result["primary_arrival_accounting"]["status"] == "UNKNOWN"


@pytest.mark.parametrize("future_offset", [1, 2])
def test_offsets_one_and_two_cannot_rescue_primary_arrival_mismatch(future_offset):
    later = force(vector=[3] + [0] * 9)
    snaps = contiguous_snapshots(arrival_inventory=[2] + [0] * 9)
    snaps[f"offset_{future_offset}"]["forces"] = [later]
    result = disposition.analyze_case(case(snaps))

    assert result["primary_arrival_accounting"]["status"] == "MISMATCH"
    assert result["primary_positive_outgoing_exact"] is False
    assert result["supplementary_window_0_2_accounting"]["status"] == "EXACT"
    assert result["first_observed_new_outgoing_0_2"][0]["first_observed_offset"] == future_offset


def test_scope_tick_wrap_and_missing_observation_are_not_conflated():
    wrapped = disposition.analyze_case(case(contiguous_snapshots()))
    assert wrapped["time_scope_contiguous"] == {
        "before_to_arrival": True, "arrival_to_offset_1": True,
        "offset_1_to_offset_2": True,
    }

    broken = contiguous_snapshots()
    broken["offset_1"] = snapshot(0, scope=["other", "match", 7, 100.0])
    broken_result = disposition.analyze_case(case(broken))
    assert broken_result["time_scope_contiguous"]["arrival_to_offset_1"] is False
    assert broken_result["supplementary_window_0_2_accounting"]["status"] == "UNKNOWN"

    wrong_arrival_scope = contiguous_snapshots(arrival_inventory=[3] + [0] * 9,
                                                offset0_forces=[force()])
    wrong_arrival_scope["offset_0"] = snapshot(
        65535, scope=["other", "match", 7, 100.0],
        towers=[tower(NEW_OWNER, [3] + [0] * 9)], forces=[force()])
    wrong_scope_result = disposition.analyze_case(case(wrong_arrival_scope))
    assert wrong_scope_result["time_scope_contiguous"]["before_to_arrival"] is False
    assert wrong_scope_result["primary_arrival_accounting"]["status"] == "UNKNOWN"

    wrong_arrival_tick = contiguous_snapshots(arrival_inventory=[3] + [0] * 9,
                                               offset0_forces=[force()])
    wrong_arrival_tick["offset_0"] = snapshot(
        3, towers=[tower(NEW_OWNER, [3] + [0] * 9)], forces=[force()])
    wrong_tick_result = disposition.analyze_case(case(wrong_arrival_tick))
    assert wrong_tick_result["time_scope_contiguous"]["before_to_arrival"] is False
    assert wrong_tick_result["primary_arrival_accounting"]["status"] == "UNKNOWN"

    missing = contiguous_snapshots()
    missing["offset_2"] = None
    missing_result = disposition.analyze_case(case(missing))
    assert missing_result["time_scope_contiguous"]["offset_1_to_offset_2"] is False
    assert missing_result["source_census_by_offset"]["offset_2"]["census_complete"] is False
    assert missing_result["supplementary_window_0_2_accounting"]["status"] == "UNKNOWN"

    incomplete_scope = contiguous_snapshots()
    incomplete_scope["before"]["provenance"]["scope"] = []
    incomplete_scope["offset_0"]["provenance"]["scope"] = []
    incomplete_scope_result = disposition.analyze_case(case(incomplete_scope))
    assert incomplete_scope_result["time_scope_contiguous"]["before_to_arrival"] is False
    assert incomplete_scope_result["primary_arrival_accounting"]["status"] == "UNKNOWN"

    missing_scope = contiguous_snapshots()
    del missing_scope["before"]["provenance"]["scope"]
    del missing_scope["offset_0"]["provenance"]["scope"]
    missing_scope_result = disposition.analyze_case(case(missing_scope))
    assert missing_scope_result["time_scope_contiguous"]["before_to_arrival"] is False
    assert missing_scope_result["primary_arrival_accounting"]["status"] == "UNKNOWN"


def test_original_population_and_split_remain_exactly_45_with_13_32_classes():
    population = disposition.load_population()
    dev, holdout = population["development"], population["holdout"]
    cases = dev + holdout

    assert len(dev) == 24
    assert len(holdout) == 21
    assert len(cases) == 45
    assert len({row["case_id"] for row in cases}) == 45
    assert Counter(row["classification"] for row in cases) == Counter({
        "MATCH": 13, "MISMATCH": 32,
    })


def test_inventory_owner_only_credit_stays_hypothesis_without_promotion():
    freeze = disposition.json.loads(disposition.FREEZE.read_text(encoding="utf-8"))
    hypothesis = freeze["hypotheses"]["OWNER_ONLY_CAPTURE"]

    assert "hypothesis only" in hypothesis.lower()
    assert freeze["limits"]["production_default"] == "NONE"
    assert disposition.BASELINE_HEAD == freeze["baseline_head"]
    assert disposition.FREEZE_COMMIT != disposition.BASELINE_HEAD
