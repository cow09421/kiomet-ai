"""戰鬥差分重播 CLI：掃描已存差分語料 → 重播 → 摘要報告。

用法：python tools/replay_battle_differential.py [--root DIR] [--out FILE]
      python tools/replay_battle_differential.py --threat-log FILE --threat-match ID [--threat-target ID] [--threat-out FILE]
      python tools/replay_battle_differential.py --battle-evidence FILE [--battle-out FILE]
只讀 runtime 證據；報告預設寫 runtime/research/pvp_validation/replay-report.json。
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kiomet_ai.replay import (replay_corpus, replay_threat_waves,  # noqa: E402
                              run_battle_differential,
                              threat_snapshot_from_force_rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(
        ROOT / "runtime/research/pvp_validation"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--threat-log", default=None)
    ap.add_argument("--threat-match", default=None)
    ap.add_argument("--threat-target", type=int, default=None)
    ap.add_argument("--threat-out", default=None)
    ap.add_argument("--threat-now", type=float, default=None)
    ap.add_argument("--battle-evidence", default=None)
    ap.add_argument("--battle-out", default=None)
    args = ap.parse_args()

    if args.battle_evidence:
        try:
            raw = json.loads(Path(args.battle_evidence).read_text(
                encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(json.dumps({"error": str(exc)[:120]},
                             ensure_ascii=False))
            return 2
        battle_result = run_battle_differential(raw)
        battle_result["generated_at"] = time.time()
        battle_out = (Path(args.battle_out) if args.battle_out
                      else Path(args.root) / "battle-differential-report.json")
        battle_out.write_text(
            json.dumps(battle_result, ensure_ascii=False, indent=2),
            encoding="utf8")
        print(json.dumps(
            {"support_status": battle_result["support_status"],
             "differential": battle_result["differential"],
             "reason": battle_result.get("reason"),
             "report": str(battle_out)}, ensure_ascii=False))
        return 0

    if args.threat_log:
        if not args.threat_match:
            print(json.dumps({"error": "threat-match-required"},
                             ensure_ascii=False))
            return 2
        try:
            raw = Path(args.threat_log).read_text(
                encoding="utf-8", errors="ignore").splitlines()
        except OSError as exc:
            print(json.dumps({"error": str(exc)[:120]},
                             ensure_ascii=False))
            return 2
        snapshot = threat_snapshot_from_force_rows(
            raw, args.threat_match,
            target_tower_id=args.threat_target)
        result = replay_threat_waves(snapshot, now=args.threat_now)
        result["generated_at"] = time.time()
        out = (Path(args.threat_out) if args.threat_out
               else Path(args.root) / "threat-replay-report.json")
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                       encoding="utf8")
        print(json.dumps({"status": result["status"],
                          "reason": result.get("reason"),
                          "threats": len(result.get("verdicts", [])),
                          "report": str(out)}, ensure_ascii=False))
        return 0

    report = replay_corpus(Path(args.root))
    report["generated_at"] = time.time()
    out = Path(args.out) if args.out else (
        Path(args.root) / "replay-report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf8")
    s = report["summary"]
    print(json.dumps({"cases": s["cases"], "flagged": s["flagged"],
                      "replayed": s["replayed"],
                      "self_ids_found": s["self_ids_found"],
                      "skipped": len(s["skipped"]), "report": str(out)},
                     ensure_ascii=False))
    for c in report["cases"]:
        if c["status"] == "FLAGGED":
            print("FLAG", c.get("case_id"), c.get("flags"))


if __name__ == "__main__":
    raise SystemExit(main())
