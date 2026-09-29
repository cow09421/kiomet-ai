"""Replay（重播）及執行期證據的自動掃描器。

單次執行會重建一份有界索引；--watch 會定期重掃並覆寫同一份報告。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from evidence_index import build_index  # noqa: E402
from kiomet_ai.replay import replay_case  # noqa: E402


IDENTITY_FIELDS = (
    ("action_id", "action_id"),
    ("match_id", "match_id"),
    ("cycle_id", "cycle_id"),
    ("source_tower_id", "source_tower"),
    ("target_tower_id", "target_tower"),
)
ACTION_KIND_TARGET_OWNER = {
    "EXPAND_NEUTRAL": "NEUTRAL",
    "REINFORCE_SELF": "SELF",
    "ATTACK_ENEMY": "ENEMY",
}
SAMPLE_NAMES = ("t0", "t1", "t2", "t3")
SIDES = ("source", "target")


def _valid_identity(field: str, value) -> bool:
    if field in ("action_id", "match_id"):
        return isinstance(value, str) and bool(value)
    if field == "cycle_id":
        return type(value) is int and value >= 0
    return type(value) is int and value > 0


def _timestamp(value) -> float | None:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value <= 0):
        return None
    return float(value)


def validate_case_integrity(diff: dict | None, bundle: dict | None,
                            action: dict | None = None) -> dict:
    """檢查行動綁定、時間順序、對局污染與所有者關係。

    缺資料回 UNKNOWN；只有可證明不一致時才回 INVALID。
    """
    issues = []
    unknown = []
    if not isinstance(diff, dict):
        return {"status": "UNKNOWN", "issues": ["differential-missing"]}
    if not isinstance(bundle, dict):
        return {"status": "UNKNOWN", "issues": ["force-bundle-missing"]}

    identity = {"diff": diff, "bundle": bundle}
    if isinstance(action, dict):
        identity["action"] = action
    else:
        unknown.append("action-log-row-missing")

    canonical = {}
    for field, diff_key in IDENTITY_FIELDS:
        bundle_key = {
            "action_id": "action_id", "match_id": "match_id",
            "cycle_id": "cycle_id", "source_tower_id": "source",
            "target_tower_id": "target",
        }[field]
        values = []
        for label, record in identity.items():
            key = diff_key if label == "diff" else bundle_key
            if label == "action":
                key = {"action_id": "action_id", "match_id": "match_id",
                       "cycle_id": "cycle_id", "source_tower_id": "source",
                       "target_tower_id": "target"}[field]
            value = record.get(key)
            if value is None:
                unknown.append(f"{label}-missing-{field}")
                continue
            if not _valid_identity(field, value):
                issues.append(f"{label}-invalid-{field}")
                continue
            values.append((label, value))
        if values:
            canonical[field] = values[0][1]
            if any(type(value) is not type(values[0][1])
                   or value != values[0][1] for _, value in values[1:]):
                issues.append(f"binding-mismatch-{field}")

    action_kind = action.get("action_kind") if isinstance(action, dict) else None
    target_owner = diff.get("target_owner")
    source_owner = diff.get("source_owner")
    expected_owner = ACTION_KIND_TARGET_OWNER.get(action_kind)
    if expected_owner is None:
        unknown.append("action-kind-unknown")
    else:
        if source_owner is None:
            unknown.append("source-owner-unknown")
        elif source_owner != "SELF":
            issues.append("source-owner-not-self")
        if target_owner is None:
            unknown.append("target-owner-unknown")
        elif target_owner != expected_owner:
            issues.append("target-owner-action-kind-mismatch")
        if expected_owner == "ENEMY":
            attacker_id = diff.get("source_owner_id")
            defender_id = diff.get("target_owner_id")
            if (type(attacker_id) is not int or attacker_id <= 0
                    or type(defender_id) is not int or defender_id <= 0):
                unknown.append("enemy-owner-id-unknown")
            elif attacker_id == defender_id:
                issues.append("enemy-owner-id-equals-self")

    dispatched_at = _timestamp(bundle.get("dispatched_at"))
    if dispatched_at is None:
        unknown.append("dispatch-time-unknown")

    observed_times = {side: {} for side in SIDES}
    tower_refs = {side: None for side in SIDES}
    expected_match = canonical.get("match_id")
    for sample_name in SAMPLE_NAMES:
        sample = bundle.get(sample_name)
        if not isinstance(sample, dict):
            unknown.append(f"{sample_name}-snapshot-missing")
            continue
        for side in SIDES:
            snapshot = sample.get(side)
            if not isinstance(snapshot, dict):
                unknown.append(f"{sample_name}-{side}-snapshot-missing")
                continue
            snapshot_match = snapshot.get("match_id")
            if not isinstance(snapshot_match, str) or not snapshot_match:
                unknown.append(f"{sample_name}-{side}-match-unknown")
            elif expected_match and snapshot_match != expected_match:
                issues.append(f"{sample_name}-{side}-match-mismatch")

            tower_ref = snapshot.get("tower_ref")
            if type(tower_ref) is not int or tower_ref <= 0:
                unknown.append(f"{sample_name}-{side}-tower-ref-unknown")
            elif tower_refs[side] is None:
                tower_refs[side] = tower_ref
            elif tower_refs[side] != tower_ref:
                issues.append(f"{sample_name}-{side}-tower-ref-mismatch")

            captured_at = _timestamp(snapshot.get("captured_at"))
            if captured_at is None:
                unknown.append(f"{sample_name}-{side}-time-unknown")
                continue
            observed_times[side][sample_name] = captured_at
            if dispatched_at is None:
                continue
            if sample_name == "t0":
                age = dispatched_at - captured_at
                if age <= 0:
                    issues.append(f"{side}-t0-after-dispatch-time")
                elif age > 30.0:
                    issues.append(f"{side}-t0-stale-before-dispatch")
            else:
                delay = captured_at - dispatched_at
                if delay <= 0:
                    issues.append(f"{side}-{sample_name}-before-dispatch-time")
                elif delay > 30.0:
                    issues.append(f"{side}-{sample_name}-stale-after-dispatch")

    for side in SIDES:
        times = observed_times[side]
        ordered = [times[name] for name in SAMPLE_NAMES if name in times]
        if len(ordered) == len(SAMPLE_NAMES) and any(
                later <= earlier for earlier, later in zip(ordered, ordered[1:])):
            issues.append(f"{side}-snapshot-time-order-invalid")
        elif len(ordered) != len(SAMPLE_NAMES):
            unknown.append(f"{side}-snapshot-time-order-unknown")

    status = "INVALID" if issues else "UNKNOWN" if unknown else "PASS"
    return {"status": status, "issues": sorted(set(issues + unknown))}


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def _replay_cases(root: Path) -> dict:
    base = root / "runtime/research/pvp_validation"
    cases, skipped = [], []
    if base.is_dir():
        for sub in sorted(path for path in base.iterdir() if path.is_dir()):
            diff_path = sub / "battle-differential.json"
            if not diff_path.is_file():
                continue
            try:
                diff = json.loads(diff_path.read_text(encoding="utf-8"))
                bundle_path = (root / "runtime/research/forces"
                               / "autonomous_validation" / sub.name
                               / "bundle.json")
                bundle = _read_json(bundle_path) if bundle_path.is_file() else None
                cases.append(replay_case({"case_id": sub.name,
                                          "diff": diff,
                                          "bundle": bundle}))
            except (OSError, ValueError, TypeError, KeyError) as exc:
                skipped.append({"case": sub.name,
                                "error": str(exc)[:120]})
    summary = {
        "cases": len(cases),
        "flagged": sum(case.get("status") == "FLAGGED" for case in cases),
        "replayed": sum(case.get("status") == "REPLAYED" for case in cases),
        "self_ids_found": sorted({
            case.get("id_evidence", {}).get("self_id") for case in cases
            if case.get("id_evidence", {}).get("self_id")}),
        "skipped": skipped,
    }
    return {"summary": summary, "cases": cases}


def _integrity_cases(root: Path, index: dict) -> dict:
    base = root / "runtime/research/pvp_validation"
    action_rows = (index.get("actions") or []) if isinstance(index, dict) else []
    actions_by_id = {}
    for row in action_rows:
        if isinstance(row, dict) and isinstance(row.get("action_id"), str):
            actions_by_id.setdefault(row["action_id"], []).append(row)

    cases = []
    if base.is_dir():
        for sub in sorted(path for path in base.iterdir() if path.is_dir()):
            diff_path = sub / "battle-differential.json"
            if not diff_path.is_file():
                continue
            diff = _read_json(diff_path)
            bundle_path = (root / "runtime/research/forces"
                           / "autonomous_validation" / sub.name
                           / "bundle.json")
            bundle = _read_json(bundle_path) if bundle_path.is_file() else None
            action_id = diff.get("action_id") if isinstance(diff, dict) else None
            action_rows_for_case = actions_by_id.get(action_id, [])
            action = action_rows_for_case[0] if len(action_rows_for_case) == 1 else None
            integrity = validate_case_integrity(diff, bundle, action)
            if len(action_rows_for_case) > 1:
                integrity = {"status": "INVALID",
                             "issues": ["duplicate-action-log-rows"]}
            if diff is None:
                integrity = {"status": "INVALID",
                             "issues": ["differential-json-invalid"]}
            elif bundle_path.is_file() and bundle is None:
                integrity = {"status": "INVALID",
                             "issues": ["force-bundle-json-invalid"]}
            cases.append({"case_id": sub.name, **integrity})

    counts = {status.lower(): sum(row["status"] == status for row in cases)
              for status in ("PASS", "INVALID", "UNKNOWN")}
    if counts["invalid"]:
        status = "INVALID"
    elif counts["unknown"] or not cases:
        status = "UNKNOWN"
    else:
        status = "PASS"
    return {"status": status, "cases": len(cases), **counts,
            "items": cases}


def build_auto_index(root: Path | None = None,
                     generated_at: float | None = None) -> dict:
    """重新掃描最新重播、綁定完整性、行動及 crash（崩潰）索引。"""
    root = Path(root if root is not None else ROOT).resolve()
    evidence = build_index(root)
    replay = _replay_cases(root)
    integrity = _integrity_cases(root, evidence)
    return {
        "schema_version": 1,
        "generated_at": time.time() if generated_at is None else generated_at,
        "replay": replay,
        "integrity": integrity,
        "evidence": evidence,
    }


def write_report(path: Path, report: dict, *, root: Path) -> Path:
    """在專案根目錄內原子覆寫單一報告，避免累積快照檔。"""
    root = Path(root).resolve()
    dest = Path(path)
    if not dest.is_absolute():
        dest = root / dest
    dest = dest.resolve()
    if dest == root or root not in dest.parents:
        raise ValueError("output-path-must-stay-under-project-root")
    dest.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n",
                dir=dest.parent, prefix=dest.name + ".",
                suffix=".tmp", delete=False) as temp:
            temp_name = temp.name
            temp.write(encoded)
        os.replace(temp_name, dest)
        temp_name = None
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()
    return dest


def _summary(report: dict, out: Path) -> dict:
    return {
        "cases": report["replay"]["summary"]["cases"],
        "flagged": report["replay"]["summary"]["flagged"],
        "integrity": report["integrity"]["status"],
        "integrity_invalid": report["integrity"]["invalid"],
        "crashes": len(report["evidence"].get("crashes") or []),
        "report": str(out),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--watch", action="store_true",
                        help="定期重掃並覆寫同一份索引")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    out = args.out or Path("runtime/research/replay-auto-index.json")
    if (not math.isfinite(args.interval) or args.interval <= 0
            or args.interval > 3600):
        print(json.dumps({"error": "interval-must-be-between-0-and-3600"}))
        return 2

    try:
        while True:
            report = build_auto_index(root)
            dest = write_report(out, report, root=root)
            print(json.dumps(_summary(report, dest), ensure_ascii=False))
            if not args.watch:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)[:160]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
