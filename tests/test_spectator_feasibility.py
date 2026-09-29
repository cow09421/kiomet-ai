"""觀戰可行性探測回歸（P0）。

純判定：無機制→BLOCKED；有 join-by-id→UNKNOWN（不得自動 VERIFIED）；
非 Kiomet→UNKNOWN。唯讀探測注入假 CDP，不接觸真實瀏覽器。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from spectator_feasibility import (analyze, classify_mechanism,
                                   probe_live_page)


def _kiomet(href="https://kiomet.com/", **over):
    base = {"is_kiomet": True, "href": href, "search": "", "hash": "",
            "title": "Kiomet", "has_canvas": True, "window_keys": []}
    base.update(over)
    return base


def test_no_mechanism_is_none():
    assert classify_mechanism(_kiomet()) == "NONE"


def test_url_match_id_is_join_by_id():
    probe = _kiomet(href="https://kiomet.com/?match_id=m1-123")
    assert classify_mechanism(probe) == "JOIN_BY_ID"


def test_url_spectate_is_spectate_api():
    probe = _kiomet(href="https://kiomet.com/spectate/abc")
    assert classify_mechanism(probe) == "SPECTATE_API"


def test_window_spectator_key_is_spectate_api():
    probe = _kiomet(window_keys=["__spectatorApi"])
    assert classify_mechanism(probe) == "SPECTATE_API"


def test_non_kiomet_is_unknown():
    assert classify_mechanism({"is_kiomet": False, "has_canvas": True}) == \
        "UNKNOWN"
    assert classify_mechanism(None) == "UNKNOWN"


def test_no_mechanism_blocks_same_match():
    report = analyze(_kiomet())
    assert report["same_match"] == "BLOCKED"
    assert report["real_camera"] == "UNAVAILABLE"
    assert report["joined_as_second_player"] is False


def test_join_by_id_never_auto_verified():
    report = analyze(_kiomet(href="https://kiomet.com/?match_id=x"))
    assert report["same_match"] == "UNKNOWN"
    assert report["same_match"] != "VERIFIED"
    assert report["url_had_match_id"] is True


def test_unknown_probe_unknown():
    report = analyze({"is_kiomet": False})
    assert report["same_match"] == "UNKNOWN"
    assert report["real_camera"] == "UNKNOWN"


def test_analyze_never_claims_verification():
    for probe in (_kiomet(), _kiomet(window_keys=["__watcher"]),
                  _kiomet(href="https://kiomet.com/?world_id=z")):
        assert analyze(probe)["same_match"] != "VERIFIED"


def test_probe_live_page_readonly_injected():
    captured = {}

    def fake_call(method, params, target, timeout):
        captured["method"] = method
        captured["target"] = target
        return {"result": {"value": {"href": "https://kiomet.com/",
                                     "search": "", "hash": "",
                                     "title": "Kiomet", "has_canvas": True,
                                     "window_keys": ["matchMedia"]}}}

    probe = probe_live_page(cdp_call=fake_call)
    assert captured["method"] == "Runtime.evaluate"
    assert captured["target"] == "https://kiomet.com/"
    assert probe["is_kiomet"] is True
    assert "Runtime.evaluate" == captured["method"]


def test_probe_page_does_not_join():
    """探測表達式不得包含任何遊戲命令或點擊。"""
    import spectator_feasibility as mod
    import inspect
    src = inspect.getsource(mod.probe_live_page)
    for banned in ("click", "dispatch", "MoveForce", "Upgrade", "Deploy",
                   "play_button"):
        assert banned not in src
