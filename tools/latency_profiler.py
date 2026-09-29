"""唯讀彙整正式行動日誌中可直接計算的延遲。"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path("runtime/logs/live_actions.jsonl")
ACTION_KINDS = {"ATTACK_ENEMY", "REINFORCE_SELF", "EXPAND_NEUTRAL"}


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON number: {value}")


def _finite_number(value: Any, *, allow_zero: bool = False) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        number = float(value)
        return math.isfinite(number) and (number >= 0 if allow_zero
                                          else number > 0)
    except (OverflowError, ValueError):
        return False


def _inside_root(root: Path, path: Path) -> Path:
    target = path if path.is_absolute() else root / path
    target = target.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("input/output path must stay inside the project root") from exc
    return target


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def _stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "min": None, "median": None, "p95": None,
                "max": None, "mean": None}
    return {
        "count": len(values),
        "min": round(min(values), 3),
        "median": round(statistics.median(values), 3),
        "p95": round(_percentile(values, 0.95), 3),
        "max": round(max(values), 3),
        "mean": round(sum(values) / len(values), 3),
    }


def _read_rows(path: Path) -> tuple[list[dict], int, str | None]:
    rows: list[dict] = []
    malformed = 0
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line, parse_constant=_reject_constant)
                except (ValueError, json.JSONDecodeError):
                    malformed += 1
                    continue
                if isinstance(value, dict):
                    rows.append(value)
                else:
                    malformed += 1
    except OSError:
        return [], malformed, "UNREADABLE"
    return rows, malformed, None


def profile_actions(root: str | Path = ROOT,
                    input_path: str | Path = DEFAULT_INPUT) -> dict:
    """只計算有明確同筆時間戳的行動延遲，不推定缺失階段。"""
    project_root = Path(root).resolve()
    generated_at = time.time()
    source = _inside_root(project_root, Path(input_path))
    if not source.is_file():
        return {
            "schema_version": 1,
            "profiler": "latency_profiler",
            "generated_at": generated_at,
            "status": "NO_DATA",
            "proof_status": "NOT_EVALUATED",
            "source": source.relative_to(project_root).as_posix(),
            "source_health": {"status": "MISSING", "rows_scanned": 0,
                              "malformed_rows": 0,
                              "latest_action": None,
                              "latest_action_age_seconds": None},
            "coverage": {},
            "metrics": {
                "controller_reported_duration_seconds": _stats([]),
                "dispatch_to_completion_log_seconds": _stats([]),
            },
            "by_action_kind": {},
            "slowest_actions": [],
            "limitations": ["行動日誌不存在；沒有延遲樣本可計算。"],
        }

    rows, malformed, read_error = _read_rows(source)
    if read_error:
        source_status = read_error
    else:
        source_status = "READABLE"

    duplicate_counts = Counter(
        row.get("action_id") for row in rows
        if isinstance(row.get("action_id"), str) and row["action_id"]
    )
    duplicate_ids = {action_id for action_id, count in duplicate_counts.items()
                      if count > 1}
    totals = Counter()
    duration_samples: list[tuple[dict, float]] = []
    dispatch_samples: list[tuple[dict, float]] = []
    grouped_duration: dict[str, list[float]] = defaultdict(list)
    grouped_dispatch: dict[str, list[float]] = defaultdict(list)
    invalid_intervals = 0
    latest_action: dict | None = None
    latest_logged_at: float | None = None

    for row in rows:
        action_id = row.get("action_id")
        has_id = isinstance(action_id, str) and bool(action_id)
        match_id = row.get("match_id")
        if match_id is None:
            match_id = row.get("match")
        has_match = isinstance(match_id, str) and bool(match_id)
        raw_kind = row.get("action_kind")
        action_kind = (raw_kind if isinstance(raw_kind, str)
                       and raw_kind in ACTION_KINDS else "UNKNOWN")
        if has_id:
            totals["rows_with_action_id"] += 1
        else:
            totals["missing_action_id"] += 1
        if has_match:
            totals["rows_with_match_id"] += 1
        else:
            totals["missing_match_id"] += 1
        if action_kind != "UNKNOWN":
            totals["rows_with_explicit_action_kind"] += 1
        else:
            totals["rows_with_unknown_action_kind"] += 1

        if action_id in duplicate_ids:
            totals["duplicate_rows_excluded"] += 1
            continue

        duration = row.get("duration_s")
        if _finite_number(duration, allow_zero=True):
            duration = float(duration)
            duration_samples.append((row, duration))
            grouped_duration[action_kind].append(duration)
        else:
            totals["missing_or_invalid_duration"] += 1

        dispatch = row.get("dispatch")
        sent_at = dispatch.get("sent_at") if isinstance(dispatch, dict) else None
        logged_at = row.get("logged_at")
        if _finite_number(logged_at):
            logged_value = float(logged_at)
            if latest_logged_at is None or logged_value > latest_logged_at:
                latest_logged_at = logged_value
                latest_action = {
                    "action_id": action_id if has_id else None,
                    "match_id": match_id if has_match else None,
                    "logged_at": logged_value,
                }
        if not has_id or not has_match:
            totals["unbound_dispatch_interval"] += 1
        elif not _finite_number(sent_at) or not _finite_number(logged_at):
            totals["missing_or_invalid_interval_timestamp"] += 1
        elif float(logged_at) < float(sent_at):
            invalid_intervals += 1
            totals["timestamp_order_errors"] += 1
        else:
            elapsed = float(logged_at) - float(sent_at)
            dispatch_samples.append((row, elapsed))
            grouped_dispatch[action_kind].append(elapsed)

    duration_values = [value for _, value in duration_samples]
    dispatch_values = [value for _, value in dispatch_samples]
    slowest = sorted(duration_samples, key=lambda item: item[1], reverse=True)[:5]
    slowest_rows = []
    dispatch_by_id = {
        row.get("action_id"): elapsed for row, elapsed in dispatch_samples
        if isinstance(row.get("action_id"), str)
    }
    for row, duration in slowest:
        candidate_match_id = row.get("match_id")
        if candidate_match_id is None:
            candidate_match_id = row.get("match")
        slowest_rows.append({
            "action_id": (row.get("action_id")
                          if isinstance(row.get("action_id"), str) else None),
            "match_id": (candidate_match_id
                         if isinstance(candidate_match_id, str) else None),
            "action_kind": (row.get("action_kind")
                            if isinstance(row.get("action_kind"), str)
                            and row["action_kind"] in ACTION_KINDS
                            else "UNKNOWN"),
            "controller_reported_duration_seconds": round(duration, 3),
            "dispatch_to_completion_log_seconds": (
                round(dispatch_by_id[row["action_id"]], 3)
                if row.get("action_id") in dispatch_by_id else None),
            "result": row.get("result") if isinstance(row.get("result"), str)
            else None,
        })

    incomplete = (malformed > 0 or invalid_intervals > 0
                  or totals["missing_action_id"] > 0
                  or totals["missing_match_id"] > 0
                  or totals["rows_with_unknown_action_kind"] > 0
                  or totals["missing_or_invalid_duration"] > 0
                  or totals["missing_or_invalid_interval_timestamp"] > 0
                  or totals["unbound_dispatch_interval"] > 0
                  or bool(duplicate_ids))
    if read_error:
        status = "ERROR"
    elif not rows:
        status = "PARTIAL" if malformed else "NO_DATA"
    elif incomplete:
        status = "PARTIAL"
    elif not duration_values and not dispatch_values:
        status = "NO_MEASUREMENTS"
    else:
        status = "OK"

    kind_names = sorted(set(grouped_duration) | set(grouped_dispatch))
    report = {
        "schema_version": 1,
        "profiler": "latency_profiler",
        "generated_at": generated_at,
        "status": status,
        "proof_status": "NOT_EVALUATED",
        "source": source.relative_to(project_root).as_posix(),
        "source_health": {
            "status": source_status,
            "rows_scanned": len(rows),
            "malformed_rows": malformed,
            "latest_action": latest_action,
            "latest_action_age_seconds": (
                round(max(0.0, generated_at - latest_logged_at), 3)
                if latest_logged_at is not None and latest_logged_at <= generated_at
                else None),
        },
        "coverage": {
            **dict(totals),
            "duplicate_action_id_count": len(duplicate_ids),
            "duplicate_rows_excluded": totals["duplicate_rows_excluded"],
            "controller_duration_sample_count": len(duration_values),
            "dispatch_interval_sample_count": len(dispatch_values),
            "timestamp_order_errors": invalid_intervals,
        },
        "metrics": {
            "controller_reported_duration_seconds": _stats(duration_values),
            "dispatch_to_completion_log_seconds": _stats(dispatch_values),
        },
        "by_action_kind": {
            kind: {
                "controller_reported_duration_seconds": _stats(
                    grouped_duration.get(kind, [])),
                "dispatch_to_completion_log_seconds": _stats(
                    grouped_dispatch.get(kind, [])),
            }
            for kind in kind_names
        },
        "slowest_actions": slowest_rows,
        "limitations": [
            "action_kind 只採用日誌明確欄位；缺失時標成 UNKNOWN，不從塔座或結果推定。",
            "第二項時間是同一行動日誌中的 dispatch.sent_at 至 logged_at；它不等於遊戲內部到達時間。",
            "來源沒有逐階段觀察、抵達或戰鬥時間戳，因此不估算這些階段。",
            "這份報告只描述輸入日誌的最後記錄，不代表目前對局或即時控制器狀態。",
            "proof_status 固定為 NOT_EVALUATED；延遲統計不是行動驗證。",
        ],
    }
    return report


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
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        source = _inside_root(root, args.input)
        target = _inside_root(root, args.out) if args.out is not None else None
    except ValueError as exc:
        parser.error(str(exc))
    report = profile_actions(root, source)
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True,
                         indent=2, allow_nan=False) + "\n"
    if target is not None:
        _atomic_write(target, encoded)
    print(encoded, end="")
    return (0 if report["status"] == "OK" else
            1 if report["status"] == "ERROR" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
