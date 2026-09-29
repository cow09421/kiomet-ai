"""PvP 觀察束必須以明確事件身分綁定，缺值不可由時間推定。"""
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from combat_evidence_arming import collect_once, watch  # noqa: E402


def _binding(action_id="match-A:101->202:1000", kind="ATTACK_ENEMY"):
    return {
        "action_id": action_id, "match_id": "match-A", "cycle_id": 7,
        "source_tower_id": 101, "target_tower_id": 202,
        "action_kind": kind,
        "source_owner": "SELF",
        "target_owner": "ENEMY" if kind == "ATTACK_ENEMY" else "SELF",
        "route": [101, 202], "world_hash": "world-7",
        "proposal_version": "proposal-7", "token_version": "token-7",
        "reservation_id": "reservation-7",
    }


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows),
                    encoding="utf-8")


def _action(**overrides):
    row = {
        **_binding(), "origin": "LIVE_CONTROLLER",
        "dispatch": {"sent_at": 1000.0}, "logged_at": 1004.0,
        "verifier": "TARGET_CAPTURED", "result": "TARGET_CAPTURED",
        "stages": {
            "t_minus_2": {"captured_at": 990.0, "world_hash": "world-5",
                           "screenshot_base64": "must-not-be-copied"},
            "t_minus_1": {"captured_at": 995.0, "world_hash": "world-6"},
        },
    }
    row.update(overrides)
    return row


def _pending(**overrides):
    row = {
        **_binding(), "status": "SENT", "created_at": 999.0,
        "sent_at": 1000.0,
        "before": {
            "match_id": "match-A",
            "source": {"owner": "SELF", "units": {"Fighter": 8}},
            "target": {"owner": "ENEMY", "units": {"Fighter": 2}},
        },
    }
    row.update(overrides)
    return row


def _force(**overrides):
    row = {
        **_binding(), "dispatched_at": 1000.0,
        "t0": {"captured_at": 999.0, "marker": "before"},
        "t1": {"captured_at": 1001.0, "marker": "after-dispatch"},
        "t2": {"captured_at": 1002.0, "marker": "moving-sample"},
        "t3": {"captured_at": 1003.0, "marker": "arrival-sample"},
        "force_match_source": "FORCE_MATCH_VERIFIED",
        "force_match_target": "FORCE_MATCH_VERIFIED",
        "dispatch_observation": "FORCE_OBSERVED",
    }
    row.update(overrides)
    return row


def _battle(**overrides):
    row = {
        **_binding(), "evaluation_status": "STATIC_PREDICTION_RUNTIME_PENDING",
        "before_attacker": {"Fighter": 8},
        "before_defender": {"Fighter": 2},
        "after_target": {"owner": "SELF"},
    }
    row.update(overrides)
    return row


def _write_action_sources(root: Path, action=None, pending=None,
                          force=None, battle=None):
    action = action or _action()
    pending = pending or _pending()
    force = force or _force()
    battle = battle or _battle()
    _write_jsonl(root / "runtime/logs/live_actions.jsonl", [action])
    _write_json(root / "runtime/state/pending-live-dispatch.json", pending)
    _write_json(root / "runtime/research/forces/autonomous_validation"
                / "case" / "bundle.json", force)
    _write_json(root / "runtime/research/pvp_validation" / "case"
                / "battle-differential.json", battle)


def test_collects_action_lifecycle_by_explicit_identity(tmp_path):
    _write_action_sources(tmp_path)

    report = collect_once(tmp_path)

    assert report["status"] == "SNAPSHOT_WITH_CASES"
    assert report["armed"] is False
    assert report["bundle_count"] == 1
    bundle = report["bundles"][0]
    assert bundle["binding_status"] == "BOUND"
    assert bundle["collection_status"] == "COLLECTED"
    assert bundle["proof_status"] == "NOT_EVALUATED"
    assert bundle["binding"]["route"] == [101, 202]
    assert bundle["binding"]["reservation_id"] == "reservation-7"
    assert all(bundle["stages"][name] is not None for name in (
        "t_minus_2", "t_minus_1", "t0", "pre_dispatch", "dispatch",
        "post_dispatch", "moving", "arrival", "battle", "verdict",
        "t_plus_1", "t_plus_2"))
    assert bundle["stages"]["arrival"]["evidence"]["status"] == (
        "TARGET_FORCE_OBSERVED")
    assert "screenshot_base64" not in bundle["stages"]["t_minus_2"]["evidence"]


def test_rejects_cross_cycle_or_cross_match_evidence(tmp_path):
    _write_action_sources(
        tmp_path,
        force=_force(cycle_id=8),
        battle=_battle(match_id="another-match"),
    )

    bundle = collect_once(tmp_path)["bundles"][0]

    assert bundle["binding_status"] == "BINDING_CONFLICT"
    assert bundle["stages"]["post_dispatch"] is None
    assert bundle["stages"]["battle"] is None
    assert any("cycle_id" in issue for issue in bundle["issues"])
    assert any("match_id" in issue for issue in bundle["issues"])


def test_does_not_infer_attack_kind_from_enemy_owner(tmp_path):
    old = _action()
    old.pop("action_kind")
    old["target_owner"] = "ENEMY"
    _write_jsonl(tmp_path / "runtime/logs/live_actions.jsonl", [old])

    report = collect_once(tmp_path)

    assert report["bundle_count"] == 0
    assert report["source_health"]["unclassified_action_rows"] == 1
    assert report["status"] == "SNAPSHOT_NO_CASES"


def test_collects_reinforcement_only_when_kind_and_owners_are_explicit(tmp_path):
    row = _action(**_binding(kind="REINFORCE_SELF"))
    # Keep the before snapshot consistent with the explicitly typed action.
    pending = _pending(**_binding(kind="REINFORCE_SELF"),
                       before={"match_id": "match-A",
                               "source": {"owner": "SELF"},
                               "target": {"owner": "SELF"}})
    force = _force(**_binding(kind="REINFORCE_SELF"))
    battle = _battle(**_binding(kind="REINFORCE_SELF"))
    _write_action_sources(tmp_path, action=row, pending=pending,
                          force=force, battle=battle)

    bundle = collect_once(tmp_path)["bundles"][0]

    assert bundle["action_kind"] == "REINFORCE_SELF"
    assert bundle["binding"]["target_owner"] == "SELF"
    assert bundle["collection_status"] == "COLLECTED"


def test_threat_history_uses_same_explicit_force_identity_and_keeps_unknown(tmp_path):
    def threat_state(cycle, row):
        return {
            "status": "OBSERVED_CANDIDATE", "freshness": "FRESH",
            "match_id": "match-A", "cycle_id": cycle,
            "observed_at": 2000.0 + cycle,
            "coverage": {"complete": True}, "threats": [row],
        }

    threat = {
        "source_force_id": 700, "source_tower_id": 101,
        "target_tower_id": 202, "owner_id": 55,
        "source_owner": "ENEMY", "target_owner": "SELF",
        "owner_relation": "ENEMY", "route": [101, 202],
        "units": {"Fighter": 4}, "eta_ticks": 3, "eta_seconds": 12,
    }
    unknown = {**threat, "source_force_id": 701,
               "source_owner": None, "target_owner": None,
               "owner_relation": "UNKNOWN"}
    journal = {
        "threat_state": {**threat_state(12, threat),
                         "threats": [threat, unknown]},
        "recent_cycles": [
            {"threat_state": threat_state(10, threat)},
            {"threat_state": threat_state(11, threat)},
        ],
    }
    _write_json(tmp_path / "runtime/state/live_controller.json",
                {"journal": journal})

    bundles = collect_once(tmp_path)["bundles"]
    enemy = next(item for item in bundles
                 if item.get("classification") == "ENEMY_TO_SELF")
    uncertain = next(item for item in bundles
                     if item.get("classification") == "UNKNOWN")

    assert enemy["stages"]["t_minus_2"] is not None
    assert enemy["stages"]["t_minus_1"] is not None
    assert enemy["stages"]["t0"] is not None
    assert enemy["binding"]["cycle_id"] == 12
    assert uncertain["binding"]["target_owner"] is None
    assert "source_owner" in uncertain["missing"]


def test_single_atomic_output_and_retention_cap(tmp_path):
    first = _action()
    second = _action(action_id="match-A:102->203:1001",
                     source_tower_id=102, target_tower_id=203,
                     cycle_id=8, dispatch={"sent_at": 1001.0},
                     logged_at=1005.0)
    _write_jsonl(tmp_path / "runtime/logs/live_actions.jsonl", [first, second])
    output = "runtime/research/combat_evidence_arming/latest.json"

    one = collect_once(tmp_path, max_bundles=1)
    two = collect_once(tmp_path, max_bundles=1)

    assert one["bundle_count"] == two["bundle_count"] == 1
    assert two["omitted_bundle_count"] == 1
    assert list((tmp_path / "runtime/research/combat_evidence_arming").glob("*.json")) == [
        tmp_path / output]
    assert json.loads((tmp_path / output).read_text(encoding="utf-8"))["bundle_count"] == 1


def test_watch_is_explicitly_armed_and_overwrites_the_same_file(tmp_path):
    _write_jsonl(tmp_path / "runtime/logs/live_actions.jsonl", [])

    report = watch(tmp_path, interval=0.1, max_cycles=2)

    assert report["armed"] is False
    assert report["mode"] == "WATCH_STOPPED"
    assert report["watch_cycles"] == 2
    assert report["status"] == "WATCH_STOPPED_NO_CASES"
    assert len(list((tmp_path / "runtime/research/combat_evidence_arming")
                    .glob("*.json"))) == 1


def test_refuses_output_outside_project_and_invalid_watch_limits(tmp_path):
    with pytest.raises(ValueError, match="inside project root"):
        collect_once(tmp_path, tmp_path.parent / "outside.json")
    with pytest.raises(ValueError, match="between 0.1 and 60"):
        watch(tmp_path, interval=0, max_cycles=1)
