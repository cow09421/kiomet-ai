"""Exact source-default Kiomet upgrade labels; translated runtime catalogs stay unknown.

Kodiak 0.1.1 commit c17719a1b54ae1eae663a26bbb39fd842cd9a5c2,
client/src/translation/phrases.rs and translator.rs; Kiomet ui/phrases.rs.
See docs/V2_GOAL_OFFICIAL_UPGRADE_LABELS.md for provenance and scope.
"""
from __future__ import annotations

OFFICIAL_ENGLISH_LABELS = (
    "Airfield", "Armory", "Artillery", "Barracks", "Bunker",
    "Centrifuge", "City", "Cliff", "EWS", "Factory",
    "Generator", "Headquarters", "Helipad", "Launcher", "Mine",
    "Projector", "Quarry", "Radar", "Rampart", "Reactor",
    "Refinery", "Rocket", "Runway", "Satellite", "Silo", "Town", "Village",
)


def official_tower_labels(type_id: int) -> tuple[str, ...]:
    if type(type_id) is not int or not 0 <= type_id < len(OFFICIAL_ENGLISH_LABELS):
        return ()
    return (OFFICIAL_ENGLISH_LABELS[type_id],)


def official_upgrade_titles() -> dict[int, tuple[str, ...]]:
    return {i: (f"Upgrade to {label}",) for i, label in enumerate(OFFICIAL_ENGLISH_LABELS)}


def match_upgrade_title(title, target_type: int) -> dict:
    labels = official_tower_labels(target_type)
    if not labels:
        return {"matched": False, "exact_title": None, "reason": "TARGET_TYPE_UNKNOWN"}
    matched = type(title) is str and title == f"Upgrade to {labels[0]}"
    return {"matched": matched, "exact_title": title if matched else None,
            "reason": None if matched else "TITLE_NOT_EXACT_SOURCE_DEFAULT"}
