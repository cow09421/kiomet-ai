from pathlib import Path

from kiomet_ai.browser import BrowserHost


def test_normal_chromium_launch_keeps_existing_hardware_defaults():
    args = BrowserHost._chromium_launch_args(
        Path("chrome.exe"), Path("profile"), Path("project"))

    assert "--remote-debugging-address=127.0.0.1" in args
    assert not any("swiftshader" in item or item == "--use-angle=warp"
                   for item in args)


def test_warp_retry_uses_the_same_profile_and_only_d3d11_software_renderer():
    args = BrowserHost._chromium_launch_args(
        Path("chrome.exe"), Path("profile"), Path("project"), use_warp=True)

    assert "--user-data-dir=profile" in args
    assert "--use-gl=angle" in args
    assert "--use-angle=warp" in args
    assert not any("swiftshader" in item or "enable-unsafe" in item
                   for item in args)


def test_warp_retry_requires_repeated_gpu_fatal_and_connection_failure():
    log = ("GPU process exited unexpectedly: exit_code=-1073741790\n"
           "GPU process exited unexpectedly: exit_code=-1073741790\n"
           "FATAL: GPU process isn't usable. Goodbye.")

    assert BrowserHost._gpu_failure_allows_warp_retry(
        "connect_over_cdp: read ECONNRESET", log)
    assert BrowserHost._gpu_failure_allows_warp_retry(
        "專用 Chromium exited before control port ready", log)
    assert BrowserHost._gpu_failure_allows_warp_retry(
        "TargetClosedError: Target page, context or browser has been closed", log)
    assert not BrowserHost._gpu_failure_allows_warp_retry(
        "connect_over_cdp: read ECONNRESET", "GPU process exited unexpectedly")
    assert not BrowserHost._gpu_failure_allows_warp_retry(
        "connect_over_cdp: read ECONNRESET",
        "GPU process isn't usable. Goodbye.")
    assert not BrowserHost._gpu_failure_allows_warp_retry(
        "connect_over_cdp: read ECONNRESET", "ordinary browser startup log")


def test_old_gpu_failure_in_log_does_not_trigger_a_new_retry(tmp_path):
    log = tmp_path / "chromium.log"
    old_failure = ("GPU process exited unexpectedly\n" * 2
                   + "FATAL: GPU process isn't usable. Goodbye.")
    log.write_text(old_failure, encoding="utf-8")
    offset = log.stat().st_size
    log.write_text("ordinary new startup log", encoding="utf-8")

    current_log = BrowserHost._startup_log_since(log, offset)

    assert current_log == "ordinary new startup log"
    assert not BrowserHost._gpu_failure_allows_warp_retry(
        "connect_over_cdp: read ECONNRESET", current_log)
