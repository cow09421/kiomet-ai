"""恢復證據包（P0 §6）。

Recovery 成功不是「renderer 回來」，而是完整鏈：
crash → recovery stage → reacquire match → fresh observation
→ controller cycle → planner decision → action / abstain。

本模組只記錄這條鏈，不 soak、不推測；缺階段回 PARTIAL，stage FAILED 回 FAILED。
純邏輯，不觸碰 app/browser/supervisor/live_controller。
"""
from __future__ import annotations

STAGES = ("DETECTED", "RECOVERING_PAGE", "RECOVERING_CHROMIUM",
          "REACQUIRING_MATCH", "READY", "FAILED")

# 完成鏈所需的最小證據鍵
REQUIRED_KEYS = ("crash_at", "new_match_id", "first_fresh_observation_at",
                 "first_cycle_at", "first_decision_at")


class RecoveryProof:
    def __init__(self):
        self.reset()

    def reset(self):
        self.crash_at = None
        self.stage = None
        self.stages_seen = []
        self.new_page_pid = None
        self.new_browser_pid = None
        self.new_match_id = None
        self.first_fresh_observation_at = None
        self.first_cycle_at = None
        self.first_cycle_id = None
        self.first_decision_at = None
        self.first_decision = None
        self.first_action = None
        self.first_abstain_reason = None
        self._timeline = []  # (ts, kind)

    # ---- 記錄 ----
    def _stamp(self, ts):
        if isinstance(ts, (int, float)):
            self._timeline.append((float(ts), "event"))
            return float(ts)
        return None

    def note_crash(self, ts=None):
        if self.crash_at is None:
            self.crash_at = self._stamp(ts)
        return self

    def note_stage(self, stage, ts=None):
        if stage not in STAGES:
            raise ValueError(f"未知 stage：{stage}")
        self.stage = stage
        if stage not in self.stages_seen:
            self.stages_seen.append(stage)
        self._stamp(ts)
        return self

    def note_new_page(self, pid):
        self.new_page_pid = pid
        return self

    def note_new_browser(self, pid):
        self.new_browser_pid = pid
        return self

    def note_match(self, match_id):
        self.new_match_id = match_id
        return self

    def note_first_fresh_observation(self, ts=None):
        if self.first_fresh_observation_at is None:
            self.first_fresh_observation_at = self._stamp(ts)
        return self

    def note_first_cycle(self, cycle_id=None, ts=None):
        if self.first_cycle_at is None:
            self.first_cycle_at = self._stamp(ts)
            self.first_cycle_id = cycle_id
        return self

    def note_first_decision(self, decision=None, ts=None):
        if self.first_decision_at is None:
            self.first_decision_at = self._stamp(ts)
            self.first_decision = decision
        return self

    def note_first_action(self, action=None):
        self.first_action = action
        return self

    def note_first_abstain(self, reason=None):
        self.first_abstain_reason = reason
        return self

    # ---- 輸出 ----
    def time_ordered(self) -> bool:
        stamps = [ts for ts, _ in self._timeline]
        return all(b >= a for a, b in zip(stamps, stamps[1:]))

    def missing(self) -> list:
        miss = [k for k in REQUIRED_KEYS if getattr(self, k) is None]
        if self.first_action is None and self.first_abstain_reason is None:
            miss.append("first_action_or_abstain")
        return miss

    def verify_chain(self) -> dict:
        if self.stage == "FAILED":
            return {"status": "FAILED", "missing": self.missing(),
                    "reason": "recovery_stage_failed"}
        miss = self.missing()
        if not miss and self.time_ordered():
            return {"status": "COMPLETE", "missing": [], "reason": None}
        reason = "time_reversal" if not self.time_ordered() else "incomplete"
        return {"status": "PARTIAL", "missing": miss, "reason": reason}

    def bundle(self) -> dict:
        return {
            "crash_at": self.crash_at,
            "stage": self.stage,
            "stages_seen": list(self.stages_seen),
            "new_page_pid": self.new_page_pid,
            "new_browser_pid": self.new_browser_pid,
            "new_match_id": self.new_match_id,
            "first_fresh_observation_at": self.first_fresh_observation_at,
            "first_cycle_at": self.first_cycle_at,
            "first_cycle_id": self.first_cycle_id,
            "first_decision_at": self.first_decision_at,
            "first_decision": self.first_decision,
            "first_action": self.first_action,
            "first_abstain_reason": self.first_abstain_reason,
            "time_ordered": self.time_ordered(),
            "verification": self.verify_chain(),
        }
