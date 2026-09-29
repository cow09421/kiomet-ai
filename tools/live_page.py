"""真頁選擇器：多 kiomet.com 分頁並存時，以存活 token 配對。

平台啟動時在遊戲頁寫入 window.__kiometLiveToken（control.json 的
token，每進程唯一）。所有研究工具必須經此選擇目標，禁止
next(p for p in pages if url==...) 首命中（曾導致錨點讀到
stale 頁的細胞渲染，30 週期全滅）。
找不到配對時 loudly 失敗，不回退首命中。
"""
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME_URL = "https://kiomet.com/"


def control_token() -> str:
    return json.loads((ROOT / "runtime/state/control.json").read_text(encoding="utf-8"))["token"]


def devtools_port() -> int:
    return int((ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0])


def list_pages() -> list:
    port = devtools_port()
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5))
    return [t for t in targets if t.get("type") == "page" and t.get("url") == GAME_URL]


def read_marker(page_id: str, timeout=5) -> str | None:
    """經由 CDP 唯讀取標記（不掛斷點、低侵入）。"""
    from cdp_probe import Session
    try:
        with Session(page_id=page_id, timeout=timeout) as session:
            result = session.call("Runtime.evaluate", {
                "expression": "window.__kiometLiveToken ?? null",
                "returnByValue": True})
            value = (result.get("result") or {}).get("value")
            return value if isinstance(value, str) else None
    except Exception:
        return None


def find_live_target_id(timeout=5) -> str:
    """回傳配對成功的 CDP targetId；失敗拋錯。"""
    token = control_token()
    pages = list_pages()
    if not pages:
        raise RuntimeError("沒有 kiomet.com 分頁")
    for page in pages:
        if read_marker(page["id"], timeout) == token:
            return page["id"]
    raise RuntimeError(
        f"找不到存活標記分頁（共 {len(pages)} 個 kiomet.com 分頁皆非本進程真頁；"
        "平台需重啟以寫入標記）")


def find_live_ws_url(timeout=5) -> str:
    """回傳真頁的 webSocketDebuggerUrl。"""
    port = devtools_port()
    target_id = find_live_target_id(timeout)
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=timeout))
    for target in targets:
        if target.get("id") == target_id:
            return target["webSocketDebuggerUrl"]
    raise RuntimeError("真頁已消失")

async def find_live_playwright_page(browser, timeout=5):
    """在已連線的 Playwright browser 中找存活標記頁。

    對每個 kiomet.com 分頁開短 CDP 會話讀標記（唯讀求值，
    不掛斷點）；配對 control.json token 者即真頁。
    找不到則 loudly 失敗。
    """
    token = control_token()
    candidates = [p for p in browser.contexts[0].pages
                  if p.url == GAME_URL]
    if not candidates:
        raise RuntimeError("沒有 kiomet.com 分頁")
    for page in candidates:
        try:
            session = await page.context.new_cdp_session(page)
            try:
                ret = await session.send("Runtime.evaluate", {
                    "expression": "window.__kiometLiveToken ?? null",
                    "returnByValue": True})
                value = (ret.get("result") or {}).get("value")
                if value == token:
                    await session.detach()
                    return page
            finally:
                try:
                    await session.detach()
                except Exception:
                    pass
        except Exception:
            continue
    raise RuntimeError(
        f"找不到存活標記分頁（{len(candidates)} 個 kiomet.com 分頁皆非本進程真頁）")
