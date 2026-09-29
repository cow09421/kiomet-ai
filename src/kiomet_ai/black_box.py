"""有界的執行期黑盒記錄器；一般記錄只留在記憶體中。"""
from __future__ import annotations

from collections import deque
import json
import math
import os
from pathlib import Path
import time
from typing import Callable
from uuid import uuid4


SCHEMA_VERSION = 1
DEFAULT_WINDOW_SECONDS = 120.0
DEFAULT_MAX_EVENTS = 512
MAX_WINDOW_SECONDS = 120.0
MAX_BUFFER_EVENTS = 512
MAX_EVENT_BYTES = 32 * 1024
FREEZE_TRIGGERS = frozenset(("crash", "combat_action"))
SNAPSHOT_FIELDS = frozenset((
    "game_lifecycle",
    "match",
    "cycle",
    "world_freshness",
    "threats",
    "proposal",
    "action",
    "reservation",
    "verification",
    "renderer_health",
))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "runtime" / "state" / "black-box.json"


def _is_json_value(value: object) -> bool:
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_is_json_value(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _is_json_value(item)
                   for key, item in value.items())
    return False


def _json_copy(value: object, *, limit_bytes: int | None = None) -> object:
    try:
        if not _is_json_value(value):
            raise ValueError(
                "black-box data must contain only finite JSON values")
    except RecursionError as exc:
        raise ValueError("black-box data nesting is too deep") from exc
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise ValueError("black-box data is not valid JSON") from exc
    if limit_bytes is not None and len(encoded) > limit_bytes:
        raise ValueError("black-box event exceeds the byte limit")
    return json.loads(encoded)


def _clock_value(clock: Callable[[], float], label: str) -> float:
    value = clock()
    if type(value) not in (int, float):
        raise ValueError(f"{label} clock must return a finite number")
    try:
        normalized = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} clock must return a finite number") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{label} clock must return a finite number")
    return normalized


class BlackBoxRecorder:
    """保留最近 120 秒快照，並只在明確觸發時覆寫單一檔案。

    每筆快照只接受遊戲生命週期、對局、週期、世界新鮮度、威脅、提案、
    行動、保留、驗證及渲染器健康等欄位；不保存畫面或任意附加欄位。
    """

    def __init__(
        self,
        *,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        max_events: int = DEFAULT_MAX_EVENTS,
        output_path: str | Path | None = DEFAULT_OUTPUT_PATH,
        monotonic_clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if type(window_seconds) not in (int, float):
            raise ValueError("window_seconds must be in the 0..120 second range")
        try:
            window_seconds = float(window_seconds)
        except OverflowError as exc:
            raise ValueError(
                "window_seconds must be in the 0..120 second range") from exc
        if (not math.isfinite(window_seconds) or window_seconds <= 0
                or window_seconds > MAX_WINDOW_SECONDS):
            raise ValueError("window_seconds must be in the 0..120 second range")
        if (type(max_events) is not int or max_events < 1
                or max_events > MAX_BUFFER_EVENTS):
            raise ValueError("max_events must be in the 1..512 range")
        if not callable(monotonic_clock) or not callable(wall_clock):
            raise TypeError("clock arguments must be callable")

        self.window_seconds = float(window_seconds)
        self.max_events = max_events
        self.output_path = self._resolve_output_path(output_path)
        self._monotonic_clock = monotonic_clock
        self._wall_clock = wall_clock
        self._events: deque[tuple[float, dict[str, object]]] = deque()
        self._frozen_artifact: dict[str, object] | None = None

    @staticmethod
    def _resolve_output_path(path: str | Path | None) -> Path | None:
        if path is None:
            return None
        if not isinstance(path, (str, Path)):
            raise TypeError("output_path must be a path or None")
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(PROJECT_ROOT)
        except ValueError as exc:
            raise ValueError("black-box output must stay inside the project") from exc
        if resolved == PROJECT_ROOT:
            raise ValueError("black-box output must name a file")
        return resolved

    @property
    def is_frozen(self) -> bool:
        return self._frozen_artifact is not None

    @property
    def buffered_event_count(self) -> int:
        return len(self._events)

    def buffered_events(self) -> list[dict[str, object]]:
        """回傳副本，呼叫端不能改動環形緩衝內容。"""
        return [event for _, event in self._copy_events()]

    def _copy_events(self) -> list[tuple[float, dict[str, object]]]:
        return [
            (stamp, _json_copy(event))
            for stamp, event in self._events
        ]

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] > self.window_seconds:
            self._events.popleft()

    def record(
        self,
        snapshot: dict[str, object],
        *,
        trigger: str | None = None,
    ) -> bool:
        """加入一筆狀態；設定 crash 或 combat_action 會立即凍結緩衝。"""
        if self.is_frozen:
            return False
        if (trigger is not None
                and (type(trigger) is not str or trigger not in FREEZE_TRIGGERS)):
            raise ValueError("trigger must be crash or combat_action")
        if type(snapshot) is not dict:
            raise TypeError("snapshot must be a dictionary")
        unexpected = set(snapshot) - SNAPSHOT_FIELDS
        if unexpected:
            raise ValueError("snapshot contains unsupported fields")
        copied = _json_copy(snapshot, limit_bytes=MAX_EVENT_BYTES)
        assert isinstance(copied, dict)

        now_mono = _clock_value(self._monotonic_clock, "monotonic")
        captured_at = _clock_value(self._wall_clock, "wall")
        event = {"captured_at_unix": captured_at, **copied}
        self._prune(now_mono)
        self._events.append((now_mono, event))
        while len(self._events) > self.max_events:
            self._events.popleft()

        if trigger is not None:
            self._freeze(trigger, now_mono=now_mono)
        return True

    def freeze(self, trigger: str) -> dict[str, object]:
        """凍結目前緩衝；可選擇覆寫單一診斷檔。"""
        if type(trigger) is not str or trigger not in FREEZE_TRIGGERS:
            raise ValueError("trigger must be crash or combat_action")
        if self._frozen_artifact is None:
            now_mono = _clock_value(self._monotonic_clock, "monotonic")
            self._freeze(trigger, now_mono=now_mono)
        artifact = _json_copy(self._frozen_artifact)
        assert isinstance(artifact, dict)
        return artifact

    def _freeze(self, trigger: str, *, now_mono: float) -> None:
        self._prune(now_mono)
        artifact = {
            "schema_version": SCHEMA_VERSION,
            "window_seconds": self.window_seconds,
            "trigger": trigger,
            "frozen_at_unix": _clock_value(self._wall_clock, "wall"),
            "events": [event for _, event in self._events],
        }
        encoded = json.dumps(
            artifact, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if self.output_path is not None:
            self._atomic_overwrite(encoded)
        self._frozen_artifact = artifact

    def _atomic_overwrite(self, encoded: bytes) -> None:
        assert self.output_path is not None
        destination = self.output_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            destination.parent.resolve().relative_to(PROJECT_ROOT)
        except ValueError as exc:
            raise ValueError(
                "black-box output must stay inside the project") from exc
        temporary = destination.with_name(
            f".{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(encoded)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
