"""孤兒專用瀏覽器清理回歸（profile 白名單，絕不誤殺使用者 Chrome）。

背景：app 強殺後殘留同 profile Chromium → 新實例開場即 Target crashed
（事件 13/14）。start() 啟動前必須 reap，且只能認命令列含專用 profile 者。

成功證據：帶專用 profile 的 chrome.exe 被認定；系統 User Data、空命令列、
非 chrome 一律不認；find 回正確 PID 集合。
失敗證據：使用者 Chrome 被納入（條件寬鬆）或孤兒漏抓。
"""
from pathlib import Path

from kiomet_ai.browser import (find_orphan_browser_pids,
                               is_our_browser_cmdline)

PROFILE = Path("C:/kiomet-test/runtime/browser-profile")
USER_DATA = "C:\\Users\\example-user\\AppData\\Local\\Google\\Chrome\\User Data"


def test_our_profile_cmdline_matches_case_insensitively():
    cmd = ["chrome.exe", f"--user-data-dir={PROFILE}",
           "--remote-debugging-port=0"]
    assert is_our_browser_cmdline(cmd, PROFILE) is True
    assert is_our_browser_cmdline(
        ["chrome.exe", f"--user-data-dir={str(PROFILE).lower()}"],
        PROFILE) is True


def test_user_chrome_profile_never_matches():
    cmd = ["chrome.exe", f"--user-data-dir={USER_DATA}"]
    assert is_our_browser_cmdline(cmd, PROFILE) is False


def test_empty_or_unverifiable_cmdline_never_matches():
    assert is_our_browser_cmdline([], PROFILE) is False
    assert is_our_browser_cmdline(None, PROFILE) is False
    assert is_our_browser_cmdline(["chrome.exe"], PROFILE) is False
    assert is_our_browser_cmdline(["chrome.exe", "--x"], None) is False


def test_finder_keeps_only_our_chrome_processes():
    processes = [
        (101, "chrome.exe", ["chrome.exe", f"--user-data-dir={PROFILE}"]),
        (102, "chrome.exe", ["chrome.exe", f"--user-data-dir={USER_DATA}"]),
        (103, "firefox.exe", [f"--profile={PROFILE}"]),
        (104, "chrome.exe", []),
        (105, "CHROME.EXE", ["CHROME.EXE", f"--user-data-dir={PROFILE}"]),
        (106, "python.exe", ["python.exe", "-m", "kiomet_ai.app"]),
    ]
    assert find_orphan_browser_pids(PROFILE, processes=processes) == [101, 105]


def test_finder_returns_empty_when_profile_absent():
    assert find_orphan_browser_pids(
        PROFILE,
        processes=[(1, "chrome.exe", ["chrome.exe", f"--user-data-dir={USER_DATA}"])],
    ) == []
