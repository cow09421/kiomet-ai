"""測試分層（§13）：smoke / pvp / replay / evidence / runtime-contract / recovery / full。

只列 MUSE 擁有檔案；GPT 檔案不列（不建議分層範圍外）。
full = tests 目錄下全部，由 pytest 自行發現。

使用：python tools/test_tiers.py [tier] [-- dry pytest args...]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

SMOKE = [
    "test_verify_hardening.py",
    "test_milestone_coverage.py",
    "test_crash_evidence_index.py",
    "test_research_corpus_inventory.py",
    "test_cli_error_paths.py",
    "test_tiers.py",
]
PVP = [
    "test_battle_diff_pipeline.py",
    "test_threat_state_replay.py",
    "test_threat_eta_replay.py",
    "test_threat_eta_42_21.py",
    "test_threat_bridge.py",
    "test_threat_snapshot_builder.py",
    "test_multi_threat_sequential.py",
    "test_multi_threat_regression_suite.py",
    "test_source_safety_robustness.py",
    "test_rescue_reinforcement_regressions.py",
    "test_arbitration_priority.py",
    "test_attack_path_audit.py",
    "test_attack_edge_cases.py",
    "test_verifier_unknown_finalize.py",
    "test_verifier_accounting.py",
]
REPLAY = [
    "test_battle_replay.py",
    "test_replay_real_fixture.py",
    "test_replay_offline_verdict.py",
    "test_replay_dispatch_observed.py",
    "test_replay_report_refresh.py",
    "test_replay_stage_branches.py",
    "test_cross_match_stale.py",
]
# 註：test_autonomous_accounting / test_evidence_index /
# test_pending_finalize / test_proof_envelope_verify 目前有 GPT 未提交
# 修改，暫不列入分層；待他 commit 後再補回。
EVIDENCE = [
    "test_evidence_conversion.py",
    "test_action_timeline.py",
    "test_cross_match_stress.py",
    "test_evidence_backfill.py",
]
RUNTIME_CONTRACT = [
    "test_dashboard_display.py",
    "test_dashboard_threat.py",
    "test_dashboard_pvp.py",
    "test_dashboard_lifecycle.py",
    "test_dashboard_timeline.py",
    "test_live_viewer_ux.py",
    "test_tactical_world_view.py",
    "test_stale_data_semantics.py",
]
RECOVERY = [
    "test_repair_ladder.py",
    "test_recovery_replay.py",
    "test_recovery_action_safety.py",
    "test_orphan_browser_reap.py",
    "test_renderer_recovery_ui.py",
]

TIERS: dict = {
    "smoke": SMOKE,
    "pvp": PVP,
    "replay": REPLAY,
    "evidence": EVIDENCE,
    "runtime-contract": RUNTIME_CONTRACT,
    "recovery": RECOVERY,
}


def tier_files(tier: str) -> list:
    """已知分層的檔案路徑；full 以外的未知分層拋錯，不編造。"""
    if tier == "full":
        return []  # 由 pytest 發現全部
    if tier not in TIERS:
        known = sorted(list(TIERS) + ["full"])
        raise KeyError(f"unknown tier {tier!r}; known: {known}")
    return [str(TESTS / name) for name in TIERS[tier]]


def run_tier(tier: str, extra: list | None = None) -> int:
    """執行分層，回傳 pytest exit code；印出耗時。"""
    files = tier_files(tier)
    cmd = ([str(ROOT / ".venv/Scripts/python.exe"), "-m", "pytest", "-q",
            "-p", "no:cacheprovider"] + (files if files else ["tests/"])
           + (extra or []))
    started = time.time()
    code = subprocess.call(cmd, cwd=str(ROOT))
    print(f"[tiers] {tier}: exit={code} elapsed={time.time()-started:.1f}s")
    return code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tier", nargs="?", default="smoke")
    parser.add_argument("extra", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    extra = [a for a in args.extra if a != "--"]
    try:
        return run_tier(args.tier, extra)
    except KeyError as exc:
        print(f"[tiers] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
