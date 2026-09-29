"""CLI 錯誤路徑回歸。

覆蓋：威脅模式缺 match（exit 2）、日誌檔不存在、
證據索引 CLI 寫 --out 到暫存（不污染 runtime）。
"""
import json
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
REPLAY_CLI = str(TOOLS / "replay_battle_differential.py")
INDEX_CLI = str(TOOLS / "evidence_index.py")


def test_threat_mode_requires_match(tmp_path):
    log = tmp_path / "force.log"
    log.write_text('{"t": 1}\n', encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, REPLAY_CLI, "--threat-log", str(log)],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2
    assert "threat-match-required" in proc.stdout


def test_threat_mode_missing_log_file(tmp_path):
    proc = subprocess.run(
        [sys.executable, REPLAY_CLI, "--threat-log",
         str(tmp_path / "nope.log"), "--threat-match", "m1"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2
    assert "error" in proc.stdout


def test_evidence_index_cli_writes_out(tmp_path):
    out = tmp_path / "index.json"
    proc = subprocess.run(
        [sys.executable, INDEX_CLI, "--out", str(out)],
        capture_output=True, text=True, timeout=120,
        cwd=str(Path(__file__).resolve().parents[1]))
    assert proc.returncode == 0, proc.stderr[-500:]
    index = json.loads(out.read_text(encoding="utf-8"))
    for key in ("actions", "differentials", "bundles", "crashes",
                "episodes", "journal"):
        assert key in index, key
