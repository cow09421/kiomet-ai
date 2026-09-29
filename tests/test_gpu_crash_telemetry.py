"""GPU 崩潰遙測回歸。

解析 GPU fallback 簽名、exit code 解碼、sandbox/network 事件；
缺證據不得宣稱 fallback。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from gpu_crash_telemetry import (build_index, decode_exit_code,
                                 parse_chromium_log, scan_logs)

GPU_LOG = """\
[30452:30460:0929/201536.234:ERROR:content/browser/gpu/gpu_process_host.cc:1054] GPU process exited unexpectedly: exit_code=-1073741790
[30452:30460:0929/201536.234:WARNING:content/browser/gpu/gpu_process_host.cc:1506] The GPU process has crashed 3 time(s)
[30452:30460:0929/201536.271:FATAL:content/browser/gpu/gpu_data_manager_impl_private.cc:417] GPU process isn't usable. Goodbye.
"""

SANDBOX_LOG = """\
[1:2:0927/021724.906:ERROR:sandbox/policy/win/sandbox_win.cc:804] Sandbox cannot access executable C:\\x\\chrome.exe. Check filesystem permissions are valid.
[1:2:0927/021724.943:ERROR:content/browser/network_service_instance_impl.cc:655] Network service crashed or was terminated, restarting service.
DevTools listening on ws://127.0.0.1:65176/devtools/browser/abc
"""


def test_parse_gpu_fallback():
    parsed = parse_chromium_log(GPU_LOG)
    assert parsed["gpu_exit_count"] == 1
    assert parsed["gpu_crashed_max"] == 3
    assert parsed["gpu_unusable_fatal"] is True
    assert parsed["gpu_fallback_confirmed"] is True
    assert parsed["gpu_exit_codes"] == ["0xC0000022"]


def test_decode_exit_code():
    assert decode_exit_code(-1073741790) == "0xC0000022"
    assert decode_exit_code(0) == "0x00000000"


def test_parse_sandbox_and_network():
    parsed = parse_chromium_log(SANDBOX_LOG)
    assert parsed["sandbox_denials"]
    assert parsed["network_crashes"] == 1
    assert parsed["devtools_endpoints"] == [
        "ws://127.0.0.1:65176/devtools/browser/abc"]
    assert parsed["gpu_fallback_confirmed"] is False


def test_no_evidence_not_confirmed():
    parsed = parse_chromium_log("just some normal line\n")
    assert parsed["gpu_exit_count"] == 0
    assert parsed["gpu_fallback_confirmed"] is False


def test_scan_logs_reads_chromium_files(tmp_path):
    (tmp_path / "chromium-startup.log").write_text(GPU_LOG, encoding="utf-8")
    (tmp_path / "chromium.log").write_text(SANDBOX_LOG, encoding="utf-8")
    (tmp_path / "other.log").write_text("ignored", encoding="utf-8")
    files = scan_logs(tmp_path)
    assert len(files) == 2
    names = {f["file"] for f in files}
    assert "other.log" not in names


def test_build_index_from_tree(tmp_path):
    logs = tmp_path / "runtime/logs"
    logs.mkdir(parents=True)
    (logs / "chromium-startup.log").write_text(GPU_LOG, encoding="utf-8")
    incidents = tmp_path / "runtime/research/crash/incidents"
    incidents.mkdir(parents=True)
    (incidents / "crash-001.json").write_text(
        '{"signature": "GPU_PROCESS_FATAL"}', encoding="utf-8")
    index = build_index(tmp_path)
    assert index["verdict"] == "GPU_FALLBACK_CONFIRMED"
    assert index["total_gpu_exits"] == 1
    assert index["crashes"] == 1


def test_build_index_empty_is_no_evidence(tmp_path):
    index = build_index(tmp_path)
    assert index["verdict"] == "NO_GPU_FALLBACK_EVIDENCE"
    assert index["total_gpu_exits"] == 0
