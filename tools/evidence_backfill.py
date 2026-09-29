"""證據元資料回填（P1 §16C）。

舊證據案例缺 cycle_id/dispatched_at/snapshot 時間 → integrity UNKNOWN
（GPT #131 指出 13 案例全 UNKNOWN）。本工具由 live_actions.jsonl 以
action_id 相關性推导 dispatched_at 等，寫入 sidecar derived-meta.json；
絕不覆寫原始證據檔。cycle_id 取不到時顯示 UNKNOWN，不編造。
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "runtime/research/pvp_validation"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _load_actions(path: Path) -> dict:
    """action_id → row（最後一筆為準）。"""
    out: dict = {}
    try:
        lines = path.read_text(encoding="utf-8",
                               errors="ignore").splitlines()
    except OSError:
        return out
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("action_id"):
            out[row["action_id"]] = row
    return out


def _load_cycles(journal: dict | None) -> dict:
    """dispatch.action_id → cycle_id（近期週期才取得到）。"""
    out: dict = {}
    if not isinstance(journal, dict):
        return out
    for cycle in journal.get("recent_cycles") or []:
        if not isinstance(cycle, dict):
            continue
        dispatch = cycle.get("dispatch")
        action_id = (dispatch.get("action_id")
                     if isinstance(dispatch, dict) else None)
        if action_id and cycle.get("cycle_id") is not None:
            out[action_id] = cycle["cycle_id"]
    return out


def _dir_bindings(case_dir: Path, doc: dict) -> dict:
    """目錄名 vs 檔案內容 binding（只回報一致與否，不判定真假）。

    真實語料格式：{match}_{source}-_{target}_{time}；
    亦相容 {match}_{source->_target}_{time}。
    """
    parts = case_dir.name.split("_")
    match_from_dir = parts[0] if parts else None
    src_from_dir = tgt_from_dir = None
    if len(parts) >= 3:
        src_seg = parts[1]
        if src_seg.endswith("-"):
            src_seg = src_seg[:-1]
        if "->" in src_seg:
            a, _, b = src_seg.partition("->")
            src_from_dir = int(a) if a.isdigit() else None
            tgt_from_dir = int(b) if b.isdigit() else None
        else:
            src_from_dir = int(src_seg) if src_seg.isdigit() else None
            tgt_from_dir = (int(parts[2]) if parts[2].isdigit() else None)
    return {
        "match_consistent": (match_from_dir is not None
                             and doc.get("match_id") == match_from_dir),
        "source_consistent": (src_from_dir is not None
                              and doc.get("source_tower") == src_from_dir),
        "target_consistent": (tgt_from_dir is not None
                              and doc.get("target_tower") == tgt_from_dir),
    }


def _time_ordering(dispatched_at, logged_at) -> str:
    """sent_at <= logged_at 才一致；缺任一為 UNKNOWN，不編造。"""
    if (not isinstance(dispatched_at, (int, float))
            or not isinstance(logged_at, (int, float))):
        return "UNKNOWN"
    return "OK" if dispatched_at <= logged_at else "INVERTED"


def backfill_case(case_dir: Path, doc: dict, actions: dict, cycles: dict,
                  now: float | None = None) -> dict | None:
    """組成 sidecar payload；無 action_id 時回 None（不編造）。

    cycles 接受已處理的 action_id→cycle_id map，
    或含 recent_cycles 的原始 journal（自動正規化）。
    """
    if not isinstance(doc, dict):
        return None
    if isinstance(cycles, dict) and "recent_cycles" in cycles:
        cycles = _load_cycles(cycles)
    cycles = cycles if isinstance(cycles, dict) else {}
    action_id = doc.get("action_id")
    if not action_id:
        return None
    row = actions.get(action_id) or {}
    dispatch = row.get("dispatch")
    dispatched_at = (dispatch.get("sent_at")
                     if isinstance(dispatch, dict)
                     and isinstance(dispatch.get("sent_at"), (int, float))
                     else None)
    logged_at = (row.get("logged_at")
                 if isinstance(row.get("logged_at"), (int, float))
                 else None)
    cycle_id = cycles.get(action_id, "UNKNOWN")
    return {
        "action_id": action_id,
        "cycle_id": cycle_id,
        "dispatched_at": dispatched_at if dispatched_at is not None
        else "UNKNOWN",
        "logged_at": logged_at if logged_at is not None else "UNKNOWN",
        "origin": row.get("origin", "UNKNOWN"),
        "verifier": row.get("verifier", "UNKNOWN"),
        "result": row.get("result", "UNKNOWN"),
        "time_ordering": _time_ordering(dispatched_at, logged_at),
        "bindings": _dir_bindings(case_dir, doc),
        "provenance": {
            "source": ("runtime/logs/live_actions.jsonl"
                       "+runtime/state/live_controller.json"),
            "method": "action_id correlation",
            "derived_at": now if now is not None else time.time(),
            "originals_unmodified": True,
        },
    }


def _atomic_json(path: Path, payload: dict) -> bool:
    """原子寫入 sidecar（tmp＋replace），失敗回 False。"""
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_name, str(path))
        return True
    except OSError:
        return False


def backfill_cases(root: Path = ROOT, cases_dir: Path | None = None,
                   journal: dict | None = None,
                   now: float | None = None) -> dict:
    """掃描案例目錄，寫 sidecar；回傳摘要。"""
    base = (cases_dir if cases_dir is not None
            else root / "runtime/research/pvp_validation")
    actions = _load_actions(root / "runtime/logs/live_actions.jsonl")
    cycles = _load_cycles(journal)
    results = {"cases": 0, "backfilled": 0, "skipped": 0, "cycle_unknown": 0}
    if not base.is_dir():
        results["error"] = f"cases dir not found: {base}"
        return results
    for case_dir in sorted(base.iterdir()):
        if not case_dir.is_dir():
            continue
        doc = _read_json(case_dir / "battle-differential.json")
        if doc is None:
            results["skipped"] += 1
            continue
        results["cases"] += 1
        payload = backfill_case(case_dir, doc, actions, cycles, now=now)
        if payload is None:
            results["skipped"] += 1
            continue
        if payload.get("cycle_id") == "UNKNOWN":
            results["cycle_unknown"] += 1
        if _atomic_json(case_dir / "derived-meta.json", payload):
            results["backfilled"] += 1
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = backfill_cases(Path(args.root))
    if args.json:
        print(json.dumps(results, ensure_ascii=False))
    else:
        print(f"cases={results.get('cases')} "
              f"backfilled={results.get('backfilled')} "
              f"skipped={results.get('skipped')} "
              f"cycle_unknown={results.get('cycle_unknown')}"
              + (f" error={results.get('error')}"
                 if results.get("error") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
