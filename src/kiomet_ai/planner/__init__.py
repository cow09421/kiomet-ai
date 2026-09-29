from kiomet_ai.actions import Action
from kiomet_ai.world import ObservableState

class MockPlanner:
    """無瀏覽器依賴；只接收不可變、可序列化的可觀察狀態。"""
    def plan(self, state: ObservableState) -> Action:
        if not isinstance(state, ObservableState):
            raise TypeError("規劃器只接受可觀察狀態")
        own = [t for t in state.towers if t.owner == state.player.id]
        king = next((t for t in own if t.king), None)
        if king and king.units < 15:
            donor = next((t for t in own if t.id != king.id and king.id in t.neighbors and t.units > 25), None)
            if donor:
                return Action("MoveForce", donor.id, king.id, 10, reason="國王安全：增援國王所在塔")
        for source in own:
            if source.units < 25:
                continue
            target = next((t for t in state.towers if t.id in source.neighbors and t.owner is None and t.units < 10), None)
            if target:
                return Action("MoveForce", source.id, target.id, 10, reason="安全佔領：保留至少十五單位守軍")
        if king:
            front = next((t for t in own if t.id != king.id and t.units < 15 and t.id in king.neighbors), None)
            if front and king.units >= 30:
                return Action("MoveForce", king.id, front.id, 10, reason="前線增援")
        for tower in own:
            if tower.tower_type == "Outpost" and (state.player.upgrade_resources or 0) >= 10 and tower.units >= 20:
                return Action("UpgradeTower", source=tower.id, upgrade="Radar", reason="配置模擬升級資源")
        return Action("Wait", reason="保留兵力，等待新的可觀察局面")
