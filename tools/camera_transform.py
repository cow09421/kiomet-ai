"""相容墊片：正式實作已移至 src/kiomet_ai/camera.py，此檔僅轉出口。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kiomet_ai.camera import (  # noqa: F401
    client_to_page,
    world_to_client,
    world_to_page,
)
