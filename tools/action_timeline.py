"""行動時間線產生器：observe→plan→gate→dispatch→verify→refresh→replan。

輸入 journal recent_cycles ＋ live_actions rows，
輸出每週期一行：階段、具體原因、提案、派送、驗證。
每次 NO_ACTION 都有具體原因（raw_reason），不再只有 NO_SAFE_PROPOSAL。

唯讀既有證據；不送遊戲命令；UNKNOWN 不編造。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _parse_action_id(action_id):
    """m1:S->T:TS → (match, src, tgt)；不合法回 (None, None, None)。"""
    if not isinstance(action_id, str) or "->" not in action_id:
        return None, None, None
    head, _, tail = action_id.partition("->")
    match, sep, src = head.rpartition(":")
    if not sep:
        match, src = head, None
    tgt, _, _ts = tail.partition(":")
    return (match or None,
            int(src) if src and src.isdigit() else None,
            int(tgt) if tgt.isdigit() else None)


def build_timeline(journal: dict | None,
                   actions_by_id: dict | None = None,
                   limit: int = 50) -> list:
    """由 journal 週期＋行動記錄組成時間線（新→舊裁剪至 limit）。"""
    journal = journal if isinstance(journal, dict) else {}
    actions_by_id = (actions_by_id if isinstance(actions_by_id, dict)
                     else {})
    cycles = journal.get("recent_cycles") or []
    if not isinstance(cycles, list):
        cycles = []
    entries = []
    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue
        dispatch = cycle.get("dispatch")
        action_id = (dispatch.get("action_id")
                     if isinstance(dispatch, dict) else None)
        action = actions_by_id.get(action_id, {}) if action_id else {}
        if not isinstance(action, dict):
            action = {}
        match_id_parsed, src_parsed, tgt_parsed = (
            _parse_action_id(action_id))
        source = (action.get("source")
                  if action.get("source") is not None else src_parsed)
        target = (action.get("target")
                  if action.get("target") is not None else tgt_parsed)
        entries.append({
            "cycle_id": cycle.get("cycle_id"),
            "timestamp": cycle.get("timestamp"),
            "match_id": cycle.get("match_id"),
            "phase": cycle.get("phase"),
            "observe": ("STALE" if cycle.get("match_id") is None
                        else "FRESH"),
            "planned": cycle.get("proposal") or
            cycle.get("candidate_count"),
            "gate": cycle.get("preflight"),
            "no_action_reason": cycle.get("no_action_reason"),
            "raw_reason": cycle.get("raw_reason"),
            "dispatched_action": action_id,
            "action_kind": action.get("action_kind") or "UNKNOWN",
            "source": source,
            "target": target,
            "origin": action.get("origin") or "UNKNOWN",
            "verified": (action.get("verifier") or action.get("result")
                         or cycle.get("verification")),
            "verdict": (action.get("verifier") or action.get("result")
                        or cycle.get("verification") or "UNKNOWN"),
        })
    entries.sort(key=lambda e: (
        e["timestamp"] is None, e["timestamp"] or 0))
    return entries[-limit:] if limit and limit > 0 else entries


def render_text(entries: list) -> str:
    """人類可讀時間線；缺欄顯示 UNKNOWN，不編造。"""
    lines = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        cycle = entry.get("cycle_id")
        cycle_label = f"#{cycle}" if type(cycle) is int else "UNKNOWN"
        reason = (entry.get("raw_reason")
                  or entry.get("no_action_reason")
                  or "UNKNOWN")
        planned = entry.get("planned")
        planned_label = "proposal" if planned else "no-proposal"
        dispatched = entry.get("dispatched_action") or "-"
        verified = (entry.get("verdict") or entry.get("verified") or "-")
        kind = entry.get("action_kind") or "UNKNOWN"
        origin = entry.get("origin") or "UNKNOWN"
        src = entry.get("source")
        tgt = entry.get("target")
        route = (f"{src} → {tgt}" if src is not None and tgt is not None
                 else "-")
        lines.append(
            f"{cycle_label} [{entry.get('phase') or 'UNKNOWN'}] "
            f"{kind} · {route} · origin={origin} "
            f"reason={reason} | {planned_label} | "
            f"dispatch={dispatched} | verdict={verified}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", default=None)
    parser.add_argument("--actions", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    journal_path = (Path(args.journal) if args.journal else
                    ROOT / "runtime/state/live_controller.json")
    journal_doc = _read_json(journal_path) or {}
    actions = {}
    actions_path = (Path(args.actions) if args.actions else
                    ROOT / "runtime/logs/live_actions.jsonl")
    try:
        for line in actions_path.read_text(
                encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if (isinstance(row, dict) and row.get("action_id")):
                actions[row["action_id"]] = row
    except OSError:
        pass
    entries = build_timeline(journal_doc.get("journal"), actions,
                             limit=args.limit)
    text = render_text(entries)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
