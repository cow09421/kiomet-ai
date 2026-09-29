"""收集正式執行期的敵方攻擊證據，並以行動識別碼保存單一證據束。

預設單次掃描 runtime/；--watch 會定期重掃並原子覆寫同一行動的證據檔。
工具唯讀取證據來源，不會啟動瀏覽器、等待對局或操作遊戲。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_RELATIVE = Path("runtime/research/enemy_evidence")
IDENTITY = ("match_id", "cycle_id", "source_tower_id", "target_tower_id")
KNOWN_ACTION_KINDS = {"ATTACK_ENEMY", "REINFORCE_SELF", "EXPAND_NEUTRAL"}


def _reject_json_constant(value: str):
    raise ValueError(f"non-finite JSON number: {value}")


def _read_json(path: Path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"),
                           parse_constant=_reject_json_constant)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _read_actions(path: Path) -> tuple[list[dict], int]:
    rows = []
    malformed = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line, parse_constant=_reject_json_constant)
                except ValueError:
                    malformed += 1
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    malformed += 1
    except OSError:
        pass
    return rows, malformed


def _number(value) -> bool:
    if type(value) not in (int, float) or value <= 0:
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _normalize(record: dict) -> dict:
    dispatch = record.get("dispatch")
    if not isinstance(dispatch, dict):
        dispatch = {}
    return {
        "action_id": record.get("action_id"),
        "match_id": record.get("match_id", record.get("match")),
        "cycle_id": record.get("cycle_id"),
        "source_tower_id": record.get(
            "source_tower_id", record.get("source_tower", record.get("source"))),
        "target_tower_id": record.get(
            "target_tower_id", record.get("target_tower", record.get("target"))),
        "action_kind": record.get("action_kind"),
        "origin": record.get("origin"),
        "dispatched_at": (dispatch.get("sent_at") or record.get("sent_at")
                          or record.get("dispatched_at")),
        "target_owner": record.get("target_owner"),
        "source_owner": record.get("source_owner"),
    }


def _valid_identity(identity: dict) -> list[str]:
    missing = []
    if not isinstance(identity.get("action_id"), str) or not identity["action_id"]:
        missing.append("action_id")
    match_id = identity.get("match_id")
    if not isinstance(match_id, str) or not match_id:
        missing.append("match_id")
    cycle_id = identity.get("cycle_id")
    if type(cycle_id) is not int or cycle_id < 0:
        missing.append("cycle_id")
    for field in ("source_tower_id", "target_tower_id"):
        if type(identity.get(field)) is not int or identity[field] <= 0:
            missing.append(field)
    if (type(identity.get("source_tower_id")) is int
            and type(identity.get("target_tower_id")) is int
            and identity["source_tower_id"] == identity["target_tower_id"]):
        missing.append("distinct_source_target")
    if not _number(identity.get("dispatched_at")):
        missing.append("dispatched_at")
    return missing


def _relative(root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return None


def _source_files(root: Path, relative: str) -> list[Path]:
    base = root / relative
    if base.is_file():
        return [base] if _relative(root, base) is not None else []
    if not base.is_dir():
        return []
    return sorted(path for path in base.rglob("*.json")
                  if _relative(root, path) is not None)


def _add_issue(candidate: dict, issue: str, *, invalid: bool = True) -> None:
    if issue not in candidate["issues"]:
        candidate["issues"].append(issue)
    if invalid:
        candidate["invalid"] = True


def _candidate_for_action(candidates: dict, row: dict,
                          source_path: str) -> None:
    normalized = _normalize(row)
    action_id = normalized.get("action_id")
    if normalized.get("action_kind") != "ATTACK_ENEMY":
        return
    if not isinstance(action_id, str) or not action_id:
        return
    candidate = candidates.setdefault(action_id, {
        "action_id": action_id, "actions": [], "supplemental": {},
        "issues": [], "invalid": False, "sources": set(),
    })
    candidate["actions"].append((row, normalized))
    candidate["sources"].add(source_path)
    if normalized.get("origin") not in (None, "LIVE_CONTROLLER"):
        _add_issue(candidate, "action-origin-not-live-controller")


def _same_identity(expected: dict, observed: dict,
                   candidate: dict, label: str) -> bool:
    """只有所有已提供的綁定欄位相同，來源才會併入證據束。"""
    valid = True
    for field in IDENTITY:
        left, right = expected.get(field), observed.get(field)
        if right is None:
            _add_issue(candidate, f"{label}-missing-{field}", invalid=False)
            valid = False
        elif left is None:
            _add_issue(candidate, f"action-missing-{field}", invalid=False)
            valid = False
        elif type(left) is not type(right) or left != right:
            _add_issue(candidate, f"{label}-binding-mismatch-{field}")
            valid = False
    return valid


def _atomic_json(path: Path, payload: dict) -> bool:
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          indent=2, allow_nan=False) + "\n").encode("utf-8")
    try:
        if path.is_file() and path.read_bytes() == encoded:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{path.name}.", suffix=".tmp",
                dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return True


def _merge_binding(candidate: dict, action_rows: list[tuple[dict, dict]]) -> dict:
    binding = {
        "action_id": candidate["action_id"],
        "match_id": None, "cycle_id": None,
        "source_tower_id": None, "target_tower_id": None,
        "source_owner": "UNKNOWN", "target_owner": "UNKNOWN",
        "origin": None, "dispatched_at": None,
    }
    owners = set()
    source_owners = set()
    times = []
    for raw, row in action_rows:
        for field in IDENTITY:
            value = row.get(field)
            if value is None:
                continue
            current = binding.get(field)
            if current is None:
                binding[field] = value
            elif type(current) is not type(value) or current != value:
                _add_issue(candidate, f"action-binding-conflict-{field}")
        origin = row.get("origin")
        if origin is not None:
            if binding["origin"] is None:
                binding["origin"] = origin
            elif binding["origin"] != origin:
                _add_issue(candidate, "action-binding-conflict-origin")
        if row.get("target_owner") is not None:
            owners.add(row["target_owner"])
        if row.get("source_owner") is not None:
            source_owners.add(row["source_owner"])
        if _number(row.get("dispatched_at")):
            times.append(float(row["dispatched_at"]))
        proof = raw.get("attack_proof_bundle")
        if isinstance(proof, dict):
            battle = proof.get("battle_differential_evidence")
            if isinstance(battle, dict):
                if battle.get("target_owner"):
                    owners.add(battle["target_owner"])
                if battle.get("source_owner"):
                    source_owners.add(battle["source_owner"])
    if len(owners) > 1:
        _add_issue(candidate, "target-owner-conflict")
    elif owners:
        binding["target_owner"] = next(iter(owners))
    if len(source_owners) > 1:
        _add_issue(candidate, "source-owner-conflict")
    elif source_owners:
        binding["source_owner"] = next(iter(source_owners))
    if times:
        if max(times) - min(times) > 0.001:
            _add_issue(candidate, "action-dispatch-time-conflict")
        binding["dispatched_at"] = times[0]
    return binding


def _attach_record(candidate: dict, binding: dict, record: dict,
                   source_path: str, source_label: str) -> bool:
    if record.get("action_id") != candidate["action_id"]:
        return False
    normalized = _normalize(record)
    if not _same_identity(binding, normalized, candidate, source_label):
        return False
    observed_time = normalized.get("dispatched_at")
    if _number(observed_time) and _number(binding.get("dispatched_at")):
        if abs(float(observed_time) - float(binding["dispatched_at"])) > 0.001:
            _add_issue(candidate, f"{source_label}-dispatch-time-mismatch")
            return False
    if source_label in candidate["supplemental"]:
        _add_issue(candidate, f"duplicate-{source_label}-records")
        return False
    candidate["supplemental"][source_label] = record
    candidate["sources"].add(source_path)
    return True


def _owner_evidence(candidate: dict, pending: dict | None,
                    differential: dict | None) -> None:
    binding = candidate["binding"]
    owners = set()
    source_owners = set()
    if binding.get("target_owner") not in (None, "UNKNOWN"):
        owners.add(binding["target_owner"])
    if isinstance(pending, dict):
        before = pending.get("before")
        target = before.get("target") if isinstance(before, dict) else None
        source = before.get("source") if isinstance(before, dict) else None
        if isinstance(target, dict) and target.get("owner") is not None:
            owners.add(target["owner"])
        if isinstance(source, dict) and source.get("owner") is not None:
            source_owners.add(source["owner"])
    if isinstance(differential, dict):
        if differential.get("target_owner") is not None:
            owners.add(differential["target_owner"])
        if differential.get("source_owner") is not None:
            source_owners.add(differential["source_owner"])
    if len(owners) > 1:
        _add_issue(candidate, "target-owner-conflict")
    elif owners:
        binding["target_owner"] = next(iter(owners))
    else:
        _add_issue(candidate, "target-owner-unknown", invalid=False)
    if len(source_owners) > 1:
        _add_issue(candidate, "source-owner-conflict")
    elif source_owners:
        binding["source_owner"] = next(iter(source_owners))
    if binding.get("source_owner") == "UNKNOWN":
        _add_issue(candidate, "source-owner-unknown", invalid=False)
    elif binding.get("source_owner") != "SELF":
        _add_issue(candidate, "source-owner-not-self")
    if (binding.get("target_owner") not in ("ENEMY", "UNKNOWN")):
        _add_issue(candidate, "target-owner-not-enemy")


def _case_payload(candidate: dict) -> dict:
    binding = candidate["binding"]
    supplements = candidate["supplemental"]
    force = supplements.get("force_bundle")
    pending = supplements.get("pending_dispatch")
    differential = supplements.get("battle_differential")
    capture = supplements.get("pending_capture")

    def stage(name):
        value = force.get(name) if isinstance(force, dict) else None
        return value if isinstance(value, dict) else None

    t0 = stage("t0")
    if t0 is None and isinstance(pending, dict):
        before = pending.get("before")
        t0 = before if isinstance(before, dict) else None
    t3 = stage("t3")
    if t3 is None and isinstance(differential, dict):
        after_target = differential.get("after_target")
        if isinstance(after_target, dict):
            t3 = {"target": after_target}
    verdict_row = next((raw for raw, _normalized in reversed(candidate["actions"])
                        if raw.get("verifier") is not None
                        or raw.get("result") is not None), {})
    verdict_value = verdict_row.get("verifier") or verdict_row.get("result")
    verdict = None
    if verdict_value is not None:
        verdict = {"verifier": verdict_row.get("verifier"),
                   "result": verdict_row.get("result"),
                   "observed_at": verdict_row.get("logged_at")}
    elif isinstance(capture, dict):
        status = capture.get("status") or capture.get("verdict")
        if status is not None:
            verdict = {"verifier": status, "source": "pending_capture"}

    stages = {
        "t0_pre_dispatch": t0,
        "pre_dispatch": (pending.get("before") if isinstance(pending, dict)
                         and isinstance(pending.get("before"), dict) else None),
        "t1_post_dispatch": stage("t1"),
        "t2_post_dispatch": stage("t2"),
        "t3_post_battle": t3,
        "battle_differential": differential,
        "verification": verdict,
        "pending_capture": capture,
    }
    def captured_times(value):
        found = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("captured_at", "observed_at"):
                    if _number(item):
                        found.append(float(item))
                elif isinstance(item, (dict, list)):
                    found.extend(captured_times(item))
        elif isinstance(value, list):
            for item in value:
                found.extend(captured_times(item))
        return found

    target_force_match = (force.get("force_match_target")
                          if isinstance(force, dict) else None)
    arrival_observation = None
    if target_force_match == "FORCE_MATCH_VERIFIED":
        post_dispatch_times = (
            captured_times(stages["t1_post_dispatch"])
            + captured_times(stages["t2_post_dispatch"])
            + captured_times(stages["t3_post_battle"]))
        arrival_observation = {
            "status": "TARGET_FORCE_OBSERVED",
            "target_force_match": target_force_match,
            "sample_timestamps": sorted(set(post_dispatch_times)),
            "timestamp_scope": "T1-T3; exact matching sample is not recorded",
        }
    stages["arrival_observation"] = arrival_observation

    timestamp_stages = {
        name: captured_times(stages[name])
        for name in ("t0_pre_dispatch", "t1_post_dispatch",
                     "t2_post_dispatch", "t3_post_battle")
    }
    timestamp_issues = []
    dispatch_at = binding.get("dispatched_at")
    timing_missing = []
    if not _number(dispatch_at):
        timing_missing.append("dispatch_at")
    for name, values in timestamp_stages.items():
        if not values:
            timing_missing.append(name)
    t0_times = timestamp_stages["t0_pre_dispatch"]
    if _number(dispatch_at) and t0_times:
        if max(t0_times) > float(dispatch_at):
            timestamp_issues.append("t0-after-dispatch")
        if float(dispatch_at) - min(t0_times) > 30:
            timestamp_issues.append("t0-stale-at-dispatch")
    previous = t0_times
    for name in ("t1_post_dispatch", "t2_post_dispatch", "t3_post_battle"):
        values = timestamp_stages[name]
        if _number(dispatch_at) and values and min(values) < float(dispatch_at):
            timestamp_issues.append(f"{name}-before-dispatch")
        if previous and values and max(previous) > min(values):
            timestamp_issues.append(f"{name}-time-order")
        if values:
            previous = values
    if timestamp_issues:
        for issue in timestamp_issues:
            _add_issue(candidate, issue)
    verdict_time = (verdict.get("observed_at")
                    if isinstance(verdict, dict) else None)
    if not _number(verdict_time):
        timing_missing.append("verification")
    elif _number(dispatch_at) and float(verdict_time) < float(dispatch_at):
        timestamp_issues.append("verification-before-dispatch")
        _add_issue(candidate, "verification-before-dispatch")
    if timing_missing:
        _add_issue(candidate, "snapshot-capture-time-missing", invalid=False)
    if timestamp_issues:
        for issue in timestamp_issues:
            _add_issue(candidate, issue)
    timestamp_status = ("INVALID" if timestamp_issues else
                        "INCOMPLETE" if timing_missing else "BOUND")
    timestamps = {
        "dispatch_at": dispatch_at,
        "snapshot_times": timestamp_stages,
        "verification_observed_at": (verdict.get("observed_at")
                                      if isinstance(verdict, dict) else None),
        "status": timestamp_status,
        "missing_timestamps": sorted(set(timing_missing)),
        "issues": timestamp_issues,
    }
    missing = _valid_identity(binding)
    if binding.get("target_owner") != "ENEMY":
        missing.append("target_owner")
    if binding.get("source_owner") != "SELF":
        missing.append("source_owner")
    if binding.get("origin") != "LIVE_CONTROLLER":
        missing.append("origin")
    for name in ("t0_pre_dispatch", "t1_post_dispatch", "t2_post_dispatch",
                 "arrival_observation",
                 "t3_post_battle", "battle_differential", "verification"):
        if stages[name] is None:
            missing.append(name)
    if timestamp_status != "BOUND":
        missing.append("snapshot_timestamps")
    missing = sorted(set(missing))
    collection_status = ("BINDING_CONFLICT" if candidate["invalid"] else
                         "COMPLETE" if not missing else "INCOMPLETE")
    return {
        "schema_version": 1,
        "collector": "enemy_evidence_collector",
        "action_kind": "ATTACK_ENEMY",
        "binding": binding,
        "collection_status": collection_status,
        "proof_status": "NOT_EVALUATED",
        "missing": missing,
        "issues": sorted(candidate["issues"]),
        "stages": stages,
        "timestamps": timestamps,
        "evidence_sources": sorted(candidate["sources"]),
    }


def _case_filename(action_id: str) -> str:
    digest = hashlib.sha256(action_id.encode("utf-8")).hexdigest()[:24]
    return f"{digest}.json"


def collect_once(root: str | Path = ROOT,
                 out_dir: str | Path | None = None) -> dict:
    """重掃行動、部隊與戰鬥記錄；每個 action_id 只覆寫一個 JSON。"""
    project_root = Path(root).resolve()
    if not project_root.is_dir():
        raise ValueError("project root must be an existing directory")
    if out_dir is None:
        output = project_root / OUTPUT_RELATIVE
    else:
        requested_output = Path(out_dir)
        output = (requested_output if requested_output.is_absolute()
                  else project_root / requested_output).resolve()
    try:
        output.relative_to(project_root)
    except ValueError as exc:
        raise ValueError("output directory must remain inside project root") from exc

    candidates: dict[str, dict] = {}
    action_path = project_root / "runtime" / "logs" / "live_actions.jsonl"
    action_rows, malformed = _read_actions(action_path)
    unclassified_action_rows = sum(
        row.get("action_kind") not in KNOWN_ACTION_KINDS for row in action_rows)
    for row in action_rows:
        _candidate_for_action(candidates, row,
                              _relative(project_root, action_path) or "")

    state_path = project_root / "runtime" / "state" / "live_controller.json"
    state = _read_json(state_path)
    journal = state.get("journal") if isinstance(state, dict) else None
    if not isinstance(journal, dict):
        journal = {}
    journal_action = journal.get("last_action")
    if isinstance(journal_action, dict):
        _candidate_for_action(candidates, journal_action,
                              _relative(project_root, state_path) or "")

    pending_path = project_root / "runtime" / "state" / "pending-live-dispatch.json"
    pending = _read_json(pending_path)
    if pending is None:
        pending = journal.get("pending_dispatch")
    if (isinstance(pending, dict)
            and pending.get("action_kind") == "ATTACK_ENEMY"
            and _number(pending.get("sent_at"))):
        _candidate_for_action(candidates, pending,
                              _relative(project_root, pending_path) or "")

    for candidate in candidates.values():
        binding = _merge_binding(candidate, candidate["actions"])
        candidate["binding"] = binding
        if binding.get("origin") not in (None, "LIVE_CONTROLLER"):
            _add_issue(candidate, "action-origin-not-live-controller")
        if binding.get("origin") is None:
            _add_issue(candidate, "action-origin-unknown", invalid=False)
        for missing_field in _valid_identity(binding):
            _add_issue(candidate, f"action-missing-or-invalid-{missing_field}",
                       invalid=False)

    force_records = [
        (path, _read_json(path)) for path in _source_files(
            project_root, "runtime/research/forces/autonomous_validation")
        if path.name == "bundle.json"
    ]
    battle_records = [
        (path, _read_json(path)) for path in _source_files(
            project_root, "runtime/research/pvp_validation")
        if path.name == "battle-differential.json"
    ]

    for candidate in candidates.values():
        binding = candidate["binding"]
        for path, record in force_records:
            if isinstance(record, dict):
                _attach_record(candidate, binding, record,
                               _relative(project_root, path) or "",
                               "force_bundle")
        for path, record in battle_records:
            if isinstance(record, dict):
                _attach_record(candidate, binding, record,
                               _relative(project_root, path) or "",
                               "battle_differential")
        if isinstance(pending, dict):
            _attach_record(candidate, binding, pending,
                           _relative(project_root, pending_path) or "",
                           "pending_dispatch")
        captures = journal.get("pending_captures")
        if isinstance(captures, list):
            for item in captures:
                if not isinstance(item, dict):
                    continue
                capture_record = dict(item)
                capture_record.setdefault("target_tower_id", item.get("target"))
                _attach_record(candidate, binding, capture_record,
                               _relative(project_root, state_path) or "",
                               "pending_capture")
        _owner_evidence(candidate,
                        candidate["supplemental"].get("pending_dispatch"),
                        candidate["supplemental"].get("battle_differential"))

    if candidates:
        output.mkdir(parents=True, exist_ok=True)
    written = 0
    summaries = []
    for action_id, candidate in sorted(candidates.items()):
        payload = _case_payload(candidate)
        filename = _case_filename(action_id)
        written += int(_atomic_json(output / filename, payload))
        summaries.append({"action_id": action_id, "file": filename,
                          "collection_status": payload["collection_status"]})

    return {
        "candidate_count": len(candidates),
        "action_rows_scanned": len(action_rows),
        "unclassified_action_rows": unclassified_action_rows,
        "written_count": written,
        "malformed_action_rows": malformed,
        "collection_counts": {
            status: sum(item["collection_status"] == status for item in summaries)
            for status in ("COMPLETE", "INCOMPLETE", "BINDING_CONFLICT")
        },
        "cases": summaries,
        "output_dir": _relative(project_root, output),
    }


def watch(root: str | Path = ROOT, out_dir: str | Path | None = None,
          interval: float = 1.0, *, max_iterations: int | None = None) -> None:
    if (type(interval) not in (int, float) or not math.isfinite(interval)
            or not 0.2 <= interval <= 3600):
        raise ValueError("watch interval must be between 0.2 and 3600 seconds")
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        print(json.dumps(collect_once(root, out_dir), ensure_ascii=False,
                         sort_keys=True), flush=True)
        iterations += 1
        if max_iterations is None or iterations < max_iterations:
            time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="專案根目錄（預設為本工具所在專案）")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="輸出目錄，必須位於專案根目錄內")
    parser.add_argument("--watch", action="store_true",
                        help="定期重掃並更新同一行動的單一證據檔")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="輪詢秒數，範圍 0.2 到 3600；預設 1 秒")
    args = parser.parse_args(argv)
    try:
        if args.watch:
            watch(args.root, args.out_dir, args.interval)
        else:
            print(json.dumps(collect_once(args.root, args.out_dir),
                             ensure_ascii=False, sort_keys=True))
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
