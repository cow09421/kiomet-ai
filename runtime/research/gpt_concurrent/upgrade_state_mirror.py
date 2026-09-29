"""Kiomet 升級狀態離線鏡像；不連線遊戲，也不呼叫正式版 WASM。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def evaluate_upgrade_state(
    tower_type: str,
    delay_ticks: int,
    owned_by_me: bool,
    tower_counts: Mapping[str, int],
    edges: Sequence[Mapping[str, Any]],
    *,
    unlocked_types: set[str] | None = None,
    rank_below_three: bool | None = None,
    rewarded_ad_available: bool | None = None,
    target_levels: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """純函數：重現來源版塔升級候選與前置進度。

    Global unlock inputs are optional. Unknown values produce `None` for the
    lock/command conclusion instead of silently treating the target as unlocked.
    """
    if not isinstance(delay_ticks, int) or not 0 <= delay_ticks <= 255:
        raise ValueError("delay_ticks must be a u8 value")
    if not isinstance(owned_by_me, bool):
        raise ValueError("owned_by_me must be bool")
    for name, count in tower_counts.items():
        if not isinstance(count, int) or not 0 <= count <= 65535:
            raise ValueError(f"count for {name} must be u16")

    children: dict[str, list[Mapping[str, Any]]] = {}
    parent: dict[str, str] = {}
    for edge in edges:
        source, target = str(edge["from"]), str(edge["to"])
        children.setdefault(source, []).append(edge)
        if target in parent and parent[target] != source:
            raise ValueError(f"ambiguous downgrade parent for {target}")
        parent[target] = source

    root = tower_type
    seen = set()
    while root in parent:
        if root in seen:
            raise ValueError("upgrade cycle")
        seen.add(root)
        root = parent[root]

    options: list[tuple[str, Mapping[str, int], bool]] = [
        (str(edge["to"]), edge.get("extras", {}), False)
        for edge in children.get(tower_type, [])
    ]
    if root != tower_type:
        options.append((root, {}, True))

    visible = owned_by_me and delay_ticks == 0
    candidates = []
    for target, requirements, downgrade in options:
        progress = {
            name: {
                "have": int(tower_counts.get(name, 0)),
                "need": int(required),
                "missing": max(0, int(required) - int(tower_counts.get(name, 0))),
            }
            for name, required in requirements.items()
        }
        prerequisites_met = all(item["missing"] == 0 for item in progress.values())
        button_enabled = visible and prerequisites_met

        locked: bool | None = None
        if (
            unlocked_types is not None
            and rank_below_three is not None
            and rewarded_ad_available is not None
            and target_levels is not None
            and target in target_levels
        ):
            locked = (
                rank_below_three
                and rewarded_ad_available
                and target_levels[target] > 0
                and target not in unlocked_types
            )

        candidates.append({
            "target": target,
            "downgrade_to_basis": downgrade,
            "prerequisite_progress": progress,
            "prerequisites_met": prerequisites_met,
            "ui_button_visible": visible,
            "ui_button_enabled": button_enabled,
            "would_open_lock_dialog": locked if button_enabled else False,
            "can_send_upgrade_command": (
                False if not button_enabled else None if locked is None else not locked
            ),
        })

    return {
        "tower_type": tower_type,
        "delay_ticks": delay_ticks,
        "delay_seconds_at_4hz": delay_ticks / 4,
        "owned_by_me": owned_by_me,
        "basis": root,
        "candidates": candidates,
        "limits": "source-derived UI decision; server may reject stale or unauthorized input",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tower-type", required=True)
    parser.add_argument("--delay-ticks", type=int, default=0)
    parser.add_argument("--owned-by-me", action="store_true")
    parser.add_argument("--counts-json", required=True, help="JSON object of tower-type counts")
    args = parser.parse_args()
    graph_path = Path(__file__).parent / "inputs" / "source_expected_graph.snapshot.json"
    edges = json.loads(graph_path.read_text(encoding="utf-8"))["edges"]
    counts = json.loads(args.counts_json)
    print(json.dumps(evaluate_upgrade_state(
        args.tower_type, args.delay_ticks, args.owned_by_me, counts, edges
    ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
