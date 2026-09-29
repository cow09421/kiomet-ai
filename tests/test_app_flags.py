"""啟動旗標測試：--no-capture（停用週期截圖）透傳到 Application。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kiomet_ai.app import Application, parse_args


def test_no_capture_defaults_off():
    args = parse_args([])
    assert args.no_capture is False


def test_no_capture_flag_parses():
    args = parse_args(["--no-capture"])
    assert args.no_capture is True


def test_application_carries_no_capture(tmp_path):
    (tmp_path / "runtime" / "logs").mkdir(parents=True)
    (tmp_path / "runtime" / "audio").mkdir(parents=True)
    config = {"log_max_bytes": 65536, "log_backups": 1}
    app_off = Application(tmp_path, config, no_browser=True)
    app_on = Application(tmp_path, config, no_browser=True, no_capture=True)
    assert app_off.no_capture is False
    assert app_on.no_capture is True
