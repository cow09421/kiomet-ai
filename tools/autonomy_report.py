"""自主產能報告（P0，唯讀）。

整合 autonomy_kpi + abstain_taxonomy + idle_diagnostics，
由 live_controller.json 與 live_actions.jsonl 產生報告。
缺資料標 UNKNOWN，不假 0；不修改任何檔案。
輸出 runtime/state/autonomy_report.json。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))
from kiomet_ai.abstain_taxonomy import window_stats  # noqa: E402
from kiomet_ai.autonomy_kpi import from_journal  # noqa: E402
from kiomet_ai.idle_diagnostics import evaluate  # noqa: E402


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _read_actions(path: Path) -> list:
    rows = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _cycle_records(journal: dict) -> list:
    records = []
    for cycle in (journal.get("recent_cycles") or []):
        if not isinstance(cycle, dict):
            continue
        dispatch = cycle.get("dispatch")
        records.append({
            "reason": cycle.get("raw_reason")
            or cycle.get("no_action_reason"),
            "actions_sent": 1 if isinstance(dispatch, dict)
            and dispatch.get("action_id") else 0,
        })
    return records


def _idle_context(journal: dict, snapshot: dict | None) -> dict:
    threat = journal.get("threat_state") \
        if isinstance(journal.get("threat_state"), dict) else {}
    coverage = threat.get("coverage") \
        if isinstance(threat.get("coverage"), dict) else {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    game = snapshot.get("game") if isinstance(snapshot.get("game"), dict) \
        else {}
    return {
        "in_match": bool(threat.get("match_id")) or \
            (game.get("state") == "IN_MATCH"),
        "world_fresh": threat.get("freshness") == "FRESH",
        "self_towers": coverage.get("self_towers"),
        "controller_running": journal.get("cycles") is not None,
    }


def build_report(journal: dict | None, actions: list | None,
                 snapshot: dict | None = None,
                 now: float | None = None) -> dict:
    journal = journal if isinstance(journal, dict) else {}
    now = now if isinstance(now, (int, float)) else time.time()
    records = _cycle_records(journal)
    kpi = from_journal(journal, actions)
    stats = window_stats(records, windows=(50, 100))
    idle = evaluate(_idle_context(journal, snapshot), records)
    return {
        "generated_at": now,
        "kpi": kpi,
        "abstain_windows": stats,
        "idle": idle,
        "cycle_records": len(records),
        "source": ("runtime/state/live_controller.json"
                   "+runtime/logs/live_actions.jsonl"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out", default=str(
        ROOT / "runtime/state/autonomy_report.json"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    journal_doc = _read_json(root / "runtime/state/live_controller.json") or {}
    journal = journal_doc.get("journal") if isinstance(journal_doc, dict) \
        else {}
    actions = _read_actions(root / "runtime/logs/live_actions.jsonl")
    snapshot = _read_json(root / "runtime/state/final-status.json") or {}
    report = build_report(journal, actions, snapshot)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        kpi = report["kpi"]
        print(f"ACTION_RATE={kpi['ACTION_RATE']} "
              f"DECISION_RATE={kpi['DECISION_RATE']} "
              f"idle={report['idle']['status']} "
              f"cycles={kpi['cycles']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
