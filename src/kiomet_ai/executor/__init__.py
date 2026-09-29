from dataclasses import replace
from kiomet_ai.actions import Action, ExecutionResult
from kiomet_ai.observer import MockGame
from kiomet_ai.world import Force
from kiomet_ai.control import ActionGate

class MockExecutor:
    def __init__(self, game: MockGame, gate: ActionGate):
        self._game, self._gate = game, gate
        self.sent = 0

    async def execute(self, action: Action) -> ExecutionResult:
        async def apply():
            raw = self._game.raw
            source = raw.towers.get(action.source)
            if action.kind == "Wait":
                return ExecutionResult(True, "等待；未送出遊戲操作")
            if source is None or source.owner != "self" or source.id not in raw.visible_ids:
                return ExecutionResult(False, "來源不存在、不屬於我方或不可見")
            target = raw.towers.get(action.destination)
            if action.kind == "MoveForce":
                if (target is None or target.id not in raw.visible_ids or target.id not in source.neighbors
                    or type(action.amount) is not int or action.amount <= 0 or action.amount > source.units - (15 if source.king else 1)):
                    return ExecutionResult(False, "不合法的可見鄰接移動或守軍不足")
                if target.owner not in (None, "self"):
                    return ExecutionResult(False, "第一版模擬執行器不支援攻擊敵方")
                if target.owner is None and action.amount <= target.units:
                    return ExecutionResult(False, "佔領兵力不足")
                raw.towers[source.id] = replace(source, units=source.units-action.amount)
                remaining = target.units+action.amount if target.owner == "self" else action.amount-target.units
                raw.towers[target.id] = replace(target, owner="self", units=remaining)
                raw.forces.append(Force(f"mock-{raw.tick}-{self.sent}", "self", source.id, target.id, action.amount))
            elif action.kind == "UpgradeTower":
                if action.upgrade != "Radar" or source.tower_type != "Outpost" or raw.resources < 10:
                    return ExecutionResult(False, "模擬升級條件不符")
                raw.towers[source.id] = replace(source, tower_type="Radar", upgrade_state="complete")
                raw.resources -= 10
            elif action.kind == "SetSupplyLine":
                if not target or target.id not in raw.visible_ids or target.owner != "self" or target.id not in source.neighbors or target.id == source.id:
                    return ExecutionResult(False, "補給線目的地不合法")
                if (source.id, target.id) not in raw.supply_lines:
                    raw.supply_lines.append((source.id, target.id))
            elif action.kind == "MoveKing":
                if not source.king or not target or target.owner != "self" or target.id not in raw.visible_ids or target.id not in source.neighbors or target.id == source.id:
                    return ExecutionResult(False, "國王移動目的地不合法")
                raw.towers[source.id] = replace(source, king=False)
                raw.towers[target.id] = replace(target, king=True)
            else:
                return ExecutionResult(False, "未支援的語意行動")
            self.sent += 1
            return ExecutionResult(True, "模擬操作已套用；仍需重新觀察驗證")
        result = await self._gate.dispatch(apply)
        return result or ExecutionResult(False, "已暫停、停止或發生錯誤；操作遭攔截")
