"""預先彙整可用的 PvP 證據，並以明確身分綁定每個事件。

工具只讀取正式執行期已落盤的記錄，不操作瀏覽器或遊戲。預設輸出為
單一原子覆寫檔；watch 模式不會逐次建立新檔。缺少的時間點及綁定欄位
會保留為 UNKNOWN/INCOMPLETE，絕不以時間接近或塔主權推定行動身分。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_RELATIVE = Path("runtime/research/combat_evidence_arming/latest.json")
ACTION_KINDS = {"ATTACK_ENEMY", "REINFORCE_SELF"}
IDENTITY_FIELDS = (
    "action_id", "match_id", "cycle_id", "source_tower_id",
    "target_tower_id", "action_kind",
)
METADATA_FIELDS = (
    "source_owner", "target_owner", "route", "world_hash",
    "proposal_version", "token_version", "reservation_id", "dispatched_at",
)
STAGE_NAMES = (
    "t_minus_2", "t_minus_1", "t0", "pre_dispatch", "dispatch",
    "post_dispatch", "moving", "arrival", "battle", "verdict",
    "t_plus_1", "t_plus_2",
)
MAX_BUNDLES = 128


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
    rows: list[dict] = []
    malformed = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line, parse_constant=_reject_constant)
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


def _finite_timestamp(value: Any) -> bool:
    if type(value) not in (int, float) or value <= 0:
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _number_or_none(value: Any) -> float | None:
    return float(value) if _finite_timestamp(value) else None


def _pick(record: dict, *names: str):
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
    return None


def _normalize(record: dict) -> dict:
    dispatch = record.get("dispatch")
    if not isinstance(dispatch, dict):
        dispatch = {}
    before = record.get("before")
    if not isinstance(before, dict):
        before = {}
    before_source = before.get("source")
    before_target = before.get("target")
    if not isinstance(before_source, dict):
        before_source = {}
    if not isinstance(before_target, dict):
        before_target = {}
    proposal = record.get("proposal")
    if not isinstance(proposal, dict):
        proposal = {}
    source_id = _pick(record, "source_tower_id", "source_tower", "source")
    target_id = _pick(record, "target_tower_id", "target_tower", "target")
    route = _pick(record, "route", "path")
    source_owner = record.get("source_owner")
    target_owner = record.get("target_owner")
    if source_id is None:
        source_id = proposal.get("source_tower_id")
    if target_id is None:
        target_id = proposal.get("target_tower_id")
    if route is None:
        route = proposal.get("route")
    if source_owner is None:
        source_owner = before_source.get("owner")
    if target_owner is None:
        target_owner = before_target.get("owner")
    return {
        "action_id": record.get("action_id"),
        "match_id": _pick(record, "match_id", "match"),
        "cycle_id": record.get("cycle_id"),
        "source_tower_id": source_id,
        "target_tower_id": target_id,
        "action_kind": record.get("action_kind"),
        "source_owner": source_owner,
        "target_owner": target_owner,
        "route": route,
        "world_hash": record.get("world_hash"),
        "proposal_version": record.get("proposal_version"),
        "token_version": _pick(record, "token_version", "action_token_version",
                                "validity_token_version"),
        "reservation_id": _pick(record, "reservation_id",
                                 "reservation_action_id"),
        "dispatched_at": _number_or_none(
            dispatch["sent_at"] if dispatch.get("sent_at") is not None
            else _pick(record, "sent_at", "dispatched_at")),
    }


def _same_value(left: Any, right: Any) -> bool:
    return type(left) is type(right) and left == right


def _stable_threat_id(match_id: str, force_id: int) -> str:
    # The source force ID is explicit evidence identity; this hash only makes
    # the serialized key compact and deterministic.
    raw = f"{match_id}\0{force_id}".encode("utf-8")
    return "threat-" + hashlib.sha256(raw).hexdigest()[:20]


def _relative(root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return None


def _safe_files(root: Path, relative: str, filename: str) -> list[Path]:
    base = root / relative
    if not base.is_dir():
        return []
    return sorted(path for path in base.rglob(filename)
                  if _relative(root, path) is not None)


def _empty_stages() -> dict:
    return {name: None for name in STAGE_NAMES}


def _evidence_data(value: Any) -> Any:
    """避免把影像或 Base64 畫面複製到證據報告。"""
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in
                   ("screenshot", "image", "base64", "png", "jpeg", "bitmap")):
                continue
            output[key] = _evidence_data(item)
        return output
    if isinstance(value, list):
        return [_evidence_data(item) for item in value]
    if isinstance(value, tuple):
        return [_evidence_data(item) for item in value]
    return value


def _add_issue(candidate: dict, issue: str, *, conflict: bool = False) -> None:
    if issue not in candidate["issues"]:
        candidate["issues"].append(issue)
    if conflict:
        candidate["binding_conflict"] = True


def _candidate(candidates: dict[str, dict], record: dict,
               source: str, unclassified: list[str]) -> None:
    kind = record.get("action_kind")
    if kind not in ACTION_KINDS:
        if kind is None:
            unclassified.append(source)
        return
    action_id = record.get("action_id")
    if not isinstance(action_id, str) or not action_id:
        unclassified.append(source)
        return
    item = candidates.setdefault(action_id, {
        "action_id": action_id, "records": [], "stages": _empty_stages(),
        "sources": set(), "issues": [], "binding_conflict": False,
    })
    item["records"].append((record, source))
    item["sources"].add(source)


def _merge_candidate(candidate: dict) -> dict:
    binding = {field: None for field in (*IDENTITY_FIELDS, *METADATA_FIELDS)}
    binding["action_id"] = candidate["action_id"]
    for record, source in candidate["records"]:
        normalized = _normalize(record)
        for field in (*IDENTITY_FIELDS[1:], *METADATA_FIELDS):
            value = normalized.get(field)
            if value is None:
                continue
            current = binding.get(field)
            if current is None:
                binding[field] = value
            elif not _same_value(current, value):
                _add_issue(candidate, f"{source}-binding-conflict-{field}",
                           conflict=True)
    expected_owners = {
        "ATTACK_ENEMY": ("SELF", "ENEMY"),
        "REINFORCE_SELF": ("SELF", "SELF"),
    }.get(binding.get("action_kind"))
    if expected_owners and all(binding.get(key) not in (None, "UNKNOWN")
                                for key in ("source_owner", "target_owner")):
        actual = (binding["source_owner"], binding["target_owner"])
        if actual != expected_owners:
            _add_issue(candidate, "action-owner-relation-mismatch",
                       conflict=True)
    return binding


def _attach(candidate: dict, binding: dict, record: dict,
            source: str) -> bool:
    normalized = _normalize(record)
    if normalized.get("action_id") != candidate["action_id"]:
        return False
    for field in IDENTITY_FIELDS[1:5]:
        expected, observed = binding.get(field), normalized.get(field)
        if expected is None or observed is None:
            _add_issue(candidate, f"{source}-missing-binding-{field}")
            return False
        if not _same_value(expected, observed):
            _add_issue(candidate, f"{source}-binding-conflict-{field}",
                       conflict=True)
            return False
    observed_kind = normalized.get("action_kind")
    if observed_kind is not None and observed_kind != binding.get("action_kind"):
        _add_issue(candidate, f"{source}-binding-conflict-action_kind",
                   conflict=True)
        return False
    for field in METADATA_FIELDS:
        value = normalized.get(field)
        if value is None:
            continue
        current = binding.get(field)
        if current is None:
            binding[field] = value
        elif not _same_value(current, value):
            _add_issue(candidate, f"{source}-binding-conflict-{field}",
                       conflict=True)
    candidate["sources"].add(source)
    return True


def _put_stage(candidate: dict, name: str, value: Any, source: str) -> None:
    if name not in candidate["stages"] or value is None:
        return
    value = _evidence_data(value)
    current = candidate["stages"][name]
    if current is None:
        candidate["stages"][name] = {"source": source, "evidence": value}
        return
    old_evidence = current.get("evidence")
    if old_evidence == value:
        return
    if (name == "dispatch" and isinstance(old_evidence, dict)
            and isinstance(value, dict)
            and _finite_timestamp(old_evidence.get("sent_at"))
            and _finite_timestamp(value.get("sent_at"))):
        if float(old_evidence["sent_at"]) != float(value["sent_at"]):
            _add_issue(candidate, "conflicting-dispatch-evidence", conflict=True)
            return
        merged = dict(old_evidence)
        for key, item in value.items():
            if key not in merged:
                merged[key] = item
            elif merged[key] != item:
                merged.setdefault("supplemental", {})[key] = item
        current["evidence"] = merged
        sources = current.setdefault("sources", [current.get("source")])
        if source not in sources:
            sources.append(source)
        return
    _add_issue(candidate, f"conflicting-{name}-evidence", conflict=True)


def _event_stages(candidate: dict, record: dict, source: str) -> None:
    direct = record.get("stages")
    if isinstance(direct, dict):
        for name in STAGE_NAMES:
            _put_stage(candidate, name, direct.get(name), source)
    stage_name = record.get("stage")
    if stage_name in STAGE_NAMES:
        _put_stage(candidate, stage_name, record.get("evidence", record), source)


def _build_action_bundle(candidate: dict) -> dict:
    binding = _merge_candidate(candidate)
    # Source records are all action-ID matched; stage snapshots still require
    # an exact match/match-cycle-route identity before they can be attached.
    for record, source in candidate["records"]:
        _event_stages(candidate, record, source)
        pending_before = record.get("before")
        if isinstance(pending_before, dict):
            _put_stage(candidate, "pre_dispatch", pending_before, source)
        dispatch = record.get("dispatch")
        if isinstance(dispatch, dict) and _finite_timestamp(dispatch.get("sent_at")):
            _put_stage(candidate, "dispatch", dispatch, source)
        elif _finite_timestamp(record.get("sent_at")):
            _put_stage(candidate, "dispatch", {"sent_at": record["sent_at"]},
                       source)
        if (record.get("verifier") is not None or record.get("result") is not None):
            verdict_time = record.get("logged_at")
            _put_stage(candidate, "verdict", {
                "verifier": record.get("verifier"),
                "result": record.get("result"),
                "observed_at": _number_or_none(verdict_time),
            }, source)
    return {"case_type": "ACTION", "action_id": candidate["action_id"],
            "action_kind": binding.get("action_kind"), "binding": binding,
            "binding_status": ("BINDING_CONFLICT" if
                               candidate["binding_conflict"] else "BOUND"),
            "collection_status": "INCOMPLETE", "proof_status": "NOT_EVALUATED",
            "missing": [], "issues": sorted(candidate["issues"]),
            "stages": candidate["stages"],
            "evidence_sources": sorted(candidate["sources"]),
            "last_event_at": _last_event_time(candidate)}


def _last_event_time(candidate: dict) -> float | None:
    values = []
    for record, _source in candidate["records"]:
        normalized = _normalize(record)
        for value in (normalized.get("dispatched_at"), record.get("logged_at"),
                      record.get("created_at")):
            if _finite_timestamp(value):
                values.append(float(value))
    return max(values) if values else None


def _same_threat_observation(state: dict, row: dict) -> bool:
    if row.get("match_id") is not None and row.get("match_id") != state.get("match_id"):
        return False
    if row.get("cycle_id") is not None and row.get("cycle_id") != state.get("cycle_id"):
        return False
    return True


def _threat_cases(journal: dict) -> tuple[list[dict], dict]:
    current = journal.get("threat_state")
    if not isinstance(current, dict):
        current = {}
    health = {key: current.get(key) for key in
              ("status", "freshness", "match_id", "cycle_id", "observed_at",
               "reason")}
    coverage = current.get("coverage")
    health["coverage_complete"] = (coverage.get("complete") is True
                                   if isinstance(coverage, dict) else False)
    candidates = []
    if isinstance(current.get("threats"), list):
        candidates.extend((current, row) for row in current["threats"]
                          if isinstance(row, dict))
    recent = journal.get("recent_cycles")
    if isinstance(recent, list):
        for cycle in recent:
            if not isinstance(cycle, dict):
                continue
            state = cycle.get("threat_state")
            if not isinstance(state, dict) or not isinstance(state.get("threats"), list):
                continue
            candidates.extend((state, row) for row in state["threats"]
                              if isinstance(row, dict))
    grouped: dict[tuple, list[dict]] = {}
    for state, row in candidates:
        if state.get("status") != "OBSERVED_CANDIDATE" \
                or state.get("freshness") != "FRESH" \
                or not (isinstance(state.get("coverage"), dict)
                        and state["coverage"].get("complete") is True):
            continue
        match_id, cycle_id = state.get("match_id"), state.get("cycle_id")
        observed_at = state.get("observed_at")
        force_id = _pick(row, "source_force_id", "force_id", "threat_id")
        source = _pick(row, "source_tower_id", "source_tower")
        target = _pick(row, "target_tower_id", "target_tower")
        if (not isinstance(match_id, str) or not match_id
                or type(cycle_id) is not int or cycle_id < 0
                or not _finite_timestamp(observed_at)
                or type(force_id) not in (str, int) or not force_id
                or type(source) is not int or source <= 0
                or type(target) is not int or target <= 0
                or not _same_threat_observation(state, row)):
            continue
        key = (match_id, str(force_id), source, target,
               row.get("owner_id"))
        grouped.setdefault(key, []).append({
            "match_id": match_id, "cycle_id": cycle_id,
            "observed_at": float(observed_at), "source_force_id": force_id,
            "source_tower_id": source, "target_tower_id": target,
            "owner_id": row.get("owner_id"),
            "source_owner": row.get("source_owner"),
            "target_owner": row.get("target_owner"),
            "owner_relation": row.get("owner_relation", row.get("relation",
                                                                  "UNKNOWN")),
            "route": row.get("route", row.get("path")),
            "units": row.get("units"), "eta_ticks": row.get("eta_ticks"),
            "eta_seconds": row.get("eta_seconds"),
            "freshness": "FRESH", "confidence": row.get("confidence"),
        })
    output = []
    for key, rows in grouped.items():
        rows.sort(key=lambda item: (item["cycle_id"], item["observed_at"]))
        distinct: dict[int, dict] = {}
        for row in rows:
            distinct[row["cycle_id"]] = row
        history = list(distinct.values())[-3:]
        match_id, force_id, source, target, owner_id = key
        case_id = _stable_threat_id(match_id, int(force_id)) \
            if str(force_id).isdigit() else _stable_threat_id(
                match_id, int(hashlib.sha256(str(force_id).encode()).hexdigest()[:8], 16))
        stages = _empty_stages()
        for index, stage in enumerate(("t_minus_2", "t_minus_1", "t0")):
            if len(history) >= 3 - index:
                observation = history[index - (3 - len(history))]
                stages[stage] = {"source": "live_controller.threat_state",
                                 "evidence": observation}
        latest = history[-1]
        relation = latest.get("owner_relation")
        classification = ("ENEMY_TO_SELF" if relation == "ENEMY"
                          and latest.get("target_owner") == "SELF"
                          and latest.get("source_owner") == "ENEMY"
                          else "UNKNOWN")
        missing = []
        if classification == "UNKNOWN":
            missing.extend(name for name, value in (
                ("source_owner", latest.get("source_owner")),
                ("target_owner", latest.get("target_owner"))) if value !=
                ("ENEMY" if name == "source_owner" else "SELF"))
        if latest.get("route") is None:
            missing.append("route")
        output.append({
            "case_type": "THREAT", "threat_id": case_id,
            "classification": classification,
            "binding": {"match_id": match_id, "cycle_id": latest["cycle_id"],
                        "source_force_id": force_id,
                        "source_tower_id": source, "target_tower_id": target,
                        "owner_id": owner_id,
                        "source_owner": latest.get("source_owner"),
                        "target_owner": latest.get("target_owner"),
                        "route": latest.get("route"),
                        "observed_at": latest["observed_at"]},
            "binding_status": "BOUND",
            "collection_status": "INCOMPLETE" if missing else "OBSERVED",
            "proof_status": "NOT_EVALUATED", "missing": sorted(set(missing)),
            "issues": [], "stages": stages,
            "evidence_sources": ["runtime/state/live_controller.json"],
            "last_event_at": latest["observed_at"],
        })
    return output, health


def _attach_source(candidate: dict, binding: dict, record: dict,
                   source: str) -> bool:
    if not _attach(candidate, binding, record, source):
        return False
    _event_stages(candidate, record, source)
    return True


def _attach_force(candidate: dict, binding: dict, force: dict,
                  source: str) -> None:
    if not _attach_source(candidate, binding, force, source):
        return
    stages = force
    _put_stage(candidate, "t0", stages.get("t0"), source)
    _put_stage(candidate, "post_dispatch", stages.get("t1"), source)
    _put_stage(candidate, "t_plus_1", stages.get("t2"), source)
    _put_stage(candidate, "t_plus_2", stages.get("t3"), source)
    if stages.get("t2") is not None:
        _put_stage(candidate, "moving", {
            "status": stages.get("force_match_source", "UNKNOWN"),
            "snapshot": stages.get("t2"),
        }, source)
    if stages.get("force_match_target") == "FORCE_MATCH_VERIFIED":
        _put_stage(candidate, "arrival", {
            "status": "TARGET_FORCE_OBSERVED",
            "snapshot": stages.get("t3"),
        }, source)
    if stages.get("dispatched_at") is not None:
        _put_stage(candidate, "dispatch", {
            "sent_at": stages.get("dispatched_at"),
            "observation": stages.get("dispatch_observation", "UNKNOWN"),
        }, source)


def _finish_bundle(bundle: dict) -> None:
    missing = list(bundle["issues"])
    binding = bundle["binding"]
    for field in (*IDENTITY_FIELDS, *METADATA_FIELDS):
        if binding.get(field) is None:
            missing.append(field)
    if not isinstance(binding.get("match_id"), str) or not binding["match_id"]:
        missing.append("match_id")
    cycle_id = binding.get("cycle_id")
    if type(cycle_id) is not int or cycle_id < 0:
        missing.append("cycle_id")
    for field in ("source_tower_id", "target_tower_id"):
        if type(binding.get(field)) is not int or binding[field] <= 0:
            missing.append(field)
    if (type(binding.get("source_tower_id")) is int
            and type(binding.get("target_tower_id")) is int
            and binding["source_tower_id"] == binding["target_tower_id"]):
        missing.append("distinct_source_target")
    for field in ("source_owner", "target_owner"):
        if binding.get(field) in (None, "UNKNOWN"):
            missing.append(field)
    route = binding.get("route")
    if (not isinstance(route, list) or len(route) < 2
            or any(type(tower_id) is not int or tower_id <= 0 for tower_id in route)
            or route[0] != binding.get("source_tower_id")
            or route[-1] != binding.get("target_tower_id")):
        missing.append("route")
    for field in ("world_hash", "proposal_version", "token_version",
                  "reservation_id"):
        value = binding.get(field)
        if not isinstance(value, (str, int)) or not str(value):
            missing.append(field)
    if not _finite_timestamp(binding.get("dispatched_at")):
        missing.append("dispatched_at")
    for stage, value in bundle["stages"].items():
        if value is None:
            missing.append(stage)
    missing = sorted(set(missing))
    bundle["missing"] = missing
    if bundle["binding_status"] == "BINDING_CONFLICT":
        bundle["collection_status"] = "BINDING_CONFLICT"
    else:
        core_identity_valid = (
            isinstance(binding.get("action_id"), str)
            and bool(binding["action_id"])
            and isinstance(binding.get("match_id"), str)
            and bool(binding["match_id"])
            and type(binding.get("cycle_id")) is int
            and binding["cycle_id"] >= 0
            and type(binding.get("source_tower_id")) is int
            and binding["source_tower_id"] > 0
            and type(binding.get("target_tower_id")) is int
            and binding["target_tower_id"] > 0
            and binding["source_tower_id"] != binding["target_tower_id"]
            and binding.get("action_kind") in ACTION_KINDS
        )
        if not core_identity_valid:
            bundle["binding_status"] = "INCOMPLETE"
        bundle["collection_status"] = "INCOMPLETE" if missing else "COLLECTED"


def _atomic_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          indent=2, allow_nan=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{path.name}.",
                                         suffix=".tmp", dir=path.parent,
                                         delete=False) as stream:
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


def collect_once(root: str | Path = ROOT, out_path: str | Path | None = None,
                 max_bundles: int = MAX_BUNDLES, *, armed: bool = False) -> dict:
    """掃描現存 action/threat 記錄並原子覆寫單一最新報告。"""
    project_root = Path(root).resolve()
    if not project_root.is_dir():
        raise ValueError("project root must be an existing directory")
    if type(max_bundles) is not int or not 1 <= max_bundles <= 512:
        raise ValueError("max_bundles must be an integer from 1 to 512")
    output = (project_root / OUTPUT_RELATIVE if out_path is None else
              Path(out_path) if Path(out_path).is_absolute() else
              project_root / Path(out_path)).resolve()
    if _relative(project_root, output) is None:
        raise ValueError("output file must remain inside project root")

    state_path = project_root / "runtime/state/live_controller.json"
    state = _read_json(state_path) or {}
    journal = state.get("journal")
    if not isinstance(journal, dict):
        journal = {}
    candidates: dict[str, dict] = {}
    unclassified: list[str] = []
    action_path = project_root / "runtime/logs/live_actions.jsonl"
    action_rows, malformed_action_rows = _read_jsonl(action_path)
    for row in action_rows:
        _candidate(candidates, row, "runtime/logs/live_actions.jsonl",
                   unclassified)
    for label, record in (("live_controller.last_action", journal.get("last_action")),
                          ("live_controller.pending_dispatch", journal.get("pending_dispatch"))):
        if isinstance(record, dict):
            _candidate(candidates, record, "runtime/state/live_controller.json#" + label,
                       unclassified)
    pending_path = project_root / "runtime/state/pending-live-dispatch.json"
    pending = _read_json(pending_path)
    if pending is None:
        pending = journal.get("pending_dispatch")
    if isinstance(pending, dict):
        _candidate(candidates, pending, "runtime/state/pending-live-dispatch.json",
                   unclassified)

    bundles = []
    for candidate in candidates.values():
        bundle = _build_action_bundle(candidate)
        binding = bundle["binding"]
        for record, source in candidate["records"]:
            _event_stages(candidate, record, source)
        if isinstance(pending, dict) and pending.get("action_id") == candidate["action_id"]:
            if _attach_source(candidate, binding, pending,
                              "runtime/state/pending-live-dispatch.json"):
                before = pending.get("before")
                if isinstance(before, dict):
                    _put_stage(candidate, "pre_dispatch", before,
                               "runtime/state/pending-live-dispatch.json")
                if _finite_timestamp(pending.get("sent_at")):
                    _put_stage(candidate, "dispatch", {
                        "sent_at": pending["sent_at"],
                        "status": pending.get("status", "UNKNOWN")},
                        "runtime/state/pending-live-dispatch.json")
        for rel, filename, label in (
            ("runtime/research/forces/autonomous_validation", "bundle.json", "force"),
            ("runtime/research/pvp_validation", "battle-differential.json", "battle"),
        ):
            for path in _safe_files(project_root, rel, filename):
                record = _read_json(path)
                if not isinstance(record, dict) or record.get("action_id") != candidate["action_id"]:
                    continue
                source = _relative(project_root, path) or label
                if label == "force":
                    _attach_force(candidate, binding, record, source)
                elif _attach_source(candidate, binding, record, source):
                    _put_stage(candidate, "battle", record, source)
        if isinstance(journal.get("pending_captures"), list):
            for record in journal["pending_captures"]:
                if (isinstance(record, dict)
                        and record.get("action_id") == candidate["action_id"]
                        and _attach_source(candidate, binding, record,
                                           "live_controller.pending_captures")):
                    _put_stage(candidate, "verdict", {
                        "status": record.get("status", record.get("verdict")),
                        "observed_at": record.get("observed_at")},
                        "live_controller.pending_captures")
        event_path = project_root / "runtime/state/combat-evidence-events.jsonl"
        events, _malformed_events = _read_jsonl(event_path)
        for event in events:
            if event.get("action_id") == candidate["action_id"] \
                    and _attach_source(candidate, binding, event,
                                       "runtime/state/combat-evidence-events.jsonl"):
                _event_stages(candidate, event,
                              "runtime/state/combat-evidence-events.jsonl")
        expected_owners = {
            "ATTACK_ENEMY": ("SELF", "ENEMY"),
            "REINFORCE_SELF": ("SELF", "SELF"),
        }.get(binding.get("action_kind"))
        if expected_owners and all(binding.get(key) not in (None, "UNKNOWN")
                                   for key in ("source_owner", "target_owner")):
            if (binding["source_owner"], binding["target_owner"]) != expected_owners:
                _add_issue(candidate, "action-owner-relation-mismatch",
                           conflict=True)
        # Rebuild public summary only after all exact-ID records were considered.
        bundle["binding"] = binding
        bundle["binding_status"] = ("BINDING_CONFLICT" if
                                    candidate["binding_conflict"] else "BOUND")
        bundle["stages"] = candidate["stages"]
        bundle["issues"] = sorted(candidate["issues"])
        bundle["evidence_sources"] = sorted(candidate["sources"])
        _finish_bundle(bundle)
        bundles.append(bundle)

    threats, threat_health = _threat_cases(journal)
    bundles.extend(threats)
    bundles.sort(key=lambda item: (item.get("last_event_at") or 0,
                                   item.get("action_id", item.get("threat_id", ""))))
    omitted = max(0, len(bundles) - max_bundles)
    if omitted:
        bundles = bundles[-max_bundles:]
    report = {
        "schema_version": 1,
        "collector": "combat_evidence_arming",
        "armed": bool(armed),
        "mode": "WATCH" if armed else "SNAPSHOT",
        "generated_at": time.time(),
        "status": (("ARMED_WITH_CASES" if bundles else "ARMED_NO_CASES")
                   if armed else
                   ("SNAPSHOT_WITH_CASES" if bundles else "SNAPSHOT_NO_CASES")),
        "source_health": {
            "live_controller": "READABLE" if state else "MISSING_OR_INVALID",
            "action_rows_scanned": len(action_rows),
            "malformed_action_rows": malformed_action_rows,
            "unclassified_action_rows": len(unclassified),
            "unclassified_sources": sorted(set(unclassified))[:32],
            "threat_observation": threat_health,
        },
        "bundle_count": len(bundles),
        "omitted_bundle_count": omitted,
        "retention_limit": max_bundles,
        "bundles": bundles,
        "output": _relative(project_root, output),
    }
    _atomic_json(output, report)
    return report


def watch(root: str | Path = ROOT, out_path: str | Path | None = None,
          interval: float = 1.0, max_cycles: int | None = None,
          max_bundles: int = MAX_BUNDLES) -> dict:
    if (isinstance(interval, bool) or not isinstance(interval, (int, float))
            or not math.isfinite(float(interval)) or not 0.1 <= interval <= 60):
        raise ValueError("interval must be between 0.1 and 60 seconds")
    if max_cycles is not None and (type(max_cycles) is not int or max_cycles < 1):
        raise ValueError("max_cycles must be a positive integer")
    last = {}
    cycles = 0
    try:
        while max_cycles is None or cycles < max_cycles:
            last = collect_once(root, out_path, max_bundles, armed=True)
            cycles += 1
            if max_cycles is None or cycles < max_cycles:
                try:
                    time.sleep(float(interval))
                except KeyboardInterrupt:
                    break
    except KeyboardInterrupt:
        pass
    if last:
        last.update(armed=False, mode="WATCH_STOPPED", watch_cycles=cycles,
                    stopped_at=time.time())
        last["status"] = ("WATCH_STOPPED_WITH_CASES" if last["bundles"]
                           else "WATCH_STOPPED_NO_CASES")
        project_root = Path(root).resolve()
        output = (project_root / OUTPUT_RELATIVE if out_path is None else
                  Path(out_path) if Path(out_path).is_absolute() else
                  project_root / Path(out_path)).resolve()
        _atomic_json(output, last)
    return last


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--max-cycles", type=int)
    parser.add_argument("--max-bundles", type=int, default=MAX_BUNDLES)
    args = parser.parse_args(argv)
    report = (watch(args.root, args.out, args.interval, args.max_cycles,
                    args.max_bundles) if args.watch else
              collect_once(args.root, args.out, args.max_bundles))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
