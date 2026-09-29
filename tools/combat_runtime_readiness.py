"""Read-only, fail-closed audit of the current PvP runtime readiness."""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _age(now: float, timestamp: Any) -> float | None:
    if not _number(timestamp) or timestamp > now + 1:
        return None
    return max(0.0, now - timestamp)


def _check(status: str, reason: str, source: str, *, age: float | None = None,
           match_id: str | None = None, cycle_id: int | None = None,
           action_id: str | None = None) -> dict:
    return {"status": status, "reason": reason, "source": source,
            "age_seconds": age, "match_id": match_id,
            "cycle_id": cycle_id, "action_id": action_id}


def _matching_candidates(attack: dict, match_id: str, cycle_id: int) -> list[dict]:
    rows = attack.get("evaluations")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)
            and row.get("match_id") == match_id
            and row.get("cycle_id") == cycle_id
            and row.get("target_relation") == "ENEMY"]


def _candidate_gate(rows: list[dict], key: str, accepted: set[str], *,
                    source: str, match_id: str, cycle_id: int,
                    missing_reason: str) -> dict:
    if not rows:
        return _check("PARTIAL", missing_reason, source,
                      match_id=match_id, cycle_id=cycle_id)
    values = [row.get(key) for row in rows]
    if any(value in accepted for value in values):
        return _check("READY", f"current-cycle candidate has {key}", source,
                      match_id=match_id, cycle_id=cycle_id)
    if any(value is None or value in ("UNKNOWN", "NOT_CHECKED", "NOT_BUILT")
           for value in values):
        return _check("UNKNOWN", f"{key} is not established for current candidate",
                      source, match_id=match_id, cycle_id=cycle_id)
    return _check("BLOCKED", f"current candidate failed {key}: {values!r}",
                  source, match_id=match_id, cycle_id=cycle_id)


def _current_action(status_doc: dict, match_id: str | None,
                    cycle_id: int | None) -> dict | None:
    controller = status_doc.get("controller")
    if not isinstance(controller, dict):
        return None
    action = controller.get("last_action")
    if not isinstance(action, dict):
        action = status_doc.get("last_action")
    if not isinstance(action, dict):
        return None
    if action.get("match_id") != match_id or action.get("cycle_id") != cycle_id:
        return None
    return action


def build_readiness(status_doc: dict | None, *, now: float | None = None,
                    process_alive: bool | None = None,
                    evidence_index: dict | None = None,
                    replay_index: dict | None = None,
                    max_state_age: float = 30.0,
                    max_cycle_age: float = 15.0) -> dict:
    """Classify readiness from one same-run status snapshot and optional indexes.

    Missing data stays UNKNOWN/PARTIAL. Historical records are never joined to
    the current run by approximate timestamps or by a reused tower identifier.
    """
    now = time.time() if now is None else now
    source = "runtime/state/final-status.json"
    if not isinstance(status_doc, dict):
        unknown = _check("UNKNOWN", "status snapshot missing or malformed", source)
        return {"schema_version": 1, "status": "UNKNOWN",
                "reason": unknown["reason"], "match_id": None, "cycle_id": None,
                "checks": {"runtime": unknown}}

    process = status_doc.get("process") or {}
    started = process.get("started_at") if isinstance(process, dict) else None
    uptime = status_doc.get("uptime_seconds")
    captured_at = started + uptime if _number(started) and _number(uptime) else None
    snapshot_age = _age(now, captured_at)
    state = status_doc.get("state")
    pid = process.get("pid") if isinstance(process, dict) else None
    if state in {"ERROR", "STOPPED", "STOPPING", "PAUSED"}:
        runtime = _check("BLOCKED", f"runtime state is {state}", source,
                         age=snapshot_age)
    elif snapshot_age is None:
        runtime = _check("UNKNOWN", "runtime snapshot time is missing or invalid",
                         source, age=None)
    elif snapshot_age > max_state_age:
        runtime = _check("BLOCKED", "runtime snapshot is stale", source,
                         age=snapshot_age)
    elif process_alive is False:
        runtime = _check("BLOCKED", "recorded runtime process is not alive",
                         source, age=snapshot_age)
    elif process_alive is None:
        runtime = _check("UNKNOWN", "process liveness could not be confirmed",
                         source, age=snapshot_age)
    elif state == "RUNNING":
        runtime = _check("READY", "runtime is running", source, age=snapshot_age)
    else:
        runtime = _check("UNKNOWN", f"unrecognized runtime state: {state!r}",
                         source, age=snapshot_age)

    browser = status_doc.get("browser") or {}
    if not isinstance(browser, dict):
        browser = {}
    if browser.get("connected") is False:
        browser_check = _check("BLOCKED", "dedicated browser is disconnected",
                               source + "#/browser", age=snapshot_age)
    elif browser.get("connected") is True and runtime["status"] == "READY":
        browser_check = _check("READY", "dedicated browser is connected",
                               source + "#/browser", age=snapshot_age)
    else:
        browser_check = _check("UNKNOWN", "browser connection is not established",
                               source + "#/browser", age=snapshot_age)

    game = status_doc.get("game") or {}
    if not isinstance(game, dict):
        game = {}
    match = game.get("match") or {}
    if not isinstance(match, dict):
        match = {}
    match_id = match.get("id")
    in_match = game.get("state") == "IN_MATCH" and isinstance(match_id, str) and bool(match_id)
    controller = status_doc.get("controller") or {}
    if not isinstance(controller, dict):
        controller = {}
    cycle_id = controller.get("cycle_id")
    if type(cycle_id) is not int or cycle_id < 0:
        cycle_id = None

    if in_match:
        match_check = _check("READY", "current match identity is explicit",
                             source + "#/game/match", age=snapshot_age,
                             match_id=match_id, cycle_id=cycle_id)
    elif game.get("state") in {"ERROR", "UNKNOWN"}:
        match_check = _check("UNKNOWN", "current match is not established",
                             source + "#/game/match", age=snapshot_age)
    else:
        match_check = _check("BLOCKED", "no active IN_MATCH game", source + "#/game/match",
                             age=snapshot_age)

    threat = controller.get("threat_state") or {}
    if not isinstance(threat, dict):
        threat = {}
    threat_source = source + "#/controller/threat_state"
    threat_age = _age(now, threat.get("observed_at"))
    threat_bound = (in_match and threat.get("match_id") == match_id
                    and threat.get("cycle_id") == cycle_id)
    coverage = threat.get("coverage") or {}
    if not isinstance(coverage, dict):
        coverage = {}
    world_ready = (threat_bound and threat.get("freshness") == "FRESH"
                   and threat.get("status") in {"CLEAR", "OBSERVED_CANDIDATE"}
                   and coverage.get("complete") is True
                   and threat_age is not None and threat_age <= max_cycle_age)
    if not in_match:
        world = _check("UNKNOWN", "world freshness cannot be assessed outside a match",
                       threat_source, age=threat_age, match_id=match_id,
                       cycle_id=cycle_id)
    elif not threat_bound:
        world = _check("BLOCKED", "threat state is cross-match or cross-cycle",
                       threat_source, age=threat_age, match_id=match_id,
                       cycle_id=cycle_id)
    elif threat.get("freshness") == "STALE" or threat.get("status") == "STALE":
        world = _check("BLOCKED", threat.get("reason") or "world observation is stale",
                       threat_source, age=threat_age, match_id=match_id,
                       cycle_id=cycle_id)
    elif world_ready:
        world = _check("READY", "complete fresh same-match threat state",
                       threat_source, age=threat_age, match_id=match_id,
                       cycle_id=cycle_id)
    else:
        world = _check("UNKNOWN", "fresh complete same-cycle threat state is absent",
                       threat_source, age=threat_age, match_id=match_id,
                       cycle_id=cycle_id)

    blocker = controller.get("observation_blocker")
    if not isinstance(blocker, dict):
        blocker = {}
    if browser_check["status"] == "BLOCKED":
        observer = _check("BLOCKED", "dedicated game page is unavailable",
                          source + "#/browser", age=snapshot_age,
                          match_id=match_id, cycle_id=cycle_id)
    elif not in_match:
        observer = _check("UNKNOWN", "no current match observation",
                          source + "#/game", age=snapshot_age,
                          match_id=match_id, cycle_id=cycle_id)
    elif world["status"] == "READY":
        observer = _check("READY", "same-match observation is fresh and complete",
                          threat_source, age=threat_age, match_id=match_id,
                          cycle_id=cycle_id)
    else:
        observer = _check("BLOCKED" if blocker or world["status"] == "BLOCKED" else "UNKNOWN",
                          (blocker.get("reason") if blocker else world["reason"]),
                          threat_source, age=threat_age, match_id=match_id,
                          cycle_id=cycle_id)

    live = status_doc.get("live") or {}
    if not isinstance(live, dict):
        live = {}
    live_age = _age(now, live.get("captured_at"))
    if type(live.get("sequence")) is int and live["sequence"] > 0 and live_age is not None and live_age <= max_state_age:
        live_view = _check("READY", "latest in-memory spectator frame is fresh",
                           source + "#/live", age=live_age, match_id=match_id,
                           cycle_id=cycle_id)
    elif browser_check["status"] == "BLOCKED":
        live_view = _check("BLOCKED", "no spectator frame from disconnected browser",
                           source + "#/live", age=snapshot_age,
                           match_id=match_id, cycle_id=cycle_id)
    else:
        live_view = _check("UNKNOWN", "fresh in-memory spectator frame is absent",
                           source + "#/live", age=live_age, match_id=match_id,
                           cycle_id=cycle_id)

    authorization = status_doc.get("live_authorization") or {}
    if not isinstance(authorization, dict):
        authorization = {}
    if (authorization.get("enabled") is True
            and runtime["status"] == "READY"
            and isinstance(authorization.get("provenance"), str)
            and authorization["provenance"]):
        auth_check = _check("READY", "explicit live authorization is recorded",
                            source + "#/live_authorization", age=snapshot_age,
                            match_id=match_id, cycle_id=cycle_id)
    elif authorization.get("enabled") is True:
        auth_check = _check("UNKNOWN", "authorization belongs to an inactive or stale runtime",
                            source + "#/live_authorization", age=snapshot_age,
                            match_id=match_id, cycle_id=cycle_id)
    elif authorization.get("enabled") is False:
        auth_check = _check("BLOCKED", "live authorization is disabled",
                            source + "#/live_authorization", age=snapshot_age,
                            match_id=match_id, cycle_id=cycle_id)
    else:
        auth_check = _check("UNKNOWN", "authorization provenance is absent",
                            source + "#/live_authorization", age=snapshot_age,
                            match_id=match_id, cycle_id=cycle_id)

    last_cycle = (status_doc.get("controller") or {}).get("last_cycle")
    if not isinstance(last_cycle, dict):
        last_cycle = {}
    if (last_cycle.get("match_id") == match_id and last_cycle.get("cycle_id") == cycle_id
            and last_cycle.get("gate_state") == "RUNNING" and last_cycle.get("authorization") is True):
        gate = _check("READY", "latest same-match cycle passed the runtime gate",
                      source + "#/controller/last_cycle", age=snapshot_age,
                      match_id=match_id, cycle_id=cycle_id)
    elif last_cycle.get("gate_state") in {"PAUSED", "ERROR", "STOPPED"}:
        gate = _check("BLOCKED", f"last cycle gate is {last_cycle.get('gate_state')}",
                      source + "#/controller/last_cycle", age=snapshot_age,
                      match_id=match_id, cycle_id=cycle_id)
    else:
        gate = _check("UNKNOWN", "same-match authorized running cycle is absent",
                      source + "#/controller/last_cycle", age=snapshot_age,
                      match_id=match_id, cycle_id=cycle_id)

    attack = controller.get("attack_assessment") or {}
    if not isinstance(attack, dict):
        attack = {}
    attack_current = (attack.get("match_id") == match_id
                      and attack.get("cycle_id") == cycle_id)
    candidates = _matching_candidates(attack, match_id, cycle_id) if in_match and cycle_id is not None else []
    if not in_match or not attack_current:
        attack_source = _check("UNKNOWN", "no current same-match attack assessment",
                               source + "#/controller/attack_assessment",
                               age=snapshot_age, match_id=match_id, cycle_id=cycle_id)
    elif not candidates:
        attack_source = _check("PARTIAL", "no current legal ENEMY candidate; target-specific checks not exercised",
                               source + "#/controller/attack_assessment",
                               age=snapshot_age, match_id=match_id, cycle_id=cycle_id)
    else:
        attack_source = _check("READY", "current-cycle ENEMY candidate exists",
                               source + "#/controller/attack_assessment",
                               age=snapshot_age, match_id=match_id, cycle_id=cycle_id)

    if not in_match:
        self_id = _check("UNKNOWN", "no active match-bound SELF identity",
                         source + "#/controller", age=snapshot_age,
                         match_id=match_id, cycle_id=cycle_id)
    else:
        ids = [row.get("attacker_owner_id") for row in candidates
               if type(row.get("attacker_owner_id")) is int and row.get("attacker_owner_id") > 0]
        if not ids:
            explicit_id = controller.get("self_owner_id")
            if type(explicit_id) is int and explicit_id > 0 and controller.get("self_owner_id_match_id") == match_id:
                ids = [explicit_id]
        if ids and len(set(ids)) == 1:
            self_id = _check("READY", "SELF identity is positive and match-bound",
                             source + "#/controller/attack_assessment",
                             age=snapshot_age, match_id=match_id, cycle_id=cycle_id)
        elif len(set(ids)) > 1:
            self_id = _check("BLOCKED", "current candidates disagree on SELF owner ID",
                             source + "#/controller/attack_assessment",
                             age=snapshot_age, match_id=match_id, cycle_id=cycle_id)
        else:
            self_id = _check("UNKNOWN", "no explicit match-bound SELF owner ID",
                             source + "#/controller", age=snapshot_age,
                             match_id=match_id, cycle_id=cycle_id)

    threats = threat.get("threats")
    if world["status"] != "READY" or not isinstance(threats, list):
        eta_check = _check("UNKNOWN", "ETA requires a complete fresh threat scan",
                           threat_source, age=threat_age, match_id=match_id,
                           cycle_id=cycle_id)
    elif not threats:
        eta_check = _check("READY", "complete fresh scan found no inbound threats",
                           threat_source, age=threat_age, match_id=match_id,
                           cycle_id=cycle_id)
    elif all(row.get("eta_status") == "CANDIDATE" and _number(row.get("eta_ticks"))
             and _number(row.get("eta_seconds")) and row["eta_ticks"] >= 0
             and row["eta_seconds"] >= 0 for row in threats if isinstance(row, dict)) and all(isinstance(row, dict) for row in threats):
        eta_check = _check("READY", "every current threat has an explicit ETA",
                           threat_source, age=threat_age, match_id=match_id,
                           cycle_id=cycle_id)
    else:
        eta_check = _check("BLOCKED", "at least one current threat has UNKNOWN ETA",
                           threat_source, age=threat_age, match_id=match_id,
                           cycle_id=cycle_id)

    candidate_source = source + "#/controller/attack_assessment/evaluations"
    gates = {
        "battle": _candidate_gate(candidates, "battle_supported", {True},
                                  source=candidate_source, match_id=match_id,
                                  cycle_id=cycle_id,
                                  missing_reason="battle evaluation awaits a current ENEMY target"),
        "source_safety": _candidate_gate(candidates, "source_safety", {"SAFE"},
                                         source=candidate_source, match_id=match_id,
                                         cycle_id=cycle_id,
                                         missing_reason="source safety is target-specific and untested"),
        "action_validity": _candidate_gate(candidates, "action_validity_token", {"OK"},
                                            source=candidate_source, match_id=match_id,
                                            cycle_id=cycle_id,
                                            missing_reason="validity token awaits a current ENEMY target"),
        "reservation": _candidate_gate(candidates, "reservation", {"AVAILABLE_NOT_HELD", "HELD"},
                                       source=candidate_source, match_id=match_id,
                                       cycle_id=cycle_id,
                                       missing_reason="reservation awaits a current ENEMY target"),
    }
    stale_candidates = (attack.get("evaluations")
                        if isinstance(attack.get("evaluations"), list) else [])
    stale_same_match = [row for row in stale_candidates
                        if isinstance(row, dict)
                        and row.get("match_id") == match_id
                        and row.get("cycle_id") != cycle_id
                        and row.get("target_relation") == "ENEMY"]
    if in_match and stale_same_match:
        attack_source = _check("BLOCKED", "enemy candidate belongs to another cycle",
                               source + "#/controller/attack_assessment",
                               age=snapshot_age, match_id=match_id,
                               cycle_id=cycle_id)
        for check in gates.values():
            check["status"] = "BLOCKED"
            check["reason"] = "candidate evidence is from a different cycle"
    for key in ("battle", "source_safety", "action_validity", "reservation"):
        if not in_match:
            gates[key]["status"] = "UNKNOWN"
            gates[key]["reason"] = "no active match-bound candidate"

    current_action = _current_action(status_doc, match_id, cycle_id)
    if current_action is None:
        moving = _check("PARTIAL" if in_match else "UNKNOWN",
                        "no same-match action has produced moving-force evidence",
                        source + "#/controller/last_action", age=snapshot_age,
                        match_id=match_id, cycle_id=cycle_id)
        verification = _check("PARTIAL" if in_match else "UNKNOWN",
                              "no same-match action has been verified",
                              source + "#/controller/last_verification", age=snapshot_age,
                              match_id=match_id, cycle_id=cycle_id)
    else:
        moving_status = current_action.get("force_observation_status")
        moving = _check("READY" if moving_status == "FORCE_OBSERVED" else "UNKNOWN",
                        f"moving-force evidence: {moving_status or 'UNKNOWN'}",
                        source + "#/controller/last_action", age=snapshot_age,
                        match_id=match_id, cycle_id=cycle_id,
                        action_id=current_action.get("action_id"))
        verdict = current_action.get("verdict") or current_action.get("result")
        action_kind = current_action.get("action_kind")
        verified = (verdict == "ATTACK_WIN" if action_kind == "ATTACK_ENEMY"
                    else verdict in {"VERIFIED", "TARGET_CAPTURED"})
        verification = _check("READY" if verified else "UNKNOWN",
                              f"same-action verifier result: {verdict or 'UNKNOWN'}",
                              source + "#/controller/last_action", age=snapshot_age,
                              match_id=match_id, cycle_id=cycle_id,
                              action_id=current_action.get("action_id"))

    action_id = current_action.get("action_id") if current_action else None
    indexed = evidence_index.get("actions") if isinstance(evidence_index, dict) else None
    evidence_age = (_age(now, evidence_index.get("generated_at"))
                    if isinstance(evidence_index, dict) else None)
    attack_rows = [row for row in indexed if isinstance(row, dict)
                   and row.get("match_id") == match_id
                   and row.get("action_id") == action_id
                   and row.get("action_kind") == "ATTACK_ENEMY"] if isinstance(indexed, list) and action_id else []
    if not action_id:
        evidence_check = _check("PARTIAL" if in_match else "UNKNOWN",
                                "no same-match attack exists to validate",
                                "runtime/research/evidence-index.json",
                                age=evidence_age,
                                match_id=match_id, cycle_id=cycle_id)
    elif any(row.get("attack_proof_status") == "VALIDATED" for row in attack_rows):
        evidence_check = _check("READY", "same-action enemy attack proof is validated",
                                "runtime/research/evidence-index.json",
                                age=evidence_age,
                                match_id=match_id, cycle_id=cycle_id, action_id=action_id)
    else:
        evidence_check = _check("PARTIAL" if attack_rows else "UNKNOWN",
                                "same-action complete enemy proof is absent",
                                "runtime/research/evidence-index.json",
                                age=evidence_age,
                                match_id=match_id, cycle_id=cycle_id, action_id=action_id)

    cases = replay_index.get("replay", {}).get("cases") if isinstance(replay_index, dict) else None
    replay_age = (_age(now, replay_index.get("generated_at"))
                  if isinstance(replay_index, dict) else None)
    same_action_cases = [row for row in cases if isinstance(row, dict)
                         and row.get("match_id") == match_id
                         and row.get("action_id") == action_id] if isinstance(cases, list) and action_id else []
    if not action_id:
        replay_check = _check("PARTIAL" if in_match else "UNKNOWN",
                              "no same-match attack exists for replay validation",
                              "runtime/research/replay-auto-index.json",
                              age=replay_age,
                              match_id=match_id, cycle_id=cycle_id)
    elif any(row.get("status") == "REPLAYED" and row.get("target_owner") == "ENEMY"
             for row in same_action_cases):
        replay_check = _check("READY", "same-action enemy case replayed",
                              "runtime/research/replay-auto-index.json",
                              age=replay_age,
                              match_id=match_id, cycle_id=cycle_id, action_id=action_id)
    else:
        replay_check = _check("PARTIAL" if same_action_cases else "UNKNOWN",
                              "same-action enemy replay is absent or incomplete",
                              "runtime/research/replay-auto-index.json",
                              age=replay_age,
                              match_id=match_id, cycle_id=cycle_id, action_id=action_id)

    recovery = status_doc.get("recovery")
    if isinstance(recovery, dict) and recovery.get("status") == "RECOVERY_REENTRY_VERIFIED" and recovery.get("match_id") == match_id:
        recovery_check = _check("READY", "same-match recovery re-entry is verified",
                                source + "#/recovery", age=snapshot_age,
                                match_id=match_id, cycle_id=cycle_id)
    elif isinstance(recovery, dict) and recovery.get("status") in {"FAILED", "ERROR"}:
        recovery_check = _check("BLOCKED", "latest browser recovery failed",
                                source + "#/recovery", age=snapshot_age,
                                match_id=match_id, cycle_id=cycle_id)
    else:
        recovery_check = _check("UNKNOWN", "no same-match recovery re-entry proof",
                                source + "#/recovery", age=snapshot_age,
                                match_id=match_id, cycle_id=cycle_id)

    checks = {
        "runtime": runtime, "browser": browser_check, "live_view": live_view,
        "match": match_check, "observer": observer, "world_freshness": world,
        "self_identity": self_id, "threat_eta": eta_check,
        "attack_candidate": attack_source, **gates,
        "authorization": auth_check, "dispatch_gate": gate,
        "moving_force": moving, "verification": verification,
        "enemy_evidence": evidence_check, "replay": replay_check,
        "recovery_reentry": recovery_check,
    }
    hard_blockers = [name for name, check in checks.items()
                     if check["status"] == "BLOCKED"]
    core_checks = {"runtime", "browser", "match", "observer", "world_freshness",
                   "self_identity", "authorization", "dispatch_gate"}
    if hard_blockers:
        overall = "BLOCKED"
        reason = "blocking checks: " + ", ".join(hard_blockers)
    elif any(checks[name]["status"] == "UNKNOWN" for name in core_checks):
        overall, reason = "UNKNOWN", "required readiness evidence is missing"
    elif any(check["status"] in {"UNKNOWN", "PARTIAL"} for check in checks.values()):
        overall, reason = "PARTIAL", "runtime is available but the full enemy loop is unverified"
    else:
        overall, reason = "READY", "all current-match PvP readiness checks passed"
    return {"schema_version": 1, "status": overall, "reason": reason,
            "generated_at": now, "snapshot_age_seconds": snapshot_age,
            "match_id": match_id, "cycle_id": cycle_id,
            "checks": checks}


def audit(root: Path, *, now: float | None = None,
          max_state_age: float = 30.0, max_cycle_age: float = 15.0) -> dict:
    state_dir = root / "runtime" / "state"
    research_dir = root / "runtime" / "research"
    status_doc = _read_json(state_dir / "final-status.json")
    evidence_index = _read_json(research_dir / "evidence-index.json")
    replay_index = _read_json(research_dir / "replay-auto-index.json")
    alive: bool | None = None
    if isinstance(status_doc, dict):
        pid = (status_doc.get("process") or {}).get("pid")
        started = (status_doc.get("process") or {}).get("started_at")
        if type(pid) is int and pid > 0:
            try:
                import psutil
                try:
                    process = psutil.Process(pid)
                except psutil.NoSuchProcess:
                    alive = False
                except psutil.AccessDenied:
                    alive = None
                else:
                    alive = (process.is_running() and _number(started)
                             and abs(process.create_time() - started) < 10)
            except ImportError:
                alive = None
            except Exception:
                alive = False
    report = build_readiness(status_doc, now=now, process_alive=alive,
                             evidence_index=evidence_index, replay_index=replay_index,
                             max_state_age=max_state_age,
                             max_cycle_age=max_cycle_age)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Kiomet project root")
    parser.add_argument("--max-state-age", type=float, default=30.0)
    parser.add_argument("--max-cycle-age", type=float, default=15.0)
    args = parser.parse_args(argv)
    report = audit(args.root, max_state_age=args.max_state_age,
                   max_cycle_age=args.max_cycle_age)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
