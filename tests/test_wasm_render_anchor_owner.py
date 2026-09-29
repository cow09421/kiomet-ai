"""Render-anchor owner labels preserve the verified color identity."""
import importlib.util
from pathlib import Path
import sys

import pytest


def load_tool():
    tools = Path(__file__).parents[1] / "tools"
    sys.path.insert(0, str(tools))
    path = tools / "wasm_render_anchor.py"
    spec = importlib.util.spec_from_file_location("wasm_render_anchor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


owner_fields_from_render_color = load_tool().owner_fields_from_render_color


@pytest.mark.parametrize(("render_color", "owner"), [
    (0, "SELF"),
    (1, "NEUTRAL"),
    (2, "ALLY"),
    (3, "ENEMY"),
])
def test_render_anchor_preserves_known_owner_color(render_color, owner):
    assert owner_fields_from_render_color(render_color) == {
        "render_color": render_color,
        "owner": owner,
    }


@pytest.mark.parametrize("render_color", [4, -1, 1.0, True, None])
def test_render_anchor_keeps_unknown_owner_color_unknown(render_color):
    assert owner_fields_from_render_color(render_color) == {
        "render_color": render_color,
        "owner": "UNKNOWN",
    }
