"""執行期遙測彙整回歸（§12H）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from runtime_telemetry import (build, percentile, summarize_errors,
                               summarize_metrics)


def test_percentile_basic():
    values = list(range(1, 101))
    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 95.0
    assert percentile([], 50) is None
    assert percentile([7], 95) == 7.0


def _rows():
    return [
        {"time": 100.0, "elapsed": 10.0, "memory_mb": 100.0,
         "state": "RUNNING", "browser": {"connected": True}},
        {"time": 110.0, "elapsed": 20.0, "memory_mb": 200.0,
         "state": "RUNNING", "browser": {"connected": True}},
        {"time": 120.0, "elapsed": 30.0, "memory_mb": 300.0,
         "state": "ERROR", "browser": {"connected": False}},
    ]


def test_summarize_metrics():
    s = summarize_metrics(_rows())
    assert s["samples"] == 3
    assert s["memory_mb"]["max"] == 300.0
    assert s["states"] == {"RUNNING": 2, "ERROR": 1}
    assert s["browser_connected_ratio"] == 0.667
    assert s["latest_state"] == "ERROR"
    assert s["latest_sample_at"] == 120.0


def test_summarize_metrics_empty():
    s = summarize_metrics([])
    assert s["samples"] == 0
    assert s["memory_mb"]["p50"] is None
    assert s["browser_connected_ratio"] is None


def test_summarize_errors():
    rows = [{"time": 1, "type": "RuntimeError", "message": "x"},
            {"time": 2, "type": "RuntimeError", "message": "y"},
            {"time": 3, "type": "ValueError", "message": "z"}]
    s = summarize_errors(rows)
    assert s["count"] == 3
    assert s["by_type"] == {"RuntimeError": 2, "ValueError": 1}
    assert s["latest"]["type"] == "ValueError"


def _write_tree(tmp_path):
    logs = tmp_path / "runtime/logs"
    logs.mkdir(parents=True)
    (logs / "metrics.jsonl").write_text(
        "\n".join(
            '{"time": %d, "memory_mb": %d, "state": "RUNNING", '
            '"browser": {"connected": true}}' % (100 + i, 100 + i)
            for i in range(5)) + "\n", encoding="utf-8")
    (logs / "errors.jsonl").write_text(
        '{"time": 1, "type": "RuntimeError", "message": "boom"}\n',
        encoding="utf-8")


def test_build_live(tmp_path):
    _write_tree(tmp_path)
    summary = build(tmp_path, now=200.0)
    assert summary["verdict"] == "LIVE"
    assert summary["samples"] == 5
    assert summary["errors"]["count"] == 1
    assert summary["latest_age_s"] == 96.0


def test_build_stale(tmp_path):
    _write_tree(tmp_path)
    summary = build(tmp_path, now=100000.0)
    assert summary["verdict"] == "STALE"


def test_build_missing_is_unknown(tmp_path):
    summary = build(tmp_path, now=200.0)
    assert summary["verdict"] == "UNKNOWN"
    assert summary["samples"] == 0
