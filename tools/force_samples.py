"""自然 Moving Force（移動軍隊）樣本登錄器：唯讀、冪等、有限保存。

樣本來源僅限 A 組（Capture ON）或非 A/B 實驗窗口的自然畫面；
B 組嚴禁產生截圖。每筆樣本必須帶 match_id＋timestamp＋新鮮度語意。
"""
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "runtime/research/forces/natural"


def record_sample(match_id, evidence_path, visible_color,
                  approx_source=None, approx_target=None,
                  path_kind=None, runtime_candidate=None,
                  note=None, count=None, timestamp=None):
    """登錄一筆自然移動軍隊樣本。未知欄位保持 None（UNKNOWN），不得造值。"""
    STORE.mkdir(parents=True, exist_ok=True)
    existing = sorted(STORE.glob("sample-*.json"))
    index = len(existing) + 1
    row = {
        "sample_id": f"natural-{index:03d}",
        "match_id": match_id,
        "timestamp": time.time() if timestamp is None else timestamp,
        "evidence": str(evidence_path),
        "visible_color": visible_color,          # SELF/NEUTRAL/ALLY/ENEMY/UNKNOWN
        "approx_source": approx_source,          # packed_id 或 None
        "approx_target": approx_target,
        "path_kind": path_kind,                   # road/unknown 等
        "runtime_candidate": runtime_candidate,   # 記憶體候選（若有唯讀觀察）
        "unit_count_estimate": count,            # 目測估計，可為 None
        "note": note,
        "sent_actions_context": 0,                # 樣本永遠在 sent_actions=0 下取得
    }
    dest = STORE / f"sample-{index:03d}.json"
    dest.write_text(json.dumps(row, ensure_ascii=False, indent=2),
                    encoding="utf8")
    return dest


def load_all():
    if not STORE.exists():
        return []
    rows = []
    for path in sorted(STORE.glob("sample-*.json")):
        rows.append(json.loads(path.read_text(encoding="utf8")))
    return rows
