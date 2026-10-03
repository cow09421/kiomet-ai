"""One frozen DEV capability report; no Planner or Final scoring."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
try:
    from tools.v2_goal_decision_harness import admit_case, evaluate, visible_state
except ModuleNotFoundError:
    from v2_goal_decision_harness import admit_case, evaluate, visible_state


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _outcome(result):
    if result["status"] != "EVALUATED":
        return {"status": result["status"], "reasons": result.get("reasons", [])}
    return {key: result[key] for key in
            ("terminal", "terminal_processed", "pending_core_losses", "alive", "final_towers", "final_forces")}


def build_report(fixture_path, source_root):
    payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload.get("source_manifest"):
        raise ValueError("frozen public source manifest required before evaluation")
    for name, expected in payload["source_manifest"].items():
        actual = hashlib.sha256((Path(source_root) / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"primary source changed before evaluation: {name}")
    rows = payload["cases"]
    cases = [row["case"] for row in rows]
    ids = [case["case_id"] for case in cases]
    strata = {f"S{i}": sum(case["stratum"].split("_", 1)[0] == f"S{i}" for case in cases)
              for i in range(1, 7)}
    if len(ids) != 12 or len(set(ids)) != 12 or any(n != 2 for n in strata.values()):
        raise ValueError("frozen DEV population must have exactly two unique cases per S1-S6")
    reports = []
    groups = {}
    for case in cases:
        admission = admit_case(case)
        if admission["status"] != "SUPPORTED":
            reports.append({"case_id": case["case_id"], "admission": admission,
                            "meaningful_alternatives": False, "actions": []})
            continue
        view = visible_state(case)
        view_key = _digest(asdict(view))
        actions = []
        for action in view.legal_choices:
            result = evaluate(case, action)
            outcome = _outcome(result)
            actions.append({"choice": action.as_dict(), "status": result["status"],
                            "outcome": outcome, "outcome_sha256": _digest(outcome),
                            "ticks_evaluated": result.get("ticks_evaluated"),
                            "trace_sha256": _digest(result.get("trace", []))})
        meaningful = len({a["outcome_sha256"] for a in actions}) >= 2
        record = {"case_id": case["case_id"], "stratum": case["stratum"],
                  "admission": admission, "view_sha256": view_key,
                  "legal_choice_count": len(view.legal_choices),
                  "meaningful_alternatives": meaningful, "actions": actions}
        reports.append(record)
        if case["stratum"].split("_", 1)[0] == "S6":
            groups.setdefault(view_key, []).append(record)
    uncertainty = []
    for key, group in groups.items():
        by_choice = {}
        for record in group:
            for action in record["actions"]:
                choice_key = json.dumps(action["choice"], sort_keys=True)
                item = by_choice.setdefault(choice_key, {"choice": action["choice"], "realized": {}})
                item["realized"][action["outcome_sha256"]] = action["outcome"]
        uncertainty.append({"view_sha256": key, "case_ids": [r["case_id"] for r in group],
                            "same_current_view": len(group) == 2,
                            "action_support": [{"choice": item["choice"],
                                                "realized_outcomes": list(item["realized"].values()),
                                                "realized_count": len(item["realized"])}
                                               for item in by_choice.values()],
                            "probability_calibration_claim": False})
    success = (all(r["meaningful_alternatives"] and len(r["actions"]) >= 2
                   and all(a["status"] == "EVALUATED" for a in r["actions"])
                   for r in reports)
               and len(uncertainty) == 1 and uncertainty[0]["same_current_view"]
               and any(a["realized_count"] > 1 for a in uncertainty[0]["action_support"]))
    return {"scope": "GOAL006_GENERATED_DEV_CAPABILITY_ONLY", "final_exposures": 0,
            "fixture_sha256": hashlib.sha256(Path(fixture_path).read_bytes()).hexdigest(),
            "strata": strata, "population": len(cases), "cases": reports,
            "realized_uncertainty": uncertainty,
            "transition_and_visibility_checks_passed": success,
            "independent_hand_reference_and_unsafe_tests": "REQUIRED_SEPARATE_REGRESSION_RECEIPT",
            "V": "INSUFFICIENT", "L": "INSUFFICIENT", "formal_combat_credit": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_report(args.fixture, args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in
                      ("population", "strata", "transition_and_visibility_checks_passed", "V", "L")}))
    return 0 if result["transition_and_visibility_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
