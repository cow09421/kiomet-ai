"""In-app LiveController（真實遊玩協調器，常駐平台進程）。

閉環：Observe → Rank → Proposal → Preflight → Execute →
Verify → Replan。每次最多 ONE Action；心跳＋週期計數常駐快照；
連續 3 次無驗證結果自動暫停戰術動作（保留觀察）。
與 tools/live_controller.py（外部版）共享語意；遊戲狀態觀察
只可使用玩家可見 UI 資料。可見 UI 觀察器未完成前必須棄權。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from kiomet_ai.action_validity import (
    ReservationBoard,
    build_token,
    validate_token,
)
from kiomet_ai.dry_rank import rank_expansion_targets, rejection_reasons
from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    UNIT_NAMES,
    build_real_tower_states,
    decode_owner_ruler_flag,
    decode_tower_type,
    decode_tower_units,
)
from kiomet_ai.proposal import (
    PREFLIGHT_READY,
    build_proposal,
    build_reinforcement_proposal,
    prepare_move,
    verify_post_action,
)
from kiomet_ai.pvp_live import PlayerIdRegistry

VERIFIED_ACTION_RESULTS = frozenset((
    "TARGET_CAPTURED", "TARGET_CONTESTED", "FORCE_OBSERVED",
    "SOURCE_CHANGED"))

OBSERVATION_BLOCKER_CATEGORIES = frozenset((
    "MATCH_STALE", "OBSERVATION_STALE", "ANCHOR_STALE", "PROBE_STALE",
    "CAMERA_STALE", "FORCE_STALE", "CONTROLLER_STALE", "RECOVERY_STALE",
    "UNKNOWN_STALE",
))


def _attack_proof_provenance_matches(candidate: dict, match_id: str,
                                     cycle_id: int) -> bool:
    """要求戰鬥與伺服器證據內容綁定本週期的同一敵方行動。"""
    if not isinstance(candidate, dict):
        return False
    source_id = candidate.get("source_tower_id")
    target_id = candidate.get("target_tower_id")
    attacker_id = candidate.get("attacker_owner_id")
    defender_id = candidate.get("defender_owner_id")
    force = candidate.get("proposed_units")
    if (not isinstance(match_id, str) or not match_id
            or type(cycle_id) is not int
            or type(source_id) is not int or source_id <= 0
            or type(target_id) is not int or target_id <= 0
            or source_id == target_id
            or type(attacker_id) is not int or attacker_id <= 0
            or type(defender_id) is not int or defender_id <= 0
            or attacker_id == defender_id
            or not isinstance(force, dict) or set(force) != set(UNIT_NAMES)
            or any(type(value) is not int or value < 0 or value > 255
                   for value in force.values())
            or not any(force.get(name, 0) for name in UNIT_NAMES[:6])
            or any(force.get(name, 0)
                   for name in ("Shell", "Emp", "Nuke", "Ruler"))):
        return False

    binding = {
        "match_id": match_id,
        "cycle_id": cycle_id,
        "source_tower_id": source_id,
        "target_tower_id": target_id,
        "attacker_owner_id": attacker_id,
        "defender_owner_id": defender_id,
        "target_relation": "ENEMY",
        "proposed_units": force,
    }

    def matches(evidence, evidence_id):
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
        digest = hashlib.sha256(encoded).hexdigest()
        return evidence_id == "sha256:" + digest

    battle = candidate.get("battle_differential_evidence")
    server = candidate.get("server_acceptance_evidence")
    battle_valid = (
        matches(battle, candidate.get("battle_differential_evidence_id"))
        and battle.get("status") == "VALIDATED"
        and battle.get("support_status") == "MATCH"
        and battle.get("result") == "ATTACK_WIN"
        and battle.get("legality") == "LEGAL_STATIC_SHAPE"
        and battle.get("safety_margin") == "ROBUST_WIN"
        and battle.get("runtime_validated") is True)
    server_valid = (
        matches(server, candidate.get("server_acceptance_evidence_id"))
        and server.get("status") == "ACCEPTED"
        and server.get("server_accepted") is True
        and server.get("command_kind") == "DeployForce"
        and server.get("action_kind") == "ATTACK_ENEMY")
    return battle_valid and server_valid


def _attack_dispatch_candidate_ready(candidate: dict, match_id: str,
                                     cycle_id: int) -> bool:
    """接受靜態穩健預測；若聲稱已有執行期 proof，則必須完整重驗。

    首次攻擊的戰鬥差分與伺服器接受狀態只能在派送後取得，不能作為
    該次派送的前置條件。靜態路徑仍要求明確支援、合法形狀與穩健勝利；
    任何已附上的執行期 proof 都必須完整有效，否則拒絕候選。
    """
    if not isinstance(candidate, dict):
        return False
    common_prediction = (
        candidate.get("match_id") == match_id
        and candidate.get("cycle_id") == cycle_id
        and candidate.get("result") == "ATTACK_WIN"
        and candidate.get("legality") == "LEGAL_STATIC_SHAPE"
        and candidate.get("battle_supported") is True
        and candidate.get("safety_margin") == "ROBUST_WIN"
    )
    static_dispatch = (
        candidate.get("dispatch_safe_candidate") is True
        and candidate.get("static_support_status") == "SUPPORTED"
        and candidate.get("runtime_validation_required") is True
    )
    runtime_validated = (
        candidate.get("safe_attack_candidate") is True
        and candidate.get("battle_differential_validated") is True
        and candidate.get("server_acceptance_validated") is True
        and candidate.get("evaluation_status") == "SUPPORTED"
        and candidate.get("runtime_validation_required") is False
        and _attack_proof_provenance_matches(
            candidate, match_id, cycle_id)
    )
    proof_fields = (
        "battle_differential_evidence_id",
        "server_acceptance_evidence_id",
        "battle_differential_evidence",
        "server_acceptance_evidence",
    )
    proof_claimed = (
        candidate.get("battle_differential_validated") is True
        or candidate.get("server_acceptance_validated") is True
        or any(candidate.get(key) is not None for key in proof_fields)
    )
    if not common_prediction:
        return False
    if proof_claimed:
        return runtime_validated
    return static_dispatch


class LiveController:
    """常駐協調器。app 在 live 模式構造並以後台任務運行。"""

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.running = False
        self.cycle_count = 0
        self.last_cycle_at: float | None = None
        self.phase = "STARTING"
        self.cooldowns: dict = {}
        self.cycle_seq = 0
        self.journal = {"mode": "LIVE_NEUTRAL_EXPANSION", "sent_actions": 0,
                        "verified_moves": 0, "verified_expansions": 0,
                        "force_observed_dispatches": 0,
                        "unobserved_dispatches": 0,
                        "unknown_dispatch_observations": 0,
                        "failed_actions": 0, "consecutive_failures": 0,
                        "cycles": 0, "no_safe_proposals": 0,
                        "last_action": None, "last_verification": None,
                        "threat_state": {
                            "match_id": None, "cycle_id": None,
                            "status": "UNKNOWN", "freshness": "UNKNOWN",
                            "coverage": {"self_towers": 0, "scanned": 0,
                                         "complete": False},
                            "threats": []},
                        "multi_threat_evaluation": {
                            "match_id": None, "cycle_id": None,
                            "status": "UNKNOWN", "evaluations": []},
                        "defense_assessment": {
                            "match_id": None, "cycle_id": None,
                            "status": "UNKNOWN", "action": "ABSTAIN",
                            "reason": "defense-assessment-not-run"},
                        "pvp_arbitration": {
                            "action": "ABSTAIN", "evaluation_status": "UNKNOWN",
                            "reason": "arbitration-not-run"},
                        "attack_assessment": {
                            "match_id": None, "cycle_id": None,
                            "status": "UNKNOWN", "evaluations": [],
                            "execution": "NOT_ATTEMPTED"}}
        pending_dispatch = self._load_pending_dispatch()
        if pending_dispatch is not None:
            self.journal["pending_dispatch"] = pending_dispatch
        self._player_ids = PlayerIdRegistry()
        self._player_ids_match_id: str | None = None
        self._reservations = ReservationBoard()
        self._reservation_match_id: str | None = None
        self._venv_python = str(self.root / ".venv/Scripts/python.exe")

    @staticmethod
    def _force_snapshot_complete(snapshot: dict) -> bool:
        """只有同局且兩個集合完整時，空結果才可解讀為 NOT_FOUND。"""
        from kiomet_ai.force import MAX_PATH_LEN, _valid_tower_id
        from kiomet_ai.observe import UNIT_NAMES

        if (not isinstance(snapshot, dict) or snapshot.get("error")
                or not isinstance(snapshot.get("match_id"), str)
                or not snapshot["match_id"]):
            return False
        collections = snapshot.get("collections")
        if not isinstance(collections, dict):
            return False
        for role in ("inbound", "outbound"):
            collection = collections.get(role)
            if not isinstance(collection, dict):
                return False
            length = collection.get("length")
            entries = collection.get("entries")
            if (type(length) is not int or length < 0
                    or not isinstance(entries, list) or len(entries) != length):
                return False
            for entry in entries:
                if not isinstance(entry, dict):
                    return False
                path = entry.get("path")
                units = entry.get("units")
                if (not isinstance(path, (list, tuple))
                        or not 2 <= len(path) <= MAX_PATH_LEN
                        or any(type(tower_id) is not int
                               or not _valid_tower_id(tower_id)
                               for tower_id in path)
                        or len(set(path)) != len(path)
                        or path[-1] == path[-2]
                        or type(entry.get("ref")) is not int
                        or entry["ref"] <= 0
                        or type(entry.get("owner_id")) is not int
                        or entry["owner_id"] <= 0
                        or not isinstance(units, dict)
                        or set(units) != set(UNIT_NAMES)
                        or any(type(value) is not int or not 0 <= value <= 255
                               for value in units.values())
                        or not any(units.values())
                        or type(entry.get("speed_flag")) is not int
                        or entry["speed_flag"] not in (0, 1)
                        or type(entry.get("progress")) is not int
                        or not 0 <= entry["progress"] <= 255
                        or type(entry.get("endurance")) is not int
                        or not 0 <= entry["endurance"] <= 255):
                    return False
        return True

    @staticmethod
    def _empty_threat_state(match_id, cycle_id, *, status="UNKNOWN",
                            reason="observation-not-complete",
                            freshness="UNKNOWN", self_towers=0,
                            scanned=0):
        return {
            "match_id": match_id if isinstance(match_id, str) else None,
            "cycle_id": cycle_id if type(cycle_id) is int else None,
            "status": status,
            "reason": reason,
            "freshness": freshness,
            "coverage": {"self_towers": self_towers, "scanned": scanned,
                         "complete": False},
            "observed_at": None,
            "threats": [],
        }

    async def _observe_cycle_threat_state(self, match_id: str,
                                         cycle_id: int, states: list,
                                         by_id: dict, now: float) -> dict:
        """逐座讀取新鮮己方塔入站集合，保存同局、同週期唯讀威脅事實。"""
        from kiomet_ai.pvp_live import candidate_inbound_threats
        from kiomet_ai.force import threat_eta_seconds

        states = list(states) if isinstance(states, (list, tuple)) else []
        self_towers = [state for state in states
                       if getattr(state, "owner", None) == "SELF"]
        result = self._empty_threat_state(
            match_id, cycle_id, self_towers=len(self_towers))
        self.journal["threat_state"] = result

        if (not isinstance(match_id, str) or not match_id
                or type(cycle_id) is not int or cycle_id < 0
                or not isinstance(by_id, dict)
                or type(now) not in (int, float) or not math.isfinite(now)):
            result["reason"] = "cycle-identity-or-observation-invalid"
            return result

        # A requested/stale cycle may not borrow the browser's current match.
        game = getattr(self.browser, "game", {}) or {}
        active_match = ((game.get("match") or {}).get("id")
                        if isinstance(game, dict) else None)
        if game.get("state") != "IN_MATCH" or active_match != match_id:
            result["reason"] = "active-match-mismatch"
            result["freshness"] = "STALE"
            return result

        # Unknown ownership can hide an unscanned SELF tower, so it prevents CLEAR.
        ownership_complete = all(
            getattr(state, "owner", None) in
            ("SELF", "ALLY", "ENEMY", "NEUTRAL")
            for state in states)
        if not self_towers or len(self_towers) > 64:
            result["reason"] = ("no-self-towers" if not self_towers
                                else "self-tower-scan-bound-exceeded")
            return result

        eligible = []
        tower_coverage_complete = True
        stale_evidence = False
        failure_reasons = []
        if not ownership_complete:
            failure_reasons.append("tower-ownership-incomplete")
        for state in self_towers:
            tower_id = getattr(state, "tower_id", None)
            freshness_fn = getattr(state, "freshness", None)
            try:
                fresh = (callable(freshness_fn)
                         and freshness_fn(match_id, now) == "FRESH")
            except Exception:
                fresh = False
            if (type(tower_id) is not int or tower_id <= 0
                    or getattr(state, "match_id", None) != match_id
                    or not fresh
                    or type(getattr(state, "tower_ref", None)) is not int
                    or state.tower_ref <= 0
                    or by_id.get(tower_id) is not state):
                tower_coverage_complete = False
                if (not fresh
                        or getattr(state, "match_id", None) != match_id):
                    stale_evidence = True
                continue
            eligible.append(state)

        rows = []
        scanned = 0
        complete = ownership_complete and tower_coverage_complete
        if not tower_coverage_complete:
            failure_reasons.append("self-tower-state-stale-or-invalid")
        observed_at = []
        for target in eligible:
            try:
                snapshot = await self.snapshot_collections(target.tower_ref)
            except Exception as exc:
                complete = False
                failure_reasons.append(
                    f"snapshot-read-failed:{type(exc).__name__}")
                continue
            scanned += 1
            if (not isinstance(snapshot, dict)
                    or snapshot.get("match_id") != match_id
                    or not self._force_snapshot_complete(snapshot)):
                complete = False
                if (isinstance(snapshot, dict)
                        and snapshot.get("match_id") != match_id):
                    stale_evidence = True
                failure_reasons.append("snapshot-incomplete-or-cross-match")
                continue

            captured_at = snapshot.get("captured_at")
            if (type(captured_at) not in (int, float)
                    or not math.isfinite(captured_at)
                    or captured_at <= 0 or captured_at > now + 1.0
                    or now - captured_at > 30.0):
                complete = False
                if (type(captured_at) in (int, float)
                        and math.isfinite(captured_at)
                        and now - captured_at > 30.0):
                    stale_evidence = True
                failure_reasons.append("snapshot-time-unknown-or-stale")
                continue

            observation = candidate_inbound_threats(
                snapshot, target, by_id, match_id,
                self_id=self._player_ids.self_id(),
                player_ids=self._player_ids)
            if observation.get("status") == "UNKNOWN":
                complete = False
                failure_reasons.append(str(
                    observation.get("reason") or "inbound-observation-unknown"))
                continue
            observed_at.append(float(captured_at))
            if observation.get("status") == "CLEAR":
                continue
            if observation.get("status") != "OBSERVED_CANDIDATE":
                complete = False
                failure_reasons.append("inbound-observation-status-invalid")
                continue

            inbound = snapshot["collections"]["inbound"]["entries"]
            candidates = observation.get("threats")
            if not isinstance(candidates, list) or len(candidates) != len(inbound):
                complete = False
                failure_reasons.append("candidate-force-count-mismatch")
                continue
            for entry, candidate in zip(inbound, candidates):
                if not isinstance(entry, dict) or not isinstance(candidate, dict):
                    complete = False
                    failure_reasons.append("candidate-force-row-invalid")
                    continue
                force_id = entry.get("ref")
                if type(force_id) is not int or force_id <= 0:
                    complete = False
                    failure_reasons.append("source-force-identity-unknown")
                    continue
                ticks = candidate.get("eta_ticks")
                if type(ticks) is not int or ticks < 0:
                    ticks = None
                relation = candidate.get("owner_relation")
                if relation not in ("SELF", "ALLY", "ENEMY", "NEUTRAL"):
                    relation = "UNKNOWN"
                rows.append({
                    "match_id": match_id,
                    "cycle_id": cycle_id,
                    "source_force_id": force_id,
                    "owner_id": candidate.get("owner_id"),
                    "relation": relation,
                    "source_tower": candidate.get("source_tower_id"),
                    "target_tower": target.tower_id,
                    "units": dict(entry["units"]),
                    "eta_ticks": ticks,
                    "eta_seconds": (threat_eta_seconds(ticks)
                                    if ticks is not None else None),
                    "eta_status": ("CANDIDATE" if ticks is not None
                                   else "UNKNOWN"),
                    "confidence": "CANDIDATE",
                    "freshness": "FRESH",
                    "provenance": {
                        "source": "WASM_INBOUND_COLLECTION",
                        "collection": "inbound",
                        "snapshot_match_id": match_id,
                        "captured_at": float(captured_at),
                        "target_tower_ref": target.tower_ref,
                        "source_force_ref": force_id,
                        "identity_scope": "snapshot-only",
                    },
                })

        game_after = getattr(self.browser, "game", {}) or {}
        active_match_after = ((game_after.get("match") or {}).get("id")
                              if isinstance(game_after, dict) else None)
        if (not isinstance(game_after, dict)
                or game_after.get("state") != "IN_MATCH"
                or active_match_after != match_id):
            complete = False
            stale_evidence = True
            rows = []
            failure_reasons.append("active-match-changed-during-threat-scan")

        if scanned != len(eligible):
            complete = False
        result.update({
            "coverage": {"self_towers": len(self_towers),
                         "scanned": scanned, "complete": bool(complete)},
            "observed_at": min(observed_at) if observed_at else None,
            "threats": rows[:512],
            "freshness": ("FRESH" if complete else
                          "STALE" if stale_evidence else "UNKNOWN"),
        })
        if not complete:
            result["status"] = "UNKNOWN"
            result["reason"] = (failure_reasons[0] if failure_reasons
                                 else "tower-ownership-incomplete")
        elif rows:
            result["status"] = "OBSERVED_CANDIDATE"
            result["reason"] = "complete-same-match-inbound-observation"
        else:
            result["status"] = "CLEAR"
            result["reason"] = "complete-empty-inbound-across-self-towers"
        self.journal["threat_state"] = result
        return result

    @staticmethod
    def _tower_multi_threat_defenders(state) -> dict | None:
        """僅由完整 MANY 塔結構與已知 Ruler 旗標組出戰鬥輸入。"""
        from kiomet_ai.observe import UNIT_NAMES
        from kiomet_ai.pvp_live import ORDINARY_UNIT_NAMES

        counts = getattr(state, "unit_counts", None)
        ruler = getattr(state, "owner_ruler", None)
        if getattr(counts, "units_kind", None) != "MANY" or type(ruler) is not bool:
            return None
        ordinary = {name: getattr(counts, name.lower(), None)
                    for name in ORDINARY_UNIT_NAMES}
        if any(type(value) is not int or not 0 <= value <= 255
               for value in ordinary.values()):
            return None
        # MANY encodes exactly six ordinary tower slots; SINGLE is rejected above.
        # Ruler is separately observed by the tower flag, not inferred from counts.
        return {**ordinary, "Shell": 0, "Emp": 0, "Nuke": 0,
                "Ruler": int(ruler)}

    def _evaluate_cycle_multi_threat(self, match_id: str, cycle_id: int,
                                     states: list, by_id: dict,
                                     now: float) -> dict:
        """正式以同週期威脅清單逐塔呼叫多威脅序列評估器。"""
        from kiomet_ai.battle_mirror import CAPACITIES
        from kiomet_ai.pvp_live import evaluate_multi_threat

        def publish(status, reason, evaluations=None):
            value = {"match_id": match_id, "cycle_id": cycle_id,
                     "status": status, "reason": reason,
                     "evaluations": (evaluations or [])[:64]}
            self.journal["multi_threat_evaluation"] = value
            return value

        state = self.journal.get("threat_state")
        if (not isinstance(state, dict)
                or state.get("match_id") != match_id
                or state.get("cycle_id") != cycle_id
                or state.get("freshness") != "FRESH"
                or (state.get("coverage") or {}).get("complete") is not True):
            return publish("UNKNOWN", "current-cycle-threat-state-incomplete")
        game = getattr(self.browser, "game", {}) or {}
        active_match = ((game.get("match") or {}).get("id")
                        if isinstance(game, dict) else None)
        if (not isinstance(game, dict) or game.get("state") != "IN_MATCH"
                or active_match != match_id):
            return publish("UNKNOWN", "active-match-mismatch")
        if state.get("status") == "CLEAR":
            if state.get("threats") != []:
                return publish("UNKNOWN", "clear-state-has-threat-rows")
            return publish("CLEAR", "complete-current-cycle-no-inbound-threats")
        if state.get("status") != "OBSERVED_CANDIDATE":
            return publish("UNKNOWN", "threat-state-not-evaluable")

        rows = state.get("threats")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 512:
            return publish("UNKNOWN", "threat-list-incomplete")
        grouped = {}
        for row in rows:
            if (not isinstance(row, dict)
                    or row.get("match_id") != match_id
                    or row.get("cycle_id") != cycle_id
                    or row.get("freshness") != "FRESH"
                    or type(row.get("source_force_id")) is not int
                    or row["source_force_id"] <= 0
                    or type(row.get("source_tower")) is not int
                    or row["source_tower"] <= 0
                    or type(row.get("target_tower")) is not int
                    or row["target_tower"] <= 0):
                return publish("UNKNOWN", "threat-row-identity-or-freshness-invalid")
            if row.get("relation") in ("SELF", "ALLY"):
                # Known friendly inbound is not hostile. It is not credited as
                # extra defenders, so the battle estimate remains conservative.
                continue
            grouped.setdefault(row["target_tower"], []).append(row)

        if not grouped:
            return publish("SAFE", "no-enemy-inbound-threats")

        evaluations = []
        self_id = self._player_ids.self_id()
        for target_id in sorted(grouped):
            target = by_id.get(target_id)
            freshness_fn = getattr(target, "freshness", None)
            try:
                target_fresh = (callable(freshness_fn)
                                and freshness_fn(match_id, now) == "FRESH")
            except Exception:
                target_fresh = False
            if (target is None or getattr(target, "owner", None) != "SELF"
                    or getattr(target, "match_id", None) != match_id
                    or not target_fresh):
                return publish("UNKNOWN", "threat-target-not-fresh-self")

            evaluator_rows = []
            for row in grouped[target_id]:
                eta = row.get("eta_ticks")
                if (row.get("eta_status") != "CANDIDATE"
                        or type(eta) is not int or eta < 0):
                    eta = None
                evaluator_rows.append({
                    "force_identity": row["source_force_id"],
                    "source_tower_id": row["source_tower"],
                    "target_tower_id": row["target_tower"],
                    "owner_id": row.get("owner_id"),
                    "owner_relation": row.get("relation"),
                    "units": row.get("units"),
                    "eta_ticks": eta,
                })

            result = evaluate_multi_threat(
                self._tower_multi_threat_defenders(target), evaluator_rows,
                CAPACITIES, getattr(target, "tower_type", None),
                self_id=self_id, enemy_id=None)
            runtime_unvalidated = (
                result.get("runtime_validation_required") is True)
            evaluations.append({
                "target_tower_id": target_id,
                "status": ("UNKNOWN" if runtime_unvalidated else
                           result.get("result", "UNKNOWN")),
                "reason": ("battle-differential-not-validated"
                           if runtime_unvalidated else
                           result.get("reason", "evaluation-result-unknown")),
                "source_force_ids": [row["source_force_id"]
                                     for row in grouped[target_id]],
                "earliest_eta_ticks": min(
                    (row["eta_ticks"] for row in evaluator_rows
                     if type(row.get("eta_ticks")) is int), default=None),
                "result": result,
                "runtime_validation_required": runtime_unvalidated,
                "freshness": "FRESH",
            })

        statuses = [row["status"] for row in evaluations]
        overall = ("UNKNOWN" if "UNKNOWN" in statuses else
                   "UNSAFE" if "UNSAFE" in statuses else "SAFE")
        return publish(overall, "sequential-current-cycle-threat-evaluation",
                       evaluations)

    def _multi_threat_action_block(self, match_id=None,
                                   cycle_id=None) -> dict | None:
        """只接受同局、同週期、完整新鮮且 SAFE/CLEAR 的威脅掃描。"""
        evaluation = self.journal.get("multi_threat_evaluation") or {}
        threat_state = self.journal.get("threat_state") or {}
        game = getattr(self.browser, "game", {}) or {}
        active_match = ((game.get("match") or {}).get("id")
                        if isinstance(game, dict) else None)
        expected_match = match_id if isinstance(match_id, str) else active_match
        expected_cycle = (cycle_id if type(cycle_id) is int else
                          evaluation.get("cycle_id")
                          if isinstance(evaluation, dict) else None)
        coverage = (threat_state.get("coverage")
                    if isinstance(threat_state, dict) else None)
        if (isinstance(evaluation, dict)
                and evaluation.get("status") in ("UNKNOWN", "UNSAFE")):
            reason = "MULTI_THREAT_" + evaluation["status"]
        elif (not isinstance(game, dict)
              or game.get("state") != "IN_MATCH"
              or active_match != expected_match
              or not isinstance(evaluation, dict)
              or evaluation.get("match_id") != expected_match
              or evaluation.get("cycle_id") != expected_cycle
              or evaluation.get("status") not in ("CLEAR", "SAFE")
              or not isinstance(threat_state, dict)
              or threat_state.get("match_id") != expected_match
              or threat_state.get("cycle_id") != expected_cycle
              or threat_state.get("freshness") != "FRESH"
              or not isinstance(coverage, dict)
              or coverage.get("complete") is not True
              or threat_state.get("status") not in (
                  "CLEAR", "OBSERVED_CANDIDATE")):
            reason = "MULTI_THREAT_STALE_OR_INCOMPLETE"
        else:
            return None
        return {"reason": reason,
                "match_id": (evaluation.get("match_id")
                             if isinstance(evaluation, dict) else None),
                "cycle_id": (evaluation.get("cycle_id")
                             if isinstance(evaluation, dict) else None),
                "multi_threat_evaluation": evaluation}

    def _arbitrate_prepared_action(self, match_id: str, cycle_id: int,
                                  neutral_candidate: dict | None, *,
                                  prepared_reinforcement: dict | None = None,
                                  prepared_attack: dict | None = None,
                                  require_execution_evidence: bool = False
                                  ) -> dict:
        """最終派送前以同週期證據執行防守→攻擊→中立→棄權仲裁。"""
        from kiomet_ai.pvp import arbitrate_pvp_action
        from kiomet_ai.observe import UNIT_NAMES

        def abstain(reason):
            decision = {"action": "ABSTAIN", "evaluation_status": "UNKNOWN",
                        "reason": reason,
                        "state_trace": ["OBSERVE", "ASSESS_THREATS",
                                        "EVALUATE_DEFENSE", "ABSTAIN"]}
            self.journal["pvp_arbitration"] = decision
            return decision

        blocked = self._multi_threat_action_block(match_id, cycle_id)
        if blocked is not None:
            return abstain(blocked["reason"])
        defense = self.journal.get("defense_assessment") or {}
        attack = self.journal.get("attack_assessment") or {}
        if (not isinstance(defense, dict)
                or defense.get("match_id") != match_id
                or defense.get("cycle_id") != cycle_id
                or defense.get("status") != "SUPPORTED"):
            return abstain("defense-assessment-stale-or-unresolved")
        if (not isinstance(attack, dict)
                or attack.get("match_id") != match_id
                or attack.get("cycle_id") != cycle_id):
            return abstain("attack-assessment-stale-or-cross-cycle")

        reservation_action_id = (neutral_candidate.get("reservation_action_id")
                                 if isinstance(neutral_candidate, dict) else None)
        reserved_source = (self._reservations.holder(
            neutral_candidate.get("source_tower_id"))
            if isinstance(neutral_candidate, dict)
            and type(neutral_candidate.get("source_tower_id")) is int else None)
        reserved_target = (self._reservations.holder(
            neutral_candidate.get("target_tower_id"))
            if isinstance(neutral_candidate, dict)
            and type(neutral_candidate.get("target_tower_id")) is int else None)
        if (not isinstance(neutral_candidate, dict)
                or neutral_candidate.get("validated") is not True
                or neutral_candidate.get("match_id") != match_id
                or neutral_candidate.get("cycle_id") != cycle_id
                or type(neutral_candidate.get("source_tower_id")) is not int
                or neutral_candidate.get("source_tower_id") <= 0
                or type(neutral_candidate.get("target_tower_id")) is not int
                or neutral_candidate.get("target_tower_id") <= 0
                or neutral_candidate.get("source_tower_id")
                == neutral_candidate.get("target_tower_id")
                or neutral_candidate.get("preflight") != "READY"
                or neutral_candidate.get("source_safety") != "SAFE"
                or neutral_candidate.get("action_validity_token") != "OK"
                or neutral_candidate.get("reservation") != "HELD"
                or not isinstance(reservation_action_id, str)
                or not reservation_action_id
                or reserved_source != reservation_action_id
                or reserved_target != reservation_action_id):
            neutral_candidate = None

        defense_rows = defense.get("defense_evaluations", [])
        attack_rows = attack.get("evaluations", [])
        if not isinstance(attack_rows, list):
            attack_rows = []
        checked_attacks = []
        self_id = self._player_ids.self_id()
        for raw in attack_rows:
            if not isinstance(raw, dict):
                checked_attacks.append(raw)
                continue
            row = dict(raw)
            source_id = row.get("source_tower_id")
            target_id = row.get("target_tower_id")
            prepared_matches = (
                isinstance(prepared_attack, dict)
                and prepared_attack.get("action_kind") == "ATTACK_ENEMY"
                and prepared_attack.get("match_id") == match_id
                and prepared_attack.get("cycle_id") == cycle_id
                and prepared_attack.get("source_tower_id") == source_id
                and prepared_attack.get("target_tower_id") == target_id)
            if prepared_matches:
                row.update({
                    "source_safety": prepared_attack.get("source_safety"),
                    "source_safety_evidence": prepared_attack.get(
                        "source_safety_evidence"),
                    "proposed_units": prepared_attack.get("proposed_units"),
                    "action_validity_token": prepared_attack.get(
                        "action_validity_token"),
                    "validity_token_match_id": prepared_attack.get(
                        "validity_token_match_id"),
                    "validity_token_cycle_id": prepared_attack.get(
                        "validity_token_cycle_id"),
                    "reservation": prepared_attack.get("reservation"),
                    "reservation_action_id": prepared_attack.get(
                        "reservation_action_id"),
                })
            reservation_id = row.get("reservation_action_id")
            board = getattr(self, "_reservations", None)
            exact_reservation = (
                isinstance(board, ReservationBoard)
                and isinstance(reservation_id, str) and bool(reservation_id)
                and type(source_id) is int and type(target_id) is int
                and board.holder(source_id) == reservation_id
                and board.holder(target_id) == reservation_id)
            force = row.get("proposed_units")
            source_evidence = row.get("source_safety_evidence")
            valid_force = (
                isinstance(force, dict) and bool(force)
                and set(force) == set(UNIT_NAMES)
                and all(type(value) is int and 0 <= value <= 255
                        for value in force.values())
                and any(force.get(name, 0) for name in UNIT_NAMES[:6])
                and not any(force.get(name, 0)
                            for name in ("Shell", "Emp", "Nuke", "Ruler")))
            valid_source_evidence = (
                isinstance(source_evidence, dict)
                and source_evidence.get("result") == "SAFE"
                and source_evidence.get("match_id") == match_id
                and source_evidence.get("source_tower_id") == source_id
                and source_evidence.get("proposed_units") == force)
            validated_safe_attack = (
                _attack_dispatch_candidate_ready(row, match_id, cycle_id)
                and type(source_id) is int and source_id > 0
                and type(target_id) is int and target_id > 0
                and source_id != target_id
                and row.get("target_relation") == "ENEMY"
                and row.get("target_owner_confidence") == "HIGH"
                and type(row.get("attacker_owner_id")) is int
                and row.get("attacker_owner_id") == self_id
                and type(self_id) is int and self_id > 0
                and type(row.get("defender_owner_id")) is int
                and row["defender_owner_id"] > 0
                and row["defender_owner_id"] != self_id
                and row.get("source_safety") == "SAFE"
                and valid_source_evidence and valid_force
                and row.get("action_validity_token") == "OK"
                and row.get("validity_token_match_id") == match_id
                and row.get("validity_token_cycle_id") == cycle_id
                and row.get("reservation") == "HELD"
                and exact_reservation)
            if ((row.get("safe_attack_candidate") is True
                 or row.get("dispatch_safe_candidate") is True)
                    and not validated_safe_attack):
                row["safe_attack_candidate"] = False
                row["dispatch_safe_candidate"] = False
                row["controller_rejection_reason"] = (
                    "live-attack-dispatch-contract-incomplete")
            checked_attacks.append(row)
        decision = arbitrate_pvp_action(
            defense_evaluations=(defense_rows
                                 if isinstance(defense_rows, list) else []),
            attack_evaluations=checked_attacks,
            neutral_expansion_candidate=neutral_candidate)
        if (decision.get("action") == "REINFORCE_SELF"
                and require_execution_evidence):
            candidate = decision.get("candidate")
            prepared = prepared_reinforcement
            source_id = (prepared.get("source_tower_id")
                         if isinstance(prepared, dict) else None)
            target_id = (prepared.get("target_tower_id")
                         if isinstance(prepared, dict) else None)
            force = (prepared.get("full_deployable_force")
                     if isinstance(prepared, dict) else None)
            source_evidence = (prepared.get("source_safety_evidence")
                               if isinstance(prepared, dict) else None)
            reservation_id = (prepared.get("reservation_action_id")
                              if isinstance(prepared, dict) else None)
            board = getattr(self, "_reservations", None)
            exact_reservation = (
                isinstance(board, ReservationBoard)
                and isinstance(reservation_id, str) and bool(reservation_id)
                and type(source_id) is int and type(target_id) is int
                and board.holder(source_id) == reservation_id
                and board.holder(target_id) == reservation_id)
            force_valid = (
                isinstance(force, dict) and bool(force)
                and set(force) == set(UNIT_NAMES)
                and all(type(value) is int and 0 <= value <= 255
                        for value in force.values())
                and not any(force.get(name, 0)
                            for name in ("Shell", "Emp", "Nuke", "Ruler")))
            evidence_valid = (
                isinstance(source_evidence, dict)
                and source_evidence.get("result") == "SAFE"
                and source_evidence.get("match_id") == match_id
                and source_evidence.get("source_tower_id") == source_id
                and source_evidence.get("proposed_units") == force)
            execution_ready = (
                isinstance(candidate, dict)
                and isinstance(prepared, dict)
                and decision.get("evaluation_status") == "SUPPORTED"
                and decision.get("match_id", match_id) == match_id
                and decision.get("cycle_id", cycle_id) == cycle_id
                and type(source_id) is int and source_id > 0
                and type(target_id) is int and target_id > 0
                and source_id != target_id
                and force_valid
                and candidate.get("source_tower_id") == source_id
                and decision.get("target_tower_id") == target_id
                and candidate.get("full_deployable_force") == force
                and candidate.get("unit_count") == sum(force.values())
                and candidate.get("command_validated") is True
                and prepared.get("command_validated") is True
                and prepared.get("match_id") == match_id
                and prepared.get("cycle_id") == cycle_id
                and prepared.get("source_owner") == "SELF"
                and prepared.get("target_owner") == "SELF"
                and prepared.get("preflight") == "READY"
                and prepared.get("source_safety") == "SAFE"
                and evidence_valid
                and prepared.get("action_validity_token") == "OK"
                and prepared.get("validity_token_match_id") == match_id
                and prepared.get("validity_token_cycle_id") == cycle_id
                and prepared.get("reservation") == "HELD"
                and exact_reservation)
            if not execution_ready:
                decision = {
                    "action": "ABSTAIN",
                    "evaluation_status": "UNKNOWN",
                    "reason": "defense-execution-evidence-incomplete",
                    "state_trace": decision.get("state_trace", [])
                    + ["EXECUTION_GATES", "ABSTAIN"],
                }
        if (decision.get("action") == "ATTACK_ENEMY"
                and require_execution_evidence):
            candidate = decision.get("candidate")
            prepared = prepared_attack
            source_id = (prepared.get("source_tower_id")
                         if isinstance(prepared, dict) else None)
            target_id = (prepared.get("target_tower_id")
                         if isinstance(prepared, dict) else None)
            force = (prepared.get("proposed_units")
                     if isinstance(prepared, dict) else None)
            force_valid = (
                isinstance(force, dict) and bool(force)
                and set(force) == set(UNIT_NAMES)
                and all(type(value) is int and 0 <= value <= 255
                        for value in force.values())
                and any(force.get(name, 0) for name in UNIT_NAMES[:6])
                and not any(force.get(name, 0)
                            for name in ("Shell", "Emp", "Nuke", "Ruler")))
            source_evidence = (prepared.get("source_safety_evidence")
                               if isinstance(prepared, dict) else None)
            reservation_id = (prepared.get("reservation_action_id")
                              if isinstance(prepared, dict) else None)
            board = getattr(self, "_reservations", None)
            exact_reservation = (
                isinstance(board, ReservationBoard)
                and isinstance(reservation_id, str) and bool(reservation_id)
                and type(source_id) is int and type(target_id) is int
                and board.holder(source_id) == reservation_id
                and board.holder(target_id) == reservation_id)
            self_id = self._player_ids.self_id()
            execution_ready = (
                isinstance(candidate, dict)
                and isinstance(prepared, dict)
                and decision.get("evaluation_status") in (
                    "SUPPORTED", "SUPPORTED_STATIC")
                and _attack_dispatch_candidate_ready(
                    candidate, match_id, cycle_id)
                and type(source_id) is int and source_id > 0
                and type(target_id) is int and target_id > 0
                and source_id != target_id
                and candidate.get("source_tower_id") == source_id
                and candidate.get("target_tower_id") == target_id
                and candidate.get("match_id") == match_id
                and candidate.get("cycle_id") == cycle_id
                and candidate.get("target_relation") == "ENEMY"
                and candidate.get("target_owner_confidence") == "HIGH"
                and candidate.get("attacker_owner_id") == self_id
                and candidate.get("defender_owner_id") ==
                prepared.get("defender_owner_id")
                and type(candidate.get("defender_owner_id")) is int
                and candidate["defender_owner_id"] > 0
                and candidate["defender_owner_id"] != self_id
                and force_valid
                and force == candidate.get("proposed_units")
                and isinstance(source_evidence, dict)
                and source_evidence.get("result") == "SAFE"
                and source_evidence.get("match_id") == match_id
                and source_evidence.get("source_tower_id") == source_id
                and source_evidence.get("proposed_units") == force
                and prepared.get("action_kind") == "ATTACK_ENEMY"
                and prepared.get("source_owner") == "SELF"
                and prepared.get("target_owner") == "ENEMY"
                and prepared.get("preflight") == "READY"
                and prepared.get("source_safety") == "SAFE"
                and prepared.get("action_validity_token") == "OK"
                and prepared.get("validity_token_match_id") == match_id
                and prepared.get("validity_token_cycle_id") == cycle_id
                and prepared.get("reservation") == "HELD"
                and exact_reservation
                and candidate.get("result") == "ATTACK_WIN"
                and candidate.get("legality") == "LEGAL_STATIC_SHAPE"
                and candidate.get("battle_supported") is True
                and candidate.get("safety_margin") == "ROBUST_WIN")
            if not execution_ready:
                decision = {
                    **decision,
                    "execution_ready": False,
                    "execution_rejection_reason": (
                        "attack-execution-evidence-incomplete"),
                    "state_trace": decision.get("state_trace", [])
                    + ["EXECUTION_GATES", "BLOCK_DISPATCH"],
                }
            else:
                decision = {**decision, "execution_ready": True}
        decision = {**decision, "match_id": match_id,
                    "cycle_id": cycle_id,
                    "selected_action_executed": False}
        self.journal["pvp_arbitration"] = decision
        return decision

    async def _evaluate_cycle_defense(self, match_id: str, cycle_id: int,
                                      states: list, by_id: dict,
                                      now: float) -> dict:
        """把序列威脅結果、來源安全與 ETA 證據送入防守評估及仲裁。"""
        from kiomet_ai.force import ForceUnits, eta_ticks, unit_speed
        from kiomet_ai.observe import UNIT_NAMES
        from kiomet_ai.pvp import arbitrate_pvp_action, evaluate_defense

        multi = self.journal.get("multi_threat_evaluation") or {}
        threat_state = self.journal.get("threat_state") or {}
        defense_rows = []
        source_gates = []
        source_snapshot_checks = 0
        source_scan_truncated = False
        evaluation_rows = (multi.get("evaluations")
                           if isinstance(multi, dict) else None)
        if not isinstance(evaluation_rows, list):
            evaluation_rows = []

        game = getattr(self.browser, "game", {}) or {}
        active_match = ((game.get("match") or {}).get("id")
                        if isinstance(game, dict) else None)
        current_evidence = (
            isinstance(game, dict) and game.get("state") == "IN_MATCH"
            and active_match == match_id
            and isinstance(multi, dict)
            and multi.get("match_id") == match_id
            and multi.get("cycle_id") == cycle_id
            and multi.get("status") in ("CLEAR", "SAFE", "UNSAFE", "UNKNOWN")
            and isinstance(threat_state, dict)
            and threat_state.get("match_id") == match_id
            and threat_state.get("cycle_id") == cycle_id
            and threat_state.get("status") in ("CLEAR", "OBSERVED_CANDIDATE")
            and threat_state.get("freshness") == "FRESH"
            and (threat_state.get("coverage") or {}).get("complete") is True
        )
        if not current_evidence:
            defense_rows.append({
                "support_status": "UNKNOWN", "tower_lost": None,
                "enemy_eta": None, "target_tower_id": None,
                "minimum_sufficient_reinforcement": None,
                "reinforcement_command_validated": False,
                "reason": "current-match-cycle-threat-evidence-required",
            })
            arbitration = arbitrate_pvp_action(
                defense_evaluations=defense_rows,
                attack_evaluations=[], neutral_expansion_candidate=None)
            published = {
                "match_id": match_id, "cycle_id": cycle_id,
                "status": arbitration.get("evaluation_status", "UNKNOWN"),
                "action": "ABSTAIN",
                "reason": "current-match-cycle-threat-evidence-required",
                "defense_evaluations": defense_rows,
                "source_gates": [], "source_scan_truncated": False,
                "arbitration": arbitration,
                "execution_gates": {
                    "reservation": "NOT_RESERVED",
                    "action_validity_token": "NOT_BUILT",
                    "ui_dispatch": "NOT_ATTEMPTED",
                },
            }
            self.journal["defense_assessment"] = published
            self.journal["pvp_arbitration"] = arbitration
            return published

        for multi_row in evaluation_rows[:64]:
            if not isinstance(multi_row, dict):
                continue
            target_id = multi_row.get("target_tower_id")
            target = by_id.get(target_id)
            raw_result = multi_row.get("result")
            first_loss = (raw_result.get("first_loss")
                          if isinstance(raw_result, dict) else None)
            if not isinstance(first_loss, dict):
                if multi_row.get("status") != "SAFE":
                    defense_rows.append({
                        "support_status": "UNKNOWN", "tower_lost": None,
                        "enemy_eta": None, "target_tower_id": target_id,
                        "minimum_sufficient_reinforcement": None,
                        "reinforcement_command_validated": False,
                        "reason": multi_row.get("reason",
                                                "threat-sequence-unresolved"),
                    })
                continue

            threat = first_loss.get("threat")
            battle_case = first_loss.get("battle_case")
            if not isinstance(threat, dict) or not isinstance(battle_case, dict):
                defense_rows.append({
                    "support_status": "UNKNOWN", "tower_lost": None,
                    "enemy_eta": None, "target_tower_id": target_id,
                    "minimum_sufficient_reinforcement": None,
                    "reinforcement_command_validated": False,
                    "reason": "first-loss-evidence-incomplete",
                })
                continue

            enemy_eta = threat.get("eta_ticks")
            incoming_source_id = threat.get("source_tower_id")
            incoming_target_id = threat.get("target_tower_id")
            incoming_owner_id = threat.get("owner_id")
            incoming_identity_valid = (
                type(incoming_owner_id) is int and incoming_owner_id > 0
                and threat.get("owner_relation") == "ENEMY"
                and type(incoming_source_id) is int
                and incoming_source_id > 0
                and type(incoming_target_id) is int
                and incoming_target_id > 0
                and incoming_target_id == target_id
                and type(enemy_eta) is int and enemy_eta >= 0
            )
            incoming_source = by_id.get(incoming_source_id)
            source_fresh = False
            target_fresh = False
            try:
                source_fresh = (
                    incoming_source is not None
                    and incoming_source.freshness(match_id, now) == "FRESH")
                target_fresh = (
                    target is not None and target.freshness(match_id, now)
                    == "FRESH")
            except Exception:
                pass
            path_valid = (
                incoming_identity_valid and source_fresh and target_fresh
                and getattr(incoming_source, "owner", None) == "ENEMY"
                and getattr(target, "owner", None) == "SELF"
                and target_id in getattr(incoming_source, "neighbors", ())
                and incoming_source_id in getattr(target, "neighbors", ()))
            world_fresh = (
                source_fresh and target_fresh
                and all(type(value) in (int, float) and math.isfinite(value)
                        for value in (
                            getattr(incoming_source, "world_x", None),
                            getattr(incoming_source, "world_y", None),
                            getattr(target, "world_x", None),
                            getattr(target, "world_y", None))))

            reinforcement_candidates = []
            source_states = (list(states)[:64]
                             if isinstance(states, (list, tuple)) else [])
            if isinstance(states, (list, tuple)) and len(states) > 64:
                source_scan_truncated = True
            for source in source_states:
                source_id = getattr(source, "tower_id", None)
                if (source_id == target_id
                        or getattr(source, "owner", None) != "SELF"
                        or getattr(source, "match_id", None) != match_id):
                    continue
                try:
                    source_is_fresh = source.freshness(match_id, now) == "FRESH"
                except Exception:
                    source_is_fresh = False
                if not source_is_fresh:
                    source_gates.append({"source_tower_id": source_id,
                                         "target_tower_id": target_id,
                                         "status": "UNKNOWN",
                                         "reason": "source-state-stale"})
                    continue
                force_obj = getattr(source, "deployable_force", None)
                force = getattr(force_obj, "counts", None)
                force_confidence = getattr(
                    source, "deployable_force_confidence", "UNKNOWN")
                if (force_confidence not in ("DERIVED", "VERIFIED")
                        or not isinstance(force, dict)
                        or set(force) != set(UNIT_NAMES)
                        or any(type(value) is not int or not 0 <= value <= 255
                               for value in force.values())
                        or any(force.get(name, 0)
                               for name in ("Shell", "Emp", "Nuke", "Ruler"))
                        or not any(force.get(name, 0) for name in UNIT_NAMES[:6])):
                    source_gates.append({"source_tower_id": source_id,
                                         "target_tower_id": target_id,
                                         "status": "UNKNOWN",
                                         "reason": "full-ordinary-force-unknown"})
                    continue
                adjacent = (target_id in getattr(source, "neighbors", ())
                            and source_id in getattr(target, "neighbors", ()))
                if not adjacent:
                    source_gates.append({"source_tower_id": source_id,
                                         "target_tower_id": target_id,
                                         "status": "REJECTED",
                                         "reason": "direct-self-path-unverified"})
                    continue

                eta = None
                try:
                    sx, sy = source.world_x, source.world_y
                    tx, ty = target.world_x, target.world_y
                    if all(type(value) in (int, float)
                           and math.isfinite(value)
                           for value in (sx, sy, tx, ty)):
                        speed = unit_speed(ForceUnits(
                            tag=0, counts=force, status="CANDIDATE"))
                        eta = eta_ticks(0, speed,
                                        math.hypot(tx - sx, ty - sy), 0)
                except (AttributeError, OverflowError, TypeError, ValueError):
                    eta = None

                gate = {"source_tower_id": source_id,
                        "target_tower_id": target_id,
                        "eta_ticks": eta,
                        "eta_confidence": "CANDIDATE" if eta is not None else "UNKNOWN",
                        "source_safety": "NOT_CHECKED",
                        "status": "UNKNOWN"}
                if (type(eta) is int and type(enemy_eta) is int
                        and eta < enemy_eta):
                    if source_snapshot_checks >= 16:
                        source_scan_truncated = True
                        gate["status"] = "UNKNOWN_SOURCE_SNAPSHOT_BUDGET"
                        gate["source_safety"] = "NOT_CHECKED_BUDGET"
                        source_gates.append(gate)
                        continue
                    source_snapshot_checks += 1
                    try:
                        source_snapshot = await self.snapshot_collections(
                            source.tower_ref)
                        safety = self.evaluate_live_source_safety(
                            match_id, source, source_snapshot, force,
                            tower_states_by_id=by_id)
                    except Exception as exc:
                        safety = {"result": "UNKNOWN",
                                  "reason": f"source-snapshot-failed:{type(exc).__name__}"}
                    gate["source_safety"] = safety.get("result", "UNKNOWN")
                    gate["source_safety_reason"] = safety.get("reason")
                    if safety.get("result") == "SAFE":
                        gate["status"] = "CANDIDATE_MERGE_EVIDENCE_REQUIRED"
                        reinforcement_candidates.append({
                            "reinforcement_eta": eta,
                            "post_merge_snapshot_exact": False,
                            "post_merge_battle_case": None,
                            "source_tower_id": source_id,
                            "full_deployable_force": dict(force),
                            "legality_evidence": {
                                "source_is_self": True,
                                "source_has_full_mobile_force": True,
                                "target_is_self": True,
                                "path_valid": True,
                                "world_fresh": world_fresh,
                                "target_owner_fresh": target_fresh,
                                "command_kind": "DeployForce",
                                "server_acceptance_validated": False,
                            },
                        })
                    else:
                        gate["status"] = "ABSTAIN_SOURCE_SAFETY"
                elif (type(eta) is int and type(enemy_eta) is int
                      and eta == enemy_eta):
                    gate["status"] = "ABSTAIN_SAME_TICK"
                    gate["source_safety"] = "NOT_CHECKED_SAME_TICK"
                elif type(eta) is int and type(enemy_eta) is int:
                    gate["status"] = "REINFORCEMENT_TOO_LATE"
                    gate["source_safety"] = "NOT_CHECKED_TOO_LATE"
                else:
                    gate["status"] = "ABSTAIN_ETA_UNKNOWN"
                source_gates.append(gate)

            assessment = evaluate_defense({
                "enemy_eta": enemy_eta,
                "incoming_path_valid": path_valid,
                "world_fresh": world_fresh,
                "target_owner_fresh": target_fresh,
                "battle_case": battle_case,
                "reinforcement_candidates": reinforcement_candidates,
            })
            defense_row = {
                "support_status": assessment.get("support_status", "UNKNOWN"),
                "tower_lost": assessment.get("tower_lost"),
                "enemy_eta": assessment.get("enemy_eta", enemy_eta),
                "target_tower_id": target_id,
                "minimum_sufficient_reinforcement": assessment.get(
                    "minimum_sufficient_reinforcement"),
                "reinforcement_command_validated": assessment.get(
                    "reinforcement_command_validated") is True,
                "reason": assessment.get("unsupported_reason")
                or assessment.get("support_reason")
                or assessment.get("rescue_requirement_status"),
            }
            defense_rows.append(defense_row)
            multi_row["defense_assessment"] = assessment

        if (multi.get("status") in ("UNKNOWN", "UNSAFE")
                and not defense_rows):
            defense_rows.append({
                "support_status": "UNKNOWN", "tower_lost": None,
                "enemy_eta": None, "target_tower_id": None,
                "minimum_sufficient_reinforcement": None,
                "reinforcement_command_validated": False,
                "reason": multi.get("reason",
                                    "threat-sequence-unresolved"),
            })

        arbitration = arbitrate_pvp_action(
            defense_evaluations=defense_rows,
            attack_evaluations=[],
            neutral_expansion_candidate=None)
        published = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": arbitration.get("evaluation_status", "UNKNOWN"),
            "action": arbitration.get("action", "ABSTAIN"),
            "reason": arbitration.get("reason", "arbitration-result-unknown"),
            "defense_evaluations": defense_rows[:64],
            "source_gates": source_gates[:128],
            "source_snapshot_checks": source_snapshot_checks,
            "source_scan_truncated": source_scan_truncated,
            "arbitration": arbitration,
            "execution_gates": {
                "reservation": "NOT_RESERVED_NO_VALIDATED_RESCUE",
                "action_validity_token": "NOT_BUILT_NO_VALIDATED_RESCUE",
                "ui_dispatch": "NOT_ATTEMPTED",
            },
        }
        self.journal["defense_assessment"] = published
        self.journal["pvp_arbitration"] = arbitration
        return published

    def _verified_enemy_tower_owner_id(self, match_id: str, target,
                                       snapshot: dict, now: float) -> dict:
        """從新鮮敵塔 outbound（出站）部隊綁定塔主 ID；不以唯一已知敵人猜測。"""
        if (target is None or getattr(target, "owner", None) != "ENEMY"
                or getattr(target, "owner_confidence", None) != "HIGH"
                or getattr(target, "match_id", None) != match_id):
            return {"owner_id": None, "status": "UNKNOWN",
                    "reason": "enemy-owner-relation-not-high-confidence"}
        try:
            if target.freshness(match_id, now) != "FRESH":
                return {"owner_id": None, "status": "UNKNOWN",
                        "reason": "enemy-target-state-stale"}
        except Exception:
            return {"owner_id": None, "status": "UNKNOWN",
                    "reason": "enemy-target-freshness-unknown"}
        captured_at = (snapshot.get("captured_at")
                       if isinstance(snapshot, dict) else None)
        if (not self._force_snapshot_complete(snapshot)
                or snapshot.get("match_id") != match_id
                or snapshot.get("tower_ref") != getattr(target, "tower_ref", None)
                or type(captured_at) not in (int, float)
                or not math.isfinite(captured_at) or captured_at <= 0
                or captured_at > now + 1.0 or now - captured_at > 30.0):
            return {"owner_id": None, "status": "UNKNOWN",
                    "reason": "enemy-owner-snapshot-incomplete-or-stale"}
        outbound = ((snapshot.get("collections") or {}).get("outbound") or {})
        entries = outbound.get("entries")
        if not isinstance(entries, list) or not entries:
            return {"owner_id": None, "status": "UNKNOWN",
                    "reason": "enemy-target-has-no-owner-bound-outbound-force"}
        owner_ids = set()
        for entry in entries:
            path = entry.get("path") if isinstance(entry, dict) else None
            owner_id = entry.get("owner_id") if isinstance(entry, dict) else None
            if (not isinstance(path, (list, tuple)) or len(path) < 2
                    or path[-1] != getattr(target, "tower_id", None)
                    or type(owner_id) is not int or owner_id <= 0):
                return {"owner_id": None, "status": "UNKNOWN",
                        "reason": "enemy-outbound-owner-evidence-invalid"}
            owner_ids.add(owner_id)
        if len(owner_ids) != 1:
            return {"owner_id": None, "status": "UNKNOWN",
                    "reason": "enemy-target-owner-id-ambiguous"}
        owner_id = next(iter(owner_ids))
        if owner_id == self._player_ids.self_id():
            return {"owner_id": None, "status": "UNKNOWN",
                    "reason": "enemy-target-owner-conflicts-with-self-id"}
        known_relations = [relation for relation in
                           ("SELF", "ALLY", "ENEMY", "NEUTRAL")
                           if self._player_ids.known_id(relation, owner_id)]
        if known_relations and known_relations != ["ENEMY"]:
            return {"owner_id": None, "status": "UNKNOWN",
                    "reason": "enemy-target-owner-relation-conflicts"}
        self._player_ids.observe("ENEMY", owner_id)
        return {"owner_id": owner_id, "status": "VERIFIED",
                "reason": "fresh-enemy-tower-outbound-owner-id"}

    async def _evaluate_cycle_attack_candidates(
            self, match_id: str, cycle_id: int, states, by_id: dict,
            anchor: dict, now: float) -> dict:
        """評估新鮮 SELF→ENEMY 鄰塔；缺少正式差分／接受證據就不升為安全候選。"""
        from kiomet_ai.pvp import arbitrate_pvp_action
        from kiomet_ai.pvp_live import evaluate_attack_candidate

        threat_state = self.journal.get("threat_state") or {}
        multi = self.journal.get("multi_threat_evaluation") or {}
        defense = self.journal.get("defense_assessment") or {}
        rows = []
        source_snapshot_cache = {}
        target_owner_cache = {}
        snapshot_reads = 0
        snapshot_budget = 16
        unclassified_adjacent_targets = []
        screen_map = None
        canvas = None
        current_evidence = (
            isinstance(threat_state, dict)
            and threat_state.get("match_id") == match_id
            and threat_state.get("cycle_id") == cycle_id
            and threat_state.get("freshness") == "FRESH"
            and threat_state.get("status") in ("CLEAR", "OBSERVED_CANDIDATE")
            and (threat_state.get("coverage") or {}).get("complete") is True
            and isinstance(multi, dict)
            and multi.get("match_id") == match_id
            and multi.get("cycle_id") == cycle_id
            and multi.get("status") in ("CLEAR", "SAFE")
            and isinstance(defense, dict)
            and defense.get("match_id") == match_id
            and defense.get("cycle_id") == cycle_id
            and defense.get("status") == "SUPPORTED"
            and defense.get("action") == "ABSTAIN"
        )
        if not current_evidence:
            result = {
                "match_id": match_id, "cycle_id": cycle_id,
                "status": "UNKNOWN",
                "reason": "current-threat-and-defense-evidence-required",
                "evaluations": [], "unclassified_adjacent_targets": [],
                "snapshot_reads": 0, "snapshot_budget": snapshot_budget,
                "execution": "NOT_ATTEMPTED",
            }
            self.journal["attack_assessment"] = result
            return result

        game = getattr(self.browser, "game", {}) or {}
        active_match = ((game.get("match") or {}).get("id")
                        if isinstance(game, dict) else None)
        self_id = self._player_ids.self_id()
        if (not isinstance(game, dict) or game.get("state") != "IN_MATCH"
                or active_match != match_id or self_id is None):
            result = {
                "match_id": match_id, "cycle_id": cycle_id,
                "status": "UNKNOWN",
                "reason": "current-match-changed-or-self-id-unknown",
                "evaluations": [], "unclassified_adjacent_targets": [],
                "snapshot_reads": 0, "snapshot_budget": snapshot_budget,
                "execution": "NOT_ATTEMPTED",
            }
            self.journal["attack_assessment"] = result
            return result

        self_states = [state for state in (states if isinstance(
            states, (list, tuple)) else [])
            if getattr(state, "owner", None) == "SELF"]
        enemy_states = [state for state in (states if isinstance(
            states, (list, tuple)) else [])
            if getattr(state, "owner", None) == "ENEMY"]
        for source in self_states[:64]:
            if getattr(source, "owner_confidence", None) != "HIGH":
                for target_id in getattr(source, "neighbors", ()):
                    target = by_id.get(target_id)
                    if target is not None and getattr(target, "owner", None) in (
                            "ENEMY", "UNKNOWN", None):
                        unclassified_adjacent_targets.append({
                            "source_tower_id": getattr(source, "tower_id", None),
                            "target_tower_id": target_id,
                            "relation": getattr(target, "owner", None)
                            or "UNKNOWN",
                            "reason": "source-owner-confidence-not-high",
                        })
                continue
            try:
                source_fresh = (source.freshness(match_id, now) == "FRESH")
            except Exception:
                source_fresh = False
            if not source_fresh:
                continue
            for target_id in getattr(source, "neighbors", ()):
                target = by_id.get(target_id)
                if target is None or getattr(target, "owner", None) not in (
                        "ENEMY", "UNKNOWN", None):
                    continue
                if getattr(target, "owner", None) != "ENEMY":
                    unclassified_adjacent_targets.append({
                        "source_tower_id": getattr(source, "tower_id", None),
                        "target_tower_id": target_id,
                        "relation": "UNKNOWN",
                        "reason": "adjacent-tower-owner-relation-unknown",
                    })
                    continue
                if (type(getattr(target, "tower_id", None)) is not int
                        or target.tower_id <= 0
                        or source.tower_id not in getattr(target, "neighbors", ())):
                    continue
                try:
                    target_fresh = (target.freshness(match_id, now) == "FRESH")
                except Exception:
                    target_fresh = False
                if not target_fresh:
                    rows.append({
                        "source_tower_id": source.tower_id,
                        "target_tower_id": target.tower_id,
                        "result": "UNKNOWN",
                        "reason": "enemy-target-state-stale",
                        "safe_attack_candidate": False,
                    })
                    continue
                if getattr(target, "owner_confidence", None) != "HIGH":
                    rows.append({
                        "source_tower_id": source.tower_id,
                        "target_tower_id": target.tower_id,
                        "result": "UNKNOWN",
                        "reason": "enemy-owner-confidence-not-high",
                        "safe_attack_candidate": False,
                    })
                    continue
                if snapshot_reads >= snapshot_budget:
                    rows.append({
                        "source_tower_id": source.tower_id,
                        "target_tower_id": target.tower_id,
                        "result": "UNKNOWN",
                        "reason": "attack-snapshot-budget-exhausted",
                        "safe_attack_candidate": False,
                    })
                    continue

                if target.tower_id not in target_owner_cache:
                    snapshot_reads += 1
                    try:
                        target_snapshot = await self.snapshot_collections(
                            target.tower_ref)
                        target_owner_cache[target.tower_id] = (
                            self._verified_enemy_tower_owner_id(
                                match_id, target, target_snapshot, now))
                    except Exception as exc:
                        target_owner_cache[target.tower_id] = {
                            "owner_id": None, "status": "UNKNOWN",
                            "reason": f"enemy-owner-snapshot-failed:{type(exc).__name__}"}
                target_owner = target_owner_cache[target.tower_id]
                defender_owner_id = target_owner.get("owner_id")
                if defender_owner_id is None:
                    rows.append({
                        "source_tower_id": source.tower_id,
                        "target_tower_id": target.tower_id,
                        "result": "UNKNOWN",
                        "reason": target_owner.get("reason",
                                                   "enemy-owner-id-unknown"),
                        "safe_attack_candidate": False,
                    })
                    continue

                source_id = source.tower_id
                if source_id not in source_snapshot_cache:
                    if snapshot_reads >= snapshot_budget:
                        source_snapshot_cache[source_id] = None
                    else:
                        snapshot_reads += 1
                        try:
                            source_snapshot_cache[source_id] = (
                                await self.snapshot_collections(source.tower_ref))
                        except Exception:
                            source_snapshot_cache[source_id] = None
                snapshot = source_snapshot_cache[source_id]
                if snapshot is None:
                    safety = {"result": "UNKNOWN",
                              "reason": "source-snapshot-budget-or-read-failed"}
                else:
                    try:
                        safety = self.evaluate_live_source_safety(
                            match_id, source, snapshot,
                            getattr(getattr(source, "deployable_force", None),
                                    "counts", None),
                            tower_states_by_id=by_id)
                    except Exception as exc:
                        safety = {"result": "UNKNOWN",
                                  "reason": f"source-safety-failed:{type(exc).__name__}"}
                force_obj = getattr(source, "deployable_force", None)
                force = getattr(force_obj, "counts", None)
                safety_evidence = {
                    **(safety if isinstance(safety, dict) else {}),
                    "match_id": match_id,
                    "source_tower_id": source_id,
                    "proposed_units": dict(force) if isinstance(force, dict)
                    else None,
                }

                token_status = "NOT_CHECKED_SOURCE_SAFETY"
                reservation_status = "NOT_CHECKED_SOURCE_SAFETY"
                if safety_evidence.get("result") == "SAFE":
                    if screen_map is None:
                        towers = anchor.get("towers") if isinstance(anchor, dict) else None
                        try:
                            screen_map, canvas = await self.fresh_screen_map(
                                towers if isinstance(towers, list) else [])
                        except Exception:
                            screen_map, canvas = {}, None
                    if (isinstance(screen_map, dict)
                            and source_id in screen_map
                            and target.tower_id in screen_map
                            and isinstance(force, dict)):
                        _token, token_status = self._build_dispatch_token(
                            match_id, cycle_id, source, target, canvas, force)
                    else:
                        token_status = "STALE_PROPOSAL:screen-map-unknown"
                    board = getattr(self, "_reservations", None)
                    if (isinstance(board, ReservationBoard)
                            and board.holder(source_id) is None
                            and board.holder(target.tower_id) is None):
                        reservation_status = "AVAILABLE_NOT_HELD"
                    else:
                        reservation_status = "RESOURCE_RESERVED"

                # No live battle differential or server-accepted attack evidence
                # currently exists. Never synthesize either proof from a model.
                candidate = evaluate_attack_candidate(
                    source, target, match_id, self_id, self_id,
                    defender_owner_id, getattr(source, "owner_ruler", None),
                    getattr(target, "owner_ruler", None),
                    source_safety_evidence=safety_evidence,
                    battle_differential_validated=False,
                    server_acceptance_validated=False, now=now)
                candidate["action_validity_token"] = token_status
                candidate["reservation"] = reservation_status
                candidate["server_acceptance_validated"] = False
                candidate["battle_differential_validated"] = False
                candidate["match_id"] = match_id
                candidate["cycle_id"] = cycle_id
                candidate["attacker_owner_id"] = self_id
                candidate["defender_owner_id"] = defender_owner_id
                candidate["target_relation"] = "ENEMY"
                candidate["target_owner_confidence"] = getattr(
                    target, "owner_confidence", "UNKNOWN")
                candidate["source_safety"] = safety_evidence.get("result")
                candidate["source_safety_evidence"] = safety_evidence
                candidate["proposed_units"] = (
                    dict(force) if isinstance(force, dict) else None)
                candidate["validity_token_match_id"] = match_id
                candidate["validity_token_cycle_id"] = cycle_id
                candidate["reservation_action_id"] = None
                candidate["battle_differential_evidence_id"] = None
                candidate["server_acceptance_evidence_id"] = None
                candidate["execution"] = "NOT_ATTEMPTED"
                if (token_status != "OK"
                        or reservation_status != "AVAILABLE_NOT_HELD"):
                    candidate["safe_attack_candidate"] = False
                    candidate["dispatch_safe_candidate"] = False
                    if candidate.get("unsupported_reason") is None:
                        candidate["unsupported_reason"] = (
                            "action token or reservation gate is not ready")
                rows.append(candidate)
                if len(rows) >= 64:
                    break
            if len(rows) >= 64:
                break

        defense_rows = defense.get("defense_evaluations", [])
        if not isinstance(defense_rows, list):
            defense_rows = []
        arbitration = arbitrate_pvp_action(
            defense_evaluations=defense_rows,
            attack_evaluations=rows,
            neutral_expansion_candidate=None)
        status = ("UNKNOWN" if not current_evidence else
                  "OBSERVED_CANDIDATE" if rows else
                  "NO_CONFIDENT_ENEMY_TARGET")
        result = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": status,
            "reason": ("current-match-changed-or-self-id-unknown"
                       if not current_evidence else
                       "no-confident-enemy-targets"
                       if not rows else
                       "safe-attack-requires-unavailable-runtime-proof"),
            "evaluations": rows[:64],
            "unclassified_adjacent_targets": unclassified_adjacent_targets[:64],
            "snapshot_reads": snapshot_reads,
            "snapshot_budget": snapshot_budget,
            "arbitration": arbitration,
            "execution": "NOT_ATTEMPTED_P0D_ASSESSMENT_ONLY",
        }
        self.journal["attack_assessment"] = result
        self.journal["pvp_arbitration"] = arbitration
        return result

    @staticmethod
    def _dispatch_observation_status(source_match: str,
                                     target_match: str) -> str:
        """UI 送出、部隊未觀察與雙端驗證是不同狀態。"""
        if (source_match == "FORCE_MATCH_VERIFIED"
                and target_match == "FORCE_MATCH_VERIFIED"):
            return "FORCE_OBSERVED"
        if (source_match == "FORCE_MATCH_NOT_FOUND"
                and target_match == "FORCE_MATCH_NOT_FOUND"):
            return "DISPATCH_NOT_OBSERVED"
        return "UNKNOWN"

    def _record_dispatch_observation(self, action_id: str, match_id: str,
                                     source_match: str,
                                     target_match: str) -> str:
        status = self._dispatch_observation_status(source_match, target_match)
        self.journal["last_dispatch_observation"] = {
            "action_id": action_id,
            "match_id": match_id,
            "status": status,
            "source_force_match": source_match,
            "target_force_match": target_match,
            "ui_event_sent": True,
        }
        counter = {
            "FORCE_OBSERVED": "force_observed_dispatches",
            "DISPATCH_NOT_OBSERVED": "unobserved_dispatches",
            "UNKNOWN": "unknown_dispatch_observations",
        }[status]
        self.journal[counter] = self.journal.get(counter, 0) + 1
        return status

    def _pending_dispatch_path(self) -> Path:
        return self.root / "runtime/state/pending-live-dispatch.json"

    def _load_pending_dispatch(self) -> dict | None:
        """重啟時恢復不確定的派兵鎖；損毀標記也必須 fail closed。"""
        path = self._pending_dispatch_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            payload = None
        except (OSError, ValueError):
            return {"status": "RECOVERY_MARKER_UNKNOWN",
                    "reason": "pending-dispatch-marker-unreadable"}
        if payload is not None:
            return payload if isinstance(payload, dict) else {
                "status": "RECOVERY_MARKER_UNKNOWN",
                "reason": "pending-dispatch-marker-malformed"}

        # 相容於曾只寫進 live_controller.json 的未完成紀錄。
        try:
            state = json.loads((self.root / "runtime/state/live_controller.json"
                               ).read_text(encoding="utf-8"))
            journal = state.get("journal") if isinstance(state, dict) else None
            pending = journal.get("pending_dispatch") if isinstance(journal, dict) else None
            return pending if isinstance(pending, dict) else None
        except (OSError, ValueError):
            return None

    def _persist_pending_dispatch(self, record: dict) -> None:
        """先 fsync 暫存檔再原子替換，確保 UI 派兵前留下復原鎖。"""
        path = self._pending_dispatch_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(
            f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _set_pending_dispatch(self, record: dict) -> None:
        pending = dict(record)
        # 獨立 marker 先落盤，主狀態寫入失敗也不得送出行動。
        self._persist_pending_dispatch(pending)
        self.journal["pending_dispatch"] = pending
        self._save()

    def _clear_pending_dispatch(self) -> bool:
        path = self._pending_dispatch_path()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
        self.journal.pop("pending_dispatch", None)
        self._save()
        return True

    def _finish_pending_dispatch(self, verdict: str) -> bool:
        """只有明確驗證結果才解除復原鎖；UNKNOWN 會持續落盤。"""
        pending = self.journal.get("pending_dispatch")
        if not isinstance(pending, dict):
            return True
        if verdict in VERIFIED_ACTION_RESULTS:
            return self._clear_pending_dispatch()
        pending.update(status="VERIFICATION_UNKNOWN",
                       last_verdict=str(verdict))
        self._persist_pending_dispatch(pending)
        self._save()
        return False

    def _reconcile_pending_dispatch(self, by_id: dict,
                                    match_id: str) -> bool:
        """以新鮮觀察解除已證實行動；否則阻止任何下一次派兵。"""
        journal = getattr(self, "journal", None)
        if not isinstance(journal, dict):
            # 部分離線呼叫只建構了控制器的必要欄位；仍須從持久標記
            # 恢復派兵鎖，不能因缺少記憶體 journal 而漏掉未驗證行動。
            loader = getattr(self, "_load_pending_dispatch", None)
            pending = loader() if callable(loader) else None
            if not isinstance(pending, dict):
                return False
            journal = {"pending_dispatch": pending}
            self.journal = journal
        pending = journal.get("pending_dispatch")
        if not isinstance(pending, dict):
            return False
        pending_match = pending.get("match_id")
        if pending_match != match_id:
            game = getattr(self.browser, "game", {}) or {}
            join_clicks = game.get("join_clicks")
            prior_clicks = pending.get("join_clicks")
            current_session = getattr(self.browser, "session_id", None)
            prior_session = pending.get("browser_session_id")
            explicit_new_entry = (
                type(join_clicks) is int and join_clicks > 0
                and ((current_session and current_session != prior_session)
                     or (current_session == prior_session
                         and type(prior_clicks) is int
                         and join_clicks > prior_clicks)))
            if explicit_new_entry:
                return not self._clear_pending_dispatch()
            return True

        source_id = pending.get("source_tower_id")
        target_id = pending.get("target_tower_id")
        before = pending.get("before")
        source = by_id.get(source_id)
        target = by_id.get(target_id)
        if (not isinstance(before, dict) or source is None or target is None
                or source.freshness(match_id, time.time()) != "FRESH"
                or target.freshness(match_id, time.time()) != "FRESH"):
            return True
        from types import SimpleNamespace
        after = {"match_id": match_id,
                 "source": self.snapshot_tower(source),
                 "target": self.snapshot_tower(target)}
        verdict = verify_post_action(
            before, after, SimpleNamespace(
                match_id=match_id,
                action_kind=pending.get("action_kind", "EXPAND_NEUTRAL")))
        if verdict not in VERIFIED_ACTION_RESULTS:
            return True
        self.journal["last_verification"] = verdict
        return not self._finish_pending_dispatch(verdict)

    def _dashboard_inbound_observation(self) -> dict:
        """回傳短效、同局且限量的唯讀威脅候選，絕不當作派兵授權。"""
        def finite_number(value) -> bool:
            if type(value) not in (int, float):
                return False
            try:
                return math.isfinite(value)
            except (OverflowError, TypeError, ValueError):
                return False

        unknown = {"match_id": None, "status": "UNKNOWN",
                   "reason": "same-match-observation-unavailable",
                   "age_seconds": None, "threats": []}
        app = getattr(self, "app", None)
        browser = getattr(app, "browser", None)
        game = getattr(browser, "game", {})
        match = game.get("match") if isinstance(game, dict) else None
        active_match = match.get("id") if isinstance(match, dict) else None
        if not isinstance(active_match, str) or not active_match:
            return unknown

        journal = getattr(self, "journal", None)
        safety = journal.get("last_source_safety") if isinstance(journal, dict) else None
        if (not isinstance(safety, dict)
                or safety.get("match_id") != active_match):
            return unknown

        observed_at = safety.get("observed_at")
        if not finite_number(observed_at) or observed_at <= 0:
            return {**unknown, "match_id": active_match,
                    "reason": "observation-time-unknown"}
        age_seconds = max(0.0, time.time() - observed_at)
        if age_seconds > 30:
            return {"match_id": active_match, "status": "STALE",
                    "reason": "observation-expired", "age_seconds": age_seconds,
                    "threats": []}

        status = safety.get("threat_observation_status")
        reason = safety.get("threat_observation_reason")
        base = {"match_id": active_match, "reason": (
                    reason[:120] if isinstance(reason, str) else "reason-unknown"),
                "age_seconds": age_seconds, "threats": []}
        if status in ("UNKNOWN", "CLEAR"):
            return {**base, "status": status}
        raw_threats = safety.get("incoming_threats")
        if (status != "OBSERVED_CANDIDATE"
                or not isinstance(raw_threats, list)
                or not 1 <= len(raw_threats) <= 8):
            return {**base, "status": "UNKNOWN",
                    "reason": "candidate-threat-list-incomplete"}

        threats = []
        for row in raw_threats:
            if (not isinstance(row, dict)
                    or row.get("match_id") != active_match
                    or type(row.get("source_tower_id")) is not int
                    or row["source_tower_id"] <= 0
                    or type(row.get("target_tower_id")) is not int
                    or row["target_tower_id"] <= 0):
                return {**base, "status": "UNKNOWN",
                        "reason": "candidate-threat-identity-invalid"}
            relation = row.get("owner_relation")
            if relation not in ("SELF", "ALLY", "ENEMY", "NEUTRAL", "UNKNOWN"):
                relation = "UNKNOWN"
            eta_ticks = row.get("eta_ticks")
            if type(eta_ticks) is not int or eta_ticks < 0:
                eta_ticks = None
            eta_seconds = row.get("eta_seconds")
            if not finite_number(eta_seconds) or eta_seconds < 0:
                eta_seconds = None
            eta_status = ("CANDIDATE"
                          if row.get("eta_status") == "CANDIDATE"
                          and eta_ticks is not None
                          and eta_seconds is not None else "UNKNOWN")
            threats.append({
                "source_tower_id": row["source_tower_id"],
                "target_tower_id": row["target_tower_id"],
                "owner_relation": relation,
                "eta_ticks": eta_ticks,
                "eta_seconds": eta_seconds,
                "eta_status": eta_status,
            })
        return {**base, "status": "OBSERVED_CANDIDATE", "threats": threats}

    def heartbeat(self) -> dict:
        journal = self.journal
        last = journal.get("last_cycle") or {}
        return {"running": self.running, "cycle_count": self.cycle_count,
                "last_cycle_at": self.last_cycle_at, "phase": self.phase,
                "cycle_id": last.get("cycle_id"),
                "no_action_reason": last.get("no_action_reason"),
                "candidates": (journal.get("last_info") or {}).get("candidate_count"),
                "last_verified_expansion": journal.get("last_expansion"),
                "inbound_threat_observation": self._dashboard_inbound_observation(),
                "threat_state": dict(journal.get("threat_state") or
                                     self._empty_threat_state(None, None)),
                "multi_threat_evaluation": dict(
                    journal.get("multi_threat_evaluation") or {
                        "match_id": None, "cycle_id": None,
                        "status": "UNKNOWN", "evaluations": []}),
                "defense_assessment": dict(
                    journal.get("defense_assessment") or {
                        "match_id": None, "cycle_id": None,
                        "status": "UNKNOWN", "action": "ABSTAIN"}),
                "pvp_arbitration": dict(
                    journal.get("pvp_arbitration") or {
                        "action": "ABSTAIN",
                        "evaluation_status": "UNKNOWN"}),
                "attack_assessment": dict(
                    journal.get("attack_assessment") or {
                        "match_id": None, "cycle_id": None,
                        "status": "UNKNOWN", "evaluations": [],
                        "execution": "NOT_ATTEMPTED"}),
                "journal": {"sent_actions": journal.get("sent_actions", 0),
                            "verified_moves": journal.get("verified_moves", 0),
                            "verified_expansions": journal.get("verified_expansions", 0),
                            "force_observed_dispatches": journal.get(
                                "force_observed_dispatches", 0),
                            "unobserved_dispatches": journal.get(
                                "unobserved_dispatches", 0),
                            "unknown_dispatch_observations": journal.get(
                                "unknown_dispatch_observations", 0)}}

    @property
    def browser(self):
        return self.app.browser

    def _tool_env(self) -> dict:
        import os
        env = dict(os.environ)
        env.update({"PYTHONUTF8": "1",
                    "PYTHONPATH": str(self.root / "src"),
                    "TEMP": str(self.root / "runtime/tmp"),
                    "TMP": str(self.root / "runtime/tmp")})
        return env

    async def _run_tool(self, script: str, *args):
        if Path(script).name.casefold() in {
                "wasm_render_anchor.py", "unit_struct_probe.py"}:
            return 2, "blocked: live game memory probing is disabled"
        proc = await asyncio.create_subprocess_exec(
            self._venv_python, str(self.root / "tools" / script), *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(self.root), env=self._tool_env())
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return 1, ""
        lines = (out.decode("utf-8", "replace") or "").strip().splitlines()
        return proc.returncode or 0, lines[-1] if lines else ""

    def _anchor_path(self) -> Path:
        return self.root / "runtime/research/source-map/verified-anchor-current.json"

    @staticmethod
    def _valid_timestamp(value) -> bool:
        return (type(value) in (int, float)
                and math.isfinite(float(value)) and value > 0)

    def _set_observation_blocker(self, category: str, component: str,
                                 reason: str, match_id: str | None,
                                 now: float | None = None) -> dict:
        """記錄本局無法使用世界狀態的原因；只沿用同局時間戳。"""
        if (not isinstance(category, str)
                or category not in OBSERVATION_BLOCKER_CATEGORIES):
            category = "UNKNOWN_STALE"
        if not isinstance(component, str) or not component:
            component = "UNKNOWN"
        if not isinstance(reason, str) or not reason:
            reason = "UNKNOWN"
        now = time.time() if now is None else now
        if not self._valid_timestamp(now):
            now = time.time()

        previous = self.journal.get("observation_blocker")
        same_blocker = (
            isinstance(previous, dict)
            and previous.get("match_id") == match_id
            and previous.get("category") == category
            and previous.get("blocking_component") == component
            and previous.get("reason") == reason
        )
        last_good = (previous.get("last_good_timestamp")
                     if isinstance(previous, dict) and
                     previous.get("match_id") == match_id else None)
        if not self._valid_timestamp(last_good):
            last_good = None
        first_bad = (previous.get("first_bad_timestamp")
                     if same_blocker else now)
        if not self._valid_timestamp(first_bad):
            first_bad = now
        blocker = {
            "status": category,
            "category": category,
            "match_id": match_id,
            "blocking_component": component,
            "reason": reason,
            "age_seconds": (max(0.0, now - last_good)
                            if last_good is not None else "UNKNOWN"),
            "last_good_timestamp": (last_good
                                    if last_good is not None else "UNKNOWN"),
            "first_bad_timestamp": first_bad,
            "blocked_for_seconds": max(0.0, now - first_bad),
        }
        self.journal["observation_blocker"] = blocker
        return blocker

    def _set_observation_fresh(self, match_id: str,
                               now: float | None = None) -> dict:
        """記錄同局可信錨點，不跨局沿用時間。"""
        now = time.time() if now is None else now
        if not self._valid_timestamp(now):
            now = time.time()
        blocker = {
            "status": "FRESH",
            "category": None,
            "match_id": match_id,
            "blocking_component": None,
            "reason": None,
            "age_seconds": 0.0,
            "last_good_timestamp": now,
            "first_bad_timestamp": None,
            "blocked_for_seconds": 0.0,
        }
        self.journal["observation_blocker"] = blocker
        return blocker

    async def ensure_anchor(self, match_id: str) -> dict | None:
        """目前沒有由玩家可見 UI 產生的可信錨點，因此一律棄權。

        舊錨點由 CDP（Chrome 開發者工具協定）斷點／遊戲記憶體探針
        建立，不能當成正常 UI 觀察證據重用。
        """
        return None

    async def _probe_ok(self, match_id: str) -> bool:
        """遊戲記憶體探針已停用；未來須改由可見 UI 證據驗證。"""
        return False

    async def fresh_screen_map(self, anchor_towers: list):
        """沒有可見 UI 相機映射來源時，拒絕產生可執行座標。"""
        del anchor_towers
        return {}, None

    def _select_reservation_match(self, match_id: str | None):
        """換局或離開遊戲時清空尚未完成的保留。"""
        board = getattr(self, "_reservations", None)
        if (getattr(self, "_reservation_match_id", object()) == match_id
                and isinstance(board, ReservationBoard)):
            return
        if isinstance(board, ReservationBoard):
            board.clear_match()
        else:
            self._reservations = ReservationBoard()
        self._reservation_match_id = match_id

    @staticmethod
    def _camera_token_values(canvas: dict | None) -> tuple | None:
        """包含相機、視窗、DPR 與畫布範圍的穩定相機快照。"""
        if not isinstance(canvas, dict):
            return None
        camera = canvas.get("camera")
        viewport = canvas.get("viewport")
        rect = canvas.get("canvas_rect")
        dpr = canvas.get("dpr")
        if (not isinstance(camera, (tuple, list)) or len(camera) < 4
                or not isinstance(viewport, (tuple, list)) or len(viewport) != 2
                or not isinstance(rect, (tuple, list)) or len(rect) != 4):
            return None
        values = (*camera, *viewport, dpr, *rect)
        if any(type(value) not in (int, float) for value in values):
            return None
        try:
            if any(not math.isfinite(float(value)) for value in values):
                return None
        except (OverflowError, ValueError):
            return None
        return values

    def _build_dispatch_token(self, match_id, cycle_id, source_state,
                              target_state, canvas, deployable_counts):
        """建立並立即重驗真實派送快照；缺任一版本即拒絕。"""
        if type(cycle_id) is not int:
            return None, "STALE_PROPOSAL:cycle-unknown"
        camera = self._camera_token_values(canvas)
        if camera is None:
            return None, "STALE_PROPOSAL:camera-unknown"
        probe_path = (self.root / "runtime/research/units"
                      / f"unit-struct-probe-{match_id}.json")
        try:
            anchor_mtime = self._anchor_path().stat().st_mtime
            probe_mtime = probe_path.stat().st_mtime
        except OSError:
            return None, "STALE_PROPOSAL:snapshot-unknown"
        if (not math.isfinite(anchor_mtime) or anchor_mtime <= 0
                or not math.isfinite(probe_mtime) or probe_mtime <= 0):
            return None, "STALE_PROPOSAL:snapshot-unknown"
        token = build_token(
            match_id, cycle_id, anchor_mtime, probe_mtime,
            source_state, target_state, camera,
            deployable_counts=deployable_counts)
        if token.reserved_deployable is None:
            return token, "STALE_PROPOSAL:deployable-unknown"
        if (type(token.source_tower_id) is not int or token.source_tower_id <= 0
                or type(token.target_tower_id) is not int
                or token.target_tower_id <= 0
                or token.source_tower_id == token.target_tower_id):
            return token, "STALE_PROPOSAL:tower-id-unknown"
        try:
            current_anchor_mtime = self._anchor_path().stat().st_mtime
            current_probe_mtime = probe_path.stat().st_mtime
        except OSError:
            return token, "STALE_PROPOSAL:snapshot-unknown"
        result = validate_token(
            token, match_id, current_anchor_mtime, current_probe_mtime,
            source_state, target_state, camera, current_cycle_id=cycle_id,
            current_deployable_counts=deployable_counts)
        return token, result

    async def _with_action_reservation(self, action_id, source_id, target_id,
                                       operation):
        """保留資源直到執行與驗證完成，任何出口都會釋放。"""
        if not isinstance(getattr(self, "_reservations", None), ReservationBoard):
            self._reservations = ReservationBoard()
        if (type(source_id) is not int or source_id <= 0
                or type(target_id) is not int or target_id <= 0
                or source_id == target_id):
            return "NO_SAFE_PROPOSAL", {
                "reason": "STALE_PROPOSAL:tower-id-unknown"}
        conflict = self._reservations.reserve(action_id, source_id, target_id)
        if conflict:
            return "NO_SAFE_PROPOSAL", {"reason": conflict}
        try:
            return await operation()
        finally:
            self._reservations.release(action_id)

    def build_states(self, anchor: dict, probe_rows: dict, now: float):
        towers = []
        for t in anchor["towers"]:
            if t["packed_id"] not in probe_rows:
                continue
            raw = probe_rows[t["packed_id"]]["bytes"][32:32 + 48]
            towers.append(ObservedTower(
                tower_id=t["packed_id"], tower_ref=t["tower_ref"],
                world_x=t["position"][0], world_y=t["position"][1],
                owner=t["owner"], owner_ruler=decode_owner_ruler_flag(raw),
                tower_type=decode_tower_type(raw),
                units_detail=decode_tower_units(raw, tower_ref=t["tower_ref"])))
        edges = [ObservedEdge(a, b) for a, b in anchor.get("edges", [])]
        obs = MatchObservation(match_id=anchor["match_id"], timestamp=now,
                               towers=tuple(towers), edges=tuple(edges))
        return build_real_tower_states(obs)

    async def snapshot_collections(self, tower_ref: int) -> dict:
        """T0/T1/T2 集合快照：兩集合頭＋逐項目＋路徑（全唯讀，有界）。"""
        from kiomet_ai.force import (ENTRY_SIZE, MAX_PATH_LEN,
                                     _u32le, _valid_tower_id,
                                     decode_collection, decode_force_units)
        import struct as _struct
        try:
            browser = self.browser
            game = browser.game if browser else {}
            match_id = (game.get("match") or {}).get("id")
        except Exception:
            match_id = None
        snap = {"tower_ref": tower_ref, "match_id": match_id,
                "captured_at": time.time(), "collections": {}}
        if not isinstance(match_id, str) or not match_id:
            snap["error"] = "match-id-unknown"
            return snap
        try:
            header = await self.browser.read_wasm_bytes(tower_ref, 24)
        except Exception as exc:
            snap["error"] = str(exc)[:120]
            return snap
        for role, base in (("inbound", tower_ref), ("outbound", tower_ref + 12)):
            collection = decode_collection(header, base, tower_ref)
            entries = []
            if collection is not None:
                for entry in collection["entries"][:8]:
                    try:
                        head = await self.browser.read_wasm_bytes(entry, ENTRY_SIZE)
                    except Exception:
                        continue
                    if len(head) < ENTRY_SIZE:
                        continue
                    path_len = _struct.unpack_from("<I", head, 8)[0]
                    path_ptr = _struct.unpack_from("<I", head, 4)[0]
                    units = decode_force_units(bytes(head[14:21]))
                    if units is None or not (2 <= path_len <= 16):
                        continue
                    try:
                        path_block = await self.browser.read_wasm_bytes(path_ptr, 4 * path_len)
                    except Exception:
                        continue
                    path = []
                    for i in range(path_len):
                        tid = _struct.unpack_from("<I", path_block, 4 * i)[0]
                        if not _valid_tower_id(tid):
                            break
                        path.append(tid)
                    else:
                        if len(set(path)) != len(path) or path[-1] == path[-2]:
                            continue
                        entries.append({"ref": entry, "path": path,
                                        "owner_id": head[12] | (head[13] << 8),
                                        "units": dict(units.counts),
                                        "speed_flag": head[21],
                                        "progress": head[22],
                                        "endurance": head[23]})
                        continue
            snap["collections"][role] = {
                "length": collection["length"] if collection else None,
                "entries": entries}
        try:
            game_after = self.browser.game if self.browser else {}
            match_after = (game_after.get("match") or {}).get("id")
        except Exception:
            match_after = None
        if match_after != match_id:
            snap["error"] = "match-changed-during-snapshot"
        snap["captured_at"] = time.time()
        return snap

    def correlate_force(self, before: dict, after: dict | list,
                        expected_path: tuple | None, *,
                        dispatched_at: float | None = None) -> str:
        """只用新鮮 T0 與派送後快照配對部隊；時間不明一律 UNKNOWN。"""
        now = time.time()

        def capture_time(snapshot):
            value = (snapshot.get("captured_at")
                     if isinstance(snapshot, dict) else None)
            if (type(value) not in (int, float)
                    or not math.isfinite(value) or value <= 0
                    or value > now + 1.0):
                return None
            return float(value)

        before_at = capture_time(before)
        if (not self._force_snapshot_complete(before)
                or before_at is None
                or type(dispatched_at) not in (int, float)
                or not math.isfinite(dispatched_at)
                or dispatched_at <= before_at
                or dispatched_at > now + 1.0
                or dispatched_at - before_at > 30.0):
            return "FORCE_MATCH_UNKNOWN"
        before_match_id = before["match_id"]
        afters = after if isinstance(after, list) else [after]
        if not afters:
            return "FORCE_MATCH_UNKNOWN"
        complete_afters = []
        for aft in afters:
            aft_at = capture_time(aft)
            if (not self._force_snapshot_complete(aft)
                    or aft["match_id"] != before_match_id
                    or aft_at is None or aft_at <= dispatched_at
                    or aft_at <= before_at or now - aft_at > 30.0):
                continue
            complete_afters.append(aft)

        def sig(entry):
            # progress/endurance/units can change while the same force moves
            # or fights. The WASM structure reference is its stable identity.
            return entry["ref"]
        before_sigs = set()
        for role in ("inbound", "outbound"):
            for entry in (before.get("collections") or {}).get(role, {}).get("entries", []):
                before_sigs.add(sig(entry))
        matches = []
        for aft in complete_afters:
            for role in ("inbound", "outbound"):
                for entry in (aft.get("collections") or {}).get(role, {}).get("entries", []):
                    if sig(entry) not in before_sigs:
                        matches.append((role, entry))
        if not matches:
            return ("FORCE_MATCH_NOT_FOUND" if len(complete_afters) == len(afters)
                    else "FORCE_MATCH_UNKNOWN")
        if (not isinstance(expected_path, (list, tuple))
                or len(expected_path) != 2
                or any(type(tower_id) is not int or tower_id <= 0
                       for tower_id in expected_path)
                or expected_path[0] == expected_path[1]):
            return ("FORCE_MATCH_AMBIGUOUS" if len(matches) > 1
                    else "FORCE_MATCH_UNVERIFIABLE")

        source_id, target_id = expected_path
        # 遊戲 force path 由目的端列回來源端：path[0] 是目標，
        # path[-1] 是來源。只比較集合會把反向路徑誤認成已驗證。
        routed = []
        for role, entry in matches:
            path = entry.get("path")
            if (isinstance(path, (list, tuple)) and len(path) >= 2
                    and all(type(tower_id) is int and tower_id > 0
                            for tower_id in path)
                    and path[0] == target_id
                    and path[-1] == source_id):
                routed.append((role, entry, path))
        if not routed:
            return "FORCE_MATCH_NOT_FOUND"
        if len(routed) != 1:
            return "FORCE_MATCH_AMBIGUOUS"
        path = routed[0][2]
        return ("FORCE_MATCH_VERIFIED" if len(path) == 2
                else "FORCE_MATCH_DERIVED")

    def _check_pending_captures(self, by_id: dict, match_id: str, now: float):
        """Finalize（終結）待確認目標，並依行動種類分開記帳。"""
        pending = self.journal.get("pending_captures", [])
        kept = []
        for item in pending:
            if item.get("match_id") != match_id:
                continue
            if now - item.get("since", now) > 1800:
                continue
            target = by_id.get(item.get("target"))
            if target is not None and target.owner == "SELF":
                # Pre-schema pending entries came only from neutral expansion;
                # keep their historical meaning while tagging new actions.
                action_kind = item.get("action_kind", "EXPAND_NEUTRAL")
                if action_kind == "ATTACK_ENEMY":
                    if (item.get("dispatch_observation") != "FORCE_OBSERVED"
                            or item.get("target_owner_before") != "ENEMY"):
                        # A target becoming SELF alone is not enough to attribute
                        # the capture to this attack; keep it unresolved.
                        kept.append(item)
                        continue
                    # A later SELF owner observation records the capture outcome,
                    # but cannot manufacture the missing battle/server proof.
                    capture_count = self.journal.get(
                        "observed_attack_captures", 0)
                    if type(capture_count) is not int or capture_count < 0:
                        capture_count = 0
                    self.journal["observed_attack_captures"] = capture_count + 1
                    capture = {
                        "action_id": item.get("action_id"),
                        "target": target.tower_id,
                        "match_id": match_id,
                        "confirmed_at": now,
                        "outcome": "TARGET_CAPTURED",
                    }
                    if item.get("attack_validation_status") == "VALIDATION_PENDING":
                        capture["attack_validation_status"] = "VALIDATION_PENDING"
                    history = self.journal.get(
                        "observed_attack_capture_history", [])
                    if not isinstance(history, list):
                        history = []
                    history.append(capture)
                    self.journal["observed_attack_capture_history"] = history[-20:]
                    self.journal["last_attack_capture"] = capture
                    continue
                if action_kind == "EXPAND_NEUTRAL":
                    self.journal["verified_expansions"] = self.journal.get("verified_expansions", 0) + 1
                    self.journal["last_expansion"] = {"target": target.tower_id,
                        "match_id": match_id, "confirmed_at": now}
                    try:
                        self.app.record_expansion(item)
                    except Exception:
                        pass
                    continue
            kept.append(item)
        self.journal["pending_captures"] = kept[-20:]

    def snapshot_tower(self, state):
        counts = state.unit_counts
        return {"owner": state.owner,
                "units": ({n: getattr(counts, n.lower()) for n in
                           ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier")}
                          if counts and counts.units_kind == "MANY" else None)}

    def evaluate_live_source_safety(self, match_id: str, source_state,
                                    source_snapshot: dict,
                                    proposed_units: dict,
                                    tower_states_by_id: dict | None = None) -> dict:
        """派送前驗證來源塔殘兵與入站集合；未知資料一律拒絕。"""
        from kiomet_ai.battle_mirror import CAPACITIES
        from kiomet_ai.force import _valid_tower_id
        from kiomet_ai.observe import UNIT_NAMES
        from kiomet_ai.pvp_live import (SPECIAL_UNIT_NAMES,
                                        candidate_inbound_threats,
                                        evaluate_source_safety)

        if (source_state is None
                or getattr(source_state, "match_id", None) != match_id
                or source_state.freshness(match_id, time.time()) != "FRESH"):
            return {"result": "UNKNOWN", "reason": "source-state-stale"}

        if not isinstance(source_snapshot, dict):
            return {"result": "UNKNOWN", "reason": "inbound-collection-unknown"}
        if source_snapshot.get("match_id") != match_id:
            return {"result": "UNKNOWN", "reason": "source-snapshot-match-mismatch"}
        if source_snapshot.get("error"):
            return {"result": "UNKNOWN", "reason": "source-snapshot-read-failed"}
        captured_at = source_snapshot.get("captured_at")
        now = time.time()
        if (type(captured_at) not in (int, float)
                or not math.isfinite(captured_at)
                or captured_at <= 0 or captured_at > now + 1.0
                or now - captured_at > 30.0):
            return {"result": "UNKNOWN",
                    "reason": "source-snapshot-time-unknown-or-stale"}
        collections = source_snapshot.get("collections")
        inbound = (collections or {}).get("inbound")
        if not isinstance(inbound, dict):
            return {"result": "UNKNOWN", "reason": "inbound-collection-unknown"}
        length = inbound.get("length")
        entries = inbound.get("entries")
        if (type(length) is not int or length < 0
                or not isinstance(entries, list) or len(entries) != length):
            return {"result": "UNKNOWN", "reason": "inbound-collection-incomplete"}

        self_id = self._player_ids.self_id()
        unresolved_foreign_inbound = False
        for entry in entries:
            if not isinstance(entry, dict):
                return {"result": "UNKNOWN",
                        "reason": "inbound-force-evidence-incomplete"}
            owner_id = entry.get("owner_id")
            if type(owner_id) is not int or owner_id <= 0:
                return {"result": "UNKNOWN",
                        "reason": "inbound-force-evidence-incomplete"}
            path = entry.get("path")
            units = entry.get("units")
            if self_id is None or owner_id != self_id:
                # Owner uncertainty is the gate's primary reason for abstaining.
                # Keep that contract even when the foreign force lacks enough
                # route detail for candidate ETA diagnostics.
                unresolved_foreign_inbound = True
                continue
            if (not isinstance(path, (list, tuple)) or not 2 <= len(path) <= 16
                    or any(type(tower_id) is not int
                           or not _valid_tower_id(tower_id) for tower_id in path)
                    or path[-2] != source_state.tower_id
                    or len(set(path)) != len(path)
                    or path[-1] == path[-2]
                    or not isinstance(units, dict) or set(units) != set(UNIT_NAMES)
                    or any(type(value) is not int or not 0 <= value <= 255
                           for value in units.values())
                    or not any(units.values())):
                return {"result": "UNKNOWN",
                        "reason": "inbound-force-evidence-incomplete"}
            if tower_states_by_id is not None:
                origin = (tower_states_by_id.get(path[-1])
                          if isinstance(tower_states_by_id, dict) else None)
                freshness = getattr(origin, "freshness", None)
                try:
                    origin_fresh = (callable(freshness)
                                    and freshness(match_id, time.time()) == "FRESH")
                except Exception:
                    origin_fresh = False
                if (origin is None
                        or getattr(origin, "match_id", None) != match_id
                        or getattr(origin, "tower_id", None) != path[-1]
                        or getattr(origin, "owner", None) != "SELF"
                        or not origin_fresh):
                    return {
                        "result": "UNKNOWN",
                        "reason": "inbound-force-self-owner-conflicts-with-origin",
                    }

        if unresolved_foreign_inbound:
            observation = candidate_inbound_threats(
                source_snapshot, source_state, tower_states_by_id or {},
                match_id, self_id=self_id,
                player_ids=getattr(self, "_player_ids", None))
            return {
                "result": "UNKNOWN",
                "reason": "inbound-force-owner-unresolved",
                "threat_observation_status": observation.get("status"),
                "threat_observation_reason": observation.get("reason"),
                "incoming_threats": observation.get("threats", []),
            }

        counts = getattr(source_state, "unit_counts", None)
        if getattr(counts, "units_kind", None) != "MANY":
            return {"result": "UNKNOWN",
                    "reason": "source-defender-composition-unknown"}
        ruler_flag = getattr(source_state, "owner_ruler", None)
        current = {
            "Shield": getattr(counts, "shield", None),
            "Fighter": getattr(counts, "fighter", None),
            "Chopper": getattr(counts, "chopper", None),
            "Bomber": getattr(counts, "bomber", None),
            "Tank": getattr(counts, "tank", None),
            "Soldier": getattr(counts, "soldier", None),
            "Shell": 0, "Emp": 0, "Nuke": 0,
            "Ruler": (1 if ruler_flag is True else
                      0 if ruler_flag is False else None),
        }
        if (set(proposed_units or {}) != set(UNIT_NAMES)
                or any(type(value) is not int or not 0 <= value <= 255
                       for value in (proposed_units or {}).values())
                or any(type(current[name]) is not int
                       or not 0 <= current[name] <= 255
                       for name in UNIT_NAMES)):
            return {"result": "UNKNOWN",
                    "reason": "source-force-vector-unknown"}
        if any(proposed_units[name] for name in SPECIAL_UNIT_NAMES):
            return {"result": "UNKNOWN",
                    "reason": "source-special-dispatch-unsupported"}
        remaining = {name: current[name] - proposed_units[name]
                     for name in UNIT_NAMES}
        if any(value < 0 for value in remaining.values()):
            return {"result": "UNKNOWN",
                    "reason": "source-force-subtraction-invalid"}

        result = evaluate_source_safety(
            remaining, [], CAPACITIES, getattr(source_state, "tower_type", None),
            self_id=self_id)
        if result.get("result") != "SAFE":
            return result
        return {"result": "SAFE", "reason": "source-state-and-inbound-known"}

    def _select_player_id_match(self, match_id: str | None):
        """每局隔離玩家 ID；離開對局時也清除上一局身份。"""
        if (getattr(self, "_player_ids_match_id", object()) == match_id
                and isinstance(getattr(self, "_player_ids", None),
                               PlayerIdRegistry)):
            return
        self._player_ids_match_id = match_id
        self._player_ids = PlayerIdRegistry()
        journal = getattr(self, "journal", None)
        if isinstance(journal, dict):
            journal.pop("self_owner_id", None)
            journal.pop("self_owner_id_match_id", None)

    def _learn_self_id_from_verified_dispatch(
            self, match_id: str, candidate: dict, refreshed,
            source_t1: dict, force_match_source: str,
            force_match_target: str) -> int | None:
        """記錄每局 SELF ID；必須是來源與目標兩端的精確配對。"""
        self._select_player_id_match(match_id)
        if (force_match_source != "FORCE_MATCH_VERIFIED"
                or force_match_target != "FORCE_MATCH_VERIFIED"):
            return None
        collections = (source_t1 or {}).get("collections") or {}
        outbound = collections.get("outbound") or {}
        forces = outbound.get("entries")
        if not isinstance(forces, list):
            return None
        owner_id = self._player_ids.observe_verified_self_dispatch(
            (candidate or {}).get("source_owner"),
            getattr(refreshed, "source_tower_id", None),
            getattr(refreshed, "target_tower_id", None),
            force_match_source, forces)
        if owner_id is None:
            return None
        self.journal["self_owner_id"] = owner_id
        self.journal["self_owner_id_match_id"] = match_id
        return owner_id

    async def cycle_once(self) -> tuple:
        """單次閉環。回 (phase, info)。一次最多一動作。"""
        now = time.time()
        cycle_id = getattr(self, "cycle_seq", 0)
        if not isinstance(getattr(self, "journal", None), dict):
            self.journal = {}
        game = self.browser.game if self.browser else {}
        match_id = (game.get("match") or {}).get("id")
        if game.get("state") != "IN_MATCH" or not match_id:
            self._set_observation_blocker(
                "MATCH_STALE", "match", "not-in-match", None, now)
            self.journal["threat_state"] = self._empty_threat_state(
                None, cycle_id, status="STALE", reason="not-in-match",
                freshness="STALE")
            self.journal["multi_threat_evaluation"] = {
                "match_id": None, "cycle_id": cycle_id,
                "status": "STALE", "evaluations": []}
            self.journal["defense_assessment"] = {
                "match_id": None, "cycle_id": cycle_id,
                "status": "STALE", "action": "ABSTAIN",
                "reason": "not-in-match"}
            self.journal["pvp_arbitration"] = {
                "action": "ABSTAIN", "evaluation_status": "UNKNOWN",
                "reason": "not-in-match"}
            self.journal["attack_assessment"] = {
                "match_id": None, "cycle_id": cycle_id,
                "status": "STALE", "evaluations": [],
                "execution": "NOT_ATTEMPTED"}
            self._select_player_id_match(None)
            self._select_reservation_match(None)
            return "NO_SAFE_PROPOSAL", {"reason": "not_in_match"}
        self.journal["threat_state"] = self._empty_threat_state(
            match_id, cycle_id, reason="cycle-observation-pending")
        self.journal["multi_threat_evaluation"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "UNKNOWN", "reason": "cycle-observation-pending",
            "evaluations": []}
        self.journal["defense_assessment"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "UNKNOWN", "action": "ABSTAIN",
            "reason": "cycle-observation-pending"}
        self.journal["pvp_arbitration"] = {
            "action": "ABSTAIN", "evaluation_status": "UNKNOWN",
            "reason": "cycle-observation-pending"}
        self.journal["attack_assessment"] = {
            "match_id": match_id, "cycle_id": cycle_id,
            "status": "UNKNOWN", "evaluations": [],
            "execution": "NOT_ATTEMPTED"}
        self._select_player_id_match(match_id)
        self._select_reservation_match(match_id)
        anchor = await self.ensure_anchor(match_id)
        if anchor is None:
            self._set_observation_blocker(
                "OBSERVATION_STALE", "visible-world-map",
                "trusted-visible-world-map-unavailable", match_id, now)
            return "NO_SAFE_PROPOSAL", {
                "reason": "anchor_unavailable", "match_id": match_id}
        self._set_observation_fresh(match_id, now)
        try:
            probe = json.loads((self.root / f"runtime/research/units/unit-struct-probe-{match_id}.json").read_text(encoding="utf8"))
        except (OSError, ValueError):
            self._set_observation_blocker(
                "PROBE_STALE", "unit-probe", "same-match-probe-unavailable",
                match_id, now)
            return "NO_SAFE_PROPOSAL", {
                "reason": "probe_unavailable", "match_id": match_id}
        prows = {r["packed_id"]: r for r in probe.get("rows", [])}
        states = self.build_states(anchor, prows, now)
        by_id = {s.tower_id: s for s in states}
        await self._observe_cycle_threat_state(
            match_id, cycle_id, states, by_id, now)
        self._evaluate_cycle_multi_threat(
            match_id, cycle_id, states, by_id, time.time())
        await self._evaluate_cycle_defense(
            match_id, cycle_id, states, by_id, time.time())
        await self._evaluate_cycle_attack_candidates(
            match_id, cycle_id, states, by_id, anchor, time.time())
        self._check_pending_captures(by_id, match_id, now)
        if self._reconcile_pending_dispatch(by_id, match_id):
            pending = self.journal.get("pending_dispatch") or {}
            return "NO_SAFE_PROPOSAL", {
                "reason": "ACTION_VERIFICATION_PENDING",
                "match_id": match_id,
                "action_id": pending.get("action_id"),
            }
        ranked = rank_expansion_targets(states, match_id, now)
        defense = self.journal.get("defense_assessment") or {}
        defense_decision = (defense.get("arbitration")
                            if isinstance(defense, dict) else None)
        defense_action = (defense_decision.get("action")
                          if isinstance(defense_decision, dict) else None)
        attack_assessment = self.journal.get("attack_assessment") or {}
        attack_decision = (attack_assessment.get("arbitration")
                           if isinstance(attack_assessment, dict) else None)
        attack_action = (attack_decision.get("action")
                         if isinstance(attack_decision, dict) else None)
        attack_decision_from_assessment = attack_action == "ATTACK_ENEMY"
        if (attack_action != "ATTACK_ENEMY"
                and defense_action != "REINFORCE_SELF"
                and isinstance(attack_assessment, dict)
                and attack_assessment.get("match_id") == match_id
                and attack_assessment.get("cycle_id") == cycle_id):
            from kiomet_ai.pvp import arbitrate_pvp_action
            attack_rows = attack_assessment.get("evaluations", [])
            defense_rows = (defense.get("defense_evaluations", [])
                            if isinstance(defense, dict) else [])
            if not isinstance(attack_rows, list):
                attack_rows = []
            if not isinstance(defense_rows, list):
                defense_rows = []
            preliminary = arbitrate_pvp_action(
                defense_evaluations=defense_rows,
                attack_evaluations=attack_rows,
                neutral_expansion_candidate=None)
            if preliminary.get("action") == "ATTACK_ENEMY":
                attack_decision = preliminary
                attack_action = "ATTACK_ENEMY"
        action_kind = "EXPAND_NEUTRAL"
        attack_candidate = None
        if defense_action == "REINFORCE_SELF":
            if (defense.get("match_id") != match_id
                    or defense.get("cycle_id") != cycle_id
                    or defense_decision.get("evaluation_status") != "SUPPORTED"):
                return "NO_SAFE_PROPOSAL", {
                    "reason": "PVP_DEFENSE_DECISION_STALE",
                    "match_id": match_id, "cycle_id": cycle_id}
            defense_candidate = defense_decision.get("candidate")
            defense_target = defense_decision.get("target_tower_id")
            if isinstance(defense_candidate, dict):
                defense_candidate = dict(defense_candidate)
                defense_candidate.setdefault("match_id", match_id)
                defense_candidate.setdefault("cycle_id", cycle_id)
            proposal = build_reinforcement_proposal(
                defense_candidate, defense_target, by_id, match_id,
                cycle_id, now)
            if proposal.status != "READY":
                self.journal["current_proposal"] = {
                    "source": proposal.source_tower_id,
                    "target": proposal.target_tower_id,
                    "match_id": match_id, "cycle_id": cycle_id,
                    "action_kind": "REINFORCE_SELF",
                    "status": proposal.status,
                    "reject_reason": proposal.reject_reason,
                }
                return "NO_SAFE_PROPOSAL", {
                    "reason": "PVP_REINFORCEMENT_PROPOSAL_"
                    + str(proposal.reject_reason),
                    "match_id": match_id, "cycle_id": cycle_id}
            action_kind = "REINFORCE_SELF"
            top = {
                "source": proposal.source_tower_id,
                "target": proposal.target_tower_id,
                "heuristic_score": None,
                "reason": "validated-pvp-reinforcement",
                "source_owner": "SELF", "target_owner": "SELF",
                "target_type": getattr(
                    by_id.get(proposal.target_tower_id), "tower_type", None),
            }
        elif attack_action == "ATTACK_ENEMY":
            if (attack_assessment.get("match_id") != match_id
                    or attack_assessment.get("cycle_id") != cycle_id
                    or attack_decision.get("match_id", match_id) != match_id
                    or attack_decision.get("cycle_id", cycle_id) != cycle_id
                    or attack_decision.get("evaluation_status") not in (
                        "SUPPORTED", "SUPPORTED_STATIC")
                    or not isinstance(defense, dict)
                    or defense.get("match_id") != match_id
                    or defense.get("cycle_id") != cycle_id
                    or defense.get("status") != "SUPPORTED"):
                return "NO_SAFE_PROPOSAL", {
                    "reason": "PVP_ATTACK_DECISION_STALE_OR_UNRESOLVED",
                    "match_id": match_id, "cycle_id": cycle_id}
            attack_candidate = attack_decision.get("candidate")
            self_id = self._player_ids.self_id()
            source_id = (attack_candidate.get("source_tower_id")
                         if isinstance(attack_candidate, dict) else None)
            target_id = (attack_candidate.get("target_tower_id")
                         if isinstance(attack_candidate, dict) else None)
            attack_force = (attack_candidate.get("proposed_units")
                            if isinstance(attack_candidate, dict) else None)
            source_evidence = (attack_candidate.get("source_safety_evidence")
                               if isinstance(attack_candidate, dict) else None)
            source_state = by_id.get(source_id)
            actual_force = getattr(
                getattr(source_state, "deployable_force", None), "counts", None)
            board = getattr(self, "_reservations", None)
            prepared_for_dispatch = (
                isinstance(attack_candidate, dict)
                and _attack_dispatch_candidate_ready(
                    attack_candidate, match_id, cycle_id)
                and attack_candidate.get("match_id") == match_id
                and attack_candidate.get("cycle_id") == cycle_id
                and type(source_id) is int and source_id > 0
                and type(target_id) is int and target_id > 0
                and source_id != target_id
                and attack_candidate.get("target_relation") == "ENEMY"
                and attack_candidate.get("target_owner_confidence") == "HIGH"
                and type(self_id) is int and self_id > 0
                and attack_candidate.get("attacker_owner_id") == self_id
                and type(attack_candidate.get("defender_owner_id")) is int
                and attack_candidate["defender_owner_id"] > 0
                and attack_candidate["defender_owner_id"] != self_id
                and isinstance(attack_force, dict)
                and set(attack_force) == set(UNIT_NAMES)
                and all(type(value) is int and 0 <= value <= 255
                        for value in attack_force.values())
                and any(attack_force.get(name, 0)
                        for name in UNIT_NAMES[:6])
                and not any(attack_force.get(name, 0)
                            for name in ("Shell", "Emp", "Nuke", "Ruler"))
                and attack_force == actual_force
                and attack_candidate.get("source_safety") == "SAFE"
                and isinstance(source_evidence, dict)
                and source_evidence.get("result") == "SAFE"
                and source_evidence.get("match_id") == match_id
                and source_evidence.get("source_tower_id") == source_id
                and source_evidence.get("proposed_units") == attack_force
                and attack_candidate.get("action_validity_token") == "OK"
                and attack_candidate.get("validity_token_match_id") == match_id
                and attack_candidate.get("validity_token_cycle_id") == cycle_id
                and attack_candidate.get("reservation") == "AVAILABLE_NOT_HELD"
                and isinstance(board, ReservationBoard)
                and board.holder(source_id) is None
                and board.holder(target_id) is None
                and attack_candidate.get("result") == "ATTACK_WIN"
                and attack_candidate.get("legality") == "LEGAL_STATIC_SHAPE"
                and attack_candidate.get("battle_supported") is True
                and attack_candidate.get("safety_margin") == "ROBUST_WIN")
            if not prepared_for_dispatch:
                blocked_attack = {
                    **attack_decision,
                    "action": "ATTACK_ENEMY",
                    "execution_ready": False,
                    "selected_action_executed": False,
                    "reason": "attack-dispatch-evidence-incomplete",
                }
                self.journal["pvp_arbitration"] = blocked_attack
                reason = ("PVP_ATTACK_EVIDENCE_INCOMPLETE"
                          if attack_decision_from_assessment else
                          "PVP_ARBITRATION_ATTACK_ENEMY")
                return "NO_SAFE_PROPOSAL", {
                    "reason": reason,
                    "match_id": match_id, "cycle_id": cycle_id,
                    "source": source_id, "target": target_id,
                    "pvp_arbitration": blocked_attack}
            top = {
                "source": source_id,
                "target": target_id,
                "heuristic_score": attack_candidate.get("heuristic_score"),
                "reason": "static-robust-pvp-enemy-attack-pending-runtime-verification",
                "source_owner": "SELF", "target_owner": "ENEMY",
                "attacker_owner_id": self_id,
                "defender_owner_id": attack_candidate["defender_owner_id"],
                "target_type": getattr(by_id.get(target_id), "tower_type", None),
                "static_support_status": attack_candidate.get(
                    "static_support_status"),
                "projected_result": attack_candidate.get(
                    "projected_result"),
                "safety_margin": attack_candidate.get("safety_margin"),
                "runtime_validation_required": attack_candidate.get(
                    "runtime_validation_required"),
                "battle_prediction": attack_candidate.get(
                    "battle_evaluation"),
            }
            proposal = build_proposal(
                top, by_id, match_id, now,
                expected_target_owner="ENEMY", action_kind="ATTACK_ENEMY",
                cycle_id=cycle_id)
            if proposal.status != "READY":
                self.journal["current_proposal"] = {
                    "source": proposal.source_tower_id,
                    "target": proposal.target_tower_id,
                    "match_id": match_id, "cycle_id": cycle_id,
                    "action_kind": "ATTACK_ENEMY",
                    "status": proposal.status,
                    "reject_reason": proposal.reject_reason,
                }
                return "NO_SAFE_PROPOSAL", {
                    "reason": "PVP_ATTACK_PROPOSAL_"
                    + str(proposal.reject_reason),
                    "match_id": match_id, "cycle_id": cycle_id}
            if proposal.source_deployable_force != attack_force:
                return "NO_SAFE_PROPOSAL", {
                    "reason": "PVP_ATTACK_FORCE_MISMATCH",
                    "match_id": match_id, "cycle_id": cycle_id}
            action_kind = "ATTACK_ENEMY"
        else:
            if not ranked:
                rejected = rejection_reasons(states, match_id, now)
                return "NO_SAFE_PROPOSAL", {
                    "reason": "no_candidate", "match_id": match_id,
                    "candidate_count": 0,
                    **self.summarize_rejections(rejected)}
            top = ranked[0]
            proposal = build_proposal(top, by_id, match_id, now)
        pair = (top["source"], top["target"])
        if self.cooldowns.get(pair, 0) > now:
            return "NO_SAFE_PROPOSAL", {
                "reason": "pair_cooldown", "match_id": match_id}
        self.journal["current_proposal"] = {
            "source": top["source"], "target": top["target"],
            "match_id": match_id, "cycle_id": cycle_id,
            "action_kind": action_kind,
            "status": proposal.status,
            "rank_score": top.get("heuristic_score")}
        if proposal.status != "READY":
            return "NO_SAFE_PROPOSAL", {
                "reason": proposal.reject_reason, "match_id": match_id}
        if getattr(self.app, "autonomy_paused", False):
            return "NO_SAFE_PROPOSAL", {
                "reason": "autonomy_paused", "match_id": match_id}
        action_id = (f"{match_id}:{proposal.source_tower_id}->"
                     f"{proposal.target_tower_id}:{int(now)}")

        async def dispatch_reserved():
            old_source = by_id.get(proposal.source_tower_id)
            old_target = by_id.get(proposal.target_tower_id)
            if old_source is None or old_target is None:
                return "NO_SAFE_PROPOSAL", {"reason": "tower_gone"}
            src_ref, tgt_ref = old_source.tower_ref, old_target.tower_ref
            t0 = {"source": await self.snapshot_collections(src_ref),
                  "target": await self.snapshot_collections(tgt_ref)}

            probe_code, _ = await self._run_tool("unit_struct_probe.py")
            if probe_code != 0:
                return "NO_SAFE_PROPOSAL", {
                    "reason": "STALE_PROPOSAL:refresh-probe-failed"}
            probe_path = (self.root / "runtime/research/units"
                          / f"unit-struct-probe-{match_id}.json")
            try:
                probe2 = json.loads(probe_path.read_text(encoding="utf8"))
            except (OSError, ValueError):
                return "NO_SAFE_PROPOSAL", {
                    "reason": "STALE_PROPOSAL:refresh-probe-unknown"}
            if (not isinstance(probe2, dict)
                    or probe2.get("match_id") != match_id
                    or not isinstance(probe2.get("rows"), list)):
                return "NO_SAFE_PROPOSAL", {
                    "reason": "STALE_PROPOSAL:match-changed"}
            prows2 = {row["packed_id"]: row for row in probe2["rows"]
                      if isinstance(row, dict) and "packed_id" in row}
            states2 = self.build_states(anchor, prows2, time.time())
            by_id2 = {state.tower_id: state for state in states2}
            source2 = by_id2.get(proposal.source_tower_id)
            target2 = by_id2.get(proposal.target_tower_id)
            if source2 is None or target2 is None:
                return "NO_SAFE_PROPOSAL", {
                    "reason": "STALE_PROPOSAL:tower-gone"}
            current_deployable = getattr(
                getattr(source2, "deployable_force", None), "counts", None)
            if (not isinstance(current_deployable, dict)
                    or current_deployable != proposal.source_deployable_force):
                return "NO_SAFE_PROPOSAL", {
                    "reason": "STALE_PROPOSAL:deployable-changed"}

            state_kwargs = {
                "camera": [0], "deployable_counts": current_deployable,
                "now": now,
            }
            original_versions = build_token(
                match_id, self.cycle_seq, 1.0, 1.0,
                old_source, old_target, **state_kwargs)
            refreshed_versions = build_token(
                match_id, self.cycle_seq, 1.0, 1.0,
                source2, target2, **state_kwargs)
            if (original_versions.source_state_version
                    != refreshed_versions.source_state_version
                    or original_versions.target_state_version
                    != refreshed_versions.target_state_version):
                return "NO_SAFE_PROPOSAL", {
                    "reason": "STALE_PROPOSAL:tower-state-changed"}

            screen_map, canvas = await self.fresh_screen_map(anchor["towers"])
            if not canvas:
                return "NO_SAFE_PROPOSAL", {"reason": "camera_failed"}
            if (action_kind in ("REINFORCE_SELF", "ATTACK_ENEMY")
                    and (proposal.action_kind != action_kind
                         or proposal.cycle_id != cycle_id)):
                return "NO_SAFE_PROPOSAL", {
                    "reason": "STALE_PROPOSAL:action-cycle-changed"}
            if action_kind in ("REINFORCE_SELF", "ATTACK_ENEMY"):
                preflight, refreshed = prepare_move(
                    proposal, by_id2, screen_map, canvas, match_id,
                    time.time(), cycle_id=cycle_id)
            else:
                preflight, refreshed = prepare_move(
                    proposal, by_id2, screen_map, canvas, match_id, time.time())
            if preflight != PREFLIGHT_READY:
                reason = refreshed[0] if isinstance(refreshed, tuple) else refreshed
                return "NO_SAFE_PROPOSAL", {"reason": reason}
            token, token_status = self._build_dispatch_token(
                match_id, self.cycle_seq, source2, target2, canvas,
                current_deployable)
            if token_status != "OK":
                self.journal["last_action_validity"] = {
                    "action_id": action_id, "match_id": match_id,
                    "cycle_id": self.cycle_seq, "status": token_status}
                return "NO_SAFE_PROPOSAL", {"reason": token_status}
            self.journal["last_action_validity"] = {
                "action_id": action_id, "match_id": match_id,
                "cycle_id": self.cycle_seq, "status": "OK"}
            source_snapshot = await self.snapshot_collections(source2.tower_ref)
            source_safety = self.evaluate_live_source_safety(
                match_id, source2, source_snapshot,
                proposal.source_deployable_force,
                tower_states_by_id=by_id2)
            self.journal["last_source_safety"] = {
                "action_id": action_id, "match_id": match_id,
                "observed_at": time.time(),
                **source_safety}
            if source_safety.get("result") != "SAFE":
                return "NO_SAFE_PROPOSAL", {
                    "reason": "SOURCE_SAFETY_" + str(
                        source_safety.get("reason", "UNKNOWN"))}
            threat_block = self._multi_threat_action_block(
                match_id, self.cycle_seq)
            if threat_block is not None:
                return "NO_SAFE_PROPOSAL", threat_block
            reservation_held = (
                self._reservations.holder(refreshed.source_tower_id)
                == action_id
                and self._reservations.holder(refreshed.target_tower_id)
                == action_id)
            prepared_neutral = None
            prepared_reinforcement = None
            prepared_attack = None
            if action_kind == "REINFORCE_SELF":
                defense_assessment = self.journal.get("defense_assessment")
                selected_defense = (
                    defense_assessment.get("arbitration")
                    if isinstance(defense_assessment, dict) else None)
                selected_candidate = (selected_defense.get("candidate")
                                      if isinstance(selected_defense, dict)
                                      else None)
                prepared_reinforcement = {
                    "match_id": match_id,
                    "cycle_id": cycle_id,
                    "source_tower_id": refreshed.source_tower_id,
                    "target_tower_id": refreshed.target_tower_id,
                    "source_owner": getattr(source2, "owner", None),
                    "target_owner": getattr(target2, "owner", None),
                    "full_deployable_force": dict(
                        proposal.source_deployable_force or {}),
                    "unit_count": sum(
                        (proposal.source_deployable_force or {}).values()),
                    "command_validated": (
                        isinstance(selected_candidate, dict)
                        and selected_candidate.get("command_validated") is True),
                    "preflight": "READY",
                    "source_safety": "SAFE",
                    "source_safety_evidence": {
                        "result": "SAFE", "match_id": match_id,
                        "source_tower_id": refreshed.source_tower_id,
                        "proposed_units": dict(
                            proposal.source_deployable_force or {}),
                    },
                    "action_validity_token": token_status,
                    "validity_token_match_id": match_id,
                    "validity_token_cycle_id": cycle_id,
                    "reservation": "HELD" if reservation_held else "MISSING",
                    "reservation_action_id": action_id,
                }
            elif action_kind == "ATTACK_ENEMY":
                prepared_attack = {
                    "action_kind": "ATTACK_ENEMY",
                    "match_id": match_id,
                    "cycle_id": cycle_id,
                    "source_tower_id": refreshed.source_tower_id,
                    "target_tower_id": refreshed.target_tower_id,
                    "source_owner": getattr(source2, "owner", None),
                    "target_owner": getattr(target2, "owner", None),
                    "defender_owner_id": attack_candidate.get(
                        "defender_owner_id"),
                    "proposed_units": dict(
                        proposal.source_deployable_force or {}),
                    "preflight": "READY",
                    "source_safety": "SAFE",
                    "source_safety_evidence": {
                        **(source_safety if isinstance(source_safety, dict)
                           else {}),
                        "result": "SAFE", "match_id": match_id,
                        "source_tower_id": refreshed.source_tower_id,
                        "proposed_units": dict(
                            proposal.source_deployable_force or {}),
                    },
                    "action_validity_token": token_status,
                    "validity_token_match_id": match_id,
                    "validity_token_cycle_id": cycle_id,
                    "reservation": "HELD" if reservation_held else "MISSING",
                    "reservation_action_id": action_id,
                }
            else:
                prepared_neutral = {
                    "validated": True,
                    "match_id": match_id,
                    "cycle_id": cycle_id,
                    "source_tower_id": refreshed.source_tower_id,
                    "target_tower_id": refreshed.target_tower_id,
                    "preflight": "READY",
                    "source_safety": "SAFE",
                    "action_validity_token": token_status,
                    "reservation": "HELD" if reservation_held else "MISSING",
                    "reservation_action_id": action_id,
                }
            decision = self._arbitrate_prepared_action(
                match_id, cycle_id, prepared_neutral,
                prepared_reinforcement=prepared_reinforcement,
                prepared_attack=prepared_attack,
                require_execution_evidence=True)
            decision_action = decision.get(
                "blocked_action", decision.get("action", "ABSTAIN"))
            if (decision_action != action_kind
                    or decision.get("execution_ready") is False):
                return "NO_SAFE_PROPOSAL", {
                    "reason": "PVP_ARBITRATION_" + str(
                        decision_action),
                    "match_id": match_id,
                    "pvp_arbitration": decision,
                }
            before = {"match_id": match_id,
                      "source": self.snapshot_tower(source2),
                      "target": self.snapshot_tower(target2)}
            src_ref, tgt_ref = source2.tower_ref, target2.tower_ref
            browser_game = getattr(self.browser, "game", {}) or {}
            attack_proof_bundle = None
            if (action_kind == "ATTACK_ENEMY"
                    and isinstance(attack_candidate, dict)):
                battle_proof = attack_candidate.get(
                    "battle_differential_evidence")
                server_proof = attack_candidate.get(
                    "server_acceptance_evidence")
                if isinstance(battle_proof, dict) and isinstance(
                        server_proof, dict):
                    attack_proof_bundle = {
                        "schema_version": 1,
                        "battle_differential_evidence_id":
                            attack_candidate.get(
                                "battle_differential_evidence_id"),
                        "server_acceptance_evidence_id":
                            attack_candidate.get(
                                "server_acceptance_evidence_id"),
                        "battle_differential_evidence": dict(battle_proof),
                        "server_acceptance_evidence": dict(server_proof),
                    }
            attack_validation_status = (
                "VALIDATION_PENDING"
                if action_kind == "ATTACK_ENEMY"
                and attack_proof_bundle is None else None)
            pending_record = {
                "schema_version": 1,
                "action_id": action_id,
                "match_id": match_id,
                "source_tower_id": refreshed.source_tower_id,
                "target_tower_id": refreshed.target_tower_id,
                "action_kind": action_kind,
                "cycle_id": cycle_id,
                "status": "PREPARED",
                "created_at": time.time(),
                "browser_session_id": getattr(
                    self.browser, "session_id", None),
                "join_clicks": browser_game.get("join_clicks"),
                "before": before,
            }
            if attack_validation_status is not None:
                pending_record["attack_validation_status"] = (
                    attack_validation_status)
            if attack_proof_bundle is not None:
                pending_record["attack_proof_bundle"] = attack_proof_bundle
            self._set_pending_dispatch(pending_record)
            exec_result = await self.app.execute_move({
                "source": list(refreshed.source_screen_xy),
                "target": list(refreshed.target_screen_xy),
                "proposal_id": action_id,
                "match_id": match_id,
                "origin": "LIVE_CONTROLLER"})
            if not exec_result.get("sent"):
                self._clear_pending_dispatch()
                self.cooldowns[pair] = now + 300
                self.journal["failed_actions"] = self.journal.get("failed_actions", 0) + 1
                return "PRECHECK_REJECTED", {"reason": exec_result.get("result")}
            dispatch_sent_at = time.time()
            arbitration_record = self.journal.get("pvp_arbitration")
            if isinstance(arbitration_record, dict):
                arbitration_record.update(
                    selected_action_executed=True,
                    dispatched_action=action_kind,
                    dispatched_at=dispatch_sent_at)
            pending_dispatch = self.journal.get("pending_dispatch")
            if isinstance(pending_dispatch, dict):
                pending_dispatch.update(status="SENT",
                                        sent_at=dispatch_sent_at)
                self._persist_pending_dispatch(pending_dispatch)
            # sent_actions 僅計 UI 事件已送出；只有下方雙端驗證才算
            # force_observed_dispatches 或 verified_moves。
            self.journal["sent_actions"] = self.journal.get("sent_actions", 0) + 1
            t1 = {"source": await self.snapshot_collections(src_ref),
                  "target": await self.snapshot_collections(tgt_ref)}
            await asyncio.sleep(8)
            after = {"match_id": match_id}
            try:
                code, _ = await self._run_tool("unit_struct_probe.py")
                if code == 0:
                    probe_after = json.loads(probe_path.read_text(encoding="utf8"))
                    prows_after = {row["packed_id"]: row
                                   for row in probe_after.get("rows", [])
                                   if isinstance(row, dict) and "packed_id" in row}
                    states_after = self.build_states(
                        anchor, prows_after, time.time())
                    by_id_after = {state.tower_id: state
                                   for state in states_after}
                    src_after = by_id_after.get(refreshed.source_tower_id)
                    tgt_after = by_id_after.get(refreshed.target_tower_id)
                    after = {"match_id": match_id,
                             "source": self.snapshot_tower(src_after) if src_after else None,
                             "target": self.snapshot_tower(tgt_after) if tgt_after else None,
                             "force_observed": False}
            except (OSError, ValueError):
                pass
            t2 = {"source": await self.snapshot_collections(src_ref),
                  "target": await self.snapshot_collections(tgt_ref)}
            await asyncio.sleep(6)
            t3 = {"source": await self.snapshot_collections(src_ref),
                  "target": await self.snapshot_collections(tgt_ref)}
            expected_path = self._expected_path(by_id2, refreshed)
            force_match = self.correlate_force(
                t0["source"],
                [t1["source"], t2["source"], t3["source"]], expected_path,
                dispatched_at=dispatch_sent_at)
            force_match_t = self.correlate_force(
                t0["target"],
                [t1["target"], t2["target"], t3["target"]], expected_path,
                dispatched_at=dispatch_sent_at)
            dispatch_observation = self._record_dispatch_observation(
                action_id, match_id, force_match, force_match_t)
            if action_kind != "REINFORCE_SELF":
                self._learn_self_id_from_verified_dispatch(
                    match_id, top, refreshed, t1["source"], force_match,
                    force_match_t)
            after["force_match"] = force_match
            after["force_match_target"] = force_match_t
            after["dispatch_observation"] = dispatch_observation
            after["force_observed"] = dispatch_observation == "FORCE_OBSERVED"
            pending_dispatch = self.journal.get("pending_dispatch")
            if isinstance(pending_dispatch, dict):
                pending_dispatch.update(
                    dispatch_observation=dispatch_observation,
                    source_force_match=force_match,
                    target_force_match=force_match_t)
                self._persist_pending_dispatch(pending_dispatch)
            self._save_force_bundle(action_id, match_id, refreshed, t0, t1,
                                    t2, force_match, force_match_t, t3,
                                    dispatch_sent_at=dispatch_sent_at)
            self._record_battle_differential(
                match_id, action_id, refreshed, before, after, top)
            verdict = verify_post_action(before, after, refreshed)
            try:
                self.app.record_verification(verdict, match_id)
            except Exception:
                pass
            if action_kind != "REINFORCE_SELF":
                pending = self.journal.get("pending_captures", [])
                pending_record = {
                    "target": refreshed.target_tower_id,
                    "match_id": match_id,
                    "action_id": action_id,
                    "action_kind": action_kind,
                    "dispatch_observation": dispatch_observation,
                    "target_owner_before": (before.get("target") or {}).get(
                        "owner"),
                    "since": dispatch_sent_at,
                }
                if attack_validation_status == "VALIDATION_PENDING":
                    pending_record["attack_validation_status"] = (
                        "VALIDATION_PENDING")
                pending.append(pending_record)
                self.journal["pending_captures"] = pending[-20:]
            self.journal["last_action"] = {
                "origin": "LIVE_CONTROLLER",
                "action_kind": action_kind,
                "cycle_id": cycle_id,
                "source": refreshed.source_tower_id,
                "target": refreshed.target_tower_id,
                "dispatch_observation": dispatch_observation,
                "match_id": match_id, "sent_at": dispatch_sent_at}
            if action_kind == "ATTACK_ENEMY" and isinstance(
                    attack_candidate, dict):
                self.journal["last_action"].update({
                    "battle_differential_evidence_id": attack_candidate.get(
                        "battle_differential_evidence_id"),
                    "server_acceptance_evidence_id": attack_candidate.get(
                        "server_acceptance_evidence_id"),
                    "attack_proof_bundle": attack_proof_bundle,
                    "attack_validation_status": (
                        attack_validation_status or "PROOF_PRESENT"),
                })
            self.journal["last_verification"] = verdict
            self._finish_pending_dispatch(verdict)
            if verdict in ("TARGET_CAPTURED", "TARGET_CONTESTED",
                           "FORCE_OBSERVED", "SOURCE_CHANGED"):
                self.journal["verified_moves"] = self.journal.get("verified_moves", 0) + 1
                if (verdict == "TARGET_CAPTURED"
                        and action_kind == "EXPAND_NEUTRAL"):
                    self.journal["verified_expansions"] = self.journal.get("verified_expansions", 0) + 1
                self.journal["consecutive_failures"] = 0
            else:
                self.journal["consecutive_failures"] = self.journal.get("consecutive_failures", 0) + 1
                self.cooldowns[pair] = now + 600
            try:
                self.app.append_live_action({
                    "action_id": action_id,
                    "origin": "LIVE_CONTROLLER",
                    "action_kind": action_kind,
                    "cycle_id": cycle_id,
                    "match": match_id,
                    "source": refreshed.source_tower_id,
                    "target": refreshed.target_tower_id,
                    "planner_score": top.get("heuristic_score"),
                    "preflight": "READY_TO_EXECUTE",
                    "dispatch": {"sent_at": dispatch_sent_at, "coords": [
                        list(refreshed.source_screen_xy),
                        list(refreshed.target_screen_xy)],
                        "observation": dispatch_observation},
                    "force_match_source": force_match,
                    "force_match_target": force_match_t,
                    **({
                        "battle_differential_evidence_id": attack_candidate.get(
                            "battle_differential_evidence_id"),
                        "server_acceptance_evidence_id": attack_candidate.get(
                            "server_acceptance_evidence_id"),
                        "attack_proof_bundle": attack_proof_bundle,
                        "attack_validation_status": (
                            attack_validation_status or "PROOF_PRESENT"),
                    } if action_kind == "ATTACK_ENEMY"
                    and isinstance(attack_candidate, dict) else {}),
                    "verifier": verdict,
                    "result": verdict,
                    "duration_s": round(time.time() - now, 1)})
            except Exception:
                pass
            return "VERIFYING", {
                "verdict": verdict,
                "dispatch_observation": dispatch_observation,
                "proposal": {"source": refreshed.source_tower_id,
                             "target": refreshed.target_tower_id}}

        phase, info = await self._with_action_reservation(
            action_id, proposal.source_tower_id, proposal.target_tower_id,
            dispatch_reserved)
        if isinstance(info, dict):
            info = dict(info)
            info.setdefault("match_id", match_id)
        return phase, info

    def _expected_path(self, by_id, refreshed):
        try:
            return (refreshed.source_tower_id, refreshed.target_tower_id)
        except AttributeError:
            return None

    def _record_battle_differential(self, match_id, action_id, refreshed,
                                      before, after, candidate):
        """保存行動快照，並明確標示 PvP 戰鬥評估是否適用／已執行。

        追蹤到部隊不等於已執行戰鬥預測；所有權或玩家 ID 不足時只記錄原因。
        """
        try:
            source_owner = (candidate or {}).get("source_owner")
            target_owner = (candidate or {}).get("target_owner")
            source_owner_id = (candidate or {}).get(
                "source_owner_id", (candidate or {}).get("attacker_owner_id"))
            target_owner_id = (candidate or {}).get(
                "target_owner_id", (candidate or {}).get("defender_owner_id"))
            prediction = None
            if source_owner == "SELF" and source_owner_id is None:
                self._select_player_id_match(match_id)
                source_owner_id = self._player_ids.self_id()
            if target_owner == "NEUTRAL":
                evaluation_status = "NOT_APPLICABLE_NEUTRAL_TARGET"
                evaluation_reason = "target_is_neutral"
            elif target_owner == "SELF":
                evaluation_status = "NOT_APPLICABLE_SELF_TARGET"
                evaluation_reason = "target_is_self"
            elif target_owner == "ENEMY":
                valid_owner_ids = all(type(value) is int and value > 0
                                      for value in (source_owner_id,
                                                    target_owner_id))
                if valid_owner_ids:
                    prediction = (candidate or {}).get("battle_prediction")
                    if ((candidate or {}).get("static_support_status")
                            == "SUPPORTED"
                            and (candidate or {}).get("projected_result")
                            in ("ATTACK_WIN", "ATTACK_LOSE",
                                "ATTACK_CONTESTED")):
                        evaluation_status = (
                            "STATIC_PREDICTION_RUNTIME_PENDING")
                        evaluation_reason = (
                            "post-action battle differential is not yet validated")
                    else:
                        prediction = None
                        evaluation_status = "NOT_EVALUATED_MODEL"
                        evaluation_reason = "battle_evaluator_not_invoked"
                else:
                    prediction = None
                    evaluation_status = "NOT_EVALUATED_UNKNOWN_IDS"
                    evaluation_reason = "owner_ids_not_recorded"
            else:
                prediction = None
                evaluation_status = "NOT_EVALUATED_UNKNOWN_RELATION"
                evaluation_reason = "target_owner_relation_unknown"
            dest = (self.root / "runtime/research/pvp_validation"
                    / str(action_id).replace(":", "_").replace(">", "_").replace("<", "_"))
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "battle-differential.json").write_text(json.dumps({
                "action_id": action_id, "match_id": match_id,
                "cycle_id": getattr(refreshed, "cycle_id", None),
                "source_tower": refreshed.source_tower_id,
                "target_tower": refreshed.target_tower_id,
                "target_type": (candidate or {}).get("target_type"),
                "source_owner": source_owner,
                "target_owner": target_owner,
                "source_owner_id": source_owner_id,
                "target_owner_id": target_owner_id,
                "before_attacker": ((before.get("source") or {}).get("units")),
                "before_defender": ((before.get("target") or {}).get("units")),
                "after_source": ((after or {}).get("source") or {}).get("units"),
                "after_target": (after or {}).get("target"),
                "evaluation_status": evaluation_status,
                "evaluation_reason": evaluation_reason,
                "prediction": prediction,
                "force_match_source": (after or {}).get("force_match"),
                "force_match_target": (after or {}).get("force_match_target"),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _save_force_bundle(self, action_id, match_id, refreshed,
                           t0, t1, t2, force_match, force_match_t, t3=None,
                           dispatch_sent_at=None):
        """保存自主验证束：T0/T1/T2＋比对结果。"""
        try:
            safe = str(action_id)
            for _ch in (chr(60), chr(62), chr(58), chr(34), chr(47), chr(92), chr(124), chr(63), chr(42)):
                safe = safe.replace(_ch, chr(95))
            safe = safe.replace("-" + chr(62), "_to_")
            dest = (self.root / "runtime/research/forces/autonomous_validation"
                    / safe)
            dest.mkdir(parents=True, exist_ok=True)
            bundle = {"action_id": action_id, "match_id": match_id,
                      "cycle_id": getattr(refreshed, "cycle_id", None),
                      "source": refreshed.source_tower_id,
                      "target": refreshed.target_tower_id,
                      "dispatched_at": dispatch_sent_at,
                      "t0": t0, "t1": t1, "t2": t2, "t3": t3,
                      "force_match_source": force_match,
                      "force_match_target": force_match_t,
                      "dispatch_observation": self._dispatch_observation_status(
                          force_match, force_match_t),
                      "sent_actions_context": self.journal.get("sent_actions", 0)}
            (dest / "bundle.json").write_text(
                json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            self.journal["last_bundle"] = str(dest.relative_to(self.root))
        except Exception as exc:
            self.journal["last_bundle_error"] = f"{type(exc).__name__}: {exc}"[:200]

    async def run_loop(self, interval: float = 2.0):
        """常駐主迴圈（app 以背景任務啟動），預設每 2 秒重規劃。"""
        if (isinstance(interval, bool) or not isinstance(interval, (int, float))
                or not math.isfinite(float(interval)) or interval < 1):
            raise ValueError("即時控制器週期間隔必須是至少 1 秒的有限數值")
        self.running = True
        while self.running and not self.app.gate.stop_event.is_set():
            now = time.time()
            self.cycle_seq += 1
            cycle_id = self.cycle_seq
            if self.journal.get("consecutive_failures", 0) >= 3:
                self.phase = "PAUSED_FAILSAFE"
                self._save()
                return
            try:
                phase, info = await asyncio.wait_for(self.cycle_once(), timeout=900)
            except asyncio.TimeoutError:
                phase, info = "ERROR", {"error": "cycle-watchdog-timeout"}
            except Exception as exc:
                phase, info = "ERROR", {"error": str(exc)[:200]}
            self.phase = phase
            self.cycle_count += 1
            self.last_cycle_at = now
            self._record_cycle(cycle_id, now, phase, info)
            self.journal["cycles"] = self.journal.get("cycles", 0) + 1
            if phase == "NO_SAFE_PROPOSAL":
                self.journal["no_safe_proposals"] = self.journal.get("no_safe_proposals", 0) + 1
            self.journal["current_phase"] = phase
            self._save()
            await asyncio.sleep(interval)

    _REASON_TAXONOMY = {
        "platform_not_in_match": "MATCH_TRANSITION",
        "not_in_match": "NOT_IN_MATCH",
        "anchor_unavailable": "OBSERVATION_STALE",
        "anchor_failed": "ANCHOR_STALE",
        "anchor_unstable": "ANCHOR_STALE",
        "anchor_quality": "ANCHOR_STALE",
        "probe_failed": "PROBE_STALE",
        "probe_unavailable": "PROBE_STALE",
        "tower_gone": "STALE_WORLD",
        "match_switched_during_anchor": "MATCH_TRANSITION",
        "no_candidate": "NO_SAFE_PROPOSAL",
        "pair_cooldown": "COOLDOWN",
        "camera_failed": "CAMERA_STALE",
        "autonomy_paused": "AUTHORIZATION_DISABLED",
        "ACTION_VERIFICATION_PENDING": "WAITING_VERIFICATION",
        "attack-dispatch-evidence-incomplete": "ACTION_GATE_BLOCKED",
        "PVP_ATTACK_FORCE_MISMATCH": "ACTION_GATE_BLOCKED",
        "static-robust-pvp-enemy-attack-pending-runtime-verification":
            "VALIDATION_PENDING",
    }

    @classmethod
    def normalize_reason(cls, reason) -> str:
        """no_action_reason 標準分類（§4）。未知一律 OTHER_EXPLICIT_REASON。"""
        if not isinstance(reason, str) or not reason:
            return "OTHER_EXPLICIT_REASON"
        if reason.startswith("SOURCE_SAFETY_"):
            return "SOURCE_SAFETY_BLOCKED"
        if reason.startswith("STALE_PROPOSAL:"):
            return "STALE_PROPOSAL"
        if reason.startswith("RESOURCE_RESERVED:"):
            return "RESOURCE_RESERVED"
        if reason in ("NO_SELF_SOURCE", "NO_NEUTRAL_NEIGHBOR",
                      "NO_DEPLOYABLE_FORCE", "COOLDOWN", "STALE_WORLD",
                      "MATCH_STALE", "OBSERVATION_STALE", "ANCHOR_STALE",
                      "PROBE_STALE", "CAMERA_STALE",
                      "FORCE_STALE", "CONTROLLER_STALE", "RECOVERY_STALE",
                      "UNKNOWN_STALE",
                      "STALE_CAMERA", "PRECHECK_REJECTED",
                      "AUTHORIZATION_DISABLED", "ACTION_GATE_BLOCKED",
                      "MATCH_TRANSITION", "NOT_IN_MATCH",
                      "NO_SAFE_PROPOSAL", "WAITING_VERIFICATION",
                      "VALIDATION_PENDING"):
            return reason
        if reason.startswith(("PVP_DEFENSE_DECISION_",
                              "PVP_ATTACK_DECISION_",
                              "PVP_ARBITRATION_")):
            return "ACTION_GATE_BLOCKED"
        if reason.startswith(("PVP_REINFORCEMENT_PROPOSAL_",
                              "PVP_ATTACK_PROPOSAL_")):
            return "NO_SAFE_PROPOSAL"
        return cls._REASON_TAXONOMY.get(reason, "OTHER_EXPLICIT_REASON")

    @staticmethod
    def summarize_rejections(rejections: list, limit: int = 20) -> dict:
        """彙總候選拒絕原因，只留有界範例供診斷顯示。"""
        rows = rejections if isinstance(rejections, list) else []
        counts = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            reason = row.get("reason")
            if isinstance(reason, str):
                counts[reason] = counts.get(reason, 0) + 1
        examples = [row for row in rows if isinstance(row, dict)][:limit]
        return {"rejection_count": len(rows), "rejection_counts": counts,
                "rejection_examples": examples}

    def _record_cycle(self, cycle_id: int, now: float, phase: str, info: dict):
        """單一權威週期狀態（Dashboard 全區顯示同一 cycle_id）。"""
        info = info if isinstance(info, dict) else {"detail": str(info)}
        record = {"cycle_id": cycle_id, "timestamp": now,
                  "match_id": info.get("match_id"),
                  "phase": phase,
                  "candidate_count": info.get("candidate_count"),
                  "proposal": info.get("proposal"),
                  "preflight": info.get("preflight"),
                  "authorization": self.app.gate.authorized,
                  "gate_state": self.app.gate.state,
                  "dispatch": info.get("dispatch"),
                  "verification": info.get("verdict", info.get("verification")),
                  "no_action_reason": self.normalize_reason(info.get("reason")),
                  "raw_reason": info.get("reason"),
                  "rejection_count": info.get("rejection_count"),
                  "rejection_counts": info.get("rejection_counts", {}),
                  "rejection_examples": info.get("rejection_examples", [])}
        blocker = self.journal.get("observation_blocker")
        if isinstance(blocker, dict):
            record["observation_blocker"] = dict(blocker)
        recent = self.journal.get("recent_cycles", [])
        recent.append(record)
        self.journal["recent_cycles"] = recent[-20:]
        self.journal["last_cycle"] = record
        self.journal["last_info"] = {
            key: record[key] for key in (
                "match_id", "candidate_count", "raw_reason", "preflight",
                "proposal", "verification", "rejection_count",
                "rejection_counts", "rejection_examples")}

    def _save(self):
        payload = {"phase": self.phase, "heartbeat": self.heartbeat(),
                   "journal": self.journal, "updated_at": time.time()}
        (self.root / "runtime/state/live_controller.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
