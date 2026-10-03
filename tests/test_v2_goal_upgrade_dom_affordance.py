"""Synthetic local-browser checks for the ordinary tower-button affordance."""
import asyncio

from tools import v2_goal_upgrade_probe as probe


def _snapshot(button_markup):
    async def collect():
        async with probe.async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=["--mute-audio"])
            try:
                page = await browser.new_page()
                await page.set_content(f"""
                    <style>
                      .x7ad2 {{ cursor: pointer; }}
                      .q93af {{ cursor: initial !important; }}
                    </style>
                    <h2><span></span><span>Barracks</span></h2>
                    {button_markup}
                """)
                return await probe._dom_snapshot(page)
            finally:
                await browser.close()
    return asyncio.run(collect())


def _target(dom):
    buttons = dom["buttons"]
    assert len(buttons) == 1
    assert dom["headings"] == ["Barracks"]
    assert buttons[0]["title"] == "Upgrade to Armory"
    return buttons[0]


def test_computed_cursor_distinguishes_normal_and_disabled_custom_div():
    normal = _snapshot('<div class="x7ad2" title="Upgrade to Armory">Armory</div>')
    normal_button = _target(normal)
    assert normal_button["enabled"] is True
    assert normal_button["cursor"] == "pointer"
    assert probe.inspect_upgrade_dom(normal, 3, 1)["eligible"] is True

    disabled = _snapshot(
        '<div class="x7ad2 q93af" title="Upgrade to Armory">Armory</div>'
    )
    disabled_button = _target(disabled)
    assert disabled_button["enabled"] is False
    assert disabled_button["title"] == "Upgrade to Armory"
    assert probe.inspect_upgrade_dom(disabled, 3, 1)["eligible"] is False


def test_missing_affordance_and_aria_disabled_are_refused():
    auto = _snapshot('<div title="Upgrade to Armory">Armory</div>')
    assert _target(auto)["enabled"] is False
    assert probe.inspect_upgrade_dom(auto, 3, 1)["eligible"] is False

    aria_disabled = _snapshot(
        '<div class="x7ad2" aria-disabled="true" title="Upgrade to Armory">Armory</div>'
    )
    assert _target(aria_disabled)["enabled"] is False
    assert probe.inspect_upgrade_dom(aria_disabled, 3, 1)["eligible"] is False


def test_locked_target_remains_rejected_even_with_pointer_affordance():
    locked = _snapshot(
        '<div class="x7ad2" title="Upgrade to Armory">'
        '<span>🔒</span>Armory</div>'
    )
    assert _target(locked)["enabled"] is True
    result = probe.inspect_upgrade_dom(locked, 3, 1)
    assert result["eligible"] is False
    assert "UPGRADE_BUTTON_DISABLED_LOCKED_OR_UNSAFE" in result["reasons"]
