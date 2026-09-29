from kiomet_ai.actions import Action, VerificationResult
from kiomet_ai.world import ObservableState

class MockVerifier:
    def verify(self, before: ObservableState, action: Action, after: ObservableState) -> VerificationResult:
        if after.observation_id == before.observation_id or after.timestamp < before.timestamp or after.tick < before.tick:
            return VerificationResult("FAILED", "缺少操作後的新觀察")
        old, new = before.tower(action.source), after.tower(action.source)
        target_before, target_after = before.tower(action.destination), after.tower(action.destination)
        success = False
        if action.kind == "Wait":
            success = True
        elif action.kind == "UpgradeTower":
            success = bool(old and new and old.tower_type != action.upgrade and new.tower_type == action.upgrade)
        elif action.kind == "MoveForce":
            expected = None
            if target_before and action.amount:
                expected = target_before.units + action.amount if target_before.owner == before.player.id else action.amount-target_before.units
            success = bool(old and new and target_after and action.amount and
                new.units == old.units-action.amount and target_after.owner == before.player.id and target_after.units == expected)
        elif action.kind == "SetSupplyLine":
            success = (action.source, action.destination) in after.supply_lines
        elif action.kind == "MoveKing":
            success = bool(old and old.king and new and not new.king and target_after and target_after.king)
        return VerificationResult("SUCCESS" if success else "FAILED", "操作後狀態符合預期" if success else "狀態未符合預期；下一輪重新規劃，不盲目重送")
