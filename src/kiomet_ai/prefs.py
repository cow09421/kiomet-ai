"""偏好讀寫：遊戲音訊開關（預設關＝靜音）。管理控制用，不經戰術閘門。"""
from __future__ import annotations

import json
from pathlib import Path

PREFS_FILE = Path(__file__).resolve().parents[2] / "config" / "runtime-preferences.json"
DEFAULTS = {"game_audio_enabled": False}


def load() -> dict:
    try:
        data = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        return {"game_audio_enabled": bool(data.get("game_audio_enabled", False))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(prefs: dict) -> None:
    PREFS_FILE.write_text(json.dumps(prefs, ensure_ascii=False, indent=2),
                          encoding="utf-8")
