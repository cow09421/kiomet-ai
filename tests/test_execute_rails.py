"""真實執行安全軌測試：無閘門／壞載荷一律拒絕，不記送出。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import asyncio

from kiomet_ai.app import Application


def make_app(tmp_path):
    (tmp_path / "runtime" / "logs").mkdir(parents=True)
    (tmp_path / "runtime" / "audio").mkdir(parents=True)
    config = {"log_max_bytes": 65536, "log_backups": 1}
    return Application(tmp_path, config, no_browser=True)


def test_execute_closed_gate_rejects(tmp_path):
    app = make_app(tmp_path)
    result = asyncio.run(app.execute_move({"source": [1, 2], "target": [3, 4]}))
    assert result["ok"] is False
    assert result["result"] == "NOT_AUTHORIZED"  # 政策優先於機制
    journal = app._read_live_journal()
    assert journal["sent_actions"] == 0


def test_execute_bad_payload_rejects(tmp_path):
    app = make_app(tmp_path)
    result = asyncio.run(app.execute_move({"nope": True}))
    assert result["ok"] is False
    assert result["result"] in ("NOT_AUTHORIZED", "GATE_CLOSED", "BAD_PAYLOAD")
    assert app._read_live_journal()["sent_actions"] == 0


def test_live_journal_defaults(tmp_path):
    app = make_app(tmp_path)
    journal = app._read_live_journal()
    assert journal["sent_actions"] == 0
    assert journal["verified_moves"] == 0
    assert journal["current_phase"] == "OBSERVING"
