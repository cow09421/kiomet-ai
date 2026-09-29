"""收集具明確己方對敵方身分的戰鬥差分，建立單一待驗證佇列。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("runtime/state/battle_validation_queue.json")
DEFAULT_MAX_CASES = 512
UNIT_NAMES = {"Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier"}
sys.path.insert(0, str(ROOT / "src"))

from kiomet_ai.replay import run_battle_differential  # noqa: E402


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON number: {value}")


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"),
                           parse_constant=_reject_constant)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _read_jsonl(path: Path) -> tuple[list[dict], int]:
    rows = []
    malformed = 0
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line, parse_constant=_reject_constant)
                except ValueError:
                    malformed += 1
                    continue
                if isinstance(value, dict):
                    rows.append(value)
                else:
                    malformed += 1
    except OSError:
        return [], malformed
    return rows, malformed


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _inside_root(root: Path, path: Path) -> Path:
    target = path if path.is_absolute() else root / path
    target = target.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("input/output path must stay inside project root") from exc
    return target


def _read_action_index(root: Path) -> tuple[dict[str, list[dict]], int, bool]:
    path = root / "runtime/logs/live_actions.jsonl"
    if not path.is_file():
        return {}, 0, False
    rows, malformed = _read_jsonl(path)
    index: dict[str, list[dict]] = {}
    for row in rows:
        action_id = row.get("action_id")
        if isinstance(action_id, str) and action_id:
            index.setdefault(action_id, []).append(row)
    return index, malformed, True


def _action_match(row: dict, case: dict) -> bool:
    match_id = row.get("match_id")
    if match_id is None:
        match_id = row.get("match")
    source = row.get("source_tower_id")
    if source is None:
        source = row.get("source")
    target = row.get("target_tower_id")
    if target is None:
        target = row.get("target")
    return all(type(left) is type(right) and left == right for left, right in (
        (row.get("action_id"), case["action_id"]),
        (match_id, case["match_id"]),
        (source, case["source"]),
        (target, case["target"]),
    ))


def _mirror_assessment(diff: dict) -> dict:
    raw = {
        "attacker_units": diff.get("before_attacker"),
        "defender_units": diff.get("before_defender"),
        "tower_type": diff.get("target_type"),
        "self_id": diff.get("source_owner_id"),
        "enemy_id": diff.get("target_owner_id"),
    }
    try:
        return run_battle_differential(raw)
    except Exception as exc:  # Keep collector read-only and fail closed on bad cases.
        return {"support_status": "UNKNOWN", "differential": "EVALUATION_ERROR",
                "reason": type(exc).__name__, "prediction": None}


def _compact_prediction(value: Any) -> dict | str | None:
    if isinstance(value, str):
        return value[:128]
    if not isinstance(value, dict):
        return None
    result = {}
    winner = value.get("winner")
    if isinstance(winner, str):
        result["winner"] = winner[:64]
    for field in ("attacker_survivors", "defender_survivors"):
        survivors = value.get(field)
        if type(survivors) is int and survivors >= 0:
            result[field] = survivors
        elif isinstance(survivors, dict):
            compact = {name: count for name, count in survivors.items()
                       if name in UNIT_NAMES and type(count) is int and count >= 0}
            if compact:
                result[field] = compact
    return result or None


def _queue_case(diff: dict, action_rows: list[dict]) -> dict:
    action_id = diff["action_id"]
    match_id = diff["match_id"]
    source = diff["source_tower"]
    target = diff["target_tower"]
    identity = {"action_id": action_id, "match_id": match_id,
                "source": source, "target": target}
    exact_rows = [row for row in action_rows if _action_match(row, identity)]
    reasons = []
    if not action_rows:
        reasons.append("live_action_record_missing")
    elif not exact_rows:
        reasons.append("live_action_identity_mismatch")
    elif len(exact_rows) != len(action_rows):
        reasons.append("live_action_identity_conflict")
    elif len(exact_rows) > 1:
        reasons.append("duplicate_live_action_records")

    action = exact_rows[0] if len(exact_rows) == 1 else None
    if action is None:
        reasons.append("action_kind_unconfirmed")
    elif action.get("action_kind") != "ATTACK_ENEMY":
        reasons.append("action_kind_not_verified_as_attack_enemy")
    if action is not None and action.get("origin") != "LIVE_CONTROLLER":
        reasons.append("live_controller_origin_unconfirmed")

    mirror = _mirror_assessment(diff)
    raw_support = mirror.get("support_status")
    if raw_support in ("PREDICTED_NO_TRUTH", "MATCH", "MISMATCH"):
        supported_case = "SUPPORTED"
    elif raw_support == "MIRROR_UNSUPPORTED":
        supported_case = "UNSUPPORTED"
        reasons.append("battle_mirror_unsupported")
    else:
        supported_case = "UNKNOWN"
        reasons.append("battle_mirror_support_unknown")

    runtime_prediction = _compact_prediction(diff.get("prediction"))
    if runtime_prediction is not None:
        predicted_result = {"source": "LIVE_BATTLE_DIFFERENTIAL",
                            "value": runtime_prediction}
    elif (mirror_prediction := _compact_prediction(mirror.get("prediction"))) \
            is not None:
        predicted_result = {"source": "BATTLE_MIRROR_REPLAY",
                            "value": mirror_prediction}
        reasons.append("runtime_prediction_missing")
    else:
        predicted_result = None
        reasons.append("predicted_result_missing")

    after_target = diff.get("after_target")
    after_owner = (after_target.get("owner")
                   if isinstance(after_target, dict) else None)
    observed = {}
    if action is not None:
        verifier = action.get("verifier")
        result = action.get("result")
        if isinstance(verifier, str):
            observed["verifier"] = verifier
        if isinstance(result, str):
            observed["result"] = result
    if isinstance(after_owner, str):
        observed["target_owner_after"] = after_owner
    observed_result = observed or None
    if not (action and isinstance(action.get("verifier"), str)):
        reasons.append("verified_battle_result_missing")

    if not reasons:
        reasons.append("awaiting_independent_battle_review")
    return {
        **identity,
        "action_kind": ("ATTACK_ENEMY" if action and
                        action.get("action_kind") == "ATTACK_ENEMY"
                        else "UNKNOWN"),
        "predicted_result": predicted_result,
        "observed_result": observed_result,
        "supported_case": supported_case,
        "needs_review": True,
        "reason": ";".join(reasons),
        "evidence_path": None,
        "mirror_differential": mirror.get("differential"),
    }


def build_queue(root: str | Path = ROOT,
                max_cases: int = DEFAULT_MAX_CASES) -> dict:
    """只整理明確 SELF→ENEMY 個案；缺少身分的資料不會被猜成敵戰。"""
    project_root = Path(root).resolve()
    if type(max_cases) is not int or max_cases < 1:
        raise ValueError("max_cases must be a positive integer")
    base = project_root / "runtime/research/pvp_validation"
    cases = []
    counts = {"differentials_scanned": 0, "enemy_relation_candidates": 0,
              "excluded_non_enemy": 0, "excluded_unknown_owner": 0,
              "unidentifiable_enemy_candidates": 0,
              "malformed_differentials": 0}
    action_index, malformed_actions, action_log_present = _read_action_index(
        project_root)
    if base.is_dir():
        for directory in sorted(base.iterdir(), key=lambda item: item.name):
            if not directory.is_dir():
                continue
            path = _inside_root(project_root,
                                directory / "battle-differential.json")
            if not path.is_file():
                continue
            counts["differentials_scanned"] += 1
            diff = _read_json(path)
            if diff is None:
                counts["malformed_differentials"] += 1
                continue
            source_owner = diff.get("source_owner")
            target_owner = diff.get("target_owner")
            if source_owner == "UNKNOWN" or target_owner == "UNKNOWN" \
                    or source_owner is None or target_owner is None:
                counts["excluded_unknown_owner"] += 1
                continue
            if (source_owner, target_owner) != ("SELF", "ENEMY"):
                counts["excluded_non_enemy"] += 1
                continue
            counts["enemy_relation_candidates"] += 1
            action_id = diff.get("action_id")
            match_id = diff.get("match_id")
            source = diff.get("source_tower")
            target = diff.get("target_tower")
            if (not isinstance(action_id, str) or not action_id
                    or len(action_id) > 512
                    or not isinstance(match_id, str) or not match_id
                    or len(match_id) > 256
                    or not _positive_int(source) or not _positive_int(target)
                    or source == target):
                counts["unidentifiable_enemy_candidates"] += 1
                continue
            queue_case = _queue_case(
                diff, action_index.get(action_id, []))
            queue_case["evidence_path"] = path.relative_to(
                project_root).as_posix()
            cases.append(queue_case)

    id_counts = {}
    for item in cases:
        id_counts[item["action_id"]] = id_counts.get(item["action_id"], 0) + 1
    duplicate_ids = {action_id for action_id, count in id_counts.items()
                     if count > 1}
    for item in cases:
        if item["action_id"] in duplicate_ids:
            item["reason"] += ";duplicate_differential_action_id"
    cases.sort(key=lambda item: (item["match_id"], item["action_id"]))
    omitted = max(0, len(cases) - max_cases)
    if omitted:
        cases = cases[:max_cases]
    return {
        "schema_version": 1,
        "queue": "battle_validation_queue",
        "generated_at": time.time(),
        "status": "NEEDS_REVIEW" if cases else "NO_CASES",
        "proof_status": "NOT_EVALUATED",
        "source_health": {
            "differential_root": ("READABLE" if base.is_dir() else "MISSING"),
            "live_action_log": ("READABLE" if action_log_present else "MISSING"),
            "malformed_live_action_rows": malformed_actions,
        },
        "summary": {**counts, "duplicate_differential_action_id_count":
                    len(duplicate_ids), "queued_cases": len(cases),
                    "omitted_case_count": omitted},
        "cases": cases,
        "limitations": [
            "只有來源 owner=SELF 且目標 owner=ENEMY 的明確差分會進入佇列。",
            "live action 只按 action_id、match_id、來源與目標精確連結；不以時間或路徑猜測。",
            "unsupported/unknown 評估與缺少驗證結果均保留供人工覆核；本佇列不代表攻擊 proof 通過。",
            "佇列輸出採單一檔案覆寫；每案保留獨立 evidence_path，不複製原始截圖或證據。",
        ],
    }


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
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-cases", type=int, default=DEFAULT_MAX_CASES)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        output = _inside_root(root, args.out)
        report = build_queue(root, args.max_cases)
    except ValueError as exc:
        parser.error(str(exc))
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True,
                         indent=2, allow_nan=False) + "\n"
    _atomic_write(output, encoded)
    print(json.dumps({"status": report["status"],
                      "queued_cases": report["summary"]["queued_cases"],
                      "output": output.relative_to(root).as_posix()},
                     ensure_ascii=False))
    return 0 if report["status"] == "NEEDS_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
