"""觀戰攝影機可行性探測（P0）。

唯讀判定：Kiomet 是否暴露「加入同一對局」的觀戰機制。
預設絕不以第二玩家身分加入；只讀取頁面位址與全域能力。
輸出 runtime/research/spectator/feasibility.json。

判定：
- same_match: VERIFIED / BLOCKED / UNKNOWN
- real_camera: AVAILABLE / UNAVAILABLE / UNKNOWN
禁止把 UNKNOWN 當 VERIFIED。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 觀戰機制關鍵字：頁面位址或全域出現時，才可能有真正的同局觀戰路徑。
MECHANISM_KEYS = ("spectate", "spectator", "watch", "replay", "joinmatch",
                  "match_id", "matchid", "world_id", "worldid")


def classify_mechanism(probe: dict) -> str:
    """由唯讀頁面探測判定機制：JOIN_BY_ID / SPECTATE_API / NONE / UNKNOWN。"""
    if not isinstance(probe, dict):
        return "UNKNOWN"
    if not probe.get("is_kiomet"):
        return "UNKNOWN"
    href = str(probe.get("href") or "")
    search = str(probe.get("search") or "")
    fragment = str(probe.get("hash") or "")
    url_text = (href + search + fragment).lower()
    for key in ("spectate", "spectator", "watch", "replay"):
        if key in url_text:
            return "SPECTATE_API"
    for key in ("match_id", "matchid", "match=", "world_id", "worldid"):
        if key in url_text:
            return "JOIN_BY_ID"
    keys = probe.get("window_keys") or []
    key_text = " ".join(str(k).lower() for k in keys)
    for key in ("spectate", "spectator", "watch", "replay"):
        if key in key_text:
            return "SPECTATE_API"
    for key in ("joinmatch", "matchid", "match_id", "worldid", "world_id"):
        if key in key_text:
            return "JOIN_BY_ID"
    if probe.get("has_canvas"):
        return "NONE"
    return "UNKNOWN"


def analyze(probe: dict, match_id_ai: str | None = None) -> dict:
    """純函式：由唯讀探測產生判定與證據。不做任何假設性成功。"""
    mechanism = classify_mechanism(probe)
    if mechanism in ("JOIN_BY_ID", "SPECTATE_API"):
        same_match = "UNKNOWN"
        real_camera = "UNKNOWN"
        reason = f"mechanism={mechanism}; 需以第二頁實測同局後才可標 VERIFIED"
    elif mechanism == "NONE":
        same_match = "BLOCKED"
        real_camera = "UNAVAILABLE"
        reason = ("未發現 join-by-id／觀戰 API；對局由伺服器配對，"
                  "第二頁無法保證同一 match")
    else:
        same_match = "UNKNOWN"
        real_camera = "UNKNOWN"
        reason = "頁面能力探測不完整（非 Kiomet 或缺少畫布）"
    return {
        "same_match": same_match,
        "real_camera": real_camera,
        "mechanism": mechanism,
        "reason": reason,
        "ai_match_id": match_id_ai,
        "spectator_match_id": None,
        "url_had_match_id": mechanism in ("JOIN_BY_ID", "SPECTATE_API"),
        "probe": {
            "href": (probe or {}).get("href"),
            "search": (probe or {}).get("search"),
            "hash": (probe or {}).get("hash"),
            "window_keys": (probe or {}).get("window_keys"),
            "has_canvas": (probe or {}).get("has_canvas"),
        },
        "generated_at": time.time(),
        "joined_as_second_player": False,
    }


def probe_live_page(target: str = "https://kiomet.com/",
                    cdp_call=None, timeout: float = 8.0) -> dict:
    """讀取專用 Chromium 的 Kiomet 頁面（唯讀；不送輸入、不加入對局）。"""
    expression = (
        "(() => {const c=document.querySelector('canvas');"
        "const keys=Object.keys(window).filter(k=>"
        "/spectat|replay|join|watch|match|world/i.test(k));"
        "return {href:location.href,search:location.search,hash:location.hash,"
        "title:document.title,has_canvas:!!c,window_keys:keys.slice(0,60)};})()"
    )
    if cdp_call is None:
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        from cdp_probe import call as cdp_call  # noqa: E402
    result = cdp_call("Runtime.evaluate",
                      {"expression": expression, "returnByValue": True},
                      target=target, timeout=timeout)
    value = (result.get("result") or {}).get("value") or {}
    value["is_kiomet"] = "kiomet" in str(value.get("href", "")).lower()
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(
        ROOT / "runtime/research/spectator/feasibility.json"))
    parser.add_argument("--ai-match-id", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        probe = probe_live_page()
    except Exception as exc:  # 瀏覽器不可用時不得偽造
        probe = {"is_kiomet": False, "error": str(exc)}
    report = analyze(probe, match_id_ai=args.ai_match_id)
    if probe.get("error"):
        report["probe_error"] = probe["error"]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"same_match={report['same_match']} "
              f"real_camera={report['real_camera']} "
              f"mechanism={report['mechanism']} :: {report['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
