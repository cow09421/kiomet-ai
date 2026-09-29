"""唯讀驗證 PvP 證據束的身分、時間順序與來源指標。"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STAGE_ORDER = (
    "t_minus_2", "t_minus_1", "t0", "pre_dispatch", "dispatch",
    "post_dispatch", "moving", "arrival", "battle", "verdict",
    "t_plus_1", "t_plus_2", "post_state",
)
REQUIRED_STAGES = STAGE_ORDER
ACTION_KINDS = {"ATTACK_ENEMY", "REINFORCE_SELF"}
TIMESTAMP_KEYS = {"captured_at", "observed_at", "sent_at", "dispatched_at",
                  "logged_at", "timestamp"}
OWNER_VALUES = {"SELF", "ENEMY", "ALLY", "NEUTRAL", "UNKNOWN"}


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON number: {value}")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"),
                          parse_constant=_reject_constant)
    except (OSError, ValueError):
        return None


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line, parse_constant=_reject_constant)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def _finite_number(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _same(left: Any, right: Any) -> bool:
    return type(left) is type(right) and left == right


def _pick(record: dict, *keys: str):
    for key in keys:
        if record.get(key) is not None:
            return record[key]
    return None


def _normalize(record: dict) -> dict:
    dispatch = record.get("dispatch")
    if not isinstance(dispatch, dict):
        dispatch = {}
    before = record.get("before")
    if not isinstance(before, dict):
        before = {}
    source_before = before.get("source")
    target_before = before.get("target")
    if not isinstance(source_before, dict):
        source_before = {}
    if not isinstance(target_before, dict):
        target_before = {}
    binding = record.get("binding")
    if not isinstance(binding, dict):
        binding = record
    source = _pick(binding, "source_tower_id", "source_tower", "source_id",
                   "source")
    target = _pick(binding, "target_tower_id", "target_tower", "target_id",
                   "target")
    source_owner = binding.get("source_owner")
    target_owner = binding.get("target_owner")
    dispatch_at = binding.get("dispatched_at")
    if source_owner is None:
        source_owner = source_before.get("owner")
    if target_owner is None:
        target_owner = target_before.get("owner")
    if dispatch_at is None:
        dispatch_at = binding.get("sent_at")
    if dispatch_at is None:
        dispatch_at = dispatch.get("sent_at")
    return {
        "action_id": binding.get("action_id"),
        "match_id": _pick(binding, "match_id", "match"),
        "cycle_id": binding.get("cycle_id"),
        "source_tower_id": source,
        "target_tower_id": target,
        "action_kind": _pick(binding, "action_kind", "kind"),
        "source_owner": source_owner,
        "target_owner": target_owner,
        "route": _pick(binding, "route", "path"),
        "world_hash": binding.get("world_hash"),
        "proposal_version": binding.get("proposal_version"),
        "token_version": _pick(binding, "token_version", "action_token_version",
                                "validity_token_version"),
        "reservation_id": _pick(binding, "reservation_id",
                                 "reservation_action_id"),
        "dispatched_at": dispatch_at,
    }


def _stages(bundle: dict) -> dict:
    value = bundle.get("stages")
    return value if isinstance(value, dict) else {}


def _payload(stage: Any) -> Any:
    if isinstance(stage, dict) and "evidence" in stage:
        return stage.get("evidence")
    return stage


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _stage_has_identity(payload: Any, binding: dict) -> bool:
    return any(node.get("action_id") == binding.get("action_id")
               and node.get("match_id", node.get("match")) == binding.get("match_id")
               for node in _walk(payload))


def _add(issues: list[dict], code: str, severity: str = "FAIL",
         detail: str | None = None) -> None:
    item = {"code": code, "severity": severity}
    if detail:
        item["detail"] = detail
    if item not in issues:
        issues.append(item)


def _route_valid(route: Any, binding: dict) -> bool:
    if not isinstance(route, list) or len(route) < 2:
        return False
    if any(not _positive_int(node) for node in route):
        return False
    if len(set(route)) != len(route):
        return False
    return (route[0] == binding.get("source_tower_id")
            and route[-1] == binding.get("target_tower_id"))


def _pointer_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    path = value.split("#", 1)[0]
    if path.startswith("runtime/") or "/" in path or "\\" in path:
        return path
    return None


def _check_pointer(root: Path, pointer: str, binding: dict,
                    issues: list[dict]) -> bool:
    raw = Path(pointer)
    if raw.is_absolute() or ".." in raw.parts:
        _add(issues, "evidence-pointer-outside-project")
        return False
    target = (root / raw).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        _add(issues, "evidence-pointer-outside-project")
        return False
    if not target.is_file():
        _add(issues, "stale-evidence-pointer", "PARTIAL", pointer)
        return False
    records = _read_jsonl(target) if target.suffix.lower() == ".jsonl" else []
    if not records:
        payload = _read_json(target)
        if isinstance(payload, dict):
            records = [node for node in _walk(payload)
                       if isinstance(node.get("action_id"), str)]
    matches = [record for record in records
               if record.get("action_id") == binding.get("action_id")]
    if not matches:
        _add(issues, "stale-evidence-pointer", "PARTIAL", pointer)
        return False
    valid = True
    for record in matches:
        normalized = _normalize(record)
        for field in ("match_id", "cycle_id", "source_tower_id",
                      "target_tower_id"):
            value = normalized.get(field)
            if value is None:
                _add(issues, "incomplete-evidence-pointer", "PARTIAL",
                     f"{pointer}:{field}")
                valid = False
            elif not _same(value, binding.get(field)):
                _add(issues, "evidence-pointer-binding-conflict", "FAIL",
                     f"{pointer}:{field}")
                valid = False
    return valid


def _check_stage_identity(stage_name: str, payload: Any, binding: dict,
                          issues: list[dict], cycles: list[int],
                          timestamps: list[tuple[str, float]]) -> None:
    if payload is None:
        return
    for node in _walk(payload):
        action_id = node.get("action_id")
        if action_id is not None and action_id != binding.get("action_id"):
            _add(issues, "cross-action-stage", detail=stage_name)
        match_id = _pick(node, "match_id", "match")
        if match_id is not None and match_id != binding.get("match_id"):
            _add(issues, "cross-match-stage", detail=stage_name)
        cycle_id = node.get("cycle_id")
        if cycle_id is not None:
            if type(cycle_id) is not int or cycle_id < 0:
                _add(issues, "invalid-stage-cycle", detail=stage_name)
            elif stage_name in ("t0", "pre_dispatch", "dispatch") \
                    and cycle_id != binding.get("cycle_id"):
                _add(issues, "action-cycle-binding-conflict",
                     detail=stage_name)
            else:
                cycles.append(cycle_id)
        for fields, target_field in ((("source_tower_id", "source_tower",
                                       "source_id", "source"), "source_tower_id"),
                                     (("target_tower_id", "target_tower",
                                       "target_id", "target"), "target_tower_id")):
            value = _pick(node, *fields)
            if isinstance(value, dict):
                value = value.get("tower_id", value.get("id"))
            if value is not None and not _same(value, binding.get(target_field)):
                _add(issues, "source-target-stage-conflict", detail=stage_name)
        if stage_name in ("t_minus_2", "t_minus_1", "t0", "pre_dispatch"):
            for field in ("source_owner", "target_owner"):
                value = node.get(field)
                expected = binding.get(field)
                if value == "UNKNOWN":
                    _add(issues, "unknown-stage-owner", "PARTIAL",
                         f"{stage_name}:{field}")
                elif value is not None and expected not in (None, "UNKNOWN") \
                        and value != expected:
                    _add(issues, "owner-stage-conflict",
                         detail=f"{stage_name}:{field}")
        observed_kind = node.get("action_kind")
        if observed_kind is not None and observed_kind != binding.get("action_kind"):
            _add(issues, "action-kind-stage-conflict", detail=stage_name)
        observed_route = _pick(node, "route", "path")
        if observed_route is not None and not _route_valid(observed_route, binding):
            _add(issues, "route-stage-conflict", detail=stage_name)
        for field in ("world_hash", "proposal_version", "token_version",
                      "reservation_id"):
            observed = node.get(field)
            expected = binding.get(field)
            if (observed is not None and expected is not None
                    and not _same(observed, expected)):
                _add(issues, "binding-metadata-stage-conflict",
                     detail=f"{stage_name}:{field}")
        for key in TIMESTAMP_KEYS:
            value = node.get(key)
            if value is not None:
                if not _finite_number(value) or float(value) <= 0:
                    _add(issues, "invalid-stage-timestamp", detail=stage_name)
                else:
                    timestamps.append((stage_name, float(value)))


def _check_owners(binding: dict, issues: list[dict], missing: list[str]) -> None:
    kind = binding.get("action_kind")
    source_owner, target_owner = (binding.get("source_owner"),
                                  binding.get("target_owner"))
    expected = {"ATTACK_ENEMY": ("SELF", "ENEMY"),
                "REINFORCE_SELF": ("SELF", "SELF")}.get(kind)
    for field, value in (("source_owner", source_owner),
                         ("target_owner", target_owner)):
        if value is None or value == "UNKNOWN":
            missing.append(field)
        elif not isinstance(value, str) or value not in OWNER_VALUES:
            _add(issues, "invalid-owner-relation", detail=field)
    if (expected and isinstance(source_owner, str)
            and isinstance(target_owner, str)
            and source_owner in OWNER_VALUES and target_owner in OWNER_VALUES
            and source_owner != "UNKNOWN" and target_owner != "UNKNOWN"):
        if (source_owner, target_owner) != expected:
            _add(issues, "action-owner-relation-conflict")


def _case_id(bundle: dict, binding: dict) -> str | None:
    value = binding.get("action_id") or bundle.get("threat_id")
    return value if isinstance(value, str) and value else None


def validate_bundle(bundle: dict, root: str | Path = ROOT) -> dict:
    """驗證單一 action/threat 束；完整性不等於戰鬥 proof。"""
    project_root = Path(root).resolve()
    binding = _normalize(bundle)
    issues: list[dict] = []
    missing: list[str] = []
    case_type = bundle.get("case_type", "ACTION")
    action_id = binding.get("action_id")

    if case_type not in ("ACTION", "THREAT"):
        _add(issues, "unsupported-case-type")
        case_type = "ACTION"

    if case_type == "THREAT":
        threat_binding = bundle.get("binding")
        if not isinstance(threat_binding, dict):
            threat_binding = {}
        stages = _stages(bundle)
        for field in ("match_id", "cycle_id", "source_force_id",
                      "source_tower_id", "target_tower_id", "observed_at",
                      "route"):
            value = threat_binding.get(field)
            if value is None:
                missing.append(field)
        if type(threat_binding.get("cycle_id")) is not int or threat_binding[
                "cycle_id"] < 0:
            _add(issues, "invalid-threat-cycle")
        for field in ("source_tower_id", "target_tower_id"):
            if not _positive_int(threat_binding.get(field)):
                _add(issues, "invalid-threat-tower-id", detail=field)
        force_id = threat_binding.get("source_force_id")
        if not ((type(force_id) is int and force_id > 0)
                or (isinstance(force_id, str) and bool(force_id))):
            _add(issues, "invalid-threat-force-id")
        if not _finite_number(threat_binding.get("observed_at")):
            _add(issues, "invalid-threat-timestamp")
        if not _route_valid(threat_binding.get("route"), threat_binding):
            _add(issues, "invalid-threat-route")
        source_owner = threat_binding.get("source_owner")
        target_owner = threat_binding.get("target_owner")
        if (source_owner != "ENEMY" or target_owner != "SELF"):
            missing.append("explicit_enemy_to_self_ownership")
        freshness = threat_binding.get("freshness")
        if freshness is None:
            t0 = _payload(stages.get("t0"))
            if isinstance(t0, dict):
                freshness = t0.get("freshness")
        if freshness == "STALE":
            _add(issues, "stale-threat-observation")
        elif freshness != "FRESH":
            missing.append("freshness")
        last_cycle = None
        last_timestamp = None
        for stage_name in STAGE_ORDER:
            payload = _payload(stages.get(stage_name))
            for node in _walk(payload):
                match = _pick(node, "match_id", "match")
                if match is not None and match != threat_binding.get("match_id"):
                    _add(issues, "cross-match-threat-stage", detail=stage_name)
                cycle = node.get("cycle_id")
                if cycle is not None:
                    if type(cycle) is not int or cycle < 0:
                        _add(issues, "invalid-threat-stage-cycle",
                             detail=stage_name)
                    elif stage_name == "t0" and cycle != threat_binding.get(
                            "cycle_id"):
                        _add(issues, "threat-binding-cycle-conflict")
                    elif last_cycle is not None and cycle < last_cycle:
                        _add(issues, "threat-cycle-order-reversal")
                    else:
                        last_cycle = cycle
                for key in TIMESTAMP_KEYS:
                    value = node.get(key)
                    if value is None:
                        continue
                    if not _finite_number(value) or float(value) <= 0:
                        _add(issues, "invalid-threat-stage-timestamp",
                             detail=stage_name)
                    elif last_timestamp is not None and float(value) < last_timestamp:
                        _add(issues, "threat-timestamp-order-reversal")
                    else:
                        last_timestamp = float(value)
                source = _pick(node, "source_tower_id", "source_tower")
                target = _pick(node, "target_tower_id", "target_tower")
                if source is not None and source != threat_binding.get("source_tower_id"):
                    _add(issues, "threat-source-conflict", detail=stage_name)
                if target is not None and target != threat_binding.get("target_tower_id"):
                    _add(issues, "threat-target-conflict", detail=stage_name)
        status = "FAIL" if issues else "PARTIAL" if missing else "OBSERVED"
        return {"case_id": _case_id(bundle, binding), "case_type": "THREAT",
                "status": status, "proof_status": "NOT_EVALUATED",
                "missing": sorted(set(missing)), "issues": issues}

    required = ("action_id", "match_id", "cycle_id", "source_tower_id",
                "target_tower_id", "action_kind", "source_owner", "target_owner",
                "route", "world_hash", "proposal_version", "token_version",
                "reservation_id", "dispatched_at")
    for field in required:
        if binding.get(field) is None:
            missing.append(field)
    if not isinstance(action_id, str) or not action_id:
        _add(issues, "invalid-action-id")
    if not isinstance(binding.get("match_id"), str) or not binding["match_id"]:
        _add(issues, "invalid-match-id")
    if type(binding.get("cycle_id")) is not int or binding["cycle_id"] < 0:
        _add(issues, "invalid-cycle-id")
    source_id, target_id = (binding.get("source_tower_id"),
                            binding.get("target_tower_id"))
    if not _positive_int(source_id) or not _positive_int(target_id):
        _add(issues, "invalid-source-target-id")
    elif source_id == target_id:
        _add(issues, "source-target-not-distinct")
    if binding.get("action_kind") not in ACTION_KINDS:
        _add(issues, "unsupported-action-kind")
    _check_owners(binding, issues, missing)
    if not _route_valid(binding.get("route"), binding):
        if binding.get("route") is None:
            missing.append("route")
        else:
            _add(issues, "invalid-route")
    for field in ("world_hash", "proposal_version", "token_version", "reservation_id"):
        value = binding.get(field)
        if value is None or value == "":
            missing.append(field)
        elif not isinstance(value, (str, int)) or type(value) is bool:
            _add(issues, "invalid-binding-metadata", detail=field)
    dispatched_at = binding.get("dispatched_at")
    if not _finite_number(dispatched_at) or float(dispatched_at) <= 0:
        _add(issues, "invalid-dispatch-timestamp")

    stages = _stages(bundle)
    for stage_name in REQUIRED_STAGES:
        if _payload(stages.get(stage_name)) is None:
            missing.append(stage_name)
    if _payload(stages.get("dispatch")) is None:
        missing.append("dispatch")
    if _payload(stages.get("verdict")) is None:
        missing.append("verdict")
    verdict = _payload(stages.get("verdict"))
    if isinstance(verdict, dict) and not any(verdict.get(key) is not None
                                             for key in ("verifier", "result", "status")):
        missing.append("verdict_value")
    post_state = _payload(stages.get("post_state"))
    if post_state is None:
        missing.append("post_state")

    stage_cycles: list[int] = []
    stage_times: list[tuple[str, float]] = []
    pointers = set()
    checked_pointers = set()
    for stage_name in STAGE_ORDER:
        stage = stages.get(stage_name)
        payload = _payload(stage)
        local_cycles: list[int] = []
        _check_stage_identity(stage_name, payload, binding, issues,
                              local_cycles, stage_times)
        if len(set(local_cycles)) > 1:
            _add(issues, "stage-cycle-conflict", detail=stage_name)
        elif local_cycles:
            stage_cycles.append(local_cycles[0])
        if isinstance(stage, dict):
            pointer = _pointer_path(stage.get("source"))
            if pointer:
                if _check_pointer(project_root, pointer, binding, issues):
                    pointers.add(pointer)
                    checked_pointers.add(pointer)
            for node in _walk(stage):
                for key in ("evidence_pointer", "source_path", "evidence_path"):
                    pointer = _pointer_path(node.get(key))
                    if pointer:
                        pointers.add(pointer)
        if payload is not None and not _stage_has_identity(payload, binding):
            stage_source = stage.get("source") if isinstance(stage, dict) else None
            source_pointer = _pointer_path(stage_source)
            # A source file verified against the same action/match can bind
            # legacy snapshots that do not repeat their envelope identity.
            if not source_pointer or source_pointer not in pointers:
                missing.append(f"{stage_name}_binding")
        stage_values = [value for name, value in stage_times
                        if name == stage_name]
        if payload is not None and not stage_values:
            missing.append(f"{stage_name}_timestamp")
    for pointer in bundle.get("evidence_sources", []):
        pointer = _pointer_path(pointer)
        if pointer:
            pointers.add(pointer)
    for pointer in sorted(pointers - checked_pointers):
        _check_pointer(project_root, pointer, binding, issues)

    for previous, current in zip(stage_cycles, stage_cycles[1:]):
        if current < previous:
            _add(issues, "cycle-order-reversal")
            break
    dispatch_stage_times = [value for stage, value in stage_times if stage == "dispatch"]
    if _finite_number(dispatched_at) and dispatch_stage_times:
        if any(abs(value - float(dispatched_at)) > 0.001
               for value in dispatch_stage_times):
            _add(issues, "dispatch-time-binding-conflict")
    previous_time = None
    for stage_name in STAGE_ORDER:
        values = [value for name, value in stage_times if name == stage_name]
        if stage_name == "dispatch" and not values and _finite_number(dispatched_at):
            values = [float(dispatched_at)]
        if not values:
            continue
        stage_min, stage_max = min(values), max(values)
        if previous_time is not None and stage_min < previous_time:
            _add(issues, "timestamp-order-reversal")
            break
        previous_time = stage_max
    if bundle.get("collection_status") == "BINDING_CONFLICT":
        _add(issues, "collector-reported-binding-conflict")

    if any(issue["severity"] == "FAIL" for issue in issues):
        status = "FAIL"
    elif missing or any(issue["severity"] == "PARTIAL" for issue in issues):
        status = "PARTIAL"
    else:
        status = "PASS"
    return {"case_id": _case_id(bundle, binding), "case_type": "ACTION",
            "action_kind": binding.get("action_kind"), "status": status,
            "proof_status": "NOT_EVALUATED", "missing": sorted(set(missing)),
            "issues": issues}


def validate_document(document: Any, root: str | Path = ROOT) -> dict:
    if isinstance(document, dict) and isinstance(document.get("bundles"), list):
        bundles = document["bundles"]
    elif isinstance(document, dict) and isinstance(document.get("binding"), dict):
        bundles = [document]
    else:
        return {"schema_version": 1, "status": "FAIL", "case_count": 0,
                "pass_count": 0, "partial_count": 0, "fail_count": 1,
                "proof_status": "NOT_EVALUATED", "cases": [],
                "issues": [{"code": "unsupported-document", "severity": "FAIL"}]}
    if not bundles:
        return {"schema_version": 1, "status": "NO_CASES", "case_count": 0,
                "pass_count": 0, "partial_count": 0, "fail_count": 0,
                "proof_status": "NOT_EVALUATED", "cases": [], "issues": []}
    cases = [validate_bundle(bundle, root) for bundle in bundles
             if isinstance(bundle, dict)]
    if len(cases) != len(bundles):
        cases.append({"case_id": None, "case_type": "UNKNOWN", "status": "FAIL",
                      "proof_status": "NOT_EVALUATED", "missing": [],
                      "issues": [{"code": "non-object-bundle", "severity": "FAIL"}]})
    by_action: dict[str, list[dict]] = {}
    by_reservation: dict[str, list[dict]] = {}
    for case, bundle in zip(cases, [item for item in bundles if isinstance(item, dict)]):
        binding = _normalize(bundle)
        action_id = binding.get("action_id")
        reservation_id = binding.get("reservation_id")
        if isinstance(action_id, str) and action_id:
            by_action.setdefault(action_id, []).append(case)
        if isinstance(reservation_id, str) and reservation_id:
            by_reservation.setdefault(reservation_id, []).append(case)
    for repeated in by_action.values():
        if len(repeated) > 1:
            for case in repeated:
                _add(case["issues"], "duplicate-action-id")
                case["status"] = "FAIL"
    for repeated in by_reservation.values():
        action_ids = {case.get("case_id") for case in repeated}
        if len(action_ids) > 1:
            for case in repeated:
                _add(case["issues"], "duplicate-reservation-id")
                case["status"] = "FAIL"
    counts = {status: sum(case["status"] == status for case in cases)
              for status in ("PASS", "PARTIAL", "FAIL", "OBSERVED")}
    status = ("FAIL" if counts["FAIL"] else
              "PARTIAL" if counts["PARTIAL"] or any(
                  case["status"] == "OBSERVED" for case in cases) else "PASS")
    return {"schema_version": 1, "validator": "validate_combat_evidence",
            "status": status, "proof_status": "NOT_EVALUATED",
            "case_count": len(cases), "pass_count": counts["PASS"],
            "partial_count": counts["PARTIAL"], "fail_count": counts["FAIL"],
            "observed_count": counts["OBSERVED"],
            "cases": cases, "issues": []}


def _inside_root(root: Path, path: Path) -> Path:
    target = path if path.is_absolute() else root / path
    target = target.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("input/output path must remain inside project root") from exc
    return target


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path,
                        default=Path("runtime/research/combat_evidence_arming/latest.json"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    source = _inside_root(root, args.input)
    if not source.is_file():
        parser.error(f"input file does not exist inside project root: {source}")
    document = _read_json(source)
    report = validate_document(document, root)
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.out is not None:
        target = _inside_root(root, args.out)
        _atomic_write(target, encoded)
    print(encoded, end="")
    return 1 if report["status"] == "FAIL" else 2 if report["status"] in (
        "PARTIAL", "NO_CASES") else 0


if __name__ == "__main__":
    raise SystemExit(main())
