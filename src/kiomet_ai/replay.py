"""戰鬥差分離線重播：T0-T3 bundle + battle differential → 確定性重評。

目的：把正式 Runtime 記錄轉成可反覆重播的回歸資產，不再等待新事件。

紀律：
- 未知一律 UNKNOWN / SKIPPED，不以 0 冒充，不編造 player id。
- owner id 只採信 FORCE_MATCH_VERIFIED bundle 條目的 +12 原值。
- 任何 stage 不確定即輸出該 stage 的 UNKNOWN，不得整案假裝 MATCH。
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from kiomet_ai.battle_mirror import CAPACITIES
from kiomet_ai.observe import UNIT_NAMES

NAMES6 = ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier")
ORDINARY = NAMES6
SPECIAL = ("Ruler", "Shell", "Emp", "Nuke")


def _vec(d: dict | None) -> dict | None:
    if not isinstance(d, dict):
        return None
    out = {}
    for n in NAMES6:
        v = d.get(n)
        if type(v) is not int or v < 0:
            return None
        out[n] = v
    return out


def load_case(case_dir: Path) -> dict:
    """載入一筆差分＋（可選）同 action_id 的 force bundle。"""
    diff_path = Path(case_dir) / "battle-differential.json"
    diff = json.loads(diff_path.read_text(encoding="utf8"))
    bundle = None
    bundle_path = (Path(case_dir).parents[1] / "forces" / "autonomous_validation"
                   / Path(case_dir).name / "bundle.json")
    if bundle_path.is_file():
        bundle = json.loads(bundle_path.read_text(encoding="utf8"))
    return {"diff": diff, "bundle": bundle,
            "case_id": Path(case_dir).name}


def derive_id_evidence(bundle: dict | None, diff: dict | None) -> dict:
    """由 FORCE_MATCH_VERIFIED bundle 條目萃取 owner id＋來源證明。

    只有帶 FORCE_MATCH_VERIFIED 的條目才構成證據；其餘不寫入。
    """
    evidence = {"self_id": None, "self_id_provenance": None,
                "observed_owner_ids": [], "sources": []}
    if not bundle:
        return evidence
    if (bundle.get("force_match_source") != "FORCE_MATCH_VERIFIED"
            or bundle.get("force_match_target") != "FORCE_MATCH_VERIFIED"):
        evidence["sources"].append(
            {"bundle": bundle.get("action_id"), "status": "NOT_VERIFIED",
             "note": "bundle force matches not VERIFIED; ids not accepted"})
        return evidence
    src_owner = ((diff or {}).get("source_owner"))
    entries = []
    for stage in ("t0", "t1", "t2", "t3"):
        part = (bundle.get(stage) or {})
        for role in ("source", "target"):
            colls = ((part.get(role) or {}).get("collections") or {})
            for role_name in ("inbound", "outbound"):
                for e in (colls.get(role_name) or {}).get("entries") or []:
                    entries.append((stage, role, role_name, e))
    owners = set()
    for stage, anchor_role, role_name, e in entries:
        oid = e.get("owner_id")
        if type(oid) is int and oid > 0:
            owners.add(oid)
            evidence["sources"].append(
                {"bundle": bundle.get("action_id"), "stage": stage,
                 "anchor": anchor_role, "role": role_name,
                 "owner_id": oid, "path": e.get("path"),
                 "force_match": "FORCE_MATCH_VERIFIED"})
    evidence["observed_owner_ids"] = sorted(owners)
    # SELF：僅當差分記載來源塔為 SELF 且該塔 outbound 條目存在（己方派出）
    if src_owner == "SELF":
        for stage, anchor_role, role_name, e in entries:
            if (anchor_role == "source" and role_name == "outbound"
                    and type(e.get("owner_id")) is int and e["owner_id"] > 0):
                evidence["self_id"] = e["owner_id"]
                evidence["self_id_provenance"] = (
                    "verified-dispatch-outbound+12@"
                    + str(bundle.get("action_id")))
                break
    return evidence


def _check_temporal(bundle: dict) -> dict:
    """T0 無移動 → T1 出現條目 → T2/T3 消失。"""
    if not bundle:
        return {"status": "UNKNOWN", "reason": "bundle-missing"}
    def count(stage):
        part = bundle.get(stage) or {}
        n = 0
        for role in ("source", "target"):
            colls = ((part.get(role) or {}).get("collections") or {})
            for r in ("inbound", "outbound"):
                n += len((colls.get(r) or {}).get("entries") or [])
        return n
    c0, c1, c2, c3 = count("t0"), count("t1"), count("t2"), count("t3")
    if c0 == 0 and c1 > 0 and c2 == 0 and c3 == 0:
        return {"status": "TEMPORAL_OK", "counts": [c0, c1, c2, c3]}
    if c1 == 0:
        return {"status": "TEMPORAL_NO_FORCE", "counts": [c0, c1, c2, c3]}
    return {"status": "TEMPORAL_ANOMALY", "counts": [c0, c1, c2, c3]}


def _entry_sig(e: dict) -> tuple:
    return (tuple(e.get("path") or ()), e.get("owner_id"),
            tuple(sorted((e.get("units") or {}).items())))


def _check_force_identity(bundle: dict) -> dict:
    """T1 source outbound 與 target inbound 應為同一支部隊。"""
    if not bundle:
        return {"status": "UNKNOWN", "reason": "bundle-missing"}
    t1 = bundle.get("t1") or {}
    outs = ((((t1.get("source") or {}).get("collections") or {})
             .get("outbound") or {}).get("entries") or [])
    inbs = ((((t1.get("target") or {}).get("collections") or {})
             .get("inbound") or {}).get("entries") or [])
    if not outs and not inbs:
        return {"status": "UNKNOWN", "reason": "no-t1-entries"}
    if not outs or not inbs:
        return {"status": "IDENTITY_MISMATCH",
                "reason": "one-sided t1 entries",
                "outbound": len(outs), "inbound": len(inbs)}
    # Keep multiplicity: a set would collapse two identical forces into one
    # and could falsely pair them with a single opposite-side record.
    out_sigs = Counter(_entry_sig(e) for e in outs)
    inb_sigs = Counter(_entry_sig(e) for e in inbs)
    if out_sigs == inb_sigs:
        return {"status": "IDENTITY_VERIFIED",
                "count": sum(out_sigs.values())}
    return {"status": "IDENTITY_MISMATCH",
            "only_source": sum((out_sigs - inb_sigs).values()),
            "only_target": sum((inb_sigs - out_sigs).values())}


def _check_force_observed(bundle: dict, self_id: int | None) -> dict:
    """派送是否被觀察到（force_match 不得為 NOT_FOUND）。

    缺口：controller 可能在 execute_move 回 sent 後就計入 sent_actions，
    但 WASM 中從未出現己方部隊。此檢查捕捉該落差。
    """
    if not bundle:
        return {"status": "UNKNOWN", "reason": "bundle-missing"}
    src_match = bundle.get("force_match_source")
    tgt_match = bundle.get("force_match_target")
    if src_match == "FORCE_MATCH_NOT_FOUND" or tgt_match == "FORCE_MATCH_NOT_FOUND":
        return {"status": "DISPATCH_NOT_OBSERVED",
                "reason": "force_match_not_found",
                "source_match": src_match, "target_match": tgt_match}
    if src_match != "FORCE_MATCH_VERIFIED" or tgt_match != "FORCE_MATCH_VERIFIED":
        return {"status": "UNKNOWN",
                "reason": "force-match-not-verified",
                "source_match": src_match, "target_match": tgt_match}
    return {"status": "FORCE_OBSERVED"}


def _sent_units(bundle: dict) -> dict | None:
    t1 = bundle.get("t1") or {}
    outs = ((((t1.get("source") or {}).get("collections") or {})
             .get("outbound") or {}).get("entries") or [])
    if len(outs) != 1:
        return None
    return _vec(outs[0].get("units"))


def _check_sent_within(diff: dict, bundle: dict) -> dict:
    """派兵量不得超過派前來源存量（production 未知不放寬）。"""
    before = _vec(diff.get("before_attacker"))
    sent = _sent_units(bundle)
    if before is None or sent is None:
        return {"status": "UNKNOWN", "reason": "vectors-unavailable"}
    over = [n for n in NAMES6 if sent[n] > before[n]]
    if over:
        return {"status": "SENT_EXCEEDS_AVAILABLE", "units": over}
    return {"status": "SENT_WITHIN_AVAILABLE"}


def _check_source_drop(diff: dict, bundle: dict) -> dict:
    """來源下降 vs 已派量：== 匹配；< 回收/生產不確定；> 違規。"""
    before = _vec(diff.get("before_attacker"))
    after = _vec(diff.get("after_source"))
    sent = _sent_units(bundle)
    if before is None or after is None:
        return {"status": "UNKNOWN", "reason": "vectors-unavailable"}
    drop = {n: before[n] - after[n] for n in NAMES6}
    if any(v < 0 for v in drop.values()):
        return {"status": "SOURCE_REGAINED", "drop": drop}
    if sent is None:
        return {"status": "UNKNOWN", "reason": "bundle-sent-unavailable",
                "drop": drop}
    exact = all(drop[n] == sent[n] for n in NAMES6)
    less = all(drop[n] <= sent[n] for n in NAMES6) and not exact
    if exact:
        return {"status": "DROP_MATCHES_SENT", "drop": drop}
    if less:
        # 生產回填或 T3 拍攝時序；不假裝匹配
        return {"status": "DROP_BELOW_SENT_PRODUCTION_UNKNOWN",
                "drop": drop, "sent": sent}
    return {"status": "DROP_EXCEEDS_SENT", "drop": drop, "sent": sent}


def _normalize_units(d: dict | None) -> dict | None:
    """稀疏兵種 dict → 十種兵種齊備（缺欄 = 0）；已出現欄非法值回 None。"""
    if not isinstance(d, dict):
        return None
    out = {}
    for n in UNIT_NAMES:
        v = d.get(n, 0)
        if type(v) is not int or v < 0 or v > 255:
            return None
        out[n] = v
    return out


def _enemy_id_from_bundle(bundle: dict, self_id: int | None) -> int | None:
    """從 bundle 敵方部隊條目推論 ENEMY owner id（target outbound 優先）。"""
    if not bundle:
        return None
    for stage in ("t0", "t1", "t2", "t3"):
        part = bundle.get(stage) or {}
        for role, roles in (("target", ("outbound", "inbound")),
                            ("source", ("inbound",))):
            colls = ((part.get(role) or {}).get("collections") or {})
            for role_name in roles:
                for e in (colls.get(role_name) or {}).get("entries") or []:
                    oid = e.get("owner_id")
                    if type(oid) is int and oid > 0 and oid != self_id:
                        return oid
    return None


def _offline_battle_verdict(diff: dict, bundle: dict,
                            self_id: int) -> dict:
    """離線重評 ENEMY 目標戰鬥：sent vs before_defender。

    runtime 目前不產生戰鬥預測（prediction 恆為 None），此離線重評
    填補該缺口。特殊兵種（Ruler/Shell/Emp/Nuke）在差分中未記錄，
    一律假設 0 → confidence=DERIVED（非驗證）。
    """
    from kiomet_ai.pvp import evaluate_battle
    enemy_id = _enemy_id_from_bundle(bundle, self_id)
    if enemy_id is None:
        return {"status": "UNKNOWN", "reason": "enemy-id-unknown"}
    sent = _normalize_units(_sent_units(bundle))
    defender = _normalize_units(diff.get("before_defender"))
    if sent is None or defender is None:
        return {"status": "UNKNOWN", "reason": "vectors-unavailable"}
    tower_type = diff.get("target_type")
    capacity = CAPACITIES.get(tower_type)
    if not isinstance(capacity, dict):
        return {"status": "UNKNOWN", "reason": "tower-capacity-unknown"}
    case = {
        "world_context_required": False,
        "observed_tick": 0,
        "attacker_units": {n: sent[n] for n in ORDINARY},
        "defender_units": {n: defender[n] for n in ORDINARY},
        "special_unit_flags": {"ruler": False, "shell": False,
                               "emp": False, "nuke": False},
        "attacker_owner_relation": "SELF",
        "defender_owner_relation": "ENEMY",
        "self_owner_id": self_id,
        "attacker_aura_snapshot": False,
        "defender_aura_snapshot": False,
        "ruler_aura_state": {
            "attacker": {"ruler_unit_present": False,
                         "aura_flag_snapshot": False},
            "defender": {"ruler_unit_present": False,
                         "aura_flag_snapshot": False}},
        "shield_state": {"attacker": sent["Shield"],
                         "defender": defender["Shield"]},
        "battle_kind": "force_vs_tower",
        "target_branch": "tower_combat",
        "tower_type": tower_type,
        "tower_capacity": dict(capacity),
        "attacker_owner_id": self_id,
        "defender_owner_id": enemy_id,
    }
    result = evaluate_battle(case)
    if not result.get("supported"):
        return {"status": "UNKNOWN",
                "reason": "mirror-unsupported",
                "unsupported_reason": result.get("unsupported_reason")}
    return {
        "status": "OFFLINE_VERDICT",
        "winner": result.get("winner"),
        "attacker_survivors": result.get("attacker_survivors"),
        "defender_survivors": result.get("defender_survivors"),
        "confidence": "DERIVED",
        "note": "special units assumed 0 (diff records sparse mobile units)",
    }


def _check_arrival(diff: dict, bundle: dict) -> dict:
    """抵達：T3 目標塔應含已派兵（不判定 owner 語意）。"""
    after = _vec((diff.get("after_target") or {}).get("units"))
    sent = _sent_units(bundle)
    if after is None or sent is None:
        return {"status": "UNKNOWN", "reason": "vectors-unavailable"}
    missing = [n for n in NAMES6 if after[n] < sent[n]]
    if missing:
        return {"status": "ARRIVAL_NOT_OBSERVED", "short": missing,
                "after": after, "sent": sent}
    return {"status": "ARRIVAL_OBSERVED"}


def replay_case(case: dict) -> dict:
    """單案重播：分 stage 獨立判定，任一未知不污染其他 stage。"""
    diff = case.get("diff") or {}
    bundle = case.get("bundle")
    out = {"case_id": case.get("case_id"),
           "match_id": diff.get("match_id"),
           "action_id": diff.get("action_id"),
           "target_type": diff.get("target_type")}
    if bundle and bundle.get("match_id") != diff.get("match_id"):
        out["status"] = "NOT_REPLAYABLE"
        out["reason"] = "bundle-match-mismatch"
        return out
    id_ev = derive_id_evidence(bundle, diff)
    out["id_evidence"] = {"self_id": id_ev["self_id"],
                          "provenance": id_ev["self_id_provenance"],
                          "observed_owner_ids": id_ev["observed_owner_ids"]}
    out["temporal"] = _check_temporal(bundle) if bundle else {
        "status": "UNKNOWN", "reason": "bundle-missing"}
    out["force_identity"] = _check_force_identity(bundle) if bundle else {
        "status": "UNKNOWN", "reason": "bundle-missing"}
    out["force_observed"] = (_check_force_observed(bundle, id_ev["self_id"])
                            if bundle else {
                                "status": "UNKNOWN", "reason": "bundle-missing"})
    out["sent_within"] = _check_sent_within(diff, bundle or {})
    out["source_drop"] = _check_source_drop(diff, bundle or {})
    # 戰鬥評估：只有目標非中立才可能構成戰鬥；無條件保留原 runtime 判定
    tgt_owner = (diff.get("after_target") or {}).get("owner")
    if tgt_owner in ("OTHER", "ENEMY"):
        # 戰鬥目標：戰損使 after < sent 屬預期，不得誤判未抵達
        out["arrival"] = {"status": "NOT_APPLICABLE_BATTLE_TARGET"}
        if id_ev["self_id"] is None:
            out["battle"] = {"status": "SKIPPED_UNKNOWN_IDS"}
        else:
            out["battle"] = _offline_battle_verdict(
                diff, bundle or {}, id_ev["self_id"])
        out["runtime_evaluation"] = {
            "status": diff.get("evaluation_status"),
            "reason": diff.get("evaluation_reason"),
        }
    else:
        out["arrival"] = _check_arrival(diff, bundle or {})
        out["battle"] = {"status": "NOT_BATTLE_TARGET_OWNER",
                         "target_owner": tgt_owner}
    out["runtime_prediction"] = diff.get("prediction")
    flags = []
    if (out["runtime_prediction"] == "SKIPPED_UNKNOWN_IDS"
            and id_ev["self_id"] is not None):
        flags.append("RUNTIME_SKIPPED_BUT_SELF_ID_VERIFIABLE_FROM_BUNDLE")
    for key in ("temporal", "force_identity", "force_observed", "sent_within",
                "source_drop", "arrival"):
        st = out[key].get("status")
        if st in ("TEMPORAL_ANOMALY", "IDENTITY_MISMATCH",
                  "DISPATCH_NOT_OBSERVED",
                  "SENT_EXCEEDS_AVAILABLE", "DROP_EXCEEDS_SENT",
                  "ARRIVAL_NOT_OBSERVED"):
            flags.append(f"{key}:{st}")
    out["flags"] = flags
    out["status"] = "FLAGGED" if flags else "REPLAYED"
    return out


def replay_corpus(pvp_validation_root: Path) -> dict:
    """重播整個差分語料，回摘要。"""
    root = Path(pvp_validation_root)
    cases, skipped = [], []
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        if not (sub / "battle-differential.json").is_file():
            continue
        try:
            cases.append(replay_case(load_case(sub)))
        except (OSError, ValueError, KeyError) as exc:
            skipped.append({"case": sub.name, "error": str(exc)[:120]})
    summary = {"cases": len(cases),
               "flagged": sum(1 for c in cases if c["status"] == "FLAGGED"),
               "replayed": sum(1 for c in cases if c["status"] == "REPLAYED"),
               "self_ids_found": sorted({
                   c.get("id_evidence", {}).get("self_id")
                   for c in cases
                   if c.get("id_evidence", {}).get("self_id")}),
               "skipped": skipped}
    return {"summary": summary, "cases": cases}


BATTLE_EVIDENCE_REQUIRED = (
    "attacker_units", "defender_units", "tower_type",
    "self_id", "enemy_id",
)


def validate_battle_evidence_schema(raw: dict | None) -> dict:
    """驗證敵方戰鬥證據 schema；回正規化證據或錯誤列。

    不補值、不猜值：缺欄或型別錯誤即回 errors。
    """
    if not isinstance(raw, dict):
        return {"valid": False, "errors": ["evidence-must-be-object"],
                "evidence": None}
    errors = []
    for field in BATTLE_EVIDENCE_REQUIRED:
        if field not in raw:
            errors.append(f"missing-field:{field}")
    attacker = _normalize_units(
        raw.get("attacker_units")) if "attacker_units" in raw else None
    defender = _normalize_units(
        raw.get("defender_units")) if "defender_units" in raw else None
    if "attacker_units" in raw and attacker is None:
        errors.append("attacker-units-invalid")
    if "defender_units" in raw and defender is None:
        errors.append("defender-units-invalid")
    tower_type = raw.get("tower_type")
    if "tower_type" in raw and not isinstance(tower_type, str):
        errors.append("tower-type-invalid")
    elif "tower_type" in raw and tower_type not in CAPACITIES:
        errors.append("tower-capacity-unknown")
    for field in ("self_id", "enemy_id"):
        if field in raw:
            value = raw.get(field)
            if type(value) is not int or value <= 0:
                errors.append(f"{field}-invalid")
    if "self_id" in raw and "enemy_id" in raw:
        if raw.get("self_id") == raw.get("enemy_id"):
            errors.append("self-enemy-id-conflict")
    if errors:
        return {"valid": False, "errors": errors, "evidence": None}
    evidence = {
        "attacker_units": attacker,
        "defender_units": defender,
        "tower_type": tower_type,
        "self_id": raw.get("self_id"),
        "enemy_id": raw.get("enemy_id"),
        "recorded_truth": raw.get("recorded_truth"),
    }
    return {"valid": True, "errors": [], "evidence": evidence}


def run_battle_differential(raw: dict | None) -> dict:
    """敵方戰鬥差分管線：證據→評估器輸入→預測→真值→差分→報告。

    未來 GPT 產出 enemy combat evidence 後可直接餵入，
    無需等待真實敵方案例。UNKNOWN 永不轉成假值。
    """
    from kiomet_ai.pvp import evaluate_battle
    checked = validate_battle_evidence_schema(raw)
    if not checked["valid"]:
        return {"input": None, "prediction": None,
                "recorded_truth": (raw or {}).get("recorded_truth"),
                "support_status": "UNKNOWN",
                "differential": "EVIDENCE_INVALID",
                "reason": ";".join(checked["errors"])}
    evidence = checked["evidence"]
    attacker = evidence["attacker_units"]
    defender = evidence["defender_units"]
    case = {
        "world_context_required": False,
        "observed_tick": 0,
        "attacker_units": {n: attacker[n] for n in ORDINARY},
        "defender_units": {n: defender[n] for n in ORDINARY},
        "special_unit_flags": {"ruler": False, "shell": False,
                               "emp": False, "nuke": False},
        "attacker_owner_relation": "SELF",
        "defender_owner_relation": "ENEMY",
        "self_owner_id": evidence["self_id"],
        "attacker_aura_snapshot": False,
        "defender_aura_snapshot": False,
        "ruler_aura_state": {
            "attacker": {"ruler_unit_present": False,
                         "aura_flag_snapshot": False},
            "defender": {"ruler_unit_present": False,
                         "aura_flag_snapshot": False}},
        "shield_state": {"attacker": attacker["Shield"],
                         "defender": defender["Shield"]},
        "battle_kind": "force_vs_tower",
        "target_branch": "tower_combat",
        "tower_type": evidence["tower_type"],
        "tower_capacity": dict(CAPACITIES[evidence["tower_type"]]),
        "attacker_owner_id": evidence["self_id"],
        "defender_owner_id": evidence["enemy_id"],
    }
    result = evaluate_battle(case)
    if not result.get("supported"):
        return {"input": case, "prediction": None,
                "recorded_truth": evidence["recorded_truth"],
                "support_status": "UNKNOWN",
                "differential": "MIRROR_UNSUPPORTED",
                "reason": result.get("unsupported_reason")}
    prediction = {
        "winner": result.get("winner"),
        "attacker_survivors": result.get("attacker_survivors"),
        "defender_survivors": result.get("defender_survivors"),
    }
    truth = evidence["recorded_truth"]
    if truth is None:
        return {"input": case, "prediction": prediction,
                "recorded_truth": None,
                "support_status": "PREDICTED_NO_TRUTH",
                "differential": "NO_TRUTH_TO_COMPARE",
                "reason": "evaluator ran; no recorded truth supplied"}
    if not isinstance(truth, dict):
        return {"input": case, "prediction": prediction,
                "recorded_truth": truth,
                "support_status": "UNKNOWN",
                "differential": "TRUTH_MALFORMED",
                "reason": "recorded truth must be an object"}
    if truth.get("winner") == prediction["winner"]:
        return {"input": case, "prediction": prediction,
                "recorded_truth": truth,
                "support_status": "MATCH",
                "differential": "PREDICTION_MATCHES_TRUTH",
                "reason": "winner agrees"}
    return {"input": case, "prediction": prediction,
            "recorded_truth": truth,
            "support_status": "MISMATCH",
            "differential": "PREDICTION_DIFFERS_FROM_TRUTH",
            "reason": (f"predicted {prediction['winner']} "
                       f"vs recorded {truth.get('winner')}")}


THREAT_SNAPSHOT_REQUIRED = ("match_id", "observed_at", "target_tower_id",
                            "threats")
THREAT_STALE_SECONDS = 30


def threat_snapshot_from_force_rows(rows, match_id: str,
                                    target_tower_id: int | None = None,
                                    observed_at: float | None = None,
                                    distance_m: float | None = None) -> dict:
    """force-poll 原始列 → 威脅快照（供 replay_threat_waves）。

    只收 role=INBOUND 且 owner_id 為正整數者；同
    (owner_id, src, dst) 取最新樣本，全部樣本按時序保留；
    損壞列跳過。force-poll 不記錄 speed_flag／ETA，
    故重算所需輸入預設缺席（ETA_UNKNOWN，而非 0）。
    """
    import math
    groups: dict = {}
    latest_t = observed_at
    if isinstance(rows, str):
        rows = rows.splitlines()
    for row in rows or []:
        if isinstance(row, str):
            if not row.strip():
                continue
            try:
                row = json.loads(row)
            except ValueError:
                continue
        if not isinstance(row, dict):
            continue
        if row.get("role") != "INBOUND":
            continue
        owner_id = row.get("owner_id")
        if type(owner_id) is not int or owner_id <= 0:
            continue
        units = _normalize_units(row.get("units"))
        if units is None:
            continue
        progress = row.get("progress")
        if type(progress) is not int or progress < 0:
            continue
        moment = row.get("t")
        if (type(moment) not in (int, float)
                or not math.isfinite(moment)):
            continue
        key = (owner_id, row.get("src"), row.get("dst"))
        groups.setdefault(key, []).append({
            "t": moment, "progress": progress, "units": units,
            "relation": row.get("relation"),
        })
        if latest_t is None or moment > latest_t:
            latest_t = moment
    threats = []
    for (owner_id, src, dst), samples in sorted(groups.items()):
        samples.sort(key=lambda s: s["t"])
        latest = samples[-1]
        threats.append({
            "owner_id": owner_id,
            "owner_relation": latest["relation"],
            "units": latest["units"],
            "progress": latest["progress"],
            "speed_flag": None,
            "eta_ticks": None,
            "distance_m": distance_m,
            "src_tower_id": src,
            "dst_tower_id": dst,
            "samples": [{"t": s["t"], "progress": s["progress"],
                         "units": s["units"]} for s in samples],
        })
    return {"match_id": match_id, "observed_at": latest_t,
            "target_tower_id": target_tower_id, "threats": threats}


def _threat_units_signature(units: dict | None) -> tuple | None:
    """兵種簽名（count>0 的兵種集合）；供波次同一性檢查。"""
    if not isinstance(units, dict):
        return None
    try:
        return tuple(sorted(n for n, v in units.items() if v))
    except Exception:
        return None


def validate_threat_snapshot(raw: dict | None) -> dict:
    """驗證威脅快照 schema；缺欄或型別錯誤即回 errors，不補值。"""
    import math
    if not isinstance(raw, dict):
        return {"valid": False, "errors": ["snapshot-must-be-object"],
                "snapshot": None}
    errors = []
    for field in THREAT_SNAPSHOT_REQUIRED:
        if field not in raw:
            errors.append(f"missing-field:{field}")
    match_id = raw.get("match_id")
    if "match_id" in raw and (not isinstance(match_id, str) or not match_id):
        errors.append("match-id-invalid")
    observed_at = raw.get("observed_at")
    if "observed_at" in raw and (
            type(observed_at) not in (int, float)
            or not math.isfinite(observed_at) or observed_at <= 0):
        errors.append("observed-at-invalid")
    target = raw.get("target_tower_id")
    if "target_tower_id" in raw and (type(target) is not int or target <= 0):
        errors.append("target-tower-invalid")
    threats = raw.get("threats")
    clean_threats = []
    if "threats" in raw:
        if not isinstance(threats, list):
            errors.append("threats-must-be-list")
        else:
            for index, threat in enumerate(threats):
                if not isinstance(threat, dict):
                    errors.append(f"threat-{index}-not-object")
                    continue
                owner_id = threat.get("owner_id")
                if type(owner_id) is not int or owner_id <= 0:
                    errors.append(f"threat-{index}-owner-unknown")
                    continue
                units = _normalize_units(threat.get("units"))
                if units is None:
                    errors.append(f"threat-{index}-units-invalid")
                    continue
                progress = threat.get("progress")
                if type(progress) is not int or progress < 0:
                    errors.append(f"threat-{index}-progress-invalid")
                    continue
                speed_flag = threat.get("speed_flag")
                if (speed_flag is not None
                        and type(speed_flag) is not int):
                    errors.append(f"threat-{index}-speed-flag-invalid")
                    continue
                recorded = threat.get("eta_ticks")
                if (recorded is not None
                        and (type(recorded) is not int or recorded < 0)):
                    errors.append(f"threat-{index}-eta-invalid")
                    continue
                distance = threat.get("distance_m")
                if (distance is not None
                        and (isinstance(distance, bool)
                             or not isinstance(distance, (int, float))
                             or distance <= 0)):
                    errors.append(f"threat-{index}-distance-invalid")
                    continue
                samples = threat.get("samples")
                if samples is not None:
                    if not isinstance(samples, list) or not samples:
                        errors.append(f"threat-{index}-samples-invalid")
                        continue
                    ok = True
                    for sample in samples:
                        if not isinstance(sample, dict):
                            ok = False
                            break
                        if _normalize_units(sample.get("units")) is None:
                            ok = False
                            break
                        if (type(sample.get("t")) not in (int, float)
                                or type(sample.get("progress")) is not int):
                            ok = False
                            break
                    if not ok:
                        errors.append(f"threat-{index}-samples-invalid")
                        continue
                clean_threats.append({
                    "owner_id": owner_id,
                    "owner_relation": threat.get("owner_relation"),
                    "units": units,
                    "progress": progress,
                    "speed_flag": speed_flag,
                    "eta_ticks": recorded,
                    "distance_m": distance,
                    "samples": samples,
                })
    if errors:
        return {"valid": False, "errors": errors, "snapshot": None}
    return {"valid": True, "errors": [], "snapshot": {
        "match_id": match_id, "observed_at": observed_at,
        "target_tower_id": target, "threats": clean_threats}}


def replay_threat_waves(snapshot: dict | None, now: float | None = None,
                        current_match_id: str | None = None) -> dict:
    """威脅波次重播：ETA 重算、波次同一性、過期判定、依 ETA 排序。

    UNKNOWN 永不轉成假值：缺記錄 ETA 或缺距離即為 ETA_UNKNOWN，
    不參與一致／不一致判定。
    current_match_id 指定時，快照屬他局即整批 CROSS_MATCH_STALE。
    """
    import time as _time
    from kiomet_ai.force import ForceUnits, eta_ticks, unit_speed
    checked = (validate_threat_snapshot(snapshot) if isinstance(snapshot, dict)
               else {"valid": False, "errors": ["snapshot-must-be-object"],
                     "snapshot": None})
    if not checked["valid"]:
        return {"status": "UNKNOWN", "reason": "EVIDENCE_INVALID",
                "errors": checked["errors"], "verdicts": []}
    snap = checked["snapshot"]
    if (current_match_id is not None
            and snap["match_id"] != current_match_id):
        return {"status": "UNKNOWN", "reason": "CROSS_MATCH_STALE",
                "errors": [], "verdicts": []}
    now = _time.time() if now is None else now
    stale = (now - snap["observed_at"]) > THREAT_STALE_SECONDS
    verdicts = []
    for threat in snap["threats"]:
        speed = unit_speed(ForceUnits(tag=0, counts=dict(threat["units"])))
        recomputed = None
        if threat["distance_m"] is not None:
            recomputed = eta_ticks(threat["progress"], speed,
                                   threat["distance_m"],
                                   threat["speed_flag"])
        recorded = threat["eta_ticks"]
        if recorded is None or recomputed is None:
            eta_verdict = "ETA_UNKNOWN"
        elif recorded == recomputed:
            eta_verdict = "ETA_MATCH"
        else:
            eta_verdict = "ETA_MISMATCH"
        wave = {"identity": "SINGLE_SAMPLE", "monotonic": None}
        samples = threat.get("samples") or []
        if len(samples) >= 2:
            sigs = {_threat_units_signature(s.get("units")) for s in samples}
            if len(sigs) != 1 or None in sigs:
                wave = {"identity": "ROUTE_CONFLATED",
                        "monotonic": None,
                        "note": ("units signature changes across samples; "
                                 "route groups distinct forces, not one wave")}
            else:
                progs = [s.get("progress") for s in samples]
                wave = {"identity": "STABLE",
                        "monotonic": all(b >= a for a, b in zip(
                            progs, progs[1:]))}
        verdicts.append({
            "owner_id": threat["owner_id"],
            "owner_relation": threat["owner_relation"],
            "speed": speed,
            "recomputed_eta_ticks": recomputed,
            "recorded_eta_ticks": recorded,
            "eta_verdict": eta_verdict,
            "wave": wave,
        })
    key = lambda v: (v["recomputed_eta_ticks"] if v["recomputed_eta_ticks"]
                     is not None else 10 ** 12)
    ordered = sorted(range(len(verdicts)), key=lambda i: key(verdicts[i]))
    if any(v["eta_verdict"] == "ETA_MISMATCH" for v in verdicts):
        status, reason = "FLAGGED", "recomputed ETA differs from recorded"
    elif stale:
        status, reason = "STALE", "observation older than 30s"
    else:
        status, reason = "REPLAYED", "all checks passed"
    return {"status": status, "reason": reason, "stale": stale,
            "verdicts": verdicts, "ordered_by_eta": ordered}


PROOF_BINDING_FIELDS = (
    "match_id", "cycle_id", "source_tower_id", "target_tower_id",
)


def verify_proof_envelope(envelope: dict | None) -> dict:
    """獨立驗證攻擊 proof envelope 完整性（離線重算雜湊）。

    與產生器不同程式、同一規範（canonical JSON＋sha256）：
    只驗證「此 ID 確實對應此內容」，不判斷內容真假。
    缺欄、格式錯誤、雜湊不符一律回 INVALID，不猜測。
    """
    if not isinstance(envelope, dict):
        return {"valid": False, "reason": "envelope-must-be-object"}
    evidence_id = envelope.get("evidence_id")
    if (not isinstance(evidence_id, str)
            or not evidence_id.startswith("sha256:")
            or len(evidence_id) != len("sha256:") + 64):
        return {"valid": False, "reason": "evidence-id-malformed"}
    try:
        payload = {key: value for key, value in envelope.items()
                   if key != "evidence_id"}
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        return {"valid": False, "reason": "envelope-not-encodable"}
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    if digest != evidence_id:
        return {"valid": False, "reason": "hash-mismatch"}
    missing = [field for field in PROOF_BINDING_FIELDS
               if field not in envelope]
    if missing:
        return {"valid": False, "reason": "binding-fields-missing",
                "missing": missing}
    return {"valid": True, "reason": "hash-matches-content",
            "evidence_id": evidence_id}


def verify_attack_proof_bundle(bundle: dict | None) -> dict:
    """驗證攻擊 proof bundle 雙封包（battle＋server）。

    兩封包各自獨立驗證；任一無效即整包 INVALID。
    不判斷戰鬥勝負或伺服器接受語意，只驗完整性＋綁定欄位。
    """
    if not isinstance(bundle, dict):
        return {"valid": False, "reason": "bundle-must-be-object"}
    battle = bundle.get("battle_differential_evidence")
    server = bundle.get("server_acceptance_evidence")
    battle_id = bundle.get("battle_differential_evidence_id")
    server_id = bundle.get("server_acceptance_evidence_id")
    if not isinstance(battle, dict) or not isinstance(server, dict):
        return {"valid": False, "reason": "bundle-evidences-missing"}
    if not isinstance(battle_id, str) or not battle_id:
        return {"valid": False, "reason": "battle-evidence-id-missing"}
    if not isinstance(server_id, str) or not server_id:
        return {"valid": False, "reason": "server-evidence-id-missing"}
    battle_check = verify_proof_envelope({**battle, "evidence_id": battle_id})
    if not battle_check["valid"]:
        return {"valid": False, "reason": "battle-envelope-invalid",
                "detail": battle_check["reason"]}
    server_check = verify_proof_envelope({**server, "evidence_id": server_id})
    if not server_check["valid"]:
        return {"valid": False, "reason": "server-envelope-invalid",
                "detail": server_check["reason"]}
    for field in PROOF_BINDING_FIELDS:
        battle_value = battle.get(field)
        server_value = server.get(field)
        if (type(battle_value) is not type(server_value)
                or battle_value != server_value):
            return {"valid": False, "reason": "bundle-binding-mismatch",
                    "field": field}

    binding = {field: battle.get(field) for field in PROOF_BINDING_FIELDS}
    if (type(binding["match_id"]) is not str
            or not binding["match_id"]):
        return {"valid": False, "reason": "bundle-binding-invalid",
                "field": "match_id"}
    if type(binding["cycle_id"]) is not int or binding["cycle_id"] <= 0:
        return {"valid": False, "reason": "bundle-binding-invalid",
                "field": "cycle_id"}
    for field in ("source_tower_id", "target_tower_id"):
        if type(binding[field]) is not int or binding[field] <= 0:
            return {"valid": False, "reason": "bundle-binding-invalid",
                    "field": field}
    if binding["source_tower_id"] == binding["target_tower_id"]:
        return {"valid": False, "reason": "bundle-binding-invalid",
                "field": "target_tower_id"}
    return {"valid": True, "reason": "both-envelopes-verified"}
