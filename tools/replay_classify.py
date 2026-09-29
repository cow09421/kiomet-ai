"""Build one fail-closed classification index for replay evidence."""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KIND_MAP = {
    "EXPAND_NEUTRAL": "NEUTRAL_EXPANSION",
    "NEUTRAL_EXPANSION": "NEUTRAL_EXPANSION",
    "REINFORCE_SELF": "SELF_REINFORCE",
    "SELF_REINFORCE": "SELF_REINFORCE",
    "ENEMY_THREAT": "ENEMY_THREAT",
    "ATTACK_ENEMY": "ATTACK_ENEMY",
}
OWNER_VALUES = {"SELF", "ENEMY", "NEUTRAL", "UNKNOWN"}
REQUIRED_FILES = {"differential", "derived_meta", "bundle", "action"}


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _path_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _read_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return None, "invalid-json"
    if not isinstance(value, dict):
        return None, "json-root-not-object"
    return value, None


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _group(groups: dict[str, dict], key: str,
           case_id: str | None = None) -> dict:
    if key not in groups:
        groups[key] = {
            "case_id": case_id,
            "artifacts": [],
            "files": set(),
            "invalid": [],
            "partial": [],
        }
    return groups[key]


def _add_artifact(root: Path, group: dict, label: str,
                  path: Path) -> dict | None:
    if not _path_inside(root, path):
        group["invalid"].append(f"{label}-path-outside-root")
        return None
    relative = _relative(root, path)
    group["files"].add(relative)
    value, error = _read_json(path)
    artifact = {"label": label, "path": relative, "data": value}
    group["artifacts"].append(artifact)
    if error:
        group["invalid"].append(f"{label}-{error}")
    return value


def _load_case_artifacts(root: Path) -> tuple[dict[str, dict], list[dict]]:
    groups: dict[str, dict] = {}
    actions: list[dict] = []

    pvp_root = root / "runtime/research/pvp_validation"
    if pvp_root.is_dir():
        for case_dir in sorted(pvp_root.iterdir()):
            if not case_dir.is_dir() or not _path_inside(root, case_dir):
                continue
            group = _group(groups, f"case:{case_dir.name}", case_dir.name)
            for filename, label in (("battle-differential.json", "differential"),
                                    ("derived-meta.json", "derived_meta")):
                path = case_dir / filename
                if path.is_file():
                    _add_artifact(root, group, label, path)

    bundle_root = root / "runtime/research/forces/autonomous_validation"
    if bundle_root.is_dir():
        for case_dir in sorted(bundle_root.iterdir()):
            if not case_dir.is_dir() or not _path_inside(root, case_dir):
                continue
            group = _group(groups, f"case:{case_dir.name}", case_dir.name)
            path = case_dir / "bundle.json"
            if path.is_file():
                _add_artifact(root, group, "bundle", path)

    action_log = root / "runtime/logs/live_actions.jsonl"
    if action_log.is_file() and _path_inside(root, action_log):
        relative = _relative(root, action_log)
        try:
            lines = action_log.read_text(
                encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            lines = []
        for line_number, line in enumerate(lines, start=1):
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(row, dict) and _valid_id(row.get("action_id")):
                actions.append({"data": row, "path": relative,
                                "line": line_number})

    return groups, actions


def _explicit_action_ids(group: dict) -> set[str]:
    values = set()
    for artifact in group["artifacts"]:
        data = artifact.get("data")
        if isinstance(data, dict) and _valid_id(data.get("action_id")):
            values.add(data["action_id"])
    return values


def _attach_action_rows(groups: dict[str, dict],
                        actions: list[dict]) -> None:
    groups_by_action: dict[str, list[dict]] = {}
    for group in groups.values():
        for action_id in _explicit_action_ids(group):
            groups_by_action.setdefault(action_id, []).append(group)

    for row in actions:
        action_id = row["data"]["action_id"]
        targets = groups_by_action.get(action_id, [])
        if not targets:
            target = _group(groups, f"action:{action_id}")
            targets = [target]
            groups_by_action[action_id] = targets
        for target in targets:
            target["files"].add(row["path"])
            target["artifacts"].append({"label": "action",
                                        "path": row["path"],
                                        "line": row["line"],
                                        "data": row["data"]})
            if len(targets) > 1:
                target["invalid"].append("duplicate-case-action-id")


def _field_values(group: dict, field: str) -> tuple[list[Any], bool]:
    values: list[Any] = []
    malformed = False
    for artifact in group["artifacts"]:
        data = artifact.get("data")
        if not isinstance(data, dict):
            continue
        label = artifact["label"]
        keys = {
            "action_id": ("action_id",),
            "match_id": ("match", "match_id") if label == "action"
            else ("match_id",),
            "source_tower_id": ("source", "source_tower", "source_tower_id")
            if label == "action" or label == "bundle"
            else ("source_tower", "source", "source_tower_id"),
            "target_tower_id": ("target", "target_tower", "target_tower_id")
            if label == "action" or label == "bundle"
            else ("target_tower", "target", "target_tower_id"),
            "cycle_id": ("cycle_id",),
        }.get(field, ())
        for key in keys:
            if key not in data:
                continue
            value = data.get(key)
            if value is None or value == "" or value == "UNKNOWN":
                continue
            if field in ("action_id", "match_id"):
                if not _valid_id(value):
                    malformed = True
                else:
                    values.append(value)
            elif field == "cycle_id":
                if type(value) is not int or value < 0:
                    malformed = True
                else:
                    values.append(value)
            elif type(value) is not int or value <= 0:
                malformed = True
            else:
                values.append(value)
    return values, malformed


def _owner_values(group: dict, side: str) -> tuple[list[str], bool]:
    key = f"{side}_owner"
    values: list[str] = []
    malformed = False
    for artifact in group["artifacts"]:
        data = artifact.get("data")
        if not isinstance(data, dict):
            continue
        candidates = [data.get(key)]
        # Some capture formats put an explicit owner beside each endpoint.
        for sample_name in ("t0", "t1", "t2", "t3"):
            sample = data.get(sample_name)
            endpoint = sample.get(side) if isinstance(sample, dict) else None
            if isinstance(endpoint, dict):
                candidates.append(endpoint.get("owner"))
        before_key = "before_attacker" if side == "source" else "before_defender"
        before = data.get(before_key)
        if isinstance(before, dict):
            candidates.append(before.get("owner"))
        for value in candidates:
            if value is None or value == "" or value == "UNKNOWN":
                continue
            if not isinstance(value, str) or value.upper() not in OWNER_VALUES:
                malformed = True
            else:
                values.append(value.upper())
    return values, malformed


def _kind_values(group: dict) -> tuple[list[str], bool]:
    values: list[str] = []
    malformed = False
    for artifact in group["artifacts"]:
        data = artifact.get("data")
        if not isinstance(data, dict):
            continue
        for key in ("action_kind", "event_kind"):
            value = data.get(key)
            if value is None or value == "" or value == "UNKNOWN":
                continue
            if not isinstance(value, str):
                malformed = True
            else:
                values.append(value.strip().upper())
    return values, malformed


def _verdict_values(group: dict) -> tuple[list[str], bool]:
    values: list[str] = []
    malformed = False
    for artifact in group["artifacts"]:
        data = artifact.get("data")
        if not isinstance(data, dict):
            continue
        value = data.get("verdict") or data.get("verifier")
        if value is None or value == "":
            value = data.get("result")
        if value is None or value == "" or value == "UNKNOWN":
            continue
        if not isinstance(value, str):
            malformed = True
        else:
            values.append(value.strip().upper())
    return values, malformed


def _consensus(values: list[Any]) -> tuple[Any, bool]:
    unique = []
    for value in values:
        if not any(type(value) is type(existing) and value == existing
                   for existing in unique):
            unique.append(value)
    return (unique[0] if len(unique) == 1 else None, len(unique) > 1)


def _positive_time(value: Any) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and value > 0)


def _evidence_shape(group: dict, match_id: str | None
                    ) -> tuple[list[str], list[str]]:
    """Check only the required capture shape and timestamp ordering."""
    invalid: list[str] = []
    partial: list[str] = []
    by_label: dict[str, list[dict]] = {}
    for artifact in group["artifacts"]:
        by_label.setdefault(artifact["label"], []).append(artifact)
    for label in ("differential", "derived_meta", "bundle"):
        if len(by_label.get(label, [])) > 1:
            invalid.append(f"duplicate-{label}-files")

    metas = by_label.get("derived_meta", [])
    meta = metas[0].get("data") if metas else None
    if not isinstance(meta, dict):
        partial.append("dispatch-times-unavailable")
        dispatched_at = logged_at = None
    else:
        times = []
        for key in ("dispatched_at", "logged_at"):
            value = meta.get(key)
            if value is None:
                partial.append(f"{key}-unknown")
                times.append(None)
            elif not _positive_time(value):
                invalid.append(f"{key}-invalid")
                times.append(None)
            else:
                times.append(float(value))
        dispatched_at, logged_at = times
        if (dispatched_at is not None and logged_at is not None
                and logged_at <= dispatched_at):
            invalid.append("logged-before-or-at-dispatch")

    bundles = by_label.get("bundle", [])
    bundle = bundles[0].get("data") if bundles else None
    if not isinstance(bundle, dict):
        partial.append("force-bundle-samples-unavailable")
        return invalid, partial

    captures: dict[str, list[float | None]] = {"source": [], "target": []}
    for sample_name in ("t0", "t1", "t2"):
        sample = bundle.get(sample_name)
        if not isinstance(sample, dict):
            partial.append(f"{sample_name}-snapshot-unknown")
            for side in captures:
                captures[side].append(None)
            continue
        for side in captures:
            snapshot = sample.get(side)
            if not isinstance(snapshot, dict):
                partial.append(f"{sample_name}-{side}-snapshot-unknown")
                captures[side].append(None)
                continue
            snapshot_match = snapshot.get("match_id")
            if not isinstance(snapshot_match, str) or not snapshot_match:
                partial.append(f"{sample_name}-{side}-match-unknown")
            elif match_id and snapshot_match != match_id:
                invalid.append(f"{sample_name}-{side}-match-mismatch")
            captured_at = snapshot.get("captured_at")
            if captured_at is None:
                partial.append(f"{sample_name}-{side}-time-unknown")
                captures[side].append(None)
            elif not _positive_time(captured_at):
                invalid.append(f"{sample_name}-{side}-time-invalid")
                captures[side].append(None)
            else:
                captures[side].append(float(captured_at))

    for side, values in captures.items():
        before, first_after, second_after = values
        if dispatched_at is not None:
            if before is not None and before >= dispatched_at:
                invalid.append(f"{side}-t0-not-before-dispatch")
            for name, value in (("t1", first_after), ("t2", second_after)):
                if value is not None and value <= dispatched_at:
                    invalid.append(f"{side}-{name}-not-after-dispatch")
        if (before is not None and first_after is not None
                and first_after <= before):
            invalid.append(f"{side}-t1-not-after-t0")
        if (first_after is not None and second_after is not None
                and second_after <= first_after):
            invalid.append(f"{side}-t2-not-after-t1")
    return invalid, partial


def _classify(group: dict) -> dict:
    invalid = list(group["invalid"])
    partial: list[str] = list(group["partial"])
    classification_notes: list[str] = []
    output: dict[str, Any] = {
        "case_id": group["case_id"],
        "match_id": None,
        "action_id": None,
        "kind": "UNKNOWN_ACTION",
        "source_owner": "UNKNOWN",
        "target_owner": "UNKNOWN",
        "source_tower_id": None,
        "target_tower_id": None,
        "cycle_id": None,
        "verdict": "UNKNOWN",
        "evidence_status": "PARTIAL",
        "files": sorted(group["files"]),
    }

    for field in ("action_id", "match_id", "source_tower_id",
                  "target_tower_id", "cycle_id"):
        values, malformed = _field_values(group, field)
        value, conflict = _consensus(values)
        if malformed:
            invalid.append(f"invalid-{field}")
        if conflict:
            invalid.append(f"conflicting-{field}")
        if value is None:
            partial.append(f"missing-{field}")
        else:
            output[field] = value

    raw_kinds, malformed_kind = _kind_values(group)
    if malformed_kind:
        invalid.append("invalid-action-kind")
    distinct_kinds = sorted(set(raw_kinds))
    if len(distinct_kinds) > 1:
        invalid.append("conflicting-action-kind")
    if len(distinct_kinds) == 1:
        output["kind"] = KIND_MAP.get(distinct_kinds[0], "UNKNOWN_ACTION")
        if output["kind"] == "UNKNOWN_ACTION":
            classification_notes.append("unrecognized-action-kind")
    else:
        classification_notes.append("action-kind-unknown")

    for side in ("source", "target"):
        values, malformed = _owner_values(group, side)
        value, conflict = _consensus(values)
        if malformed:
            invalid.append(f"invalid-{side}-owner")
        if conflict:
            invalid.append(f"conflicting-{side}-owner")
        if value is None:
            partial.append(f"{side}-owner-unknown")
        else:
            output[f"{side}_owner"] = value

    verdicts, malformed_verdict = _verdict_values(group)
    verdict, verdict_conflict = _consensus(verdicts)
    if malformed_verdict:
        invalid.append("invalid-verdict")
    if verdict_conflict:
        invalid.append("conflicting-verdict")
    if verdict is None:
        partial.append("verdict-unknown")
    else:
        output["verdict"] = verdict

    labels = {artifact["label"] for artifact in group["artifacts"]}
    if sum(artifact["label"] == "action"
           for artifact in group["artifacts"]) > 1:
        invalid.append("duplicate-action-log-rows")
    for label in sorted(REQUIRED_FILES - labels):
        partial.append(f"missing-{label}-file")

    expected_owners = {
        "NEUTRAL_EXPANSION": ("SELF", "NEUTRAL"),
        "SELF_REINFORCE": ("SELF", "SELF"),
        "ATTACK_ENEMY": ("SELF", "ENEMY"),
    }.get(output["kind"])
    if expected_owners:
        for side, expected in zip(("source_owner", "target_owner"),
                                  expected_owners):
            actual = output[side]
            if actual != "UNKNOWN" and actual != expected:
                invalid.append(f"{side}-action-kind-mismatch")

    shape_invalid, shape_partial = _evidence_shape(
        group, output["match_id"])
    invalid.extend(shape_invalid)
    partial.extend(shape_partial)

    output["classification_issues"] = sorted(set(classification_notes))
    output["issues"] = sorted(set(invalid + partial + classification_notes))
    if invalid:
        output["evidence_status"] = "INVALID"
    elif partial:
        output["evidence_status"] = "PARTIAL"
    else:
        output["evidence_status"] = "COMPLETE"
    return output


def build_replay_index(root: Path | None = None,
                       generated_at: float | None = None) -> dict:
    """Index replay cases using explicit action identity; missing stays unknown."""
    root = Path(root if root is not None else ROOT).resolve()
    if generated_at is None:
        generated_at = time.time()
    if (type(generated_at) not in (int, float)
            or not math.isfinite(generated_at) or generated_at <= 0):
        raise ValueError("generated-at-must-be-a-positive-finite-number")

    groups, actions = _load_case_artifacts(root)
    _attach_action_rows(groups, actions)
    items = [_classify(group) for _, group in sorted(groups.items())]
    statuses = ("COMPLETE", "PARTIAL", "INVALID")
    kinds = ("NEUTRAL_EXPANSION", "SELF_REINFORCE", "ENEMY_THREAT",
             "ATTACK_ENEMY", "UNKNOWN_ACTION")
    summary = {
        "items": len(items),
        "evidence_status": {
            status: sum(item["evidence_status"] == status for item in items)
            for status in statuses
        },
        "kind": {kind: sum(item["kind"] == kind for item in items)
                 for kind in kinds},
    }
    overall = ("INVALID" if summary["evidence_status"]["INVALID"] else
               "PARTIAL" if summary["evidence_status"]["PARTIAL"]
               or not items else "COMPLETE")
    return {"schema_version": 1, "generated_at": float(generated_at),
            "status": overall, "summary": summary, "items": items}


def write_index(path: Path, report: dict, *, root: Path) -> Path:
    """Atomically overwrite one index, with output constrained under root."""
    root = Path(root).resolve()
    dest = Path(path)
    if not dest.is_absolute():
        dest = root / dest
    dest = dest.resolve()
    if dest == root or not _path_inside(root, dest):
        raise ValueError("output-path-must-stay-under-project-root")
    dest.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, ensure_ascii=False, indent=2,
                         allow_nan=False)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n",
                dir=dest.parent, prefix=dest.name + ".",
                suffix=".tmp", delete=False) as stream:
            temp_name = stream.name
            stream.write(encoded)
        os.replace(temp_name, dest)
        temp_name = None
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path,
                        default=Path("runtime/research/replay/index.json"))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        report = build_replay_index(root)
        dest = write_index(args.out, report, root=root)
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)[:160]}, ensure_ascii=False))
        return 2
    print(json.dumps({"items": report["summary"]["items"],
                      "status": report["status"],
                      "evidence_status": report["summary"]["evidence_status"],
                      "kind": report["summary"]["kind"],
                      "index": _relative(root, dest)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
