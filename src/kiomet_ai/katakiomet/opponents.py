"""Rule-Based Opponent（規則式對手）：前向模擬用的四種本地對手。

AGGRESSIVE（激進）：打可打的最弱鄰接。
DEFENSIVE（防守）：增援被威脅的塔。
EXPANSION（擴張）：吃中立弱塔。
RANDOM（隨機）：確定性種子隨機（可重現）。
"""
from __future__ import annotations

import random

from kiomet_ai.actions import Action
from kiomet_ai.katakiomet.graph import GameGraph


def opponent_actions(graph: GameGraph, enemy_id: str, style: str,
                     seed: int = 0) -> list[Action]:
    rng = random.Random(f"{seed}:{style}")
    own = [t for t in graph.towers.values()
           if t.visible and t.owner == enemy_id and (t.units or 0) > 0]
    actions: list[Action] = []
    if style == "AGGRESSIVE":
        targets = sorted(
            (t for t in graph.towers.values()
             if t.visible and t.owner not in (None, enemy_id)),
            key=lambda t: t.units if t.units is not None else 10**9)
        for tower in own:
            if not targets:
                break
            prey = next((t for t in targets if t.id in tower.neighbors), None)
            if prey is not None and (tower.units or 0) > (prey.units or 0) + 1:
                amount = min(tower.units - 1, (prey.units or 0) + 1)
                actions.append(Action("MoveForce", tower.id, prey.id, amount,
                                      reason="對手激進攻擊"))
                break
    elif style == "DEFENSIVE":
        for tower in own:
            if (tower.units or 0) < 12:
                for nid in tower.neighbors:
                    donor = graph.towers.get(nid)
                    if donor and donor.visible and donor.owner == enemy_id \
                            and (donor.units or 0) > 20:
                        actions.append(Action(
                            "MoveForce", nid, tower.id,
                            min(8, donor.units - 15), reason="對手防守增援"))
                        break
                break
    elif style == "EXPANSION":
        for tower in own:
            if (tower.units or 0) < 25:
                continue
            for nid in tower.neighbors:
                target = graph.towers.get(nid)
                if target and target.visible and target.owner is None \
                        and (target.units or 99) < (tower.units or 0) - 1:
                    actions.append(Action(
                        "MoveForce", tower.id, nid, (target.units or 0) + 1,
                        reason="對手擴張"))
                    break
            if actions:
                break
    else:  # RANDOM：確定性隨機鄰接移動。
        moves = [(t.id, n) for t in own for n in t.neighbors
                 if (t.units or 0) > 5]
        if moves:
            source, dest = rng.choice(moves)
            tower = graph.towers[source]
            actions.append(Action("MoveForce", source, dest,
                                  max(1, (tower.units or 1) // 2),
                                  reason="對手隨機移動"))
    return actions
