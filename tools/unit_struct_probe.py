"""讀取已由渲染函式確認的塔參照附近位元組；不呼叫遊戲函式。

用法：python tools/unit_struct_probe.py --help
"""
import argparse
import json
from pathlib import Path
import time
import urllib.request

from live_page import find_live_target_id
from cdp_probe import Session

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime/research/units"
ANCHOR = ROOT / "runtime/research/source-map/verified-anchor-current.json"


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    anchor = json.loads(ANCHOR.read_text(encoding="utf8"))
    match = anchor["match_id"]
    status = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=4))
    if status["state"] != "RUNNING" or status["game"]["state"] != "IN_MATCH" or status["game"]["match"]["id"] != match:
        raise ValueError("錨點或對局已過期")
    refs = [t["tower_ref"] for t in anchor["towers"]]
    # Runtime.queryObjects 只列出記憶體物件；對局邏輯完全不變。
    with Session("https://kiomet.com/", page_id=find_live_target_id(), timeout=12) as cdp:
        proto = cdp.call("Runtime.evaluate", {"expression":"WebAssembly.Memory.prototype"})["result"]["objectId"]
        mem = cdp.call("Runtime.queryObjects", {"prototypeObjectId":proto})["objects"]["objectId"]
        try:
            result = cdp.call("Runtime.callFunctionOn", {
                "objectId":mem,"returnByValue":True,"arguments":[{"value":refs}],
                "functionDeclaration":"""function(refs) {
                  if(this.length!==1) throw Error('Expected one WASM memory');
                  const v=new Uint8Array(this[0].buffer);
                  return refs.map(p=>({ref:p,bytes:Array.from(v.slice(p-32,p+160))}));
                }"""})
            if "exceptionDetails" in result:
                raise ValueError(result["exceptionDetails"])
            rows = result["result"]["value"]
        finally:
            cdp.call("Runtime.releaseObject", {"objectId":mem})
            cdp.call("Runtime.releaseObject", {"objectId":proto})
    report = {"match_id":match,"time":time.time(),"sent_actions":status["sent_actions"],"rows":[]}
    for t, row in zip(anchor["towers"], rows):
        report["rows"].append({"packed_id":t["packed_id"],"position":t["position"],
                               "owner":t["owner"],"render_color":t["render_color"],
                               "ref":row["ref"],"bytes":row["bytes"]})
    OUT.mkdir(parents=True,exist_ok=True)
    dest=OUT/f"unit-struct-probe-{match}.json"
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"match":match,"towers":len(rows),"bytes_each":len(rows[0]["bytes"]),"file":str(dest)},ensure_ascii=False))


if __name__ == "__main__":
    main()
