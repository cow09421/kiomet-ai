"""Formal live observation must not read hidden game memory."""
import asyncio
import importlib.util
from pathlib import Path

import pytest

from kiomet_ai.live_controller import LiveController


ROOT = Path(__file__).parents[1]


def _load_disabled_anchor_tool():
    path = ROOT / "tools" / "wasm_render_anchor.py"
    spec = importlib.util.spec_from_file_location("disabled_wasm_anchor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("script", [
    "wasm_render_anchor.py",
    "unit_struct_probe.py",
    "nested/unit_struct_probe.py",
])
def test_live_controller_blocks_game_memory_probe_launch(script):
    controller = object.__new__(LiveController)

    code, reason = asyncio.run(controller._run_tool(script))

    assert code != 0
    assert "memory probing is disabled" in reason


def test_legacy_anchor_is_not_reused_as_visible_ui_evidence():
    controller = object.__new__(LiveController)

    anchor = asyncio.run(controller.ensure_anchor("current-match"))

    assert anchor is None


def test_screen_map_fails_closed_without_visible_ui_mapping():
    controller = object.__new__(LiveController)

    screen_map, canvas = asyncio.run(controller.fresh_screen_map([]))

    assert screen_map == {}
    assert canvas is None


def test_live_controller_has_no_direct_game_memory_inspection_code():
    source = (ROOT / "src" / "kiomet_ai" / "live_controller.py").read_text(
        encoding="utf-8")

    for forbidden in (
            "WebAssembly.Memory.prototype", "Runtime.queryObjects",
            "Runtime.callFunctionOn", "Debugger.setBreakpoint"):
        assert forbidden not in source


def test_wasm_anchor_tool_refuses_live_page_access():
    tool = _load_disabled_anchor_tool()

    with pytest.raises(RuntimeError, match="玩家可見 UI"):
        asyncio.run(tool.main(color=True))
