"""PvP 即時案例句柄：真實狀態 → 評估器輸入。

核心紀律：數字玩家編號未知即 ABSTAIN（不行動）。
SELF 編號只能從己方已派部隊的 +12 學得；此前一切需編號的
評估一律 UNKNOWN。絕不編造編號。
"""
from __future__ import annotations

import math
import time

from kiomet_ai.observe import UNIT_NAMES

ORDINARY_UNIT_NAMES = tuple(UNIT_NAMES[:6])
SPECIAL_UNIT_NAMES = tuple(UNIT_NAMES[6:])


class PlayerIdRegistry:
    """關係→數字編號集合。SELF 只能由己方部隊觀測寫入。"""

    def __init__(self):
        self._by_relation: dict = {}

    def observe(self, relation: str, owner_id: int | None):
        if type(owner_id) is int and owner_id > 0 and relation in (
                "SELF", "ALLY", "ENEMY", "NEUTRAL"):
            ids = self._by_relation.setdefault(relation, set())
            ids.add(owner_id)

    def observe_verified_self_dispatch(
            self, source_relation: str, source_tower_id: int,
            target_tower_id: int, force_match_status: str,
            observed_forces: list) -> int | None:
        """只從精確驗證的己方派兵記錄學習 SELF owner ID。"""
        if (source_relation != "SELF"
                or force_match_status != "FORCE_MATCH_VERIFIED"
                or type(source_tower_id) is not int or source_tower_id <= 0
                or type(target_tower_id) is not int or target_tower_id <= 0
                or source_tower_id == target_tower_id
                or not isinstance(observed_forces, list)):
            return None
        matches = []
        for force in observed_forces:
            if not isinstance(force, dict):
                continue
            path = force.get("path")
            if (not isinstance(path, (list, tuple)) or len(path) < 2
                    or any(type(tower_id) is not int or tower_id <= 0
                           for tower_id in path)):
                continue
            if tuple(path[-2:]) == (target_tower_id, source_tower_id):
                matches.append(force)
        if len(matches) != 1:
            return None
        owner_id = matches[0].get("owner_id")
        if type(owner_id) is not int or owner_id <= 0:
            return None
        known_self_ids = self._by_relation.get("SELF", set())
        if known_self_ids and known_self_ids != {owner_id}:
            return None
        self.observe("SELF", owner_id)
        return owner_id

    def unique_id(self, relation: str) -> int | None:
        """關係恰有一個有效 ID 才回傳；缺失或歧義一律 UNKNOWN。"""
        if relation not in ("SELF", "ALLY", "ENEMY", "NEUTRAL"):
            return None
        ids = self._by_relation.get(relation, set())
        if not isinstance(ids, set) or len(ids) != 1:
            return None
        owner_id = next(iter(ids))
        return (owner_id if type(owner_id) is int and owner_id > 0
                else None)

    def self_id(self) -> int | None:
        return self.unique_id("SELF")

    def known_id(self, relation: str, owner_id: int | None) -> bool:
        return (type(owner_id) is int and owner_id > 0
                and owner_id in self._by_relation.get(relation, set()))


def threat_from_force(force, self_tower_ids: set,
                      tower_positions: dict | None = None) -> dict | None:
    """MovingForceState → IncomingThreat 輸入（目標須為 SELF 塔）。"""
    from kiomet_ai.force import eta_ticks, threat_eta_seconds, unit_speed
    if force is None or force.current_destination not in self_tower_ids:
        return None
    force_units = getattr(force, "units", None)
    counts = getattr(force_units, "counts", None)
    ticks = None
    if tower_positions is not None:
        src = tower_positions.get(force.current_source)
        dst = tower_positions.get(force.current_destination)
        progress = getattr(force, "progress", None)
        speed_flag = getattr(force, "speed_flag", None)
        valid_xy = lambda point: (
            isinstance(point, (tuple, list)) and len(point) == 2
            and all(type(value) in (int, float)
                    and math.isfinite(value) for value in point))
        if (valid_xy(src) and valid_xy(dst)
                and type(progress) is int and 0 <= progress <= 255
                and type(speed_flag) is int and speed_flag in (0, 1)
                and _valid_unit_vector(counts) and any(counts.values())):
            distance = math.hypot(dst[0] - src[0], dst[1] - src[1])
            speed = unit_speed(force_units)
            if math.isfinite(distance) and distance > 0:
                ticks = eta_ticks(progress, speed, distance, speed_flag)
    return {
        "force_identity": None,
        "target_tower_id": force.current_destination,
        "source_tower_id": force.current_source,
        "source_player": force.owner_id,
        "owner_id": force.owner_id,
        "owner_relation": force.owner_relation,
        "units": (dict(counts) if _valid_unit_vector(counts) else None),
        "progress": force.progress,
        "eta_ticks": ticks,
        "eta_seconds": threat_eta_seconds(ticks),
        "freshness": "FRESH",
        "confidence": "CANDIDATE",
    }


def candidate_inbound_threats(snapshot: dict, target_state,
                              tower_states_by_id: dict | None,
                              match_id: str, self_id: int | None = None,
                              player_ids: PlayerIdRegistry | None = None) -> dict:
    """從完整同局 inbound snapshot 建唯讀候選威脅；絕不當作行動授權。"""
    from kiomet_ai.force import (MAX_PATH_LEN, ForceUnits, MovingForceState,
                                 _valid_tower_id)

    unknown = lambda reason: {"status": "UNKNOWN", "reason": reason,
                              "threats": []}
    if (not isinstance(snapshot, dict) or snapshot.get("error")
            or snapshot.get("match_id") != match_id):
        return unknown("snapshot-match-or-read-invalid")
    if (target_state is None
            or getattr(target_state, "match_id", None) != match_id
            or getattr(target_state, "owner", None) != "SELF"
            or target_state.freshness(match_id, time.time()) != "FRESH"):
        return unknown("target-state-not-fresh-self")
    inbound = ((snapshot.get("collections") or {}).get("inbound"))
    if not isinstance(inbound, dict):
        return unknown("inbound-collection-unknown")
    length, entries = inbound.get("length"), inbound.get("entries")
    if (type(length) is not int or length < 0
            or not isinstance(entries, list) or len(entries) != length):
        return unknown("inbound-collection-incomplete")
    if length == 0:
        return {"status": "CLEAR", "reason": "complete-empty-inbound",
                "threats": []}

    states = tower_states_by_id if isinstance(tower_states_by_id, dict) else {}
    positions = {}
    for tower_id, state in states.items():
        if (type(tower_id) is not int or state is None
                or getattr(state, "match_id", None) != match_id
                or state.freshness(match_id, time.time()) != "FRESH"):
            continue
        x, y = getattr(state, "world_x", None), getattr(state, "world_y", None)
        if (type(x) in (int, float) and math.isfinite(x)
                and type(y) in (int, float) and math.isfinite(y)):
            positions[tower_id] = (float(x), float(y))

    threats = []
    for entry in entries:
        if not isinstance(entry, dict):
            return unknown("inbound-force-row-invalid")
        path, units = entry.get("path"), entry.get("units")
        owner_id = entry.get("owner_id")
        if (not isinstance(path, (list, tuple))
                or not 2 <= len(path) <= MAX_PATH_LEN
                or any(type(tower_id) is not int
                       or not _valid_tower_id(tower_id) for tower_id in path)
                or len(set(path)) != len(path)
                or path[-1] == path[-2]
                or path[-2] != target_state.tower_id
                or type(owner_id) is not int or owner_id <= 0
                or not _valid_unit_vector(units) or not any(units.values())
                or type(entry.get("speed_flag")) is not int
                or entry["speed_flag"] not in (0, 1)
                or type(entry.get("progress")) is not int
                or not 0 <= entry["progress"] <= 255
                or type(entry.get("endurance")) is not int
                or not 0 <= entry["endurance"] <= 255):
            return unknown("inbound-force-row-invalid")

        source_state = states.get(path[-1])
        source_owner = getattr(source_state, "owner", None)
        target_owner = getattr(target_state, "owner", None)
        relation = "UNKNOWN"
        if source_owner in ("ENEMY", "ALLY") and target_owner == "SELF":
            relation = source_owner
        elif (source_owner == "SELF" and target_owner == "SELF"
              and type(self_id) is int and owner_id == self_id):
            relation = "SELF"
        known_relations = []
        if player_ids is not None:
            known_relations = [candidate for candidate in (
                "SELF", "ALLY", "ENEMY", "NEUTRAL")
                if player_ids.known_id(candidate, owner_id)]
        if known_relations and known_relations != [relation]:
            relation = "UNKNOWN"

        force = MovingForceState(
            match_id=match_id, timestamp=time.time(),
            collection_role="INBOUND", anchor_tower_id=target_state.tower_id,
            owner_id=owner_id, owner_relation=relation,
            units=ForceUnits(tag=0, counts=dict(units), status="CANDIDATE"),
            path=tuple(path), current_source=path[-1],
            current_destination=path[-2], final_destination=path[0],
            speed_flag=entry["speed_flag"], progress=entry["progress"],
            endurance=entry["endurance"], evidence_status="CANDIDATE",
            raw_ref=entry.get("ref"))
        fact = threat_from_force(force, {target_state.tower_id}, positions)
        if fact is None:
            return unknown("inbound-force-target-invalid")
        fact["match_id"] = match_id
        fact["confidence"] = "CANDIDATE"
        fact["relation_confidence"] = (
            "CANDIDATE" if relation != "UNKNOWN" else "UNKNOWN")
        fact["eta_status"] = (
            "CANDIDATE" if type(fact.get("eta_ticks")) is int else "UNKNOWN")
        threats.append(fact)
    return {"status": "OBSERVED_CANDIDATE",
            "reason": "complete-readonly-inbound-snapshot",
            "threats": threats}


def _special_free(counts: dict | None) -> bool | None:
    """無 Ruler／Shell／Emp／Nuke 才 True；未知 None。"""
    if not isinstance(counts, dict):
        return None
    if any(type(counts.get(name)) is not int or not 0 <= counts[name] <= 255
           for name in SPECIAL_UNIT_NAMES):
        return None
    return not any(counts[name] for name in SPECIAL_UNIT_NAMES)


def _ordered_threats(threats: list) -> list | None:
    """只排序可信的非負整數 ETA；缺失或型別錯誤時回 None。"""
    if not isinstance(threats, list):
        return None
    if any(not isinstance(threat, dict)
           or type(threat.get("eta_ticks")) is not int
           or threat["eta_ticks"] < 0
           for threat in threats):
        return None
    return sorted(threats, key=lambda threat: threat["eta_ticks"])


def _valid_unit_vector(units: dict) -> bool:
    """要求十種兵種都明確出現；缺欄不能默認成 0。"""
    return (isinstance(units, dict)
            and set(units) == set(UNIT_NAMES)
            and all(type(units[name]) is int and 0 <= units[name] <= 255
                    for name in UNIT_NAMES))


def _valid_player_id(owner_id) -> bool:
    return type(owner_id) is int and owner_id > 0


def _tower_ordinary_unit_vector(state) -> dict | None:
    """只接受 MANY 塔的完整六種普通守軍數量。"""
    counts = getattr(state, "unit_counts", None)
    if getattr(counts, "units_kind", None) != "MANY":
        return None
    values = {name: getattr(counts, name.lower(), None)
              for name in ORDINARY_UNIT_NAMES}
    if any(type(count) is not int or not 0 <= count <= 255
           for count in values.values()):
        return None
    return values


def battle_case_for_tower_attack(source_state, target_state,
                                 self_owner_id: int | None,
                                 attacker_owner_id: int | None,
                                 defender_owner_id: int | None,
                                 attacker_aura: bool | None,
                                 defender_aura: bool | None,
                                 capacities: dict) -> dict | None:
    """SELF→ENEMY 塔戰案例；任一未知回 None（ABSTAIN）。"""
    if (not _valid_player_id(self_owner_id)
            or not _valid_player_id(attacker_owner_id)
            or not _valid_player_id(defender_owner_id)
            or attacker_owner_id != self_owner_id
            or defender_owner_id == self_owner_id
            or type(attacker_aura) is not bool
            or type(defender_aura) is not bool):
        return None
    for state in (source_state, target_state):
        if state is None or state.unit_counts is None:
            return None
    if (getattr(source_state, "owner", None) != "SELF"
            or getattr(target_state, "owner", None) != "ENEMY"):
        return None
    deployable = source_state.deployable_force
    if (deployable is None
            or not _valid_unit_vector(deployable.counts)):
        return None
    if _special_free(deployable.counts) is not True:
        return None
    defender_units = _tower_ordinary_unit_vector(target_state)
    if defender_units is None:
        return None
    attacker_units = {n: (deployable.counts.get(n) or 0)
                      for n in ORDINARY_UNIT_NAMES}
    capacity = capacities.get(target_state.tower_type)
    if not isinstance(capacity, dict):
        return None
    return {
        "world_context_required": False,
        "observed_tick": 0,
        "attacker_units": attacker_units,
        "defender_units": defender_units,
        "special_unit_flags": {"ruler": False, "shell": False,
                               "emp": False, "nuke": False},
        "attacker_owner_relation": "SELF",
        "defender_owner_relation": "ENEMY",
        "self_owner_id": self_owner_id,
        "attacker_aura_snapshot": attacker_aura,
        "defender_aura_snapshot": defender_aura,
        "ruler_aura_state": {
            "attacker": {"ruler_unit_present": False,
                         "aura_flag_snapshot": attacker_aura},
            "defender": {"ruler_unit_present": False,
                         "aura_flag_snapshot": defender_aura},
        },
        "shield_state": {"attacker": attacker_units.get("Shield", 0),
                         "defender": defender_units.get("Shield", 0)},
        "battle_kind": "force_vs_tower",
        "target_branch": "tower_combat",
        "tower_type": target_state.tower_type,
        "tower_capacity": dict(capacity),
        "attacker_owner_id": attacker_owner_id,
        "defender_owner_id": defender_owner_id,
    }


def evaluate_attack_candidate(
        source_state, target_state, current_match_id: str,
        self_owner_id: int | None, attacker_owner_id: int | None,
        defender_owner_id: int | None, attacker_aura: bool | None,
        defender_aura: bool | None, *,
        source_safety_evidence: dict | None = None,
        battle_differential_validated: bool = False,
        server_acceptance_validated: bool = False,
        now: float | None = None,
        marginal_survivor_max: int | None = None) -> dict:
    """評估新鮮的 SELF→ENEMY 相鄰攻擊，不派兵。

    safe_attack_candidate 表示已有執行期戰鬥與接受證據；
    dispatch_safe_candidate 表示靜態鏡像明確支援且預測穩健勝利，
    可進入即時安全閘門，但結果仍須派後驗證。
    """
    source_id = getattr(source_state, "tower_id", None)
    target_id = getattr(target_state, "tower_id", None)

    def abstain(reason: str) -> dict:
        return {
            "source_tower_id": source_id, "target_tower_id": target_id,
            "result": "UNSUPPORTED", "legality": "UNKNOWN",
            "evaluation_status": "UNKNOWN", "safe_attack_candidate": False,
            "unsupported_reason": reason,
        }

    if not isinstance(current_match_id, str) or not current_match_id:
        return abstain("attack match is unknown")
    if (source_state is None or target_state is None
            or getattr(source_state, "match_id", None) != current_match_id
            or getattr(target_state, "match_id", None) != current_match_id):
        return abstain("attack states are missing or from another match")
    if (type(source_id) is not int or source_id <= 0
            or type(target_id) is not int or target_id <= 0
            or source_id == target_id):
        return abstain("attack tower identity is invalid")
    if (getattr(source_state, "owner", None) != "SELF"
            or getattr(target_state, "owner", None) != "ENEMY"):
        return abstain("attack requires observed SELF-to-ENEMY ownership")
    neighbors = getattr(source_state, "neighbors", None)
    if not isinstance(neighbors, (tuple, list, set)) or target_id not in neighbors:
        return abstain("enemy target is not a verified direct neighbor")

    now = time.time() if now is None else now
    if (type(now) not in (int, float) or not math.isfinite(now)
            or any(not callable(getattr(state, "freshness", None))
                   or state.freshness(current_match_id, now) != "FRESH"
                   for state in (source_state, target_state))):
        return abstain("attack state is stale or freshness is unknown")
    if (getattr(getattr(source_state, "unit_counts", None), "units_kind", None)
            != "MANY"):
        return abstain("source mobile unit composition is unknown")
    deployable = getattr(source_state, "deployable_force", None)
    counts = getattr(deployable, "counts", None)
    mobile_unit_names = tuple(
        name for name in ORDINARY_UNIT_NAMES if name != "Shield")
    if (getattr(source_state, "deployable_force_confidence", None)
            not in ("DERIVED", "VERIFIED")
            or not _valid_unit_vector(counts)
            or not any(counts[name] for name in mobile_unit_names)):
        return abstain("source deployable force is unknown or empty")
    if (not isinstance(source_safety_evidence, dict)
            or source_safety_evidence.get("result") != "SAFE"
            or source_safety_evidence.get("match_id") != current_match_id
            or type(source_safety_evidence.get("source_tower_id")) is not int
            or source_safety_evidence["source_tower_id"] != source_id
            or not _valid_unit_vector(
                source_safety_evidence.get("proposed_units"))
            or source_safety_evidence["proposed_units"] != counts):
        return abstain("source safety is not verified for this exact dispatch")

    from kiomet_ai.battle_mirror import CAPACITIES
    from kiomet_ai.pvp import evaluate_attack

    battle_case = battle_case_for_tower_attack(
        source_state, target_state, self_owner_id, attacker_owner_id,
        defender_owner_id, attacker_aura, defender_aura, CAPACITIES)
    if battle_case is None:
        return abstain("attack battle case requires complete known identity and units")
    battle_case["battle_differential_validated"] = (
        battle_differential_validated is True)
    evidence = {
        "source_is_self": True,
        "source_has_full_mobile_force": True,
        "target_is_enemy": True,
        "target_is_direct_neighbor": True,
        "path_valid": True,
        "world_fresh": True,
        "target_owner_fresh": True,
        "command_kind": "DeployForce",
        "server_acceptance_validated": server_acceptance_validated is True,
    }
    mobile_force = {name: counts[name] for name in mobile_unit_names}
    result = evaluate_attack({
        "legality_evidence": evidence, "deployable_force": mobile_force,
        "battle_case": battle_case,
        **({"marginal_survivor_max": marginal_survivor_max}
           if marginal_survivor_max is not None else {}),
    })
    return {"source_tower_id": source_id, "target_tower_id": target_id,
            **result}


def evaluate_source_safety(post_dispatch_defender_units: dict | None,
                           threats: list, capacities: dict,
                           tower_type: str | None,
                           self_id: int | None = None,
                           enemy_id: int | None = None) -> dict:
    """來源塔安全閘：派兵後殘留能否擋住已知威脅。

    threats: IncomingThreat dict 列表（需 eta_ticks＋units＋source）。
    回傳 SAFE / UNSAFE(SOURCE_WOULD_BECOME_UNSAFE) / UNKNOWN。
    無已知威脅 → SAFE（無事實可判不安全；中立擴張不受此閘影響）。
    """
    from kiomet_ai.pvp import evaluate_battle
    if not _valid_unit_vector(post_dispatch_defender_units):
        return {"result": "UNKNOWN", "reason": "remaining-defenders-unknown"}
    if not isinstance(threats, list):
        return {"result": "UNKNOWN", "reason": "threat-list-unknown"}
    if not threats:
        return {"result": "SAFE", "reason": "no-known-threats"}
    if not _special_free(post_dispatch_defender_units):
        return {"result": "UNKNOWN", "reason": "remaining-defenders-special"}
    if tower_type not in (capacities or {}):
        return {"result": "UNKNOWN", "reason": "tower-capacity-unknown"}
    ordered = _ordered_threats(threats)
    if ordered is None:
        return {"result": "UNKNOWN", "reason": "threat-eta-unknown"}
    etas = [th["eta_ticks"] for th in ordered]
    if len(set(etas)) != len(etas):
        return {"result": "UNKNOWN", "reason": "UNSUPPORTED_TEMPORAL_CASE"}
    defenders = dict(post_dispatch_defender_units)
    for threat in ordered:
        units = threat.get("units")
        if not _valid_unit_vector(units) or not any(units.values()):
            return {"result": "UNKNOWN", "reason": "threat-units-unknown"}
        if not _special_free(units):
            return {"result": "UNKNOWN", "reason": "threat-special-units"}
        case = _defense_case(defenders, units, tower_type, capacities,
                             self_id, enemy_id)
        if case is None:
            return {"result": "UNKNOWN", "reason": "case-unbuildable"}
        result = evaluate_battle(case)
        if not result.get("supported"):
            return {"result": "UNKNOWN", "reason": "mirror-unsupported"}
        if result.get("winner") != "defender":
            return {"result": "UNSAFE",
                    "reason": "SOURCE_WOULD_BECOME_UNSAFE",
                    "threat": threat.get("force_identity"),
                    "eta_ticks": threat.get("eta_ticks")}
        survivors = result.get("defender_survivors") or {}
        defenders = {name: int(survivors.get(name, 0)) for name in defenders}
    return {"result": "SAFE", "reason": "all-known-threats-held"}


def _defense_case(defender_units: dict, attacker_units: dict,
                  tower_type: str, capacities: dict,
                  self_id: int | None = None,
                  enemy_id: int | None = None) -> dict | None:
    """ENEMY 攻 SELF 塔戰案例。編號未知回 None（ABSTAIN，不編造）。"""
    if (not _valid_player_id(self_id) or not _valid_player_id(enemy_id)
            or self_id == enemy_id):
        return None
    if not all(_valid_unit_vector(units)
               for units in (defender_units, attacker_units)):
        return None
    if any(units.get(name, 0) for units in (defender_units, attacker_units)
           for name in ("Ruler", "Shell", "Emp", "Nuke")):
        return None
    names = ORDINARY_UNIT_NAMES
    try:
        defender = {n: int(defender_units.get(n, 0)) for n in names}
        attacker = {n: int(attacker_units.get(n, 0)) for n in names}
    except (TypeError, ValueError):
        return None
    if not any(attacker.values()) or not any(defender.values()):
        return None
    return {
        "world_context_required": False, "observed_tick": 0,
        "attacker_units": attacker, "defender_units": defender,
        "special_unit_flags": {"ruler": False, "shell": False,
                               "emp": False, "nuke": False},
        "attacker_owner_relation": "ENEMY",
        "defender_owner_relation": "SELF",
        "self_owner_id": self_id,
        "attacker_aura_snapshot": False,
        "defender_aura_snapshot": False,
        "ruler_aura_state": {
            "attacker": {"ruler_unit_present": False, "aura_flag_snapshot": False},
            "defender": {"ruler_unit_present": False, "aura_flag_snapshot": False}},
        "shield_state": {"attacker": attacker.get("Shield", 0),
                         "defender": defender.get("Shield", 0)},
        "battle_kind": "force_vs_tower",
        "target_branch": "tower_combat",
        "tower_type": tower_type,
        "tower_capacity": dict(capacities.get(tower_type, {})),
        "attacker_owner_id": enemy_id, "defender_owner_id": self_id,
    }


def evaluate_multi_threat(defender_units: dict | None,
                          threats: list, capacities: dict,
                          tower_type: str | None,
                          self_id: int | None = None,
                          enemy_id: int | None = None) -> dict:
    """多威脅逐場評估：依 arrival_tick 排序，殘兵帶入下一場。

    同 tick 多支 → UNSUPPORTED_TEMPORAL_CASE（首版 ABSTAIN）。
    第一場守住 ≠ 解除；全部守住才 SAFE。
    enemy_id 綁定未帶逐列身分的整批輸入。若每個 threat 都帶有完整
    owner_id／owner_relation，允許不同敵方 ID，但每列仍須是 ENEMY；
    傳入 enemy_id 時則維持整批 ID 綁定，矛盾或部分身分一律 UNKNOWN。
    """
    from kiomet_ai.pvp import evaluate_battle
    if (not _valid_unit_vector(defender_units)
            or any(type(defender_units.get(n)) is not int
                   for n in ORDINARY_UNIT_NAMES)):
        return {"result": "UNKNOWN", "reason": "defender-unknown"}
    if not _special_free(defender_units):
        return {"result": "UNKNOWN", "reason": "defender-special-units"}
    if tower_type not in (capacities or {}):
        return {"result": "UNKNOWN", "reason": "tower-capacity-unknown"}
    if enemy_id is not None and not _valid_player_id(enemy_id):
        return {"result": "UNKNOWN", "reason": "enemy-id-invalid"}
    ordered = _ordered_threats(threats)
    if ordered is None:
        return {"result": "UNKNOWN", "reason": "threat-eta-unknown"}
    etas = [th["eta_ticks"] for th in ordered]
    if len(set(etas)) != len(etas):
        return {"result": "UNKNOWN",
                "reason": "UNSUPPORTED_TEMPORAL_CASE",
                "detail": "same-tick forces lack validated ordering"}
    current = dict(defender_units)
    runtime_validation_required = False
    for index, threat in enumerate(ordered):
        units = threat.get("units")
        if not _valid_unit_vector(units) or not any(units.values()):
            return {"result": "UNKNOWN", "reason": "threat-units-unknown",
                    "resolved_before": index}
        if not _special_free(units):
            return {"result": "UNKNOWN", "reason": "threat-special-units",
                    "resolved_before": index}
        has_owner_id = "owner_id" in threat
        has_owner_relation = "owner_relation" in threat
        if has_owner_id != has_owner_relation:
            return {"result": "UNKNOWN",
                    "reason": "threat-owner-evidence-incomplete",
                    "resolved_before": index}
        attacker_id = enemy_id
        if has_owner_id:
            owner_id = threat.get("owner_id")
            if (threat.get("owner_relation") != "ENEMY"
                    or type(owner_id) is not int or owner_id <= 0
                    or owner_id == self_id
                    or (enemy_id is not None and owner_id != enemy_id)):
                return {"result": "UNKNOWN",
                        "reason": "threat-owner-conflicts-with-batch",
                        "resolved_before": index}
            attacker_id = owner_id
        names = ORDINARY_UNIT_NAMES
        case = _defense_case(
            {n: int(current.get(n, 0)) for n in UNIT_NAMES},
            {n: int(units.get(n, 0)) for n in UNIT_NAMES},
            tower_type, capacities, self_id, attacker_id)
        if case is None:
            return {"result": "UNKNOWN", "reason": "case-unbuildable",
                    "resolved_before": index}
        result = evaluate_battle(case)
        if not result.get("supported"):
            return {"result": "UNKNOWN", "reason": "mirror-unsupported",
                    "resolved_before": index}
        runtime_validation_required = (
            runtime_validation_required
            or result.get("runtime_validation_required") is True)
        if result.get("winner") != "defender":
            return {"result": "UNSAFE", "reason": "tower-lost",
                    "lost_at_index": index,
                    "eta_ticks": threat.get("eta_ticks"),
                    "runtime_validation_required": runtime_validation_required,
                    "first_loss": {
                        "index": index,
                        "threat": dict(threat),
                        "defenders_before_loss": dict(current),
                        "battle_case": case,
                        "battle_evaluation": result,
                    }}
        survivors = result.get("defender_survivors") or {}
        current = {n: int(survivors.get(n, 0)) for n in names}
        current.update({name: 0 for name in SPECIAL_UNIT_NAMES})
    return {"result": "SAFE", "reason": "all-threats-held",
            "final_defenders": current,
            "runtime_validation_required": runtime_validation_required}
