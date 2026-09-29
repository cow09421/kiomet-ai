"""LiveController（真實遊玩協調器）：Observe→Rank→Proposal→Preflight
→Execute→Verify→Replan 閉環。

- 真實世界狀態每次重取（錨點＋探測＋相機），不信任舊 JSON。
- 每次最多 ONE Action（一動作），送完即驗證，無盲連發。
- 連續 3 次無驗證結果 → 自動暫停戰術動作（保留觀察）。
- 同一 source-target 連續失敗有冷卻。
- sent_actions 只在真實輸入送出後由平台日誌累計。
用法：python tools/live_controller.py [--max-actions N] [--interval S]
"""
import argparse
import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kiomet_ai.dry_rank import rank_expansion_targets
from kiomet_ai.observe import (
    MatchObservation,
    ObservedEdge,
    ObservedTower,
    build_real_tower_states,
    decode_owner_ruler_flag,
    decode_tower_type,
    decode_tower_units,
)
from kiomet_ai.proposal import (
    PREFLIGHT_READY,
    build_proposal,
    prepare_move,
    run_dry_cycle,
    verify_post_action,
)

sys.path.insert(0, str(ROOT / "tools"))
from camera_transform import world_to_page
from live_page import find_live_playwright_page

ANCHOR = ROOT / "runtime/research/source-map/verified-anchor-current.json"
STATE = ROOT / "runtime/state/live_controller.json"
BASE = "http://127.0.0.1:8765"


def api(path: str, token: str | None = None, payload: dict | None = None,
        timeout=15):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {}
    if token:
        headers["X-Control-Token"] = token
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers,
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def run_tool(script: str, *args):
    env = {"PYTHONUTF8": "1", "PYTHONPATH": str(ROOT / "src"),
           "TEMP": str(ROOT / "runtime/tmp"), "TMP": str(ROOT / "runtime/tmp")}
    import os
    full = dict(os.environ)
    full.update(env)
    proc = subprocess.run(
        [str(ROOT / ".venv/Scripts/python.exe"), str(ROOT / "tools" / script),
         *args], capture_output=True, text=True, timeout=600, cwd=ROOT,
        env=full)
    return proc.returncode, (proc.stdout or "").strip().splitlines()[-1] if proc.stdout.strip() else ""


def save_state(state: dict):
    state["updated_at"] = time.time()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


async def fresh_screen_map(anchor_towers: list):
    """唯讀相機＋換算（獨立 CDP 會話，用完即關）。"""
    from playwright.async_api import async_playwright
    import statistics
    async with async_playwright() as pw:
        port = (ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0]
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:" + port)
        page = await find_live_playwright_page(browser)
        session = await page.context.new_cdp_session(page)
        try:
            mx = statistics.median(t["position"][0] for t in anchor_towers)
            my = statistics.median(t["position"][1] for t in anchor_towers)
            proto = (await session.send("Runtime.evaluate", {"expression": "WebAssembly.Memory.prototype"}))["result"]["objectId"]
            objs = (await session.send("Runtime.queryObjects", {"prototypeObjectId": proto}))["objects"]["objectId"]
            try:
                ret = await session.send("Runtime.callFunctionOn", {"objectId": objs, "returnByValue": True,
                    "arguments": [{"value": mx}, {"value": my}],
                    "functionDeclaration": """function(mx,my){return this.flatMap(m=>{const v=new DataView(m.buffer),out=[];
                      for(let o=0x171680;o<0x171780;o+=4){if(o+32>=v.byteLength)break;
                        let z=v.getFloat32(o,true),x=v.getFloat32(o+24,true),y=v.getFloat32(o+28,true);
                        if(z>2&&z<150&&Math.abs(x-mx)<100&&Math.abs(y-my)<100)out.push([o,x,y,z]);}
                      return out})}"""})
                cams = ret["result"]["value"]
                if not cams:
                    return {}, None
                cam = cams[0]
            finally:
                await session.send("Runtime.releaseObject", {"objectId": objs})
                await session.send("Runtime.releaseObject", {"objectId": proto})
            view = await page.evaluate("""() => {let r=document.querySelector('canvas').getBoundingClientRect();
                return {viewport:[innerWidth,innerHeight],canvas:[r.left,r.top,r.width,r.height],dpr:devicePixelRatio}}""")
            screen = {}
            for t in anchor_towers:
                x, y = world_to_page(*t["position"], *cam[1:], *view["viewport"],
                                     view["dpr"], view["canvas"][0], view["canvas"][1])
                screen[t["packed_id"]] = (round(x, 2), round(y, 2))
            return screen, {"w": view["viewport"][0], "h": view["viewport"][1]}
        finally:
            await session.detach()



def _anchor_quality_ok(match_id: str) -> bool:
    """錨點品質閘：抽檢首 3 塔，tag 須為 0/1、+46 為合法塔型、
    packed_id 不得為長連號（細胞渲染誤捕）。"""
    from kiomet_ai.observe import TOWER_TYPES
    try:
        probe = json.loads((ROOT / f"runtime/research/units/unit-struct-probe-{match_id}.json").read_text(encoding="utf8"))
    except (OSError, ValueError):
        return False
    rows = probe.get("rows", [])[:3]
    if len(rows) < 3:
        return False
    good = 0
    for row in rows:
        raw = row["bytes"][32:32 + 48]
        if raw[38] in (0, 1) and 0 <= raw[46] < len(TOWER_TYPES):
            good += 1
    if good < 2:
        return False
    ids = sorted(r["packed_id"] for r in probe.get("rows", []))
    run = 1
    for a, b in zip(ids, ids[1:]):
        run = run + 1 if b == a + 1 else 1
        if run >= 8:
            return False
    return True

def build_states(anchor: dict, probe_rows: dict, now: float):
    towers = []
    for t in anchor["towers"]:
        if t["packed_id"] not in probe_rows:
            continue
        raw = probe_rows[t["packed_id"]]["bytes"][32:32 + 48]
        towers.append(ObservedTower(
            tower_id=t["packed_id"], tower_ref=t["tower_ref"],
            world_x=t["position"][0], world_y=t["position"][1],
            owner=t["owner"], owner_ruler=decode_owner_ruler_flag(raw),
            tower_type=decode_tower_type(raw),
            units_detail=decode_tower_units(raw, tower_ref=t["tower_ref"])))
    edges = [ObservedEdge(a, b) for a, b in anchor.get("edges", [])]
    obs = MatchObservation(match_id=anchor["match_id"], timestamp=now,
                           towers=tuple(towers), edges=tuple(edges))
    return build_real_tower_states(obs)


def snapshot_tower(state):
    counts = state.unit_counts
    return {"owner": state.owner,
            "units": ({n: getattr(counts, n.lower()) for n in
                       ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier")}
                      if counts and counts.units_kind == "MANY" else None)}


async def cycle(token: str, journal: dict, cooldowns: dict, now: float):
    """單次閉環。回傳 (phase, info)。絕不連發：一次最多一動作。"""
    status = api("/api/status", token)
    match_id = ((status.get("game") or {}).get("match") or {}).get("id")
    if status.get("state") != "RUNNING" or (status.get("game") or {}).get("state") != "IN_MATCH":
        return "NO_SAFE_PROPOSAL", {"reason": "platform_not_in_match"}
    # 1) 錨點：同局已有且新鮮（5 分鐘內）則沿用，避免重複斷點風險
    anchor_path = ROOT / "runtime/research/source-map/verified-anchor-current.json"
    anchor_fresh = False
    if anchor_path.exists():
        try:
            cached = json.loads(anchor_path.read_text(encoding="utf8"))
            import os as _os
            age = time.time() - _os.path.getmtime(anchor_path)
            anchor_fresh = (cached.get("match_id") == match_id
                            and cached.get("anchor") == "PASS" and age < 300)
        except (OSError, ValueError):
            anchor_fresh = False
    if not anchor_fresh:
        code, _ = run_tool("wasm_render_anchor.py", "--color")
        if code != 0:
            return "NO_SAFE_PROPOSAL", {"reason": "anchor_failed"}
        code, _ = run_tool("wasm_anchor_report.py",
                           "runtime/research/source-map/render-owner.json",
                           "runtime/research/source-map/verified-anchor-current.json")
        if code != 0:
            return "NO_SAFE_PROPOSAL", {"reason": "anchor_unstable"}
    anchor = json.loads(ANCHOR.read_text(encoding="utf8"))
    if anchor["match_id"] != match_id:
        return "NO_SAFE_PROPOSAL", {"reason": "match_switched_during_anchor"}
    # 2) 結構探測＋錨點品質閘（首 3 塔抽檢：tag／塔型／非連號）
    code, _ = run_tool("unit_struct_probe.py")
    if code != 0:
        return "NO_SAFE_PROPOSAL", {"reason": "probe_failed"}
    if not _anchor_quality_ok(match_id):
        try:
            (ROOT / "runtime/research/source-map/verified-anchor-current.json").unlink()
        except OSError:
            pass
        return "NO_SAFE_PROPOSAL", {"reason": "anchor_quality"}
    probe = json.loads((ROOT / f"runtime/research/units/unit-struct-probe-{match_id}.json").read_text(encoding="utf8"))
    prows = {r["packed_id"]: r for r in probe["rows"]}
    states = build_states(anchor, prows, now)
    by_id = {s.tower_id: s for s in states}
    # 3) 排名→提案
    ranked = rank_expansion_targets(states, match_id, now)
    if not ranked:
        return "NO_SAFE_PROPOSAL", {"reason": "no_candidate", "match_id": match_id}
    top = ranked[0]
    pair = (top["source"], top["target"])
    if cooldowns.get(pair, 0) > now:
        return "NO_SAFE_PROPOSAL", {"reason": "pair_cooldown", "pair": pair}
    proposal = build_proposal(top, by_id, match_id, now)
    if proposal.status != "READY":
        return "NO_SAFE_PROPOSAL", {"reason": proposal.reject_reason}
    # 4) 新鮮屏座標＋預檢
    screen_map, canvas = await fresh_screen_map(anchor["towers"])
    if not canvas:
        return "NO_SAFE_PROPOSAL", {"reason": "camera_failed"}
    result, refreshed = prepare_move(proposal, by_id, screen_map, canvas, match_id, now)
    if result != PREFLIGHT_READY:
        return "NO_SAFE_PROPOSAL", {"reason": refreshed[0] if isinstance(refreshed, tuple) else refreshed}
    # 5) 執行（單次）
    before = {"match_id": match_id,
              "source": snapshot_tower(by_id[refreshed.source_tower_id]),
              "target": snapshot_tower(by_id[refreshed.target_tower_id])}
    exec_result = api("/api/execute-move", token, {
        "source": list(refreshed.source_screen_xy),
        "target": list(refreshed.target_screen_xy),
        "proposal_id": f"{match_id}:{refreshed.source_tower_id}->{refreshed.target_tower_id}:{int(now)}",
        "match_id": match_id}, timeout=120)
    if not exec_result.get("sent"):
        cooldowns[pair] = now + 300
        journal["failed_actions"] = journal.get("failed_actions", 0) + 1
        return "PRECHECK_REJECTED", {"reason": exec_result.get("result"), "pair": pair}
    journal["sent_actions"] = journal.get("sent_actions", 0) + 1
    # 6) 驗證（等遊戲結算＋重讀）
    await asyncio.sleep(8)
    code, _ = run_tool("unit_struct_probe.py")
    after_states = {}
    if code == 0:
        probe2 = json.loads((ROOT / f"runtime/research/units/unit-struct-probe-{match_id}.json").read_text(encoding="utf8"))
        prows2 = {r["packed_id"]: r for r in probe2["rows"]}
        states2 = build_states(anchor, prows2, time.time())
        by_id2 = {s.tower_id: s for s in states2}
        after_states = {"match_id": match_id,
                        "source": snapshot_tower(by_id2.get(refreshed.source_tower_id)) if by_id2.get(refreshed.source_tower_id) else None,
                        "target": snapshot_tower(by_id2.get(refreshed.target_tower_id)) if by_id2.get(refreshed.target_tower_id) else None,
                        "force_observed": False}
    verdict = verify_post_action(before, after_states or {"match_id": None}, refreshed)
    journal["last_action"] = {"source": refreshed.source_tower_id, "target": refreshed.target_tower_id,
                              "match_id": match_id, "sent_at": now}
    journal["last_verification"] = verdict
    if verdict in ("TARGET_CAPTURED", "TARGET_CONTESTED", "FORCE_OBSERVED", "SOURCE_CHANGED"):
        journal["verified_moves"] = journal.get("verified_moves", 0) + 1
        if verdict == "TARGET_CAPTURED":
            journal["verified_expansions"] = journal.get("verified_expansions", 0) + 1
        journal["consecutive_failures"] = 0
    else:
        journal["consecutive_failures"] = journal.get("consecutive_failures", 0) + 1
        cooldowns[pair] = now + 600
    return "VERIFYING", {"verdict": verdict, "pair": pair,
                         "proposal": {"source": refreshed.source_tower_id,
                                      "target": refreshed.target_tower_id}}


async def main(max_actions: int, interval: int):
    token = json.loads((ROOT / "runtime/state/control.json").read_text(encoding="utf8"))["token"]
    journal = {"mode": "LIVE_NEUTRAL_EXPANSION", "sent_actions": 0,
               "verified_moves": 0, "verified_expansions": 0,
               "failed_actions": 0, "consecutive_failures": 0,
               "cycles": 0, "no_safe_proposals": 0}
    cooldowns: dict = {}
    save_state({"phase": "STARTING", "journal": journal})
    while True:
        now = time.time()
        if max_actions and journal["sent_actions"] >= max_actions:
            save_state({"phase": "MAX_ACTIONS_REACHED", "journal": journal})
            print("MAX_ACTIONS_REACHED sent=", journal["sent_actions"], flush=True)
            return
        if journal.get("consecutive_failures", 0) >= 3:
            save_state({"phase": "PAUSED_FAILSAFE", "journal": journal})
            print("PAUSED_FAILSAFE: 3 consecutive unverified", flush=True)
            return
        try:
            phase, info = await cycle(token, journal, cooldowns, now)
        except Exception as exc:
            phase, info = "ERROR", {"error": str(exc)[:200]}
        journal["cycles"] = journal.get("cycles", 0) + 1
        if phase == "NO_SAFE_PROPOSAL":
            journal["no_safe_proposals"] = journal.get("no_safe_proposals", 0) + 1
        journal["current_phase"] = phase
        journal["last_info"] = info
        save_state({"phase": phase, "journal": journal})
        append_cycle_log({"time": now, "phase": phase, "info": info,
                          "sent": journal["sent_actions"],
                          "verified": journal["verified_moves"]})
        print(f"[{time.strftime('%H:%M:%S')}] {phase} {info} sent={journal['sent_actions']} verified={journal['verified_moves']}", flush=True)
        await asyncio.sleep(interval)


def save_state(payload: dict):
    payload["updated_at"] = time.time()
    (ROOT / "runtime/state/live_controller.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_cycle_log(row: dict):
    """附加式週期日誌（不覆寫歷史）。"""
    path = ROOT / "runtime/state/live_controller_log.jsonl"
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-actions", type=int, default=0)
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    asyncio.run(main(args.max_actions, args.interval))
