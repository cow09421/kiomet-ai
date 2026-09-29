"""第一閉環垂直切片：ActionProposal（行動提案）＋預檢＋驗證器。

全部純函數，不碰瀏覽器、不發送任何輸入。閉環終點永遠是
WAITING_FOR_EXECUTE（等待執行授權）；EXECUTING（執行中）
在本模組不存在進入路徑（構造性保證，見測試）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# 閉環狀態（§37）。EXECUTING／VERIFYING 在本輪不可進。
LOOP_OBSERVING = "OBSERVING"
LOOP_PLANNING = "PLANNING"
LOOP_PROPOSAL_READY = "PROPOSAL_READY"
LOOP_PREFLIGHT_PASS = "PREFLIGHT_PASS"
LOOP_WAITING_FOR_EXECUTE = "WAITING_FOR_EXECUTE"

# 提案狀態。
PROPOSAL_READY = "READY"
PROPOSAL_REJECTED = "REJECTED"
PROPOSAL_STALE = "STALE"

# 預檢結果。
PREFLIGHT_READY = "READY_TO_EXECUTE"
PREFLIGHT_REJECTED = "REJECTED"

# 驗證狀態（§32）。
VERIFY_STATES = ("ACTION_SENT", "SOURCE_CHANGED", "FORCE_OBSERVED",
                 "TARGET_CONTESTED", "TARGET_CAPTURED", "ACTION_REJECTED",
                 "ACTION_TIMEOUT", "MATCH_ENDED", "UNKNOWN")


@dataclass(frozen=True)
class ActionProposal:
    """完整調兵提案（§9 全欄位）。executor_ready 表示輸入完備，
    authorization_required 永遠 True（本輪無授權）。"""
    match_id: str | None
    created_at: float
    source_tower_id: int
    source_tower_ref: int | None = None
    source_world_xy: tuple | None = None
    source_screen_xy: tuple | None = None
    source_owner: str | None = None
    source_type: str | None = None
    source_units: dict | None = None
    source_deployable_force: dict | None = None
    deployable_status: str = "UNKNOWN"       # DERIVED / VERIFIED / UNKNOWN
    target_tower_id: int | None = None
    target_tower_ref: int | None = None
    target_world_xy: tuple | None = None
    target_screen_xy: tuple | None = None
    target_owner: str | None = None
    target_type: str | None = None
    target_units: dict | None = None
    path: tuple = ()
    path_length: int = 0
    neighbor_verified: bool = False
    source_fresh: bool = False
    target_fresh: bool = False
    camera_fresh: bool = False
    screen_mapping_fresh: bool = False
    rank_score: float | None = None
    rank_reasons: tuple = ()
    safety_checks: tuple = ()
    executor_ready: bool = False
    authorization_required: bool = True
    status: str = PROPOSAL_REJECTED
    reject_reason: str | None = None
    action_kind: str = "EXPAND_NEUTRAL"
    cycle_id: int | None = None


def _counts_dict(counts) -> dict | None:
    if counts is None:
        return None
    return {"fighter": counts.fighter, "chopper": counts.chopper,
            "bomber": counts.bomber, "tank": counts.tank,
            "soldier": counts.soldier, "shield": counts.shield,
            "kind": counts.units_kind,
            "single_type": counts.single_unit_type,
            "single_count": counts.single_count}


def build_proposal(candidate: dict, states_by_id: dict,
                   match_id: str, now: float | None = None, *,
                   expected_target_owner: str = "NEUTRAL",
                   action_kind: str | None = None,
                   cycle_id: int | None = None) -> ActionProposal:
    """由候選建提案；目標所有權必須符合明確指定的安全閘。"""
    now = time.time() if now is None else now
    owner_actions = {"NEUTRAL": "EXPAND_NEUTRAL",
                     "ENEMY": "ATTACK_ENEMY",
                     "SELF": "REINFORCE_SELF"}
    expected_action = (owner_actions.get(expected_target_owner)
                       if isinstance(expected_target_owner, str) else None)
    resolved_action = (expected_action if action_kind is None else action_kind)
    base = dict(match_id=match_id, created_at=now,
                source_tower_id=candidate.get("source"),
                target_tower_id=candidate.get("target"),
                rank_score=candidate.get("heuristic_score"),
                rank_reasons=tuple([candidate.get("reason", "")]),
                authorization_required=True,
                action_kind=resolved_action or "UNSUPPORTED",
                cycle_id=cycle_id)
    source = states_by_id.get(candidate.get("source"))
    target = states_by_id.get(candidate.get("target"))
    checks = []
    ok = True

    def gate(name: str, passed: bool):
        nonlocal ok
        checks.append((name, "PASS" if passed else "FAIL"))
        if not passed:
            ok = False

    gate("match_current", bool(match_id))
    gate("source_exists", source is not None)
    gate("target_exists", target is not None)
    if source is None or target is None:
        return ActionProposal(status=PROPOSAL_REJECTED,
                              reject_reason="missing_tower",
                              safety_checks=tuple(checks), **base)
    gate("source_self", source.owner == "SELF")
    gate("source_many",
         source.unit_counts is not None and source.unit_counts.units_kind == "MANY")
    gate("source_deployable",
         source.deployable_force is not None
         and source.deployable_force_confidence in ("DERIVED", "VERIFIED"))
    target_owner_gate = ({
        "NEUTRAL": "target_neutral",
        "ENEMY": "target_enemy",
        "SELF": "target_self",
    }.get(expected_target_owner, "target_owner_unsupported")
        if isinstance(expected_target_owner, str)
        else "target_owner_unsupported")
    gate(target_owner_gate,
         expected_target_owner in ("NEUTRAL", "ENEMY", "SELF")
         and target.owner == expected_target_owner)
    gate("action_owner_contract",
         expected_action is not None and resolved_action == expected_action
         and (expected_target_owner != "SELF"
              or action_kind == "REINFORCE_SELF"))
    if expected_target_owner == "SELF" and action_kind == "REINFORCE_SELF":
        from kiomet_ai.observe import UNIT_NAMES
        force = candidate.get("full_deployable_force")
        source_force = getattr(getattr(source, "deployable_force", None),
                               "counts", None)
        force_valid = (
            isinstance(force, dict)
            and set(force) == set(UNIT_NAMES)
            and all(type(value) is int and 0 <= value <= 255
                    for value in force.values())
            and not any(force.get(name, 0)
                        for name in ("Shell", "Emp", "Nuke", "Ruler"))
            and any(force.get(name, 0)
                    for name in UNIT_NAMES[:6]))
        gate("reinforcement_match_cycle",
             bool(match_id) and type(cycle_id) is int and cycle_id >= 0
             and candidate.get("match_id") == match_id
             and candidate.get("cycle_id") == cycle_id)
        gate("reinforcement_command_validated",
             candidate.get("command_validated") is True)
        gate("reinforcement_full_force_exact",
             force_valid and isinstance(source_force, dict)
             and force == source_force)
        gate("reinforcement_unit_count_exact",
             type(candidate.get("unit_count")) is int
             and force_valid
             and candidate["unit_count"] == sum(force.values()))
        gate("reinforcement_bidirectional_neighbor",
             target.tower_id in source.neighbors
             and source.tower_id in target.neighbors)
    gate("direct_neighbor", target.tower_id in source.neighbors)
    gate("not_same", source.tower_id != target.tower_id)
    gate("source_fresh", source.freshness(match_id, now) == "FRESH")
    gate("target_fresh", target.freshness(match_id, now) == "FRESH")
    if not ok:
        failed = next(name for name, result in checks if result == "FAIL")
        return ActionProposal(status=PROPOSAL_REJECTED, reject_reason=failed,
                              safety_checks=tuple(checks), **base)
    force = source.deployable_force
    return ActionProposal(
        source_tower_ref=source.tower_ref,
        source_world_xy=(source.world_x, source.world_y),
        source_screen_xy=(source.screen_x, source.screen_y),
        source_owner=source.owner, source_type=source.tower_type,
        source_units=_counts_dict(source.unit_counts),
        source_deployable_force=dict(force.counts),
        deployable_status=source.deployable_force_confidence,
        target_tower_ref=target.tower_ref,
        target_world_xy=(target.world_x, target.world_y),
        target_screen_xy=(target.screen_x, target.screen_y),
        target_owner=target.owner, target_type=target.tower_type,
        target_units=_counts_dict(target.unit_counts),
        path=(source.tower_id, target.tower_id), path_length=1,
        neighbor_verified=True,
        source_fresh=True, target_fresh=True,
        camera_fresh=False, screen_mapping_fresh=False,
        safety_checks=tuple(checks),
        executor_ready=False,  # 需 preflight 補齊座標驗證才可
        status=PROPOSAL_READY, reject_reason=None, **base)


def build_reinforcement_proposal(candidate: dict, target_tower_id: int,
                                 states_by_id: dict, match_id: str,
                                 cycle_id: int, now: float | None = None
                                 ) -> ActionProposal:
    """把當週期已驗證的防守候選轉成 SELF→SELF 預檢提案。

    candidate 必須攜帶仲裁候選的 match_id、cycle_id、完整可派兵力、
    精確 unit_count 與 command_validated；本函式不保留輸入或發送操作。
    """
    now = time.time() if now is None else now
    source_id = (candidate.get("source_tower_id")
                 if isinstance(candidate, dict) else None)
    valid_ids = (type(source_id) is int and source_id > 0
                 and type(target_tower_id) is int and target_tower_id > 0)
    normalized = {
        "source": source_id if type(source_id) is int else -1,
        "target": target_tower_id if type(target_tower_id) is int else -1,
        "reason": "validated-pvp-reinforcement",
    }
    if isinstance(candidate, dict):
        normalized.update({
            "match_id": candidate.get("match_id"),
            "cycle_id": candidate.get("cycle_id"),
            "command_validated": candidate.get("command_validated"),
            "full_deployable_force": candidate.get("full_deployable_force"),
            "unit_count": candidate.get("unit_count"),
        })
    if (not valid_ids or type(cycle_id) is not int or cycle_id < 0
            or not isinstance(candidate, dict)):
        return ActionProposal(
            match_id=match_id, created_at=now,
            source_tower_id=normalized["source"],
            target_tower_id=normalized["target"],
            status=PROPOSAL_REJECTED,
            reject_reason="reinforcement-candidate-malformed",
            action_kind="REINFORCE_SELF", cycle_id=cycle_id)
    return build_proposal(
        normalized, states_by_id, match_id, now,
        expected_target_owner="SELF", action_kind="REINFORCE_SELF",
        cycle_id=cycle_id)


def prepare_move(proposal: ActionProposal, states_by_id: dict,
                 screen_map: dict, canvas: dict,
                 match_id: str, now: float | None = None, *,
                 cycle_id: int | None = None) -> tuple:
    """執行前置檢查（§17）：用新鮮狀態＋重算屏座標驗證。

    screen_map: {tower_id: (x, y)} 由呼叫方以新鮮 camera 算出；
    canvas: {"w":..., "h":...} 畫布範圍。本函式不產生任何輸入，
    只回 (READY_TO_EXECUTE|REJECTED, proposal|reasons)。
    """
    now = time.time() if now is None else now
    if proposal.status != PROPOSAL_READY:
        return PREFLIGHT_REJECTED, ("proposal_not_ready",)
    if proposal.match_id != match_id:
        return PREFLIGHT_REJECTED, ("match_changed",)
    action_kind = getattr(proposal, "action_kind", "EXPAND_NEUTRAL")
    if (action_kind == "REINFORCE_SELF"
            and (type(cycle_id) is not int
                 or cycle_id != proposal.cycle_id)):
        return PREFLIGHT_REJECTED, ("cycle_changed",)
    if action_kind == "REINFORCE_SELF":
        required_gates = {
            "action_owner_contract", "reinforcement_match_cycle",
            "reinforcement_command_validated",
            "reinforcement_full_force_exact",
            "reinforcement_unit_count_exact",
            "reinforcement_bidirectional_neighbor",
        }
        passed_gates = {name for name, result in proposal.safety_checks
                        if result == "PASS"}
        if not required_gates.issubset(passed_gates):
            return PREFLIGHT_REJECTED, ("reinforcement_evidence_missing",)
    source = states_by_id.get(proposal.source_tower_id)
    target = states_by_id.get(proposal.target_tower_id)
    if source is None or target is None:
        return PREFLIGHT_REJECTED, ("tower_gone",)
    if source.owner != "SELF":
        return PREFLIGHT_REJECTED, ("source_owner_changed",)
    expected_target_owner = proposal.target_owner
    owner_actions = {"NEUTRAL": "EXPAND_NEUTRAL",
                     "ENEMY": "ATTACK_ENEMY",
                     "SELF": "REINFORCE_SELF"}
    if (not isinstance(expected_target_owner, str)
            or expected_target_owner not in owner_actions
            or action_kind != owner_actions[expected_target_owner]
            or target.owner != expected_target_owner):
        return PREFLIGHT_REJECTED, ("target_owner_changed",)
    if target.tower_id not in source.neighbors:
        return PREFLIGHT_REJECTED, ("neighbor_gone",)
    if (action_kind == "REINFORCE_SELF"
            and source.tower_id not in target.neighbors):
        return PREFLIGHT_REJECTED, ("reverse_neighbor_gone",)
    if source.tower_ref != proposal.source_tower_ref:
        return PREFLIGHT_REJECTED, ("source_ref_changed",)
    if target.tower_ref != proposal.target_tower_ref:
        return PREFLIGHT_REJECTED, ("target_ref_changed",)
    if source.freshness(match_id, now) != "FRESH":
        return PREFLIGHT_REJECTED, ("source_stale",)
    if target.freshness(match_id, now) != "FRESH":
        return PREFLIGHT_REJECTED, ("target_stale",)
    s_xy = screen_map.get(source.tower_id)
    t_xy = screen_map.get(target.tower_id)
    if s_xy is None or t_xy is None:
        return PREFLIGHT_REJECTED, ("screen_missing",)
    w, h = canvas.get("w", 0), canvas.get("h", 0)
    if not (0 <= s_xy[0] < w and 0 <= s_xy[1] < h
            and 0 <= t_xy[0] < w and 0 <= t_xy[1] < h):
        return PREFLIGHT_REJECTED, ("screen_out_of_canvas",)
    import dataclasses
    refreshed = dataclasses.replace(
        proposal, source_screen_xy=tuple(s_xy), target_screen_xy=tuple(t_xy),
        camera_fresh=True, screen_mapping_fresh=True,
        executor_ready=True, created_at=now)
    return PREFLIGHT_READY, refreshed


def _force_credit_ok(after: dict, proposal: ActionProposal) -> bool:
    """FORCE_OBSERVED 信用閘（§32 硬化）：證據綁定缺一不可。

    - force_match 存在時必須 FORCE_MATCH_VERIFIED（DERIVED 不予信用）；
    - force_path 存在時必須與提案 source→target 同向；
    - action_id 存在時必須綁定本案 match/source/target 前綴；
    - temporal_status 存在時必須 TEMPORAL_OK；
    - action_origin 存在時不得 UNKNOWN。
    欄位缺失不阻擋（向後相容）；任一不符即拒絕信用。
    """
    fm = after.get("force_match")
    if fm is not None and fm != "FORCE_MATCH_VERIFIED":
        return False
    fp = after.get("force_path")
    if fp is not None:
        try:
            if tuple(fp) != (proposal.source_tower_id,
                             proposal.target_tower_id):
                return False
        except TypeError:
            return False
    aid = after.get("action_id")
    if aid is not None:
        prefix = (f"{proposal.match_id}:{proposal.source_tower_id}->"
                  f"{proposal.target_tower_id}:")
        if not str(aid).startswith(prefix):
            return False
    ts = after.get("temporal_status")
    if ts is not None and ts != "TEMPORAL_OK":
        return False
    origin = after.get("action_origin")
    if origin is not None and origin == "UNKNOWN":
        return False
    return True


def verify_post_action(before: dict, after: dict,
                       proposal: ActionProposal) -> str:
    """行動後驗證器（合成／歷史狀態輸入）：回傳驗證狀態（§32）。"""
    if after.get("match_id") != proposal.match_id:
        return "MATCH_ENDED"
    src_before, src_after = before.get("source"), after.get("source")
    tgt_before, tgt_after = before.get("target"), after.get("target")
    if src_before is None or src_after is None:
        return "UNKNOWN"
    if after.get("timeout"):
        return "ACTION_TIMEOUT"
    if after.get("rejected"):
        return "ACTION_REJECTED"
    if getattr(proposal, "action_kind", "EXPAND_NEUTRAL") == "REINFORCE_SELF":
        if tgt_after is not None and tgt_after.get("owner") != "SELF":
            return "TARGET_CONTESTED"
        if after.get("force_observed") and _force_credit_ok(after, proposal):
            return "FORCE_OBSERVED"
        if src_after != src_before:
            return "SOURCE_CHANGED"
        if after.get("sent"):
            return "ACTION_SENT"
        return "UNKNOWN"
    if tgt_after is not None and tgt_after.get("owner") == "SELF":
        return "TARGET_CAPTURED"
    if tgt_after is not None and tgt_after != tgt_before:
        return "TARGET_CONTESTED"
    if after.get("force_observed") and _force_credit_ok(after, proposal):
        return "FORCE_OBSERVED"
    if src_after != src_before:
        return "SOURCE_CHANGED"
    if after.get("sent"):
        return "ACTION_SENT"
    return "UNKNOWN"


def run_dry_cycle(candidate: dict | None, states_by_id: dict,
                  screen_map: dict, canvas: dict,
                  match_id: str, now: float | None = None) -> dict:
    """乾閉環（§35）：Observe→Rank→Proposal→Preflight→WAIT。
    永遠停在 WAITING_FOR_EXECUTE；無 EXECUTING 路徑。"""
    trail = [LOOP_OBSERVING, LOOP_PLANNING]
    if not candidate:
        return {"phase": LOOP_PLANNING, "trail": tuple(trail),
                "proposal": None, "preflight": ("NO_CANDIDATE",),
                "gate": LOOP_WAITING_FOR_EXECUTE, "sent": False}
    proposal = build_proposal(candidate, states_by_id, match_id, now)
    trail.append(LOOP_PROPOSAL_READY)
    if proposal.status != PROPOSAL_READY:
        return {"phase": LOOP_PROPOSAL_READY, "trail": tuple(trail),
                "proposal": proposal,
                "preflight": ("SKIPPED", proposal.reject_reason),
                "gate": LOOP_WAITING_FOR_EXECUTE, "sent": False}
    result, refreshed = prepare_move(proposal, states_by_id, screen_map,
                                     canvas, match_id, now)
    if result == PREFLIGHT_READY:
        trail.append(LOOP_PREFLIGHT_PASS)
    return {"phase": LOOP_PREFLIGHT_PASS if result == PREFLIGHT_READY else LOOP_PROPOSAL_READY,
            "trail": tuple(trail), "proposal": refreshed,
            "preflight": (result,),
            "gate": LOOP_WAITING_FOR_EXECUTE, "sent": False}
