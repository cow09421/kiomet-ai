"""已停用的遊戲內部錨點探針。

正式觀察只能使用玩家可見 UI（使用者介面）資料。此相容模組保留
舊 owner（所有者）標籤純函式供離線測試使用，不再連接 Chromium、
設定偵錯中斷點或讀取 WebAssembly（網頁組譯）記憶體。
"""
import argparse
import asyncio


def owner_fields_from_render_color(render_color):
    """保留已驗證的四種渲染顏色；未知值維持 UNKNOWN。"""
    owner = ({0: "SELF", 1: "NEUTRAL", 2: "ALLY", 3: "ENEMY"}
             .get(render_color, "UNKNOWN")
             if type(render_color) is int else "UNKNOWN")
    return {"render_color": render_color, "owner": owner}


async def main(color=False, sample_count=16):
    del color, sample_count
    raise RuntimeError(
        "停用：正式遊戲狀態只能來自玩家可見 UI，不能讀取遊戲記憶體")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--color", action="store_true")
    parser.add_argument("--samples", type=int, choices=range(1, 65), default=16)
    parser.parse_args()
    print("停用：正式遊戲狀態只能來自玩家可見 UI，不能讀取遊戲記憶體")
    raise SystemExit(2)
