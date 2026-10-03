"""Independent source-derived labels and unsafe DOM controls; no live success credit."""
import json
from pathlib import Path
import pytest
from tools.v2_goal_upgrade_titles import official_tower_labels, official_upgrade_titles, match_upgrade_title
from tools.v2_goal_upgrade_probe import inspect_upgrade_dom, ALLOWED_TARGETS
SOURCE = json.loads((Path(__file__).parent / "fixtures/v2_goal_upgrade_titles_source.json").read_text(encoding="utf-8"))
LABELS = {int(k): v for k, v in SOURCE["labels"].items()}


def dom(target, heading="Barracks"):
    return {"headings": [heading], "buttons": [{
        "title": SOURCE["template"].replace("{upgrade}", LABELS[target]),
        "visible": True, "enabled": True, "pointer_events": True,
        "locked_glyph": False, "hidden_lock_icon": False, "bbox": [10, 20, 100, 40],
    }]}


@pytest.mark.parametrize("target", range(27))
def test_all_official_source_default_labels_identify_exact_target(target):
    expected = SOURCE["template"].replace("{upgrade}", LABELS[target])
    assert official_tower_labels(target) == (LABELS[target],)
    assert official_upgrade_titles()[target] == (expected,)
    assert match_upgrade_title(expected, target) == {"matched": True, "exact_title": expected, "reason": None}
    assert inspect_upgrade_dom(dom(target), 3, target)["eligible"] is True


def test_every_wrong_target_pair_is_rejected_without_label_collisions():
    assert set(LABELS) == set(range(27)) and len(set(LABELS.values())) == 27
    checked = 0
    for observed in LABELS:
        title = SOURCE["template"].replace("{upgrade}", LABELS[observed])
        for requested in LABELS:
            if observed == requested:
                continue
            assert match_upgrade_title(title, requested)["matched"] is False
            assert inspect_upgrade_dom(dom(observed), 3, requested)["eligible"] is False
            checked += 1
    assert checked == 702


@pytest.mark.parametrize("target", [None, True, False, -1, 27, 99, "1", 1.0, [], {}])
def test_unknown_or_wrong_typed_target_is_not_an_official_label(target):
    assert official_tower_labels(target) == ()
    assert match_upgrade_title("Upgrade to Armory", target)["matched"] is False


@pytest.mark.parametrize("title", [None, True, 1, [], {}, "", "Armory", "Upgrade",
    "upgrade to Armory", "Upgrade to armory", "Upgrade to Armory ", " Upgrade to Armory",
    "Upgrade to Armory\n", "Upgrade to Armory 🔒", "Downgrade to Armory",
    "Upgrade to level 1", "Upgrade to {upgrade}", "Upgrade to 軍械庫", "升級至軍械庫", "Upgrade to Ews"])
def test_unknown_adorned_downgrade_or_unverified_localized_title_is_rejected(title):
    assert match_upgrade_title(title, 1)["matched"] is False
    snapshot = dom(1); snapshot["buttons"][0]["title"] = title
    assert inspect_upgrade_dom(snapshot, 3, 1)["eligible"] is False


@pytest.mark.parametrize("field,value", [("visible", False), ("visible", None),
    ("enabled", False), ("enabled", 1), ("pointer_events", None), ("locked_glyph", True),
    ("locked_glyph", None), ("hidden_lock_icon", True), ("hidden_lock_icon", None),
    ("bbox", None), ("bbox", [0, 0, 0, 20]), ("bbox", [0, 0, float("nan"), 20])])
def test_exact_title_never_overrides_normal_button_safety(field, value):
    snapshot = dom(1); snapshot["buttons"][0][field] = value
    assert inspect_upgrade_dom(snapshot, 3, 1)["eligible"] is False


@pytest.mark.parametrize("headings", [[], ["Barracks", "Barracks"], ["Armory"],
    ["兵營"], [None], [{"text": "Barracks"}]])
def test_source_heading_must_be_one_verified_current_label(headings):
    snapshot = dom(1); snapshot["headings"] = headings
    assert inspect_upgrade_dom(snapshot, 3, 1)["eligible"] is False


def test_duplicate_target_button_remains_ambiguous():
    snapshot = dom(1); snapshot["buttons"].append(dict(snapshot["buttons"][0]))
    assert inspect_upgrade_dom(snapshot, 3, 1)["eligible"] is False


def test_ews_source_default_capitalization_and_allowlist_preserved():
    snapshot = dom(1, "EWS")
    assert inspect_upgrade_dom(snapshot, 8, 1)["eligible"] is True
    snapshot["headings"] = ["Ews"]
    assert inspect_upgrade_dom(snapshot, 8, 1)["eligible"] is False
    assert ALLOWED_TARGETS == frozenset({1, 3, 4, 9, 10, 12, 14, 16, 17, 18, 22, 25, 26})


def test_callers_cannot_mutate_future_title_registry():
    registry = official_upgrade_titles(); registry[1] = ("Downgrade to Armory",)
    assert official_upgrade_titles()[1] == ("Upgrade to Armory",)
