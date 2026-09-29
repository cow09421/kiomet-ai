"""里程碑覆蓋映射（契約資產，非文件）。

把 AUTONOMOUS_PVP_V0 每條成功條件映射到契約測試＋證據路徑；
任一映射目標消失即失敗，防止漂移。
只斷言存在性，不重跑被映射測試。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MILESTONE_MAP = {
    "neutral-expansion": {
        "tests": ["tests/test_battle_replay.py",
                  "tests/test_replay_real_fixture.py",
                  "tests/test_replay_report_refresh.py",
                  "tests/test_replay_stage_branches.py",
                  "tests/test_replay_dispatch_observed.py"],
        "evidence": ["runtime/logs/live_actions.jsonl"],
    },
    "threat-perception": {
        "tests": ["tests/test_threat_state_replay.py",
                  "tests/test_threat_snapshot_builder.py",
                  "tests/test_threat_eta_replay.py",
                  "tests/test_threat_eta_42_21.py",
                  "tests/test_threat_bridge.py"],
        "evidence": ["runtime/research/forces/muse-threat-eta-001.json"],
    },
    "eta": {
        "tests": ["tests/test_threat_eta_replay.py",
                  "tests/test_threat_eta_42_21.py"],
        "evidence": ["runtime/research/forces/muse-threat-eta-001.json"],
    },
    "multi-threat": {
        "tests": ["tests/test_multi_threat_sequential.py",
                  "tests/test_multi_threat_regression_suite.py"],
        "evidence": [],
    },
    "self-reinforcement": {
        "tests": ["tests/test_rescue_reinforcement_regressions.py"],
        "evidence": ["runtime/research/pvp_validation/self-self-001.json",
                     "runtime/research/pvp_validation/self-self-002.json"],
    },
    "source-safety": {
        "tests": ["tests/test_source_safety_robustness.py"],
        "evidence": [],
    },
    "battle-evaluator": {
        "tests": ["tests/test_battle_diff_pipeline.py",
                  "tests/test_replay_offline_verdict.py",
                  "tests/test_proof_envelope_verify.py"],
        "evidence": [],
    },
    "self-id": {
        "tests": ["tests/test_replay_real_fixture.py",
                  "tests/test_evidence_conversion.py"],
        "evidence": ["runtime/research/pvp_validation/self-id-001.json"],
    },
    "verifier": {
        "tests": ["tests/test_verify_hardening.py",
                  "tests/test_verifier_unknown_finalize.py",
                  "tests/test_verifier_accounting.py",
                  "tests/test_replay_dispatch_observed.py"],
        "evidence": [],
    },
    "arbitration": {
        "tests": ["tests/test_arbitration_priority.py"],
        "evidence": [],
    },
    "attack": {
        "tests": ["tests/test_attack_path_audit.py",
                  "tests/test_attack_edge_cases.py",
                  "tests/test_pvp.py",
                  "tests/test_pvp_live_attack_adapter.py",
                  "tests/test_pvp_attack_identity_validation.py",
                  "tests/test_pvp_attack_special_units.py",
                  "tests/test_live_action_arbitration.py",
                  "tests/test_live_attack_wiring.py",
                  "tests/test_live_attack_dispatch.py",
                  "tests/test_evidence_index.py"],
        "evidence": [],
    },
    "cross-match": {
        "tests": ["tests/test_cross_match_stale.py",
                  "tests/test_cross_match_stress.py"],
        "evidence": [],
    },
    "recovery": {
        "tests": ["tests/test_repair_ladder.py",
                  "tests/test_recovery_replay.py",
                  "tests/test_recovery_action_safety.py",
                  "tests/test_crash_evidence_index.py"],
        "evidence": ["runtime/research/crash/incidents"],
    },
    "pending-finalize": {
        "tests": ["tests/test_pending_finalize.py"],
        "evidence": [],
    },
    "dashboard-lifecycle": {
        "tests": ["tests/test_dashboard_lifecycle.py"],
        "evidence": [],
    },
    "live-viewer-ux": {
        "tests": ["tests/test_live_viewer_ux.py",
                   "tests/test_viewer_ai_isolation.py"],
        "evidence": [],
    },
    "tactical-world-view": {
        "tests": ["tests/test_tactical_world_view.py"],
        "evidence": [],
    },
    "stale-data-semantics": {
        "tests": ["tests/test_stale_data_semantics.py"],
        "evidence": [],
    },
    "renderer-recovery-ui": {
        "tests": ["tests/test_renderer_recovery_ui.py"],
        "evidence": ["runtime/research/crash/incidents"],
    },
    "action-timeline": {
        "tests": ["tests/test_action_timeline.py",
                   "tests/test_dashboard_timeline.py"],
        "evidence": [],
    },
    "evidence-backfill": {
        "tests": ["tests/test_evidence_backfill.py"],
        "evidence": [],
    },
}


def test_every_capability_has_tests():
    assert set(MILESTONE_MAP) == {
        "neutral-expansion", "threat-perception", "eta",
        "multi-threat", "self-reinforcement", "source-safety",
        "battle-evaluator", "self-id", "verifier", "arbitration",
        "attack", "cross-match", "recovery", "pending-finalize",
        "dashboard-lifecycle", "live-viewer-ux", "tactical-world-view",
        "stale-data-semantics", "renderer-recovery-ui", "action-timeline",
        "evidence-backfill",
    }
    for capability, mapping in MILESTONE_MAP.items():
        assert mapping["tests"], capability
        for test_file in mapping["tests"]:
            assert (ROOT / test_file).is_file(), (capability, test_file)


def test_attack_capability_maps_live_dispatch_and_proof_lifecycle():
    mapped = set(MILESTONE_MAP["attack"]["tests"])
    assert {
        "tests/test_pvp_live_attack_adapter.py",
        "tests/test_live_action_arbitration.py",
        "tests/test_live_attack_wiring.py",
        "tests/test_live_attack_dispatch.py",
        "tests/test_evidence_index.py",
    } <= mapped


def test_evidence_paths_present_when_runtime_available():
    import pytest
    missing = []
    for capability, mapping in MILESTONE_MAP.items():
        for evidence in mapping["evidence"]:
            if not (ROOT / evidence).exists():
                missing.append((capability, evidence))
    if missing:
        pytest.skip(f"runtime evidence absent (gitignored): {missing}")
