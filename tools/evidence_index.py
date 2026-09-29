"""執行期證據索引：actions／verifier／threats／forces／crashes／matches。

目的：未來 Agent 不必人工翻幾千個 JSON。
以 match_id／action_id／origin／verdict 等欄位查詢。

用法：
    python tools/evidence_index.py [--out 路徑]
唯讀掃描 runtime/；損壞檔案跳過不中斷。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATTACK_FORCE_NAMES = (
    "Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier",
    "Shell", "Emp", "Nuke", "Ruler",
)
ATTACK_MOBILE_NAMES = ATTACK_FORCE_NAMES[:6]


def _proof_envelope_matches(evidence: dict, evidence_id: str,
                            binding: dict) -> bool:
    if (not isinstance(evidence, dict)
            or not isinstance(evidence_id, str)
            or evidence.get("evidence_id") != evidence_id
            or not all(type(evidence.get(key)) is type(value)
                       and evidence.get(key) == value
                       for key, value in binding.items())):
        return False
    try:
        payload = {key: value for key, value in evidence.items()
                   if key != "evidence_id"}
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        return False
    return evidence_id == "sha256:" + hashlib.sha256(encoded).hexdigest()


def _attack_proof_status(action: dict) -> str | None:
    """以 action log 本身重驗敵方證據封套與實際行動端點。"""
    if not isinstance(action, dict) or action.get("action_kind") != "ATTACK_ENEMY":
        return None
    bundle = action.get("attack_proof_bundle")
    if (bundle is None
            and action.get("attack_validation_status") ==
            "VALIDATION_PENDING"):
        return "AWAITING_VERIFICATION"
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
        return "MISSING"
    match_id = action.get("match")
    source_id = action.get("source")
    target_id = action.get("target")
    action_cycle_id = action.get("cycle_id")
    action_id = action.get("action_id")
    battle_id = bundle.get("battle_differential_evidence_id")
    server_id = bundle.get("server_acceptance_evidence_id")
    battle = bundle.get("battle_differential_evidence")
    server = bundle.get("server_acceptance_evidence")
    if (not isinstance(match_id, str) or not match_id
            or type(source_id) is not int or source_id <= 0
            or type(target_id) is not int or target_id <= 0
            or source_id == target_id
            or type(action_cycle_id) is not int
            or not isinstance(action_id, str)
            or not action_id.startswith(f"{match_id}:{source_id}->{target_id}:")
            or not isinstance(battle, dict)
            or not isinstance(server, dict)):
        return "INVALID"
    attacker_id = battle.get("attacker_owner_id")
    defender_id = battle.get("defender_owner_id")
    force = battle.get("proposed_units")
    if (type(attacker_id) is not int or attacker_id <= 0
            or type(defender_id) is not int or defender_id <= 0
            or attacker_id == defender_id
            or not isinstance(force, dict)
            or set(force) != set(ATTACK_FORCE_NAMES)
            or any(type(value) is not int or value < 0 or value > 255
                   for value in force.values())
            or not any(force.get(name, 0) for name in ATTACK_MOBILE_NAMES)
            or any(force.get(name, 0)
                   for name in ("Shell", "Emp", "Nuke", "Ruler"))):
        return "INVALID"
    binding = {
        "match_id": match_id,
        "cycle_id": action_cycle_id,
        "source_tower_id": source_id,
        "target_tower_id": target_id,
        "attacker_owner_id": attacker_id,
        "defender_owner_id": defender_id,
        "target_relation": "ENEMY",
        "proposed_units": force,
    }
    battle_valid = (
        _proof_envelope_matches(battle, battle_id, binding)
        and battle.get("status") == "VALIDATED"
        and battle.get("support_status") == "MATCH"
        and battle.get("result") == "ATTACK_WIN"
        and battle.get("legality") == "LEGAL_STATIC_SHAPE"
        and battle.get("safety_margin") == "ROBUST_WIN"
        and battle.get("runtime_validated") is True)
    server_valid = (
        _proof_envelope_matches(server, server_id, binding)
        and server.get("status") == "ACCEPTED"
        and server.get("server_accepted") is True
        and server.get("command_kind") == "DeployForce"
        and server.get("action_kind") == "ATTACK_ENEMY")
    if not battle_valid or not server_valid:
        return "INVALID"
    verdict = (action.get("verdict") or action.get("verifier")
               or action.get("result"))
    if verdict not in SUCCESS_VERDICTS:
        return "AWAITING_VERIFICATION"
    return "VALIDATED"


def _attack_validation_summary(actions: list) -> dict:
    attack_rows = [row for row in actions
                   if isinstance(row, dict)
                   and row.get("action_kind") == "ATTACK_ENEMY"]
    validated = [row for row in attack_rows
                 if row.get("attack_proof_status") == "VALIDATED"]
    if validated:
        return {
            "status": "PASS",
            "attack_actions": len(attack_rows),
            "validated_actions": len(validated),
            "reason": None,
        }
    if not attack_rows:
        reason = "no_enemy_attack_record"
    elif any(row.get("attack_proof_status") == "AWAITING_VERIFICATION"
             for row in attack_rows):
        reason = "attack_verification_pending"
    else:
        reason = "no_attack_record_with_complete_proofs"
    return {
        "status": "VALIDATION_PENDING",
        "attack_actions": len(attack_rows),
        "validated_actions": 0,
        "reason": reason,
    }


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _index_actions(root: Path) -> list:
    out = []
    path = root / "runtime/logs/live_actions.jsonl"
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return out
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        out.append({
            "action_id": row.get("action_id"),
            "match_id": row.get("match"),
            "origin": row.get("origin"),
            "action_kind": row.get("action_kind"),
            "cycle_id": row.get("cycle_id"),
            "source": row.get("source"),
            "target": row.get("target"),
            "attack_proof_bundle": row.get("attack_proof_bundle"),
            "attack_proof_status": _attack_proof_status(row),
            "owner_relation": None,
            "verdict": row.get("verifier") or row.get("result"),
            "timestamp": row.get("dispatch", {}).get("sent_at")
            if isinstance(row.get("dispatch"), dict) else None,
            "evidence_path": "runtime/logs/live_actions.jsonl",
        })
    return out


def _index_differentials(root: Path) -> list:
    out = []
    base = root / "runtime/research/pvp_validation"
    if not base.is_dir():
        return out
    for sub in sorted(p for p in base.iterdir() if p.is_dir()):
        diff = _read_json(sub / "battle-differential.json")
        if not isinstance(diff, dict):
            continue
        after = diff.get("after_target") or {}
        out.append({
            "action_id": diff.get("action_id"),
            "match_id": diff.get("match_id"),
            "source": diff.get("source_tower"),
            "target": diff.get("target_tower"),
            "owner_relation": (after.get("owner")
                               if isinstance(after, dict) else None),
            "verdict": diff.get("evaluation_status"),
            "prediction": diff.get("prediction"),
            "timestamp": None,
            "evidence_path": ("runtime/research/pvp_validation/"
                              + sub.name + "/battle-differential.json"),
        })
    return out


def _index_bundles(root: Path) -> list:
    out = []
    base = root / "runtime/research/forces/autonomous_validation"
    if not base.is_dir():
        return out
    for sub in sorted(p for p in base.iterdir() if p.is_dir()):
        bundle = _read_json(sub / "bundle.json")
        if not isinstance(bundle, dict):
            continue
        out.append({
            "action_id": bundle.get("action_id"),
            "match_id": bundle.get("match_id"),
            "force_match_source": bundle.get("force_match_source"),
            "force_match_target": bundle.get("force_match_target"),
            "evidence_path": ("runtime/research/forces/"
                              "autonomous_validation/" + sub.name
                              + "/bundle.json"),
        })
    return out


def _index_crashes(root: Path) -> list:
    out = []
    base = root / "runtime/research/crash/incidents"
    if not base.is_dir():
        return out
    for path in sorted(base.glob("*.json")):
        incident = _read_json(path)
        if not isinstance(incident, dict):
            continue
        out.append({
            "incident_id": incident.get("incident_id"),
            "timestamp": incident.get("timestamp"),
            "signature": incident.get("signature"),
            "match_id": incident.get("match_context"),
            "evidence_path": ("runtime/research/crash/incidents/"
                              + path.name),
        })
    return out


def _index_episodes(root: Path) -> list:
    out = []
    base = root / "runtime/research/pvp_validation"
    if not base.is_dir():
        return out
    for path in sorted(base.glob("*.json")):
        if path.name in ("replay-report.json",):
            continue
        episode = _read_json(path)
        if not isinstance(episode, dict):
            continue
        out.append({
            "episode": episode.get("episode") or episode.get("evidence_id")
            or episode.get("validation_id") or path.stem,
            "match_id": episode.get("match_id"),
            "evidence_path": ("runtime/research/pvp_validation/"
                              + path.name),
        })
    return out


def _index_journal(root: Path) -> dict:
    journal = _read_json(root / "runtime/state/live_controller.json") or {}
    inner = journal.get("journal") or {}
    cycles = inner.get("recent_cycles") or []
    reasons: dict = {}
    no_safe = 0
    if isinstance(cycles, list):
        for cycle in cycles:
            if not isinstance(cycle, dict):
                continue
            if cycle.get("phase") == "NO_SAFE_PROPOSAL":
                no_safe += 1
            reason = cycle.get("no_action_reason")
            if isinstance(reason, str) and reason:
                reasons[reason] = reasons.get(reason, 0) + 1
    arbitration = inner.get("pvp_arbitration")
    if not isinstance(arbitration, dict):
        arbitration = {}
    threat_state = inner.get("threat_state")
    if not isinstance(threat_state, dict):
        threat_state = {}
    defense = inner.get("defense_assessment")
    if not isinstance(defense, dict):
        defense = {}
    attack = inner.get("attack_assessment")
    if not isinstance(attack, dict):
        attack = {}
    pending = inner.get("pending_captures")
    pending_summary = {"count": 0, "targets": [], "matches": []}
    if isinstance(pending, list):
        matches = set()
        for item in pending:
            if not isinstance(item, dict):
                continue
            pending_summary["count"] += 1
            target = item.get("target")
            if type(target) is int:
                pending_summary["targets"].append(target)
            match_id = item.get("match_id")
            if isinstance(match_id, str):
                matches.add(match_id)
        pending_summary["targets"] = sorted(pending_summary["targets"])
        pending_summary["matches"] = sorted(matches)
    return {
        "mode": inner.get("mode"),
        "sent_actions": inner.get("sent_actions"),
        "verified_moves": inner.get("verified_moves"),
        "verified_expansions": inner.get("verified_expansions"),
        "failed_actions": inner.get("failed_actions"),
        "cycles": inner.get("cycles"),
        "no_safe_proposals": no_safe,
        "abstain_reasons": reasons,
        "arbitration_action": arbitration.get("action"),
        "arbitration_reason": arbitration.get("reason"),
        "threat_state_status": threat_state.get("status"),
        "threat_state_reason": threat_state.get("reason"),
        "defense_assessment_status": defense.get("status"),
        "attack_assessment_status": attack.get("status"),
        "pending_captures": pending_summary,
        "last_action": inner.get("last_action"),
        "last_verification": inner.get("last_verification"),
    }


def build_index(root: Path | None = None) -> dict:
    """掃描並回傳機器可讀索引（不寫檔）。"""
    root = Path(root) if root is not None else ROOT
    actions = _index_actions(root)
    return {
        "generated_at": time.time(),
        "actions": actions,
        "attack_validation": _attack_validation_summary(actions),
        "differentials": _index_differentials(root),
        "bundles": _index_bundles(root),
        "crashes": _index_crashes(root),
        "episodes": _index_episodes(root),
        "journal": _index_journal(root),
    }


def query(records: list, **filters) -> list:
    """依欄位等值過濾；None 值永不匹配（UNKNOWN 不冒充）。"""
    out = []
    for record in records:
        if not isinstance(record, dict):
            continue
        matched = True
        for key, value in filters.items():
            if value is None or record.get(key) != value:
                matched = False
                break
        if matched:
            out.append(record)
    return out


SUCCESS_VERDICTS = frozenset({
    "TARGET_CAPTURED", "TARGET_CONTESTED", "FORCE_OBSERVED",
})
AUTONOMOUS_ORIGIN = "LIVE_CONTROLLER"


def summarize_autonomy(index: dict | None) -> dict:
    """單一自主行動統計：避免 Dashboard 與 journal 各算各的。

    - 先按 origin 分流：自主（LIVE_CONTROLLER）／人工（其他具名）
      ／未知（缺 origin）。
    - 自主列再以 differential 的目標 owner 關係分類：
      NEUTRAL→中立擴張，SELF→增援，ENEMY／OTHER→對敵攻擊；
      無對應差分者為 unclassified（不猜）。
    - verdict 分流：verified／failed／unknown_verifier。
    每筆行動只計一次；分類正交。
    """
    actions = (index or {}).get("actions") or []
    differentials = (index or {}).get("differentials") or []
    journal = (index or {}).get("journal") or {}
    diff_by_action = {}
    for diff in differentials:
        if isinstance(diff, dict) and diff.get("action_id"):
            diff_by_action.setdefault(diff["action_id"], diff)
    summary = {
        "autonomous_total": 0,
        "manual_total": 0,
        "unknown_origin_total": 0,
        "autonomous_neutral_expansion": 0,
        "autonomous_reinforcement": 0,
        "autonomous_enemy_attack": 0,
        "autonomous_defense": 0,
        "autonomous_unclassified": 0,
        "verified": 0,
        "failed": 0,
        "abstained": (journal.get("no_safe_proposals") or 0)
        if isinstance(journal.get("no_safe_proposals"), int) else 0,
        "abstain_reasons": (journal.get("abstain_reasons") or {}),
        "unknown_verifier": 0,
        "by_action": {},
    }
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_id = action.get("action_id")
        origin = action.get("origin")
        verdict = action.get("verdict")
        if origin == AUTONOMOUS_ORIGIN:
            summary["autonomous_total"] += 1
        elif origin is None:
            summary["unknown_origin_total"] += 1
            continue
        else:
            summary["manual_total"] += 1
            continue
        if verdict in SUCCESS_VERDICTS:
            summary["verified"] += 1
        elif verdict is None or verdict == "UNKNOWN":
            summary["unknown_verifier"] += 1
        else:
            summary["failed"] += 1
        diff = diff_by_action.get(action_id) or {}
        relation = diff.get("owner_relation")
        explicit_kind = action.get("action_kind")
        if explicit_kind == "EXPAND_NEUTRAL":
            summary["autonomous_neutral_expansion"] += 1
            kind = "neutral_expansion"
        elif explicit_kind == "REINFORCE_SELF":
            summary["autonomous_reinforcement"] += 1
            kind = "reinforcement"
        elif explicit_kind == "ATTACK_ENEMY":
            summary["autonomous_enemy_attack"] += 1
            kind = "enemy_attack"
        elif relation == "NEUTRAL":
            summary["autonomous_neutral_expansion"] += 1
            kind = "neutral_expansion"
        elif relation == "SELF":
            summary["autonomous_reinforcement"] += 1
            kind = "reinforcement"
        elif relation in ("ENEMY", "OTHER"):
            summary["autonomous_enemy_attack"] += 1
            kind = "enemy_attack"
        else:
            summary["autonomous_unclassified"] += 1
            kind = "unclassified"
        if action_id is not None:
            summary["by_action"][action_id] = {
                "kind": kind, "verdict": verdict,
                "match_id": action.get("match_id"),
            }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    index = build_index(ROOT)
    dest = (Path(args.out) if args.out else
            ROOT / "runtime/research/evidence-index.json")
    dest.write_text(json.dumps(index, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    summary = {key: (len(value) if isinstance(value, list) else "obj")
               for key, value in index.items() if key != "generated_at"}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
