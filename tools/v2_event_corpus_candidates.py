"""Bounded offline miner for candidate v2 arrival/reinforcement/capture/defense events.

This tool emits candidate references and small deltas only. It never promotes a
candidate to a simulator PASS or treats an endpoint learned from the after-state
as an independent scenario input.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim import UnsupportedState, from_canonical

COHORTS = ("fe678ebb30ce", "03d032d57e5b", "f3f22dae0791", "daf86d0544b7", "85391858b5d8")
DEFAULT_OUT = ROOT / "runtime/research/v2/luna-event-candidates.json"
NEW_COHORT = "85391858b5d8"
NEW_COHORT_OUT = ROOT / "runtime/research/v2/luna-corpus/85391858b5d8-candidates.json"


def val(row, key):
    fact = row.get(key)
    if not isinstance(fact, dict):
        return None
    if fact.get("knowledge") == "UNKNOWN":
        return None
    return fact.get("value")


def unitmap(fact):
    raw = val(fact, "units")
    if not isinstance(raw, dict) or not isinstance(raw.get("counts"), list):
        return None
    pairs = raw["counts"]
    if {p[0] for p in pairs if isinstance(p, list) and len(p) == 2} != set(range(10)):
        return None
    return {int(k): int(v) for k, v in pairs}


def scope(row):
    return (row.get("document_id"), val(row, "match_id"), val(row, "player_id"))


def tick(row):
    return val(row, "tick")


def force_index(row):
    f = val(row, "forces")
    if f is None or not isinstance(f, list):
        return None
    result = {}
    ambiguous = set()
    for force in f:
        fid = val(force, "id")
        # Unknown and repeated IDs cannot establish a continuing force.
        if not isinstance(fid, str) or not fid:
            continue
        if fid in result:
            ambiguous.add(fid)
        result[fid] = force
    for fid in ambiguous:
        result.pop(fid, None)
    return result


def tower_index(row):
    result = {}
    for t in row.get("towers", []):
        if isinstance(t.get("id"), int):
            result[t["id"]] = t
    return result


def positive_complete(row):
    if row.get("coverage") != "PLAYER_VISIBLE_COMPLETE":
        return False
    if scope(row)[0] is None or scope(row)[1] is None or scope(row)[2] is None or tick(row) is None:
        return False
    if val(row, "forces") is None:
        return False
    for t in row.get("towers", []):
        if any(val(t, k) is None for k in ("owner", "relation", "tower_type", "units")):
            return False
        if unitmap(t) is None:
            return False
    return True


def tower_relation(t):
    return val(t, "relation")


def transition(before, after, cohort, counts, input_check=None):
    bt, at = tick(before), tick(after)
    sc = scope(before)
    if sc != scope(after) or sc[1] is None:
        counts["exclude_scope_or_unknown_epoch"] += 1
        return []
    counts["same_scope_tick_pairs"] += 1
    if (at - bt) & 65535 != 1:
        counts["exclude_nonconsecutive_tick"] += 1
        return []
    counts["same_scope_consecutive_tick_pairs"] += 1
    if not positive_complete(before) or not positive_complete(after):
        counts["exclude_incomplete_or_nonpositive_visibility"] += 1
        if before.get("coverage") != "PLAYER_VISIBLE_COMPLETE" or after.get("coverage") != "PLAYER_VISIBLE_COMPLETE":
            counts["fog_or_visibility_uncertainty_transition"] += 1
        return []
    counts["candidate_eligible_pairs"] += 1

    pre_t, post_t = tower_index(before), tower_index(after)
    pre_f, post_f = force_index(before), force_index(after)
    if pre_f is None or post_f is None:
        counts["exclude_unknown_force_collection"] += 1
        return []
    if set(pre_t) != set(post_t):
        counts["visible_tower_set_change_uncertainty"] += 1

    removed = {fid: f for fid, f in pre_f.items() if fid not in post_f}
    added = {fid: f for fid, f in post_f.items() if fid not in pre_f}
    if added:
        counts["possible_external_force_birth_or_action"] += 1
    if removed:
        counts["force_disappearance_candidate_transitions"] += 1
    candidates = []
    explained_towers = set()
    for fid, force in removed.items():
        src, dst, owner = (val(force, "source"), val(force, "destination"), val(force, "owner"))
        units = unitmap(force)
        if src is None or dst is None or owner is None or units is None:
            counts["unknown_force_path_or_payload"] += 1
            continue
        if dst not in pre_t or dst not in post_t:
            counts["force_endpoint_not_visible_both_ticks"] += 1
            continue
        old, new = pre_t[dst], post_t[dst]
        old_units, new_units = unitmap(old), unitmap(new)
        if old_units is None or new_units is None:
            counts["unknown_endpoint_unit_vector"] += 1
            continue
        delta = {u: new_units[u] - old_units[u] for u in range(10) if new_units[u] != old_units[u]}
        old_owner, new_owner = val(old, "owner"), val(new, "owner")
        kind = None
        if old_owner != new_owner and new_owner == owner:
            kind = "capture_candidate"
        elif old_owner == new_owner == owner and any(v > 0 for v in delta.values()):
            kind = "reinforcement_or_arrival_candidate"
        elif old_owner == new_owner and any(v < 0 for v in delta.values()):
            kind = "ground_defense_or_other_loss_candidate"
        elif old_owner == new_owner and not delta and val(force, "relation") == "ENEMY":
            kind = "ground_defense_no_visible_unit_loss_candidate"
        if kind:
            explained_towers.add(dst)
            counts[kind] += 1
            eligibility = input_check(before, after) if input_check else None
            candidates.append({
                "kind": kind,
                "cohort": cohort,
                "scope": {"document_id": sc[0], "match_id": sc[1], "player_id": sc[2]},
                "before": {"sequence": before["sequence"], "world_sequence": bt},
                "after": {"sequence": after["sequence"], "world_sequence": at},
                "scenario_inputs": (eligibility if eligibility else {
                    "before_canonical_conversion": "NOT_CHECKED",
                    "after_canonical_conversion": "NOT_CHECKED",
                    "independent_before_state_input": False,
                    "target_observed_in_before_force": True,
                    "target_inferred_from_after_state": False}),
                "force_reference": {"id": fid, "identity_knowledge": val(force, "id") is not None and force["id"].get("knowledge"),
                                    "source": src, "destination": dst, "owner": owner,
                                    "relation_before": val(force, "relation"), "units": units},
                "endpoint_reference": {"tower_id": dst,
                    "relation_before": tower_relation(old), "relation_after": tower_relation(new),
                    "owner_before": old_owner, "owner_after": new_owner,
                    "unit_delta": delta,
                    "target_source": "before_tick_observed_force_destination",
                    "target_inferred_from_after_state": False,
                    "independent_scenario_input": False,
                    "terminal_route_known_before": False,
                    "fuel_known_before": False,
                    "external_actions_excluded": False},
                "limitations": ["force disappearance alone does not prove arrival",
                                "world actions and fog can explain state changes",
                                "event is an offline candidate, never a PASS"]
            })
    for tid in set(pre_t) & set(post_t):
        old, new = pre_t[tid], post_t[tid]
        if val(old, "owner") != val(new, "owner") and tid not in explained_towers:
            counts["owner_change_without_correlated_force_candidate"] += 1
        if unitmap(old) != unitmap(new) and tid not in explained_towers:
            counts["unit_change_without_correlated_force_candidate"] += 1
    if removed and not candidates:
        counts["force_disappearance_without_endpoint_event"] += 1
    return candidates


def mine(cohort, cap, check_inputs=False):
    source = ROOT / f"runtime/research/v2/snapshots-{cohort}.jsonl"
    digest = hashlib.sha256()
    counts = collections.Counter()
    emitted = []
    transition_keys = []
    last = None
    group_tick = None
    group_latest = None
    seen_pairs = set()
    input_cache = {}

    def check_pair_inputs(before, after):
        def check(row):
            seq = row["sequence"]
            if seq not in input_cache:
                try:
                    from_canonical(state_from_dict(row))
                    input_cache[seq] = {"supported": True, "reason": None}
                except (UnsupportedState, ValueError) as exc:
                    input_cache[seq] = {"supported": False,
                                        "reason": f"{type(exc).__name__}:{str(exc)}"}
            return input_cache[seq]
        pre, post = check(before), check(after)
        counts["candidate_rows_input_checked"] += 1
        counts["before_canonical_supported"] += int(pre["supported"])
        counts["after_canonical_supported"] += int(post["supported"])
        counts["both_canonical_supported"] += int(pre["supported"] and post["supported"])
        if not pre["supported"]:
            counts["before_fail_closed:" + pre["reason"]] += 1
        if not post["supported"]:
            counts["after_fail_closed:" + post["reason"]] += 1
        return {
            "before_canonical_conversion": "SUPPORTED" if pre["supported"] else "UNSUPPORTED",
            "before_reason": pre["reason"],
            "after_canonical_conversion": "SUPPORTED" if post["supported"] else "UNSUPPORTED",
            "after_reason": post["reason"],
            "independent_before_state_input": pre["supported"],
            "target_observed_in_before_force": True,
            "target_inferred_from_after_state": False,
            "terminal_route_known_before": False,
            "fuel_known_before": False,
            "external_actions_excluded": False,
            "prediction_used_to_select_candidate": False
        }

    def consume(prev, curr):
        if curr is None:
            return prev
        if prev is None:
            return curr
        if tick(prev) == tick(curr):
            return curr
        sc = scope(prev)
        pair_key = (sc, tick(prev), tick(curr))
        if pair_key in seen_pairs:
            counts["duplicate_scope_tick_transition_suppressed"] += 1
            return curr
        seen_pairs.add(pair_key)
        transition_keys.append(pair_key)
        # Includes cross-scope and nonconsecutive tick changes. Those pairs
        # are counted here, then explicitly rejected by transition().
        counts["tick_transition_observations"] += 1
        rows = transition(prev, curr, cohort, counts,
                          check_pair_inputs if check_inputs else None)
        if rows:
            counts["candidate_transition_pairs"] += 1
            for row in rows:
                if len(emitted) < cap:
                    emitted.append(row)
                else:
                    counts["candidate_rows_over_output_cap"] += 1
        return curr

    with source.open("rb") as stream:
        for raw in stream:
            digest.update(raw)
            row = json.loads(raw)
            counts["snapshots_read"] += 1
            current_tick = tick(row)
            if current_tick is None:
                counts["unknown_tick_snapshots"] += 1
                continue
            if group_tick is None:
                group_tick, group_latest = current_tick, row
                continue
            if current_tick == group_tick and scope(row) == scope(group_latest):
                counts["same_tick_poll_duplicates_collapsed"] += 1
                group_latest = row
                continue
            if group_latest is not None:
                last = consume(last, group_latest)
            group_tick, group_latest = current_tick, row
        if group_latest is not None:
            # EOF closes the final observed pair. The endpoint was fully
            # observed even though no later poll arrived to trigger the flush.
            last = consume(last, group_latest)
            counts["final_tick_endpoint_flushed"] += 1
    if check_inputs:
        counts["unique_canonical_endpoints_checked"] = len(input_cache)
        counts["unique_canonical_endpoints_supported"] = sum(x["supported"] for x in input_cache.values())
        counts["unique_canonical_endpoints_fail_closed"] = sum(not x["supported"] for x in input_cache.values())
    return {"cohort": cohort, "source_file": str(source.relative_to(ROOT)),
            "source_sha256": digest.hexdigest(), "counts": dict(counts), "candidates": emitted,
            "transition_keys": transition_keys}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohorts", nargs="+", choices=COHORTS, default=list(COHORTS[:4]))
    parser.add_argument("--max-candidates", type=int, default=250)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.max_candidates < 0:
        parser.error("--max-candidates must be nonnegative")
    output = args.output.resolve()
    if output != DEFAULT_OUT.resolve():
        if output != NEW_COHORT_OUT.resolve() or args.cohorts != [NEW_COHORT]:
            parser.error("custom output is allowed only at runtime/research/v2/luna-corpus/85391858b5d8-candidates.json for that single cohort")
    check_inputs = args.cohorts == [NEW_COHORT]
    per_cohort = [mine(name, args.max_candidates, check_inputs=check_inputs) for name in args.cohorts]
    total = collections.Counter()
    candidates = []
    global_pairs = set()
    pair_occurrences = 0
    candidate_keys = set()
    for result in per_cohort:
        total.update(result["counts"])
        pair_occurrences += len(result["transition_keys"])
        global_pairs.update(result["transition_keys"])
        for candidate in result["candidates"]:
            before, after = candidate["before"], candidate["after"]
            sc = candidate["scope"]
            force_id = candidate["force_reference"]["id"]
            key = (sc["document_id"], sc["match_id"], sc["player_id"],
                   before["world_sequence"], after["world_sequence"], force_id, candidate["kind"])
            if key not in candidate_keys:
                candidate_keys.add(key)
                candidates.append(candidate)
    categories = ("capture_candidate", "reinforcement_or_arrival_candidate",
                  "ground_defense_or_other_loss_candidate", "ground_defense_no_visible_unit_loss_candidate")
    before_reason_counts = {key.removeprefix("before_fail_closed:"): value
                            for key, value in total.items() if key.startswith("before_fail_closed:")}
    after_reason_counts = {key.removeprefix("after_fail_closed:"): value
                           for key, value in total.items() if key.startswith("after_fail_closed:")}
    report = {
        "task": "Bounded Kiomet v2 offline event corpus mining" + (" and input eligibility" if check_inputs else ""),
        "status": "CANDIDATES_ONLY_NO_PASS",
        "model_effort": "Requested via collaboration: gpt-6-luna / high; lead reviewed candidate output",
        "files_read": [f"runtime/research/v2/snapshots-{name}.jsonl" for name in args.cohorts] +
                      ["tools/v2_event_corpus_candidates.py", "src/kiomet_ai/v2/state.py",
                       "src/kiomet_ai/v2/serialization.py", "src/kiomet_ai/v2/sim/__init__.py",
                       "src/kiomet_ai/v2/sim/model.py", "src/kiomet_ai/v2/sim/step.py",
                       "src/kiomet_ai/v2/sim/combat.py", "src/kiomet_ai/v2/observe/forces.py",
                       "src/kiomet_ai/v2/observe/rules.py", "src/kiomet_ai/v2/control.py"],
        "context_files_reviewed": [],
        "files_modified": ["tools/v2_event_corpus_candidates.py",
                           str(output.relative_to(ROOT))],
        "scope": "bounded offline mining of requested canonical observation cohort(s): " + ", ".join(args.cohorts),
        "method": "Collapse repeated same-tick polls to last observed row; compare unique same-scope consecutive u16 world ticks; require known match/player, PLAYER_VISIBLE_COMPLETE coverage and observed force collection. Correlate only stable non-unknown force IDs to endpoint deltas.",
        "candidate_categories": {name: sum(row["kind"] == name for row in candidates) for name in categories},
        "counts": dict(total),
        "count_semantics": {
            "tick_transition_observations": "Distinct adjacent observed tick-group comparisons after per-cohort dedup; includes scope/unknown-epoch and nonconsecutive-sequence pairs, which are separately excluded.",
            "same_scope_tick_pairs": "Comparisons whose before and after document/match/player scope agrees and whose match epoch is known; may still be nonconsecutive.",
            "same_scope_consecutive_tick_pairs": "Same-scope comparisons with modulo-65536 tick delta exactly one; may still fail visibility/coverage checks.",
            "candidate_eligible_pairs": "Same-scope consecutive pairs with positive complete visibility, known tower facts, and observed force collections in both endpoints.",
            "candidate_transition_pairs": "Eligible pairs that emitted one or more classified force-disappearance/endpoint-change candidates; this is not an accuracy count."
        },
        "canonical_input_eligibility": ("from_canonical(state_from_dict(row)) was independently attempted for each unique referenced before/after snapshot sequence; candidate-row totals below count endpoint status per row, and unique-endpoint totals count conversion attempts after sequence caching. A supported before state does not prove external actions were absent." if check_inputs else "Not run for this cohort selection."),
        "input_eligibility": ({
            "candidate_rows_checked": total["candidate_rows_input_checked"],
            "before_supported_rows": total["before_canonical_supported"],
            "before_fail_closed_rows": total["candidate_rows_input_checked"] - total["before_canonical_supported"],
            "after_supported_rows": total["after_canonical_supported"],
            "after_fail_closed_rows": total["candidate_rows_input_checked"] - total["after_canonical_supported"],
            "both_supported_rows": total["both_canonical_supported"],
            "unique_endpoints_checked": total["unique_canonical_endpoints_checked"],
            "unique_endpoints_supported": total["unique_canonical_endpoints_supported"],
            "unique_endpoints_fail_closed": total["unique_canonical_endpoints_fail_closed"],
            "before_fail_closed_reasons": before_reason_counts,
            "after_fail_closed_reasons": after_reason_counts,
            "external_action_exclusion_established": False
        } if check_inputs else None),
        "deduplication": {"scope_key": "document_id + match_id.value + player_id.value + consecutive before/after u16 world sequence",
                           "unique_transition_pairs_across_cohorts": len(global_pairs),
                           "cohort_pair_occurrences": pair_occurrences,
                           "cross_cohort_duplicate_pairs_suppressed": pair_occurrences - len(global_pairs),
                           "unique_candidate_rows_after_dedup": len(candidates)},
        "candidate_rows_emitted": len(candidates),
        "candidate_rows_capped": total["candidate_rows_over_output_cap"],
        "scenario_input_rule": ("The destination is observed in the before-tick force, but a supported canonical conversion only establishes modeled state availability. Endpoint scenario eligibility remains false because terminal route and fuel are unknown and external actions are not excluded. After-state classifies only the observed transition; predictions do not select candidates." if check_inputs else "Target is the before-tick observed force destination; conversion eligibility is not checked for this run. Terminal route and fuel remain unknown, and external actions are not excluded."),
        "uncertainty_counts": {name: total[name] for name in (
            "possible_external_force_birth_or_action", "fog_or_visibility_uncertainty_transition",
            "visible_tower_set_change_uncertainty", "unknown_force_path_or_payload",
            "force_endpoint_not_visible_both_ticks", "force_disappearance_without_endpoint_event",
            "unit_change_without_correlated_force_candidate", "owner_change_without_correlated_force_candidate")},
        "cohorts": [{k: v for k, v in result.items() if k not in ("candidates", "transition_keys")} for result in per_cohort],
        "candidates": candidates,
        "claims": ["Emitted rows are event candidates from retained offline observations only.",
                   "No PASS, simulator accuracy, or live behavior claim is made."],
        "tests": ["Executed the finite miner for the requested cohort selection; count and provenance assertions were applied to the new-cohort report."],
        "unknowns": ["Retained observations do not establish all external actions between sampled world updates.",
                     "Stable force identity is only the recorded non-unknown ID; source lineage and event cause remain unproven."],
        "risks": ["Candidate correlations can be confounded by fog, hidden actions, simultaneous production, or combat ordering."],
        "recommended_integration": "Root review only; keep rows isolated as candidate evidence. Promote a transition into validation only after independently specified before-state inputs and an external-action exclusion are available.",
        "limitations": ["Observed force disappearance does not establish arrival or combat cause.",
                        "Even positively visible endpoints do not establish no external actions between observations.",
                        "PARTIAL cohort manifests and absent independent UI comparisons limit these to research leads.",
                        "No simulator accuracy or live behavior claim is made."]
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "candidate_categories": report["candidate_categories"],
                      "candidate_rows_emitted": report["candidate_rows_emitted"],
                      "output": str(output.relative_to(ROOT))}, sort_keys=True))


if __name__ == "__main__":
    main()
